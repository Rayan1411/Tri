from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_username: str = "rayan"
    app_password: str = "changeme"
    session_secret: str = "change-this-secret-in-production"
    cookie_secure: bool = False

    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_trading_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_url: str = "https://data.alpaca.markets"
    alpaca_data_feed: str = "iex"

    # إعدادات Gemini API بدلاً من Anthropic
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"

    # إبقاء المتغير القديم اختيارياً لعدم كسر أي إعدادات سابقة
    anthropic_api_key: str = ""
    anthropic_model: str = ""

    database_url: str = "sqlite:///./local.db"
    frontend_origin: str = "http://localhost:3000"
    alert_check_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
