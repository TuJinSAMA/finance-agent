import logging
from datetime import date

from src.agents.data_agent.providers import akshare_provider as provider

logger = logging.getLogger(__name__)


class TradingCalendar:
    """
    A 股交易日历。启动时从数据源加载全量交易日历到内存，
    提供 is_trading_day() 判断任意日期是否为交易日。
    """

    _instance: "TradingCalendar | None" = None
    _trading_days: set[date]

    def __init__(self) -> None:
        self._trading_days = set()

    @classmethod
    def get_instance(cls) -> "TradingCalendar":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def load(self) -> None:
        df = await provider.fetch_trading_calendar()
        self._trading_days = {d.date() if hasattr(d, "date") else d for d in df["trade_date"]}
        logger.info("Trading calendar loaded: %d trading days (from %s to %s)",
                     len(self._trading_days),
                     min(self._trading_days),
                     max(self._trading_days))

    def is_trading_day(self, d: date | None = None) -> bool:
        if d is None:
            d = date.today()
        return d in self._trading_days


trading_calendar = TradingCalendar.get_instance()
