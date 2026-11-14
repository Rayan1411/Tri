from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


settings = get_settings()
db_url = _normalize_db_url(settings.database_url)
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    asset_class: Mapped[str] = mapped_column(String(16), default="stock", index=True)
    note: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # "above" or "below"
    target_price: Mapped[float] = mapped_column(Float)
    note: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradePlan(Base):
    """جدول البوت الذكي لمراقبة وتنفيذ الهدف الأول والثاني ووقف الخسارة آلياً"""
    __tablename__ = "trade_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    asset_class: Mapped[str] = mapped_column(String(16), default="stock")  # "stock" or "crypto"
    side: Mapped[str] = mapped_column(String(8), default="buy")  # "buy" or "sell"
    qty: Mapped[float] = mapped_column(Float)
    remaining_qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    tp1_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp2_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sl_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp1_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active, completed, stopped, canceled
    # لا يبدأ المراقب بتنفيذ الأهداف/وقف الخسارة قبل أن يُنفَّذ أمر الدخول فعلياً
    entry_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    entry_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(24), index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    plan_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # خطة التداول المرفقة بالرد (JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


DEFAULT_STOCKS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD"]
DEFAULT_CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "AVAX-USD"]


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    try:
        cols = [c["name"] for c in inspect(engine).get_columns(table)]
        if column not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    except Exception as exc:  # لا نوقف التشغيل، لكن نُظهر السبب
        import logging

        logging.getLogger("stocks").warning("Migration %s.%s failed: %s", table, column, exc)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # ترقية تلقائية لقاعدة البيانات الحالية (Render) لإضافة أعمدة جديدة إن لم تكن موجودة
    _add_column_if_missing("watchlist_items", "asset_class", "VARCHAR(16) DEFAULT 'stock'")
    # الخطط القديمة اعتُبر دخولها منفذاً
    _add_column_if_missing("trade_plans", "entry_filled", "BOOLEAN DEFAULT TRUE")
    _add_column_if_missing("chat_messages", "plan_json", "TEXT")

    with SessionLocal() as db:
        has_stocks = db.query(WatchlistItem).filter(WatchlistItem.asset_class == "stock").first()
        if not has_stocks:
            for sym in DEFAULT_STOCKS:
                if not db.query(WatchlistItem).filter(WatchlistItem.symbol == sym).first():
                    db.add(WatchlistItem(symbol=sym, asset_class="stock"))
            db.commit()

        has_crypto = db.query(WatchlistItem).filter(WatchlistItem.asset_class == "crypto").first()
        if not has_crypto:
            for sym in DEFAULT_CRYPTO:
                if not db.query(WatchlistItem).filter(WatchlistItem.symbol == sym).first():
                    db.add(WatchlistItem(symbol=sym, asset_class="crypto"))
            db.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
