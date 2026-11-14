import os
import secrets


def _db_url(raw: str) -> str:
    """Normalize a database URL so SQLAlchemy uses the psycopg v3 driver."""
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw


class Settings:
    def __init__(self) -> None:
        # --- login (single user) ---
        self.app_username = os.getenv("APP_USERNAME", "rayan")
        self.app_password = os.getenv("APP_PASSWORD", "")
        self.secret_key = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
        self.session_hours = int(os.getenv("SESSION_HOURS", "168"))
        self.cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"

        # --- Alpaca ---
        self.alpaca_key = os.getenv("ALPACA_KEY_ID", "")
        self.alpaca_secret = os.getenv("ALPACA_SECRET_KEY", "")
        # "iex" = free plan, "sip" = Algo Trader Plus (full market)
        self.alpaca_feed = os.getenv("ALPACA_FEED", "iex")
        self.alpaca_trading_url = os.getenv(
            "ALPACA_TRADING_URL", "https://paper-api.alpaca.markets"
        ).rstrip("/")
        self.alpaca_data_url = os.getenv(
            "ALPACA_DATA_URL", "https://data.alpaca.markets"
        ).rstrip("/")

        # --- database ---
        self.database_url = _db_url(os.getenv("DATABASE_URL", "sqlite:///./local.db"))

        # --- AI (add the key whenever you are ready) ---
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.ai_model = os.getenv("AI_MODEL", "claude-sonnet-5-5")

    @property
    def is_paper(self) -> bool:
        return "paper" in self.alpaca_trading_url


settings = Settings()
