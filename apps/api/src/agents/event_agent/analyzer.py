"""
催化剂分析器 — Event Agent 核心，第一个 LLM 调用点。
将未分析的新闻/公告按股票分组，批量送入 LLM 做结构化分析，
结果回写到 stock_events 表。
"""

import asyncio
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.screener_config import screener_config as cfg
from src.core.llm import chat_json
from src.models.event import StockEvent
from src.models.stock import Stock, StockDailyQuote

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位专业的 A 股研究员。你的任务是分析给定的新闻/公告对个股的影响。

请以 JSON 格式输出分析结果，顶层为一个数组，每个元素对应一条事件。
用 "index" 字段标明该分析对应的事件序号（从 1 开始，与输入的 [事件1]、[事件2]... 对应）。
{
    "analyses": [
        {
            "index": 1,
            "sentiment": "bullish" | "bearish" | "neutral",
            "impact_score": 1-10 的整数（10 为影响最大）,
            "catalyst_type": "业绩相关" | "政策利好" | "政策利空" | "资金动向" | "行业事件" | "公司治理" | "技术突破" | "其他",
            "time_horizon": "short" | "medium" | "long",
            "key_point": "一句话总结核心影响",
            "risk_note": "主要风险点（如有，没有则为空字符串）"
        }
    ]
}

注意事项：
1. 对于常规日常新闻（参加展会、常规人事变动等），impact_score 应在 1-3
2. 只有真正重大事件（业绩大幅超预期、重大合同、政策突变、大额回购/增持）才给 7 以上
3. 如果多条新闻内容重复或高度相似，合并为一条分析
4. 保持客观中立，不要过度解读
5. time_horizon: "short"=1-5个交易日, "medium"=1-4周, "long"=1个月以上
6. 严格输出合法 JSON，不要包含注释或多余文本"""


class CatalystAnalyzer:
    """催化剂分析器：用 LLM 对新闻/公告做结构化分析。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_unanalyzed_events(self, target_date: date | None = None) -> int:
        """
        分析所有未分析的事件。按 stock_id 分组后逐组调用 LLM。
        返回成功分析的事件数量。
        """
        query = select(StockEvent).where(StockEvent.is_analyzed.is_(False))
        if target_date:
            query = query.where(StockEvent.event_date >= target_date - timedelta(days=cfg.event_lookback_days))

        result = await self.db.execute(query)
        events = result.scalars().all()

        if not events:
            logger.info("No unanalyzed events found")
            return 0

        grouped: dict[int, list[StockEvent]] = defaultdict(list)
        for event in events:
            grouped[event.stock_id].append(event)

        logger.info(
            "Analyzing %d events across %d stocks",
            len(events), len(grouped),
        )

        total_analyzed = 0
        for stock_id, stock_events in grouped.items():
            try:
                stock_info = await self._get_stock_info(stock_id)
                if not stock_info:
                    logger.warning("Stock %d not found, skipping analysis", stock_id)
                    continue

                analyses = await self._analyze_batch(stock_events, stock_info)
                await self._save_analyses(stock_events, analyses)
                total_analyzed += len(stock_events)

            except Exception:
                logger.exception("Failed to analyze events for stock %d", stock_id)
                continue

            await asyncio.sleep(cfg.llm_batch_delay)

        await self.db.flush()
        logger.info("Catalyst analysis completed: %d events analyzed", total_analyzed)
        return total_analyzed

    async def _analyze_batch(
        self,
        events: list[StockEvent],
        stock_info: dict,
    ) -> list[dict]:
        """将同一只股票的多条事件打包给 LLM 分析。"""
        events_text = "\n\n".join(
            f"[事件{i}]【{e.event_type}】{e.title}\n{(e.content or '')[:cfg.event_content_prompt_length]}"
            for i, e in enumerate(events, 1)
        )

        user_prompt = (
            f"股票：{stock_info['name']}（{stock_info['code']}）\n"
            f"行业：{stock_info['industry']}\n"
            f"当前股价：{stock_info['current_price']}，"
            f"近20日涨跌幅：{stock_info['pct_20d']}%\n\n"
            f"以下是该股票最近的 {len(events)} 条新闻/公告：\n\n"
            f"{events_text}\n\n"
            f"请逐条分析每条事件的影响。"
        )

        result = await chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        return result.get("analyses", [])

    async def _save_analyses(
        self,
        events: list[StockEvent],
        analyses: list[dict],
    ) -> None:
        """将 LLM 分析结果回写到 stock_events 表。"""
        # 优先按 index（1-based）匹配，fallback 到 title 匹配
        analysis_by_index = {a.get("index"): a for a in analyses if a.get("index")}
        analysis_by_title = {a.get("title", ""): a for a in analyses}

        for i, event in enumerate(events, 1):
            analysis = analysis_by_index.get(i) or analysis_by_title.get(event.title)

            if analysis:
                await self.db.execute(
                    update(StockEvent)
                    .where(StockEvent.id == event.id)
                    .values(
                        sentiment=analysis.get("sentiment"),
                        impact_score=self._safe_decimal(analysis.get("impact_score")),
                        catalyst_type=analysis.get("catalyst_type"),
                        time_horizon=analysis.get("time_horizon"),
                        key_point=analysis.get("key_point"),
                        risk_note=analysis.get("risk_note"),
                        analysis=analysis.get("key_point"),
                        is_analyzed=True,
                    )
                )
            else:
                # LLM 可能合并了重复事件，未匹配的也标记为已分析（neutral, score=1）
                await self.db.execute(
                    update(StockEvent)
                    .where(StockEvent.id == event.id)
                    .values(
                        sentiment="neutral",
                        impact_score=Decimal("1"),
                        catalyst_type="其他",
                        key_point="无显著影响",
                        is_analyzed=True,
                    )
                )

    async def _get_stock_info(self, stock_id: int) -> dict | None:
        """获取股票基本信息 + 最新行情，供 LLM prompt 使用。"""
        stock_result = await self.db.execute(
            select(Stock).where(Stock.id == stock_id)
        )
        stock = stock_result.scalar_one_or_none()
        if not stock:
            return None

        today = date.today()
        date_from = today - timedelta(days=30)
        quotes_result = await self.db.execute(
            select(
                StockDailyQuote.close,
                StockDailyQuote.pct_change,
            )
            .where(StockDailyQuote.stock_id == stock_id)
            .where(StockDailyQuote.trade_date > date_from)
            .order_by(StockDailyQuote.trade_date.desc())
            .limit(25)
        )
        quotes = quotes_result.all()

        current_price = float(quotes[0][0]) if quotes else 0.0

        pct_20d = 0.0
        if len(quotes) >= 20:
            old_close = float(quotes[19][0])
            if old_close > 0:
                pct_20d = round((current_price / old_close - 1) * 100, 2)

        return {
            "code": stock.code,
            "name": stock.name,
            "industry": stock.industry or "未知",
            "current_price": current_price,
            "pct_20d": pct_20d,
        }

    @staticmethod
    def _safe_decimal(val) -> Decimal | None:
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None
