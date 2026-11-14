from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    app_username: str = "rayan"
    app_password: str = "changeme"
    # SECRET_KEY هو الاسم المستخدم في render.yaml و .env.example
    session_secret: str = Field(
        "change-this-secret-in-production",
        validation_alias=AliasChoices("SECRET_KEY", "SESSION_SECRET"),
    )
    cookie_secure: bool = False

    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_trading_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    alpaca_data_feed: str = Field(
        "iex", validation_alias=AliasChoices("ALPACA_FEED", "ALPACA_DATA_FEED")
    )

    # مزود الذكاء الاصطناعي: Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = Field(
        "gemini-2.5-flash", validation_alias=AliasChoices("AI_MODEL", "GEMINI_MODEL")
    )

    database_url: str = "sqlite:///./local.db"
    frontend_origin: str = "http://localhost:3000"
    alert_check_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
