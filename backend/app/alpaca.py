"""Thin async wrapper around the Alpaca REST APIs (market data + paper trading)."""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

from .config import settings

NY = ZoneInfo("America/New_York")

# timeframe key -> (Alpaca timeframe, lookback days)
TIMEFRAMES = {
    "1m": ("1Min", 6),
    "5m": ("5Min", 20),
    "15m": ("15Min", 40),
    "1h": ("1Hour", 150),
    "1d": ("1Day", 1100),
}


class AlpacaError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


_client: Optional[httpx.AsyncClient] = None
_cache: Dict[Any, tuple] = {}


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=20.0)
    return _client


def _headers() -> Dict[str, str]:
    if not settings.alpaca_key or not settings.alpaca_secret:
        raise AlpacaError(503, "مفاتيح Alpaca غير مضبوطة على الخادم (ALPACA_KEY_ID / ALPACA_SECRET_KEY)")
    return {
        "APCA-API-KEY-ID": settings.alpaca_key,
        "APCA-API-SECRET-KEY": settings.alpaca_secret,
    }


async def _request(method: str, base: str, path: str, params=None, json=None, ttl: float = 0):
    key = None
    if method == "GET" and ttl > 0:
        key = (base, path, tuple(sorted((params or {}).items())))
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
    try:
        r = await _http().request(method, base + path, params=params, json=json, headers=_headers())
    except httpx.HTTPError as e:
        raise AlpacaError(502, f"تعذّر الاتصال بـ Alpaca: {e.__class__.__name__}")
    if r.status_code >= 400:
        detail = r.text[:300]
        try:
            detail = r.json().get("message", detail)
        except Exception:
            pass
        raise AlpacaError(r.status_code if r.status_code != 401 else 502, f"Alpaca: {detail}")
    data = None if r.status_code == 204 or not r.content else r.json()
    if key is not None:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.time() + ttl, data)
    return data


async def _data(path: str, params=None, ttl: float = 0):
    return await _request("GET", settings.alpaca_data_url, path, params, ttl=ttl)


async def _trading(method: str, path: str, params=None, json=None, ttl: float = 0):
    return await _request(method, settings.alpaca_trading_url, path, params, json, ttl)


def _epoch(t: str) -> int:
    return int(datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp())


def _rfc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- bars
async def bars(symbol: str, timeframe: str, recent: bool = False) -> List[Dict[str, Any]]:
    if timeframe not in TIMEFRAMES:
        raise AlpacaError(400, "إطار زمني غير مدعوم")
    tf, days = TIMEFRAMES[timeframe]
    now = datetime.now(timezone.utc)
    base_params = {
        "timeframe": tf,
        "feed": settings.alpaca_feed,
        "adjustment": "split",
    }
    path = f"/v2/stocks/{symbol}/bars"

    if recent:
        params = {
            **base_params,
            "start": _rfc(now - timedelta(days=min(days, 10))),
            "limit": 3,
            "sort": "desc",
        }
        data = await _data(path, params, ttl=3)
        items = list(reversed(data.get("bars") or []))
    else:
        params = {
            **base_params,
            "start": _rfc(now - timedelta(days=days)),
            "limit": 10000,
            "sort": "asc",
        }
        items = []
        for _ in range(5):
            data = await _data(path, params, ttl=5)
            items.extend(data.get("bars") or [])
            token = data.get("next_page_token")
            if not token:
                break
            params = {**params, "page_token": token}

    return [
        {
            "time": _epoch(b["t"]),
            "open": b["o"],
            "high": b["h"],
            "low": b["l"],
            "close": b["c"],
            "volume": b.get("v", 0),
        }
        for b in items
    ]


# ---------------------------------------------------------------- quotes
def _norm_snapshot(symbol: str, s: Dict[str, Any]) -> Dict[str, Any]:
    lt = s.get("latestTrade") or {}
    lq = s.get("latestQuote") or {}
    db = s.get("dailyBar") or {}
    pb = s.get("prevDailyBar") or {}

    price = lt.get("p") or db.get("c") or pb.get("c")
    prev_close = pb.get("c")
    session = db  # today's session bar

    # Pre-market of a new day: the "daily bar" is still yesterday's session.
    if lt.get("t") and db.get("t"):
        trade_day = datetime.fromisoformat(lt["t"].replace("Z", "+00:00")).astimezone(NY).date()
        bar_day = datetime.fromisoformat(db["t"].replace("Z", "+00:00")).date()
        if trade_day > bar_day:
            prev_close = db.get("c")
            session = {}

    change = pct = None
    if price is not None and prev_close:
        change = price - prev_close
        pct = change / prev_close * 100

    return {
        "symbol": symbol,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": pct,
        "open": session.get("o"),
        "high": session.get("h"),
        "low": session.get("l"),
        "volume": session.get("v"),
        "bid": lq.get("bp"),
        "ask": lq.get("ap"),
        "time": lt.get("t"),
    }


async def quotes(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    if not symbols:
        return {}
    data = await _data(
        "/v2/stocks/snapshots",
        {"symbols": ",".join(symbols), "feed": settings.alpaca_feed},
        ttl=3,
    )
    data = data.get("snapshots", data) if isinstance(data, dict) else {}
    return {sym: _norm_snapshot(sym, snap) for sym, snap in data.items() if isinstance(snap, dict)}


# ---------------------------------------------------------------- screener
async def movers() -> Dict[str, List[Dict[str, Any]]]:
    data = await _data("/v1beta1/screener/stocks/movers", {"top": 10}, ttl=30)
    pick = lambda rows: [
        {
            "symbol": r["symbol"],
            "price": r.get("price"),
            "change": r.get("change"),
            "change_pct": r.get("percent_change"),
        }
        for r in (rows or [])
    ]
    return {"gainers": pick(data.get("gainers")), "losers": pick(data.get("losers"))}


async def most_actives() -> List[Dict[str, Any]]:
    data = await _data(
        "/v1beta1/screener/stocks/most-actives", {"by": "volume", "top": 10}, ttl=30
    )
    rows = data.get("most_actives") or []
    syms = [r["symbol"] for r in rows]
    q = await quotes(syms) if syms else {}
    out = []
    for r in rows:
        s = q.get(r["symbol"], {})
        out.append(
            {
                "symbol": r["symbol"],
                "volume": r.get("volume"),
                "price": s.get("price"),
                "change": s.get("change"),
                "change_pct": s.get("change_pct"),
            }
        )
    return out


# ---------------------------------------------------------------- news
async def news(symbol: Optional[str], limit: int = 12) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit, "sort": "desc"}
    if symbol:
        params["symbols"] = symbol
    data = await _data("/v1beta1/news", params, ttl=120)
    return [
        {
            "id": n.get("id"),
            "headline": n.get("headline"),
            "summary": n.get("summary"),
            "source": n.get("source"),
            "url": n.get("url"),
            "created_at": n.get("created_at"),
            "symbols": n.get("symbols", []),
        }
        for n in (data.get("news") or [])
    ]


# ---------------------------------------------------------------- assets / search
_assets: List[Dict[str, str]] = []
_assets_at: float = 0.0
_assets_lock = asyncio.Lock()
_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"}


async def _load_assets() -> List[Dict[str, str]]:
    global _assets, _assets_at
    async with _assets_lock:
        if _assets and time.time() - _assets_at < 6 * 3600:
            return _assets
        data = await _trading("GET", "/v2/assets", {"status": "active", "asset_class": "us_equity"})
        _assets = [
            {"symbol": a["symbol"], "name": a.get("name") or "", "exchange": a.get("exchange") or ""}
            for a in data
            if a.get("tradable") and a.get("exchange") in _EXCHANGES
        ]
        _assets_at = time.time()
        return _assets


async def search(q: str, limit: int = 8) -> List[Dict[str, str]]:
    q = q.strip().upper()
    if not q:
        return []
    assets = await _load_assets()
    exact = [a for a in assets if a["symbol"] == q]
    prefix = [a for a in assets if a["symbol"].startswith(q) and a["symbol"] != q]
    by_name = [a for a in assets if q in a["name"].upper() and not a["symbol"].startswith(q)]
    prefix.sort(key=lambda a: len(a["symbol"]))
    return (exact + prefix + by_name)[:limit]


async def asset(symbol: str) -> Optional[Dict[str, str]]:
    for a in await _load_assets():
        if a["symbol"] == symbol:
            return a
    return None


# ---------------------------------------------------------------- market / account
async def clock() -> Dict[str, Any]:
    c = await _trading("GET", "/v2/clock", ttl=20)
    return {
        "is_open": c.get("is_open"),
        "next_open": c.get("next_open"),
        "next_close": c.get("next_close"),
    }


async def account() -> Dict[str, Any]:
    a = await _trading("GET", "/v2/account")
    f = lambda k: float(a[k]) if a.get(k) is not None else None
    return {
        "equity": f("equity"),
        "last_equity": f("last_equity"),
        "cash": f("cash"),
        "buying_power": f("buying_power"),
        "portfolio_value": f("portfolio_value"),
        "status": a.get("status"),
        "paper": settings.is_paper,
    }


async def positions() -> List[Dict[str, Any]]:
    rows = await _trading("GET", "/v2/positions")
    f = lambda r, k: float(r[k]) if r.get(k) is not None else None
    return [
        {
            "symbol": r["symbol"],
            "side": r.get("side"),
            "qty": f(r, "qty"),
            "avg_entry_price": f(r, "avg_entry_price"),
            "current_price": f(r, "current_price"),
            "market_value": f(r, "market_value"),
            "unrealized_pl": f(r, "unrealized_pl"),
            "unrealized_plpc": f(r, "unrealized_plpc"),
        }
        for r in rows
    ]


async def orders() -> List[Dict[str, Any]]:
    rows = await _trading("GET", "/v2/orders", {"status": "all", "limit": 50, "direction": "desc"})
    return [
        {
            "id": r["id"],
            "symbol": r["symbol"],
            "side": r.get("side"),
            "type": r.get("type"),
            "qty": r.get("qty"),
            "filled_qty": r.get("filled_qty"),
            "status": r.get("status"),
            "limit_price": r.get("limit_price"),
            "filled_avg_price": r.get("filled_avg_price"),
            "submitted_at": r.get("submitted_at"),
        }
        for r in rows
    ]


async def place_order(symbol: str, qty: float, side: str, otype: str, limit_price: Optional[float]):
    body: Dict[str, Any] = {
        "symbol": symbol,
        "qty": str(qty),
        "side": side,
        "type": otype,
        "time_in_force": "day",
    }
    if otype == "limit":
        body["limit_price"] = str(limit_price)
    return await _trading("POST", "/v2/orders", json=body)


async def cancel_order(order_id: str):
    await _trading("DELETE", f"/v2/orders/{order_id}")


async def close_position(symbol: str):
    return await _trading("DELETE", f"/v2/positions/{symbol}")
