from dataclasses import dataclass, field


RSS_FEEDS_EN = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.theguardian.com/world/rss",
    "https://search.cnbc.com/rss/news/world/",
    "https://www.timesofisrael.com/feed/",
    "https://feeds.npr.org/1004/rss.xml",
    "https://www.france24.com/en/middle-east/rss",
    "https://rss.dw.com/rss/rss-en-world",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://oilprice.com/rss/main",
    "https://www.scmp.com/rss/91/feed",
]

RSS_FEEDS_CN = [
    "https://rsshub.app/cls-telegraph",
    "https://rsshub.app/wallstreetcn/news/global",
    "https://rsshub.app/jin10",
    "https://rsshub.app/sina/finance",
    "https://rsshub.app/xueqiu/hotstock",
]

RSS_FEEDS_GLOBAL = [
    "https://www.investing.com/rss/news_301.rss",
    "https://finviz.com/rss.ashx",
]

GNEWS_QUERIES = [
    "iran war military strike",
    "hormuz strait oil tanker",
    "iran us sanctions nuclear",
    "iran israel military",
    "gulf oil supply disruption",
]

GDELT_KEYWORDS = ["iran", "oil", "military"]

GEO_CATEGORIES = [
    "military",
    "sanctions",
    "energy",
    "trade_policy",
    "geopolitics",
    "macro_economy",
    "supply_disruption",
    "regulation",
]

GEO_REGIONS = [
    "middle_east",
    "east_asia",
    "europe",
    "americas",
    "africa",
    "global",
]


@dataclass(frozen=True)
class GeoNewsConfig:
    rss_feeds: list[str] = field(default_factory=lambda: RSS_FEEDS_EN + RSS_FEEDS_CN + RSS_FEEDS_GLOBAL)
    gnews_api_key: str = ""
    gnews_base_url: str = "https://newsapi.org/v2"
    gnews_queries: list[str] = field(default_factory=lambda: list(GNEWS_QUERIES))
    gnews_max_articles_per_query: int = 10

    gdelt_base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    gdelt_keywords: list[str] = field(default_factory=lambda: list(GDELT_KEYWORDS))
    gdelt_max_articles: int = 50

    llm_model: str = "google/gemini-3.1-flash-lite-preview"
    batch_size: int = 10
    dedup_threshold: float = 0.7

    raw_article_ttl_hours: int = 48

    sensitivity_hours_ttl: int = 24
    sensitivity_days_ttl: int = 7
    sensitivity_weeks_ttl: int = 30

    rss_interval_minutes: int = 15
    gnews_interval_hours: int = 2
    gdelt_interval_hours: int = 6
    extraction_interval_minutes: int = 10


geo_news_config = GeoNewsConfig()