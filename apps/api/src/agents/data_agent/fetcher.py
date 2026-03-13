import asyncio
import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.data_agent.providers import jqdata_provider as _jq_provider
from src.agents.data_agent.providers import tushare_provider as provider
from src.agents.screener_config import screener_config
from src.models.stock import Stock, StockDailyQuote

logger = logging.getLogger(__name__)


def _code_to_exchange(code: str) -> str:
    """Map A-share stock code prefix to exchange: SH / SZ / BJ."""
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "3")):
        return "SZ"
    if code.startswith(("4", "8", "92")):
        return "BJ"
    return "UNKNOWN"


def _full_code(code: str) -> str:
    """Convert plain code '600519' to suffixed '600519.SH'."""
    return f"{code}.{_code_to_exchange(code)}"


def _is_st(name: str) -> bool:
    return "ST" in name.upper()


def _is_delisting(name: str) -> bool:
    return "退" in name


class DataAgent:
    """
    Data Agent: 负责所有市场数据的采集、清洗、入库。
    不含任何分析逻辑，只做 ETL。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_stock_list(self) -> int:
        """
        同步全市场股票列表。
        使用 ak.stock_zh_a_spot_em() 获取所有 A 股，upsert 到 stocks 表。
        返回同步的股票数量。
        """
        logger.info("Syncing stock list...")
        df = await provider.fetch_a_share_spot()
        if df is None or df.empty:
            logger.error("fetch_a_share_spot returned empty data")
            return 0

        records = []
        for _, row in df.iterrows():
            raw_code = str(row["代码"]).strip()
            name = str(row["名称"]).strip()
            exchange = _code_to_exchange(raw_code)
            code = _full_code(raw_code)

            total_shares = None
            float_shares = None
            price = _safe_decimal(row.get("最新价"))
            if price and price > 0:
                total_mv = _safe_decimal(row.get("总市值"))
                float_mv = _safe_decimal(row.get("流通市值"))
                if total_mv:
                    total_shares = int(total_mv / price)
                if float_mv:
                    float_shares = int(float_mv / price)

            records.append({
                "code": code,
                "name": name,
                "market": "CN_A",
                "exchange": exchange,
                "is_st": _is_st(name),
                "is_delisting": _is_delisting(name),
                "total_shares": total_shares,
                "float_shares": float_shares,
            })

        if not records:
            return 0

        chunk_size = screener_config.db_batch_chunk_size
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            stmt = pg_insert(Stock).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name": stmt.excluded.name,
                    "exchange": stmt.excluded.exchange,
                    "is_st": stmt.excluded.is_st,
                    "is_delisting": stmt.excluded.is_delisting,
                    "total_shares": stmt.excluded.total_shares,
                    "float_shares": stmt.excluded.float_shares,
                },
            )
            await self.db.execute(stmt)
        await self.db.commit()

        logger.info("Stock list synced: %d stocks", len(records))
        return len(records)

    async def sync_industry_mapping(self) -> int:
        """
        通过行业板块接口批量获取行业分类，更新 stocks.industry。
        返回更新的股票数量。
        """
        logger.info("Syncing industry mapping...")
        board_df = await _jq_provider.fetch_industry_board_list()
        if board_df is None or board_df.empty:
            logger.error("fetch_industry_board_list returned empty data")
            return 0

        updated = 0
        for _, row in board_df.iterrows():
            industry_code = str(row["板块代码"]).strip()
            industry_name = str(row["板块名称"]).strip()
            try:
                cons_df = await _jq_provider.fetch_industry_constituents(industry_code)
            except Exception:
                logger.warning("Failed to fetch constituents for industry: %s", industry_name)
                continue

            if cons_df is None or cons_df.empty:
                continue

            codes = [_full_code(str(c).strip()) for c in cons_df["代码"]]
            if codes:
                await self.db.execute(
                    text("UPDATE stocks SET industry = :industry WHERE code = ANY(:codes)"),
                    {"industry": industry_name, "codes": codes},
                )
                updated += len(codes)

            await asyncio.sleep(screener_config.akshare_rate_limit)

        await self.db.commit()
        logger.info("Industry mapping synced: %d stocks updated", updated)
        return updated

    async def sync_list_dates(self) -> int:
        """
        批量获取上市日期，更新 stocks.list_date。
        通过上交所/深交所的股票信息接口批量获取，无需逐只调用。
        只更新 list_date 为 NULL 的记录。返回更新的股票数量。
        """
        logger.info("Syncing list dates...")
        updated = 0

        code_date_map: dict[str, date] = {}

        # 上交所：主板A股 + 科创板
        for indicator in ("主板A股", "科创板"):
            try:
                df = await provider.fetch_sh_stock_info(indicator=indicator)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        raw_code = str(row.get("A_STOCK_CODE", row.get("证券代码", ""))).strip()
                        if not raw_code:
                            continue
                        raw_code = raw_code.lstrip("0") if len(raw_code) > 6 else raw_code
                        raw_code = raw_code.zfill(6)
                        list_date_val = row.get("LIST_DATE", row.get("上市日期"))
                        parsed = self._parse_date(list_date_val)
                        if parsed:
                            code_date_map[_full_code(raw_code)] = parsed
            except Exception:
                logger.warning("Failed to fetch SH stock info (%s)", indicator, exc_info=True)

        # 深交所：A股列表
        try:
            df = await provider.fetch_sz_stock_info(indicator="A股列表")
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    raw_code = str(row.get("A股代码", row.get("证券代码", ""))).strip()
                    if not raw_code:
                        continue
                    raw_code = raw_code.zfill(6)
                    list_date_val = row.get("A股上市日期", row.get("上市日期"))
                    parsed = self._parse_date(list_date_val)
                    if parsed:
                        code_date_map[_full_code(raw_code)] = parsed
        except Exception:
            logger.warning("Failed to fetch SZ stock info", exc_info=True)

        if not code_date_map:
            logger.warning("No list dates obtained from exchange APIs")
            return 0

        # 只更新 list_date 为 NULL 的记录
        result = await self.db.execute(
            select(Stock.id, Stock.code).where(Stock.list_date.is_(None))
        )
        null_stocks = result.all()

        for row in null_stocks:
            ld = code_date_map.get(row.code)
            if ld:
                await self.db.execute(
                    text("UPDATE stocks SET list_date = :ld WHERE id = :sid"),
                    {"ld": ld, "sid": row.id},
                )
                updated += 1

        await self.db.commit()
        logger.info("List dates synced: %d/%d stocks updated", updated, len(null_stocks))
        return updated

    @staticmethod
    def _parse_date(val) -> date | None:
        if val is None:
            return None
        if isinstance(val, date):
            return val
        try:
            s = str(val).strip().replace("/", "-")
            if len(s) >= 10:
                return date.fromisoformat(s[:10])
            if len(s) == 8 and s.isdigit():
                return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except (ValueError, TypeError):
            pass
        try:
            return pd.to_datetime(val).date()
        except Exception:
            return None

    async def fetch_daily_quotes(self, trade_date: date | None = None) -> int:
        """
        拉取全市场日线行情（当日快照）。
        使用 ak.stock_zh_a_spot_em() 一次获取所有股票当日数据。
        返回写入的行数。
        """
        if trade_date is None:
            trade_date = date.today()

        logger.info("Fetching daily quotes for %s...", trade_date)
        df = await provider.fetch_a_share_spot()
        if df is None or df.empty:
            logger.error("fetch_a_share_spot returned empty data")
            return 0

        stock_map = await self._get_stock_code_map()
        if not stock_map:
            logger.error("No stocks in database. Run sync_stock_list first.")
            return 0

        records = []
        for _, row in df.iterrows():
            code = _full_code(str(row["代码"]).strip())
            stock_id = stock_map.get(code)
            if stock_id is None:
                continue

            try:
                records.append({
                    "stock_id": stock_id,
                    "trade_date": trade_date,
                    "open": _safe_decimal(row.get("今开")),
                    "high": _safe_decimal(row.get("最高")),
                    "low": _safe_decimal(row.get("最低")),
                    "close": _safe_decimal(row.get("最新价")),
                    "volume": _safe_int(row.get("成交量")),
                    "amount": _safe_decimal(row.get("成交额")),
                    "turnover_rate": _safe_decimal(row.get("换手率")),
                    "pct_change": _safe_decimal(row.get("涨跌幅")),
                })
            except Exception:
                logger.debug("Skipping row for %s due to data error", code)
                continue

        if not records:
            return 0

        chunk_size = screener_config.db_batch_chunk_size
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            stmt = pg_insert(StockDailyQuote).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "amount": stmt.excluded.amount,
                    "turnover_rate": stmt.excluded.turnover_rate,
                    "pct_change": stmt.excluded.pct_change,
                },
            )
            await self.db.execute(stmt)
        await self.db.commit()

        logger.info("Daily quotes written: %d rows for %s", len(records), trade_date)
        return len(records)

    async def fetch_daily_quotes_history(
        self,
        stock_code: str,
        stock_id: int,
        days: int = 180,
    ) -> int:
        """
        回填单只股票的历史日线数据。
        stock_code: 纯代码如 '600519'
        返回写入的行数。
        """
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=days)).strftime("%Y%m%d")

        try:
            df = await provider.fetch_stock_history(
                symbol=stock_code,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception:
            logger.warning("Failed to fetch history for %s", stock_code)
            return 0

        if df is None or df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            try:
                trade_date_val = pd.to_datetime(row["日期"]).date()
                records.append({
                    "stock_id": stock_id,
                    "trade_date": trade_date_val,
                    "open": _safe_decimal(row.get("开盘")),
                    "high": _safe_decimal(row.get("最高")),
                    "low": _safe_decimal(row.get("最低")),
                    "close": _safe_decimal(row.get("收盘")),
                    "volume": _safe_int(row.get("成交量")),
                    "amount": _safe_decimal(row.get("成交额")),
                    "turnover_rate": _safe_decimal(row.get("换手率")),
                    "pct_change": _safe_decimal(row.get("涨跌幅")),
                })
            except Exception:
                continue

        if not records:
            return 0

        chunk_size = screener_config.db_batch_chunk_size
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            stmt = pg_insert(StockDailyQuote).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["stock_id", "trade_date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "amount": stmt.excluded.amount,
                    "turnover_rate": stmt.excluded.turnover_rate,
                    "pct_change": stmt.excluded.pct_change,
                },
            )
            await self.db.execute(stmt)

        await self.db.commit()
        return len(records)

    async def _get_stock_code_map(self) -> dict[str, int]:
        """Return a mapping of code -> stock_id for all stocks."""
        result = await self.db.execute(select(Stock.id, Stock.code))
        return {row.code: row.id for row in result.all()}

    async def get_all_stocks(self) -> list[Stock]:
        result = await self.db.execute(select(Stock).order_by(Stock.id))
        return list(result.scalars().all())


def _safe_decimal(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        v = float(val)
        return None if pd.isna(v) else v
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None
