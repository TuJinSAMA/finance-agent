import os

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV = os.getenv("ENV", "dev")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=f".env.{ENV}" if ENV != "dev" else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENV: str = "dev"
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/finance"

    CLERK_WEBHOOK_SIGNING_SECRET: str = ""
    CLERK_JWKS_URL: str = ""

    OPENROUTER_API_KEY: str = ""
    LLM_MODEL: str = "minimax/minimax-m2.5"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2000

    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "AlphaDesk <recommendations@alphadesk.ai>"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync DB URL for libraries that don't support asyncpg (e.g. APScheduler)."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")

    APP_NAME: str = "Finance Agent API"
    DEBUG: bool = ENV == "dev"
    API_V1_PREFIX: str = "/api/v1"


settings = Settings()
