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

    APP_NAME: str = "Finance Agent API"
    DEBUG: bool = ENV == "dev"
    API_V1_PREFIX: str = "/api/v1"


settings = Settings()
