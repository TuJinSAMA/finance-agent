"""
事件扫描器 — Event Agent 数据采集层。
负责从 AKShare 抓取个股新闻/公告，去重后写入 stock_events 表。
不含分析逻辑。
"""

import asyncio
import logging
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.data_agent.providers import akshare_provider as provider
from src.agents.screener_config import screener_config as cfg
from src.models.event import StockEvent
from src.models.stock import Stock

logger = logging.getLogger(__name__)


class EventScanner:
    """
    事件扫描器：从多个数据源抓取新闻和公告。
    只做抓取和去重入库，不做分析。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def scan_stock_news(self, stock_codes: list[str]) -> int:
        """
        扫描指定股票的最新新闻（东方财富个股新闻接口）。
        返回新写入的事件数量。
        """
        code_to_id = await self._get_stock_code_map(stock_codes)
        all_events: list[dict] = []

        for code in stock_codes:
            stock_id = code_to_id.get(code)
            if not stock_id:
                continue

            raw_code = code.split(".")[0] if "." in code else code
            try:
                df = await provider.fetch_stock_news(symbol=raw_code)
                if df is None or df.empty:
                    continue

                for _, row in df.head(cfg.event_news_per_stock).iterrows():
                    event_date = self._parse_event_date(row.get("发布时间"))
                    if event_date is None:
                        continue

                    title = str(row.get("新闻标题", "")).strip()
                    if not title:
                        continue

                    content_raw = str(row.get("新闻内容", "") or "")
                    all_events.append({
                        "stock_id": stock_id,
                        "event_date": event_date,
                        "event_type": "news",
                        "source": str(row.get("文章来源", "") or ""),
                        "title": title,
                        "content": content_raw[:cfg.event_content_max_length],
                        "url": str(row.get("新闻链接", "") or ""),
                    })
            except Exception:
                logger.warning("Failed to fetch news for %s", code, exc_info=True)
                continue

            await asyncio.sleep(cfg.akshare_rate_limit)

        inserted = await self._upsert_events(all_events)
        logger.info(
            "News scan completed: %d stocks, %d events fetched, %d new inserted",
            len(stock_codes), len(all_events), inserted,
        )
        return inserted

    async def _upsert_events(self, events: list[dict]) -> int:
        """批量去重写入 stock_events，ON CONFLICT DO NOTHING。返回插入数量。"""
        if not events:
            return 0

        inserted = 0
        for chunk in self._chunked(events, cfg.db_batch_chunk_size):
            stmt = pg_insert(StockEvent).values(chunk)
            stmt = stmt.on_conflict_do_nothing(constraint="uq_stock_event")
            result = await self.db.execute(stmt)
            inserted += result.rowcount
        await self.db.flush()
        return inserted

    async def _get_stock_code_map(self, codes: list[str]) -> dict[str, int]:
        """code → stock_id 映射。"""
        result = await self.db.execute(
            select(Stock.code, Stock.id).where(Stock.code.in_(codes))
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    def _parse_event_date(val) -> date | None:
        """将 AKShare 返回的发布时间字段解析为 date。"""
        if val is None:
            return None
        if isinstance(val, date):
            return val if not isinstance(val, datetime) else val.date()
        if isinstance(val, datetime):
            return val.date()
        try:
            text = str(val).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
                try:
                    return datetime.strptime(text[:19], fmt).date()
                except ValueError:
                    continue
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _chunked(lst: list, size: int):
        for i in range(0, len(lst), size):
            yield lst[i : i + size]
