"""
Reporting Agent — 推荐理由生成器。

将量化分析结果和催化剂分析整合成简洁易懂的推荐理由。
这是系统中两处 LLM 调用之一（另一处是 Event Agent 的催化剂分析）。
"""

import asyncio
import json
import logging
from datetime import date, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.screener_config import screener_config as cfg
from src.core.llm import chat_json
from src.models.stock import Stock, StockDailyQuote, StockFundamental, StockTechnicalIndicator
from src.models.watchlist import Watchlist

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位面向普通投资者的投资顾问助手。你需要将量化分析结果和催化剂分析整合成简洁易懂的推荐理由。

要求：
1. 语言简洁，避免晦涩的金融术语
2. "reason_short"是一句话摘要，不超过 30 个字
3. "reason_detail"是详细分析段落，100-200 字
4. 必须提及至少一个具体的数据点（如"近 20 日放量 40%"、"PE 处于行业较低水平"）
5. 必须提及主要风险点
6. 不要使用"建议买入"、"建议卖出"等明确的交易建议措辞。使用"值得关注"、"可以留意"等表述
7. 请严格以 JSON 格式输出，不要包含其他内容

输出格式：
{
    "reason_short": "一句话摘要",
    "reason_detail": "详细分析段落"
}"""


class RecommendationReportGenerator:
    """为推荐股票生成面向用户的推荐理由。"""

    async def generate_for_batch(
        self,
        db: AsyncSession,
        picks: list[dict],
        trade_date: date,
    ) -> list[dict]:
        """
        批量为推荐股票生成推荐理由。
        每只股票调用一次 LLM，picks 中的每个 dict 会被就地添加
        reason_short 和 reason_detail 字段。
        """
        for pick in picks:
            try:
                stock_info, quant_data, catalyst_data = await self._load_stock_context(
                    db, pick["stock_id"], trade_date
                )
                reasons = await self._generate_single(stock_info, quant_data, catalyst_data)
                pick["reason_short"] = reasons.get("reason_short", "")
                pick["reason_detail"] = reasons.get("reason_detail", "")
            except Exception:
                logger.exception(
                    "Failed to generate reason for stock_id=%d", pick["stock_id"]
                )
                pick["reason_short"] = "量化指标表现突出，值得关注"
                pick["reason_detail"] = "该股票通过多因子量化模型筛选，综合表现靠前。请结合自身情况判断。"

            await asyncio.sleep(cfg.llm_batch_delay)

        return picks

    async def _generate_single(
        self,
        stock_info: dict,
        quant_data: dict,
        catalyst_data: dict | None,
    ) -> dict:
        """为单只推荐股票生成推荐理由。"""
        catalyst_text = (
            json.dumps(catalyst_data, ensure_ascii=False)
            if catalyst_data
            else "今日无新催化剂，基于量化指标推荐。"
        )

        user_prompt = f"""股票：{stock_info['name']}（{stock_info['code']}）
行业：{stock_info['industry']}
当前价格：{stock_info['price']}

量化指标：
- 近 20 日涨幅（排除近 5 日）：{quant_data['momentum']}%
- 量比（5日均量/20日均量）：{quant_data['volume_ratio']}
- PE_TTM：{quant_data['pe']}（行业中位数：{quant_data['industry_pe_median']}）
- ROE：{quant_data['roe']}%
- 技术形态：{quant_data['technical_summary']}

催化剂分析：
{catalyst_text}"""

        return await chat_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.5,
        )

    async def _load_stock_context(
        self,
        db: AsyncSession,
        stock_id: int,
        trade_date: date,
    ) -> tuple[dict, dict, dict | None]:
        """加载生成推荐理由所需的完整上下文。"""
        stock = await db.get(Stock, stock_id)
        if not stock:
            raise ValueError(f"Stock {stock_id} not found")

        stock_info = {
            "name": stock.name,
            "code": stock.code,
            "industry": stock.industry or "未知",
            "price": "N/A",
        }

        # 近期行情
        date_from = trade_date - timedelta(days=45)
        quotes_result = await db.execute(
            select(StockDailyQuote)
            .where(StockDailyQuote.stock_id == stock_id)
            .where(StockDailyQuote.trade_date > date_from)
            .where(StockDailyQuote.trade_date <= trade_date)
            .order_by(StockDailyQuote.trade_date.asc())
        )
        quotes = quotes_result.scalars().all()

        if quotes:
            stock_info["price"] = f"{quotes[-1].close:.2f}" if quotes[-1].close else "N/A"

        quant_data = self._compute_quant_display(quotes, stock_id)

        # 行业 PE 中位数
        if stock.industry:
            industry_pe = await self._get_industry_pe_median(db, stock.industry)
            quant_data["industry_pe_median"] = (
                f"{industry_pe:.1f}" if industry_pe else "N/A"
            )
        else:
            quant_data["industry_pe_median"] = "N/A"

        # 基本面
        fund_result = await db.execute(
            select(StockFundamental)
            .where(StockFundamental.stock_id == stock_id)
            .order_by(StockFundamental.report_date.desc())
            .limit(1)
        )
        fund = fund_result.scalar_one_or_none()
        if fund:
            quant_data["pe"] = f"{fund.pe_ttm:.1f}" if fund.pe_ttm else "N/A"
            quant_data["roe"] = f"{fund.roe:.2f}" if fund.roe else "N/A"
        else:
            quant_data["pe"] = "N/A"
            quant_data["roe"] = "N/A"

        # 技术指标
        tech_result = await db.execute(
            select(StockTechnicalIndicator)
            .where(StockTechnicalIndicator.stock_id == stock_id)
            .where(StockTechnicalIndicator.trade_date <= trade_date)
            .order_by(StockTechnicalIndicator.trade_date.desc())
            .limit(1)
        )
        tech = tech_result.scalar_one_or_none()
        quant_data["technical_summary"] = self._format_technical(tech, quotes)

        # 催化剂
        watchlist_result = await db.execute(
            select(Watchlist)
            .where(Watchlist.stock_id == stock_id)
            .where(Watchlist.status == "active")
        )
        wl = watchlist_result.scalar_one_or_none()
        catalyst_data = wl.catalyst_summary if wl and wl.catalyst_summary else None

        return stock_info, quant_data, catalyst_data

    @staticmethod
    def _compute_quant_display(quotes: list, stock_id: int) -> dict:
        """从行情数据计算展示用的量化指标。"""
        result = {"momentum": "N/A", "volume_ratio": "N/A"}

        if len(quotes) < cfg.momentum_window:
            return result

        n = len(quotes)
        recent_idx = n - cfg.momentum_exclude_recent - 1
        start_idx = max(0, n - cfg.momentum_window)

        close_start = float(quotes[start_idx].close or 0)
        close_end = float(quotes[recent_idx].close or 0)

        if close_start > 0:
            momentum = ((close_end / close_start) - 1.0) * 100
            result["momentum"] = f"{momentum:.1f}"

        short_vols = [
            float(q.volume or 0) for q in quotes[-cfg.volume_trend_short:]
        ]
        long_vols = [
            float(q.volume or 0) for q in quotes[-cfg.volume_trend_long:]
        ]
        avg_short = sum(short_vols) / len(short_vols) if short_vols else 0
        avg_long = sum(long_vols) / len(long_vols) if long_vols else 0
        if avg_long > 0:
            result["volume_ratio"] = f"{avg_short / avg_long:.2f}"

        return result

    @staticmethod
    async def _get_industry_pe_median(db: AsyncSession, industry: str) -> float | None:
        """获取行业 PE 中位数。使用近似方法：取行业均值。"""
        result = await db.execute(
            select(func.avg(StockFundamental.pe_ttm))
            .join(Stock, Stock.id == StockFundamental.stock_id)
            .where(Stock.industry == industry)
            .where(StockFundamental.pe_ttm > 0)
            .where(StockFundamental.pe_ttm < 200)
        )
        val = result.scalar_one_or_none()
        return float(val) if val else None

    @staticmethod
    def _format_technical(tech, quotes: list) -> str:
        """将技术指标格式化为文字描述。"""
        if not tech:
            return "技术指标数据不足"

        parts = []

        if tech.boll_upper and tech.boll_lower and quotes:
            close = float(quotes[-1].close or 0)
            boll_range = float(tech.boll_upper) - float(tech.boll_lower)
            if boll_range > 0:
                position = (close - float(tech.boll_lower)) / boll_range
                if position < 0.2:
                    parts.append("布林带下轨附近（超卖区）")
                elif position < 0.5:
                    parts.append("布林带中下区间")
                elif position < 0.8:
                    parts.append("布林带中上区间")
                else:
                    parts.append("布林带上轨附近（超买区）")

        if tech.macd is not None and tech.macd_signal is not None:
            macd_val = float(tech.macd)
            signal_val = float(tech.macd_signal)
            if macd_val > signal_val:
                parts.append("MACD 金叉")
            else:
                parts.append("MACD 死叉")

        return "；".join(parts) if parts else "中性"
