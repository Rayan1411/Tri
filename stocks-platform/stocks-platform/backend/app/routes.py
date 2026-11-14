import asyncio
import functools
import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, alpaca
from .auth import require_user
from .db import Alert, WatchItem, get_db, iso

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


def clean_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if not SYMBOL_RE.match(s):
        raise HTTPException(status_code=400, detail="رمز سهم غير صالح")
    return s


def _wrap(coro_fn):
    """Turn AlpacaError into a clean HTTP error."""
    @functools.wraps(coro_fn)
    async def runner(*a, **kw):
        try:
            return await coro_fn(*a, **kw)
        except alpaca.AlpacaError as e:
            raise HTTPException(status_code=e.status if 400 <= e.status < 600 else 502, detail=e.detail)
    return runner


# ------------------------------------------------------------------ market data
@router.get("/market/clock")
@_wrap
async def market_clock():
    return await alpaca.clock()


@router.get("/market/movers")
async def market_movers():
    async def safe(coro, default):
        try:
            return await coro
        except alpaca.AlpacaError:
            return default

    movers, actives = await asyncio.gather(
        safe(alpaca.movers(), {"gainers": [], "losers": []}),
        safe(alpaca.most_actives(), []),
    )
    return {**movers, "actives": actives}


@router.get("/quotes")
@_wrap
async def get_quotes(symbols: str):
    syms = [clean_symbol(s) for s in symbols.split(",") if s.strip()][:60]
    return await alpaca.quotes(syms)


@router.get("/quote/{symbol}")
@_wrap
async def get_quote(symbol: str):
    sym = clean_symbol(symbol)
    q = (await alpaca.quotes([sym])).get(sym)
    if not q:
        raise HTTPException(status_code=404, detail="الرمز غير موجود")
    return q


@router.get("/asset/{symbol}")
@_wrap
async def get_asset(symbol: str):
    sym = clean_symbol(symbol)
    return await alpaca.asset(sym) or {"symbol": sym, "name": "", "exchange": ""}


@router.get("/bars/{symbol}")
@_wrap
async def get_bars(symbol: str, timeframe: str = "5m", recent: bool = False):
    return await alpaca.bars(clean_symbol(symbol), timeframe, recent)


@router.get("/news")
@_wrap
async def get_news(symbol: Optional[str] = None):
    return await alpaca.news(clean_symbol(symbol) if symbol else None)


@router.get("/search")
@_wrap
async def search(q: str = ""):
    return await alpaca.search(q[:30])


# ------------------------------------------------------------------ watchlist
class SymbolBody(BaseModel):
    symbol: str


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    rows = db.scalars(select(WatchItem).order_by(WatchItem.id)).all()
    return [r.symbol for r in rows]


@router.post("/watchlist")
def add_watch(body: SymbolBody, db: Session = Depends(get_db)):
    sym = clean_symbol(body.symbol)
    if not db.scalar(select(WatchItem).where(WatchItem.symbol == sym)):
        db.add(WatchItem(symbol=sym))
        db.commit()
    return {"ok": True}


@router.delete("/watchlist/{symbol}")
def remove_watch(symbol: str, db: Session = Depends(get_db)):
    sym = clean_symbol(symbol)
    row = db.scalar(select(WatchItem).where(WatchItem.symbol == sym))
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ alerts
class AlertBody(BaseModel):
    symbol: str
    direction: Literal["above", "below"]
    price: float = Field(gt=0)


def _alert_out(a: Alert):
    return {
        "id": a.id,
        "symbol": a.symbol,
        "direction": a.direction,
        "price": a.price,
        "active": a.active,
        "triggered_at": iso(a.triggered_at),
        "triggered_price": a.triggered_price,
        "created_at": iso(a.created_at),
    }


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db)):
    rows = db.scalars(select(Alert).order_by(Alert.id.desc()).limit(200)).all()
    return [_alert_out(a) for a in rows]


@router.post("/alerts")
def create_alert(body: AlertBody, db: Session = Depends(get_db)):
    a = Alert(symbol=clean_symbol(body.symbol), direction=body.direction, price=body.price)
    db.add(a)
    db.commit()
    return _alert_out(a)


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a:
        db.delete(a)
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ trading (Alpaca)
class OrderBody(BaseModel):
    symbol: str
    qty: float = Field(gt=0)
    side: Literal["buy", "sell"]
    type: Literal["market", "limit"] = "market"
    limit_price: Optional[float] = Field(default=None, gt=0)


@router.get("/trade/account")
@_wrap
async def trade_account():
    return await alpaca.account()


@router.get("/trade/positions")
@_wrap
async def trade_positions():
    return await alpaca.positions()


@router.get("/trade/orders")
@_wrap
async def trade_orders():
    return await alpaca.orders()


@router.post("/trade/orders")
@_wrap
async def trade_place(body: OrderBody):
    if body.type == "limit" and body.limit_price is None:
        raise HTTPException(status_code=400, detail="أدخل سعر الحد للأمر المحدد")
    await alpaca.place_order(clean_symbol(body.symbol), body.qty, body.side, body.type, body.limit_price)
    return {"ok": True}


@router.delete("/trade/orders/{order_id}")
@_wrap
async def trade_cancel(order_id: str):
    await alpaca.cancel_order(order_id)
    return {"ok": True}


@router.post("/trade/positions/{symbol}/close")
@_wrap
async def trade_close(symbol: str):
    await alpaca.close_position(clean_symbol(symbol))
    return {"ok": True}


# ------------------------------------------------------------------ AI chat
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatBody(BaseModel):
    symbol: Optional[str] = None
    messages: List[ChatMessage]


@router.get("/ai/status")
def ai_status():
    return {"configured": ai.configured()}


@router.post("/ai/chat")
async def ai_chat(body: ChatBody):
    if not ai.configured():
        return {
            "configured": False,
            "reply": "لم يُضبط مفتاح الذكاء الاصطناعي بعد. أضف ANTHROPIC_API_KEY في متغيرات البيئة على Render ثم أعد تشغيل الخادم.",
        }
    sym = clean_symbol(body.symbol) if body.symbol else None
    reply = await ai.chat(sym, [m.model_dump() for m in body.messages])
    return {"configured": True, "reply": reply}
