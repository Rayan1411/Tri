from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .ai import ask_claude
from .alpaca import AlpacaError, alpaca, is_crypto_symbol, to_ui_symbol
from .auth import (
    COOKIE_NAME,
    create_session_token,
     get_current_user,
    verify_credentials,
)
from .config import get_settings
from .db import ChatMessage, PriceAlert, TradePlan, WatchlistItem, get_db

router = APIRouter(prefix="/api")


def _handle_alpaca_error(exc: AlpacaError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ==================== Auth ====================
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginIn, response: Response) -> Dict[str, Any]:
    if not verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    settings = get_settings()
    token = create_session_token(body.username.strip())
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return {"username": body.username.strip()}


@router.post("/auth/logout")
async def logout(response: Response) -> Dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
async def me(user: str = Depends(get_current_user)) -> Dict[str, str]:
    return {"username": user}


# ==================== Dashboard & Market ====================
@router.get("/dashboard")
async def dashboard(
    asset_class: str = Query("stock", pattern="^(stock|crypto)$"),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    watch_items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.asset_class == asset_class)
        .order_by(WatchlistItem.added_at.asc())
        .all()
    )
    symbols = [w.symbol for w in watch_items]

    try:
        account = await alpaca.get_account()
    except AlpacaError:
        account = None

    try:
        positions = await alpaca.get_positions()
    except AlpacaError:
        positions = []

    pos_symbols = [p.get("ui_symbol") or p.get("symbol") for p in positions if p.get("symbol")]
    all_symbols = list(dict.fromkeys(symbols + pos_symbols))

    try:
        snapshots = await alpaca.get_snapshots(all_symbols) if all_symbols else {}
    except AlpacaError:
        snapshots = {}

    movers = await alpaca.get_movers(
        market_type="crypto" if asset_class == "crypto" else "stocks"
    )
    news = await alpaca.get_news(limit=12)

    watchlist_enriched = [
        {
            "id": w.id,
            "symbol": w.symbol,
            "asset_class": w.asset_class,
            "note": w.note,
            "snapshot": snapshots.get(w.symbol),
        }
        for w in watch_items
    ]

    active_alerts = (
        db.query(PriceAlert)
        .filter(PriceAlert.active.is_(True))
        .order_by(PriceAlert.created_at.desc())
        .limit(20)
        .all()
    )
    triggered_alerts = (
        db.query(PriceAlert)
        .filter(PriceAlert.active.is_(False), PriceAlert.triggered_at.is_not(None))
        .order_by(PriceAlert.triggered_at.desc())
        .limit(10)
        .all()
    )
    active_plans = (
        db.query(TradePlan)
        .filter(TradePlan.status == "active")
        .order_by(TradePlan.created_at.desc())
        .all()
    )

    return {
        "asset_class": asset_class,
        "account": account,
        "positions": positions,
        "watchlist": watchlist_enriched,
        "movers": movers,
        "news": news,
        "active_alerts": [_serialize_alert(a) for a in active_alerts],
        "triggered_alerts": [_serialize_alert(a) for a in triggered_alerts],
        "trade_plans": [_serialize_plan(p) for p in active_plans],
    }


@router.get("/search")
async def search(
    q: str = Query("", max_length=30),
    asset_class: str = Query("stock", pattern="^(stock|crypto)$"),
    user: str = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    try:
        return await alpaca.search_assets(q, asset_class=asset_class, limit=15)
    except AlpacaError as exc:
        _handle_alpaca_error(exc)


@router.get("/stocks/{symbol}")
async def stock_detail(
    symbol: str,
    range_key: str = Query("1M", alias="range"),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(symbol)
    is_crypto = is_crypto_symbol(sym)
    try:
        asset = await alpaca.get_asset(sym)
    except AlpacaError:
        asset = {"symbol": sym, "name": sym, "exchange": "CRYPTO" if is_crypto else ""}

    snaps = await alpaca.get_snapshots([sym])
    try:
        bars = await alpaca.get_bars(sym, range_key=range_key)
    except AlpacaError:
        bars = []

    news = await alpaca.get_news(symbol=sym, limit=12)

    try:
        positions = await alpaca.get_positions()
    except AlpacaError:
        positions = []
    position = next(
        (p for p in positions if (p.get("ui_symbol") or p.get("symbol", "")).upper() == sym),
        None,
    )

    in_watchlist = (
        db.query(WatchlistItem).filter(WatchlistItem.symbol == sym).first() is not None
    )
    alerts = (
        db.query(PriceAlert)
        .filter(PriceAlert.symbol == sym)
        .order_by(PriceAlert.created_at.desc())
        .all()
    )
    plans = (
        db.query(TradePlan)
        .filter(TradePlan.symbol == sym, TradePlan.status == "active")
        .order_by(TradePlan.created_at.desc())
        .all()
    )

    return {
        "symbol": sym,
        "asset_class": "crypto" if is_crypto else "stock",
        "asset": asset,
        "snapshot": snaps.get(sym),
        "bars": bars,
        "news": news,
        "position": position,
        "in_watchlist": in_watchlist,
        "alerts": [_serialize_alert(a) for a in alerts],
        "trade_plans": [_serialize_plan(p) for p in plans],
    }


# ==================== Watchlist ====================
class WatchlistIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=24)
    asset_class: Optional[str] = None
    note: Optional[str] = Field(None, max_length=280)


@router.get("/watchlist")
async def list_watchlist(
    asset_class: Optional[str] = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(WatchlistItem)
    if asset_class in ("stock", "crypto"):
        q = q.filter(WatchlistItem.asset_class == asset_class)
    items = q.order_by(WatchlistItem.added_at.asc()).all()
    snaps = await alpaca.get_snapshots([i.symbol for i in items]) if items else {}
    return [
        {
            "id": i.id,
            "symbol": i.symbol,
            "asset_class": i.asset_class,
            "note": i.note,
            "snapshot": snaps.get(i.symbol),
        }
        for i in items
    ]


@router.post("/watchlist")
async def add_watchlist(
    body: WatchlistIn,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(body.symbol)
    ac = body.asset_class or ("crypto" if is_crypto_symbol(sym) else "stock")
    existing = db.query(WatchlistItem).filter(WatchlistItem.symbol == sym).first()
    if existing:
        existing.note = body.note
        existing.asset_class = ac
        db.commit()
        db.refresh(existing)
        item = existing
    else:
        item = WatchlistItem(symbol=sym, asset_class=ac, note=body.note)
        db.add(item)
        db.commit()
        db.refresh(item)
    snaps = await alpaca.get_snapshots([sym])
    return {
        "id": item.id,
        "symbol": item.symbol,
        "asset_class": item.asset_class,
        "note": item.note,
        "snapshot": snaps.get(sym),
    }


@router.delete("/watchlist/{symbol}")
async def remove_watchlist(
    symbol: str,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, bool]:
    sym = to_ui_symbol(symbol)
    db.query(WatchlistItem).filter(WatchlistItem.symbol == sym).delete()
    db.commit()
    return {"ok": True}


# ==================== Portfolio & Orders ====================
class OrderIn(BaseModel):
    symbol: str
    qty: float = Field(..., gt=0)
    side: str = Field(..., pattern="^(buy|sell)$")
    order_type: str = Field("market", pattern="^(market|limit)$")
    time_in_force: str = Field("day", pattern="^(day|gtc)$")
    limit_price: Optional[float] = Field(None, gt=0)
    tp1_price: Optional[float] = Field(None, gt=0)
    tp2_price: Optional[float] = Field(None, gt=0)
    sl_price: Optional[float] = Field(None, gt=0)


@router.get("/portfolio")
async def portfolio(
    period: str = Query("1M"),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        account = await alpaca.get_account()
        positions = await alpaca.get_positions()
        orders = await alpaca.get_orders(status="all", limit=40)
    except AlpacaError as exc:
        _handle_alpaca_error(exc)

    tf_map = {"1W": "1H", "1M": "1D", "3M": "1D", "1Y": "1D", "ALL": "1W"}
    tf = tf_map.get(period, "1D")
    try:
        history = await alpaca.get_portfolio_history(period=period, timeframe=tf)
    except AlpacaError:
        history = None

    plans = (
        db.query(TradePlan)
        .order_by(TradePlan.created_at.desc())
        .limit(30)
        .all()
    )

    return {
        "account": account,
        "positions": positions,
        "orders": orders,
        "history": history,
        "trade_plans": [_serialize_plan(p) for p in plans],
    }


@router.post("/orders")
async def place_order(
    body: OrderIn,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(body.symbol)
    try:
        order = await alpaca.submit_order(
            symbol=sym,
            qty=body.qty,
            side=body.side,
            order_type=body.order_type,
            time_in_force=body.time_in_force,
            limit_price=body.limit_price,
        )
    except AlpacaError as exc:
        _handle_alpaca_error(exc)

    # إذا أرفق المستخدم أو الذكاء الاصطناعي أهدافاً أو وقف خسارة، نسجلها في مراقب البوت الذكي
    if body.tp1_price or body.tp2_price or body.sl_price:
        snaps = await alpaca.get_snapshots([sym])
        curr_p = (snaps.get(sym) or {}).get("price") or body.limit_price or 0.0
        plan = TradePlan(
            symbol=sym,
            asset_class="crypto" if is_crypto_symbol(sym) else "stock",
            side=body.side,
            qty=body.qty,
            remaining_qty=body.qty,
            entry_price=float(curr_p),
            tp1_price=body.tp1_price,
            tp2_price=body.tp2_price,
            sl_price=body.sl_price,
            status="active",
            entry_order_id=(order or {}).get("id"),
            notes="تم التنفيذ مع تفعيل مراقبة الأهداف ووقف الخسارة آلياً",
        )
        db.add(plan)
        db.commit()

    return order or {"ok": True}


@router.delete("/orders/{order_id}")
async def delete_order(
    order_id: str, user: str = Depends(get_current_user)
) -> Dict[str, bool]:
    try:
        await alpaca.cancel_order(order_id)
    except AlpacaError as exc:
        _handle_alpaca_error(exc)
    return {"ok": True}


@router.delete("/positions/{symbol}")
async def close_position(
    symbol: str,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(symbol)
    try:
        res = await alpaca.close_position(sym)
        # إيقاف أي خطة تداول نشطة لهذا الرمز بعد إغلاق المركز يدوياً
        db.query(TradePlan).filter(
            TradePlan.symbol == sym, TradePlan.status == "active"
        ).update({"status": "canceled"})
        db.commit()
        return res or {"ok": True}
    except AlpacaError as exc:
        _handle_alpaca_error(exc)


# ==================== Smart AI Trade Plans ====================
class ExecutePlanIn(BaseModel):
    symbol: str
    action: str = Field(..., pattern="^(BUY|SELL|buy|sell)$")
    order_type: str = Field("market", pattern="^(market|limit)$")
    qty: float = Field(..., gt=0)
    entry: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    sl: Optional[float] = None
    summary: Optional[str] = None


def _serialize_plan(p: TradePlan) -> Dict[str, Any]:
    return {
        "id": p.id,
        "symbol": p.symbol,
        "asset_class": p.asset_class,
        "side": p.side,
        "qty": p.qty,
        "remaining_qty": p.remaining_qty,
        "entry_price": p.entry_price,
        "tp1_price": p.tp1_price,
        "tp2_price": p.tp2_price,
        "sl_price": p.sl_price,
        "tp1_hit": p.tp1_hit,
        "status": p.status,
        "entry_order_id": p.entry_order_id,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
    }


@router.post("/trade-plans/execute")
async def execute_trade_plan(
    body: ExecutePlanIn,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(body.symbol)
    side = body.action.lower()
    is_crypto = is_crypto_symbol(sym)

    try:
        order = await alpaca.submit_order(
            symbol=sym,
            qty=body.qty,
            side=side,
            order_type=body.order_type,
            time_in_force="gtc" if is_crypto else "day",
            limit_price=body.entry if body.order_type == "limit" else None,
        )
    except AlpacaError as exc:
        _handle_alpaca_error(exc)

    snaps = await alpaca.get_snapshots([sym])
    curr_p = (snaps.get(sym) or {}).get("price") or body.entry or 0.0

    plan = TradePlan(
        symbol=sym,
        asset_class="crypto" if is_crypto else "stock",
        side=side,
        qty=body.qty,
        remaining_qty=body.qty,
        entry_price=float(curr_p),
        tp1_price=body.tp1,
        tp2_price=body.tp2,
        sl_price=body.sl,
        status="active",
        entry_order_id=(order or {}).get("id"),
        notes=body.summary or "صفقة منفذة بأمر الذكاء الاصطناعي Gemini",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return {"order": order, "trade_plan": _serialize_plan(plan)}


@router.delete("/trade-plans/{plan_id}")
async def cancel_trade_plan(
    plan_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, bool]:
    db.query(TradePlan).filter(TradePlan.id == plan_id).update({"status": "canceled"})
    db.commit()
    return {"ok": True}


# ==================== Alerts ====================
class AlertIn(BaseModel):
    symbol: str
    direction: str = Field(..., pattern="^(above|below)$")
    target_price: float = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=280)


def _serialize_alert(a: PriceAlert) -> Dict[str, Any]:
    return {
        "id": a.id,
        "symbol": a.symbol,
        "direction": a.direction,
        "target_price": a.target_price,
        "note": a.note,
        "active": a.active,
        "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
        "triggered_price": a.triggered_price,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/alerts")
async def list_alerts(
    user: str = Depends(get_current_user), db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    alerts = db.query(PriceAlert).order_by(PriceAlert.created_at.desc()).limit(100).all()
    return [_serialize_alert(a) for a in alerts]


@router.post("/alerts")
async def create_alert(
    body: AlertIn,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(body.symbol)
    alert = PriceAlert(
        symbol=sym,
        direction=body.direction,
        target_price=body.target_price,
        note=body.note,
        active=True,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _serialize_alert(alert)


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, bool]:
    db.query(PriceAlert).filter(PriceAlert.id == alert_id).delete()
    db.commit()
    return {"ok": True}


# ==================== AI Chat ====================
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    symbol: Optional[str] = None
    range_key: Optional[str] = "1M"


@router.get("/ai/history")
async def chat_history(
    symbol: Optional[str] = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    q = db.query(ChatMessage)
    if symbol:
        q = q.filter(ChatMessage.symbol == to_ui_symbol(symbol))
    else:
        q = q.filter(ChatMessage.symbol.is_(None))
    msgs = q.order_by(ChatMessage.created_at.asc()).limit(60).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


@router.delete("/ai/history")
async def clear_chat_history(
    symbol: Optional[str] = Query(None),
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, bool]:
    q = db.query(ChatMessage)
    if symbol:
        q = q.filter(ChatMessage.symbol == to_ui_symbol(symbol))
    else:
        q = q.filter(ChatMessage.symbol.is_(None))
    q.delete()
    db.commit()
    return {"ok": True}


@router.post("/ai/chat")
async def chat(
    body: ChatIn,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sym = to_ui_symbol(body.symbol) if body.symbol else None

    q = db.query(ChatMessage)
    q = q.filter(ChatMessage.symbol == sym) if sym else q.filter(ChatMessage.symbol.is_(None))
    prior = q.order_by(ChatMessage.created_at.asc()).limit(20).all()
    history = [{"role": m.role, "content": m.content} for m in prior]

    context: Dict[str, Any] = {}
    if sym:
        context["symbol"] = sym
        try:
            snaps = await alpaca.get_snapshots([sym])
            context["snapshot"] = snaps.get(sym)
        except AlpacaError:
            pass
        try:
            bars = await alpaca.get_bars(sym, range_key=body.range_key or "1M")
            context["recent_bars"] = bars[-30:]
        except AlpacaError:
            pass
        context["news"] = await alpaca.get_news(symbol=sym, limit=6)
    try:
        context["account"] = await alpaca.get_account()
        context["positions"] = await alpaca.get_positions()
    except AlpacaError:
        pass

    ai_res = await ask_claude(history=history, user_message=body.message, context=context)
    reply_text = ai_res.get("reply") or ""
    trade_plan = ai_res.get("trade_plan")

    user_row = ChatMessage(symbol=sym, role="user", content=body.message)
    bot_row = ChatMessage(symbol=sym, role="assistant", content=reply_text)
    db.add_all([user_row, bot_row])
    db.commit()

    return {"reply": reply_text, "trade_plan": trade_plan}
