from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.market_metric_value import MarketMetricValue
from src.schemas.public_board import MarketGroupSnapshot


class MarketMetricService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def persist_group_metrics(self, snapshot: MarketGroupSnapshot) -> None:
        if not snapshot.items:
            return
        rows = []
        for item in snapshot.items:
            rows.append({
                "as_of": snapshot.as_of,
                "group": snapshot.group,
                "name": item.name,
                "symbol": item.symbol,
                "value": Decimal(str(item.value)) if item.value is not None else None,
                "change_pct": Decimal(str(item.change_pct)) if item.change_pct is not None else None,
            })
        stmt = insert(MarketMetricValue).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="market_metric_values_name_as_of_key",
            set_={
                "value": stmt.excluded.value,
                "change_pct": stmt.excluded.change_pct,
            },
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def query_metric_history(
        self,
        names: list[str],
        from_dt: datetime,
        to_dt: datetime,
    ) -> dict[str, list[dict]]:
        stmt = (
            select(MarketMetricValue)
            .where(
                MarketMetricValue.name.in_(names),
                MarketMetricValue.as_of >= from_dt,
                MarketMetricValue.as_of <= to_dt,
            )
            .order_by(MarketMetricValue.name, MarketMetricValue.as_of)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        metrics: dict[str, list[dict]] = {name: [] for name in names}
        for row in rows:
            if row.name not in metrics:
                metrics[row.name] = []
            metrics[row.name].append({
                "as_of": row.as_of,
                "value": float(row.value) if row.value is not None else None,
                "change_pct": float(row.change_pct) if row.change_pct is not None else None,
            })
        return metrics