from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class DecisionChainConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deep_think_llm: str = "openai/gpt-4.1"
    quick_think_llm: str = "openai/gpt-4.1-mini"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    max_debate_rounds: int = 1
    max_risk_discuss_rounds: int = 1
    max_recur_limit: int = 100

    output_language: str = "Chinese"
    results_dir: str = str(Path(__file__).parent.parent.parent.parent / "decision_results")

    data_vendors: dict = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    tool_vendors: dict = {}


decision_chain_config = DecisionChainConfig()