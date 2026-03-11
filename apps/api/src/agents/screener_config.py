"""
量化筛选引擎的配置常量。
所有数值门槛集中在此，避免 magic number 散落在各处。
后续接入更多市场时，可以按 market 分组或做成可配置的 dict。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenerConfig:
    """筛选引擎参数（Orchestrator 第一层硬性过滤 + 第二层多因子打分）。"""

    # ── 第一层：硬性条件过滤 ──────────────────────────

    # 最低日均成交额（元），低于此值的流动性不足，不可交易
    min_daily_amount: float = 50_000_000  # 5000 万

    # 最少上市天数，排除次新股
    min_list_days: int = 60

    # 近 N 日内有涨跌停的排除
    limit_up_down_lookback_days: int = 5

    # 排除的交易所（北交所流动性差）
    excluded_exchanges: tuple[str, ...] = ("BJ",)

    # ── 第二层：多因子打分权重 ─────────────────────────

    # 动量因子：近 N 日涨幅（排除最近 M 日避免追高）
    momentum_window: int = 20
    momentum_exclude_recent: int = 5
    weight_momentum: float = 0.25

    # 成交量趋势：短期均量 / 长期均量
    volume_trend_short: int = 5
    volume_trend_long: int = 20
    weight_volume_trend: float = 0.15

    # 估值：PE_TTM 行业内分位数（越低越好）
    weight_valuation: float = 0.20

    # 盈利质量：ROE + 毛利率 + 经营现金流/净利润
    weight_profitability: float = 0.20

    # 波动率：近 N 日日收益率标准差（越低越好）
    volatility_window: int = 20
    weight_volatility: float = 0.10

    # 技术形态：布林带位置 + MACD 金叉/死叉
    weight_technical: float = 0.10

    # ── 关注池与推荐 ─────────────────────────────────

    # 第二层打分后取 Top N 进入关注池
    watchlist_size: int = 50

    # 最终推荐数量
    recommendation_count: int = 5

    # 同行业最多推荐数
    max_same_industry: int = 2

    # 反疲劳：N 天内推荐超过 M 次的降级
    anti_fatigue_days: int = 5
    anti_fatigue_max_count: int = 2

    # ── 综合评分权重 ─────────────────────────────────

    # 量化分 vs 催化剂分
    score_weight_quant: float = 0.60
    score_weight_catalyst: float = 0.40

    # ── Data Agent 相关 ──────────────────────────────

    # 技术指标计算所需最小历史天数
    min_days_for_indicators: int = 60

    # 历史回填默认天数
    default_backfill_days: int = 180

    # AKShare 请求间隔（秒）
    akshare_rate_limit: float = 0.3

    # 批量写入每块大小
    db_batch_chunk_size: int = 500

    # ── Event Agent 相关 ─────────────────────────────

    # 每只股票取最新 N 条新闻
    event_news_per_stock: int = 10

    # 事件内容存储截断长度
    event_content_max_length: int = 2000

    # 送入 LLM 的单条事件内容长度
    event_content_prompt_length: int = 500

    # LLM 调用间隔（秒），避免 API 限流
    llm_batch_delay: float = 1.0

    # 催化剂分析中，近 N 天的事件视为"近期"
    event_lookback_days: int = 3


# 全局默认配置实例
screener_config = ScreenerConfig()
