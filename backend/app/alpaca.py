from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .config import get_settings

logger = logging.getLogger("stocks")

_ACCOUNT_NUM_FIELDS = ("equity", "last_equity", "cash", "buying_power", "portfolio_value")
_POSITION_NUM_FIELDS = (
    "qty", "avg_entry_price", "current_price", "market_value", "cost_basis",
    "unrealized_pl", "unrealized_plpc", "unrealized_intraday_pl", "change_today",
)


def _to_float(v: Any) -> Any:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return v

KNOWN_CRYPTO_BASES = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "LINK", "LTC",
    "BCH", "DOT", "UNI", "SHIB", "PEPE", "AAVE", "ADA", "MATIC", "POL", "TRUMP"
}


def is_crypto_symbol(symbol: str) -> bool:
    s = symbol.strip().upper()
    if "/" in s or "-USD" in s or "-USDT" in s or "-USDC" in s:
        return True
    # الرمز المجرد (مثل ETH أو SOL أو LTC) قد يكون سهماً أمريكياً، لذا لا يُعدّ عملة رقمية
    # إلا بصيغة صريحة: BTC-USD أو BTC/USD أو BTCUSD
    return s.endswith("USD") and len(s) > 3 and s[:-3] in KNOWN_CRYPTO_BASES


def to_alpaca_crypto(symbol: str) -> str:
    """تحويل الرمز إلى صيغة Alpaca للبيانات مثل BTC/USD"""
    s = symbol.strip().upper().replace("-", "/")
    if "/" not in s:
        if s.endswith("USDT"):
            s = s[:-4] + "/USDT"
        elif s.endswith("USDC"):
            s = s[:-4] + "/USDC"
        elif s.endswith("USD") and len(s) > 3:
            s = s[:-3] + "/USD"
        else:
            s = f"{s}/USD"
    return s


def to_ui_symbol(symbol: str) -> str:
    """توحيد الرمز للواجهة والروابط مثل BTC-USD"""
    s = symbol.strip().upper()
    if is_crypto_symbol(s):
        return to_alpaca_crypto(s).replace("/", "-")
    return s


class AlpacaError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"Alpaca ({status_code}): {message}")
        self.status_code = status_code
        self.message = message


class AlpacaClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = httpx.AsyncClient(timeout=20.0)
        self._assets_cache: List[Dict[str, Any]] = []
        self._assets_cached_at: float = 0.0

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.settings.alpaca_key_id,
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.settings.alpaca_key_id or not self.settings.alpaca_secret_key:
            raise AlpacaError(500, "مفاتيح Alpaca غير مضبوطة في إعدادات الخادم")
        resp = await self._client.request(
            method, url, headers=self._headers, params=params, json=json
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message") or resp.text
            except Exception:
                detail = resp.text
            raise AlpacaError(resp.status_code, detail)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # -------- Account & portfolio --------
    async def get_account(self) -> Dict[str, Any]:
        acc = await self._request("GET", f"{self.settings.alpaca_trading_url}/v2/account")
        for k in _ACCOUNT_NUM_FIELDS:
            if k in acc:
                acc[k] = _to_float(acc[k])
        acc["paper"] = "paper" in self.settings.alpaca_trading_url
        return acc

    async def get_positions(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", f"{self.settings.alpaca_trading_url}/v2/positions")
        for p in data or []:
            for k in _POSITION_NUM_FIELDS:
                if k in p:
                    p[k] = _to_float(p[k])
            sym = p.get("symbol", "")
            if is_crypto_symbol(sym):
                p["ui_symbol"] = to_ui_symbol(sym)
                p["asset_class"] = "crypto"
            else:
                p["ui_symbol"] = sym
                p["asset_class"] = "stock"
        return data or []

    async def get_orders(self, status: str = "all", limit: int = 50) -> List[Dict[str, Any]]:
        return await self._request(
            "GET",
            f"{self.settings.alpaca_trading_url}/v2/orders",
            params={"status": status, "limit": limit, "direction": "desc"},
        )

    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        is_crypto = is_crypto_symbol(symbol)
        order_symbol = to_alpaca_crypto(symbol) if is_crypto else symbol.upper().strip()
        tif = "gtc" if is_crypto else time_in_force

        payload: Dict[str, Any] = {
            "symbol": order_symbol,
            "qty": str(qty),
            "side": side.lower(),
            "type": order_type.lower(),
            "time_in_force": tif,
        }
        if order_type.lower() == "limit" and limit_price is not None:
            payload["limit_price"] = str(round(limit_price, 4 if (is_crypto or limit_price < 1) else 2))

        # أوامر Bracket المدمجة للأسهم إذا لم تكن كسرية
        if not is_crypto and float(qty).is_integer() and take_profit_price and stop_loss_price:
            payload["order_class"] = "bracket"
            payload["take_profit"] = {"limit_price": str(round(take_profit_price, 2))}
            payload["stop_loss"] = {"stop_price": str(round(stop_loss_price, 2))}

        return await self._request(
            "POST", f"{self.settings.alpaca_trading_url}/v2/orders", json=payload
        )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"{self.settings.alpaca_trading_url}/v2/orders/{order_id}")

    async def cancel_order(self, order_id: str) -> None:
        await self._request("DELETE", f"{self.settings.alpaca_trading_url}/v2/orders/{order_id}")

    async def close_position(self, symbol: str) -> Dict[str, Any]:
        clean = to_alpaca_crypto(symbol).replace("/", "") if is_crypto_symbol(symbol) else symbol.upper().strip()
        return await self._request(
            "DELETE", f"{self.settings.alpaca_trading_url}/v2/positions/{clean}"
        )

    async def get_portfolio_history(
        self, period: str = "1M", timeframe: str = "1D"
    ) -> Dict[str, Any]:
        return await self._request(
            "GET",
            f"{self.settings.alpaca_trading_url}/v2/account/portfolio/history",
            params={"period": period, "timeframe": timeframe},
        )

    # -------- Assets & search --------
    async def get_asset(self, symbol: str) -> Dict[str, Any]:
        if is_crypto_symbol(symbol):
            alp_sym = to_alpaca_crypto(symbol)
            ui_sym = to_ui_symbol(symbol)
            return {
                "symbol": ui_sym,
                "name": f"{alp_sym} (عملة رقمية)",
                "exchange": "CRYPTO",
                "class": "crypto",
                "tradable": True,
                "fractionable": True,
            }
        return await self._request(
            "GET", f"{self.settings.alpaca_trading_url}/v2/assets/{symbol.upper()}"
        )

    async def search_assets(self, query: str, asset_class: str = "stock", limit: int = 15) -> List[Dict[str, Any]]:
        q = query.strip().upper()
        if asset_class == "crypto":
            default_cryptos = [
                ("BTC-USD", "Bitcoin / US Dollar - بيتكوين"),
                ("ETH-USD", "Ethereum / US Dollar - إيثيريوم"),
                ("SOL-USD", "Solana / US Dollar - سولانا"),
                ("XRP-USD", "Ripple / US Dollar - ريبل"),
                ("DOGE-USD", "Dogecoin / US Dollar - دوجكوين"),
                ("AVAX-USD", "Avalanche / US Dollar - أفالانش"),
                ("LINK-USD", "Chainlink / US Dollar - تشين لينك"),
                ("LTC-USD", "Litecoin / US Dollar - لايتكوين"),
                ("DOT-USD", "Polkadot / US Dollar - بولكادوت"),
                ("UNI-USD", "Uniswap / US Dollar - يوني سواب"),
                ("SHIB-USD", "Shiba Inu / US Dollar - شيبا"),
                ("PEPE-USD", "Pepe / US Dollar - بيبي"),
                ("AAVE-USD", "Aave / US Dollar - آفي"),
                ("BCH-USD", "Bitcoin Cash / US Dollar"),
            ]
            results = []
            for sym, name in default_cryptos:
                if not q or q in sym or q in name.upper():
                    results.append({"symbol": sym, "name": name, "exchange": "CRYPTO", "asset_class": "crypto"})
            return results[:limit]

        if not q:
            return []
        # قائمة الأصول كبيرة (آلاف) فتُخزَّن ساعة كاملة بدل تحميلها عند كل ضغطة مفتاح
        if not self._assets_cache or time.time() - self._assets_cached_at > 3600:
            self._assets_cache = await self._request(
                "GET",
                f"{self.settings.alpaca_trading_url}/v2/assets",
                params={"status": "active", "asset_class": "us_equity"},
            ) or []
            self._assets_cached_at = time.time()
        assets = self._assets_cache
        exact = []
        prefix = []
        contains = []
        for a in assets:
            if not a.get("tradable"):
                continue
            sym = a.get("symbol", "")
            name = (a.get("name") or "").upper()
            item = {
                "symbol": sym,
                "name": a.get("name") or sym,
                "exchange": a.get("exchange") or "",
                "asset_class": "stock",
            }
            if sym == q:
                exact.append(item)
            elif sym.startswith(q):
                prefix.append(item)
            elif q in sym or q in name:
                contains.append(item)
            if len(exact) + len(prefix) >= limit:
                break
        return (exact + prefix + contains)[:limit]

    # -------- Market data (Stocks & Crypto) --------
    async def get_snapshots(self, symbols: List[str]) -> Dict[str, Any]:
        cleaned = [s.strip().upper() for s in symbols if s.strip()]
        if not cleaned:
            return {}

        stock_syms = [s for s in cleaned if not is_crypto_symbol(s)]
        crypto_syms = [s for s in cleaned if is_crypto_symbol(s)]
        result: Dict[str, Any] = {}

        if stock_syms:
            try:
                data = await self._request(
                    "GET",
                    f"{self.settings.alpaca_data_url}/v2/stocks/snapshots",
                    params={"symbols": ",".join(stock_syms), "feed": self.settings.alpaca_data_feed},
                )
                for sym, snap in (data or {}).items():
                    result[sym] = self._parse_Snapshot(sym, snap, "stock")
            except Exception as exc:
                logger.warning("Stock snapshots failed: %s", exc)

        if crypto_syms:
            alp_map = {to_alpaca_crypto(s): to_ui_symbol(s) for s in crypto_syms}
            try:
                data = await self._request(
                    "GET",
                    f"{self.settings.alpaca_data_url}/v1beta3/crypto/us/snapshots",
                    params={"symbols": ",".join(alp_map.keys())},
                )
                snapshots = (data or {}).get("snapshots", {})
                for alp_sym, snap in snapshots.items():
                    ui_sym = alp_map.get(alp_sym, alp_sym.replace("/", "-"))
                    result[ui_sym] = self._parse_Snapshot(ui_sym, snap, "crypto")
            except Exception as exc:
                logger.warning("Crypto snapshots failed: %s", exc)

        return result

    def _parse_Snapshot(self, symbol: str, snap: Dict[str, Any], asset_class: str) -> Dict[str, Any]:
        trade = snap.get("latestTrade") or {}
        quote = snap.get("latestQuote") or {}
        daily = snap.get("dailyBar") or {}
        prev = snap.get("prevDailyBar") or {}
        price = trade.get("p") or daily.get("c") or prev.get("c")
        prev_close = prev.get("c")
        change = (price - prev_close) if (price is not None and prev_close) else None
        change_pct = (change / prev_close * 100.0) if (change is not None and prev_close) else None
        return {
            "symbol": symbol,
            "asset_class": asset_class,
            "price": price,
            "open": daily.get("o"),
            "high": daily.get("h"),
            "low": daily.get("l"),
            "close": daily.get("c"),
            "volume": daily.get("v"),
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "bid": quote.get("bp"),
            "ask": quote.get("ap"),
            "updated_at": trade.get("t") or daily.get("t"),
        }

    async def get_bars(self, symbol: str, range_key: str = "1M") -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        rk = range_key.upper()
        mapping = {
            "1M_TF": ( timedelta(days=2), "1Min" ),
            "5M_TF": ( timedelta(days=5), "5Min" ),
            "15M_TF": ( timedelta(days=10), "15Min" ),
            "1H_TF": ( timedelta(days=30), "1Hour" ),
            "4H_TF": ( timedelta(days=60), "4Hour" ),
            "1D": ( timedelta(days=5), "15Min" ),
            "1W": ( timedelta(days=14), "1Hour" ),
            "1M": ( timedelta(days=60), "1Day" ),
            "3M": ( timedelta(days=100), "1Day" ),
            "6M": ( timedelta(days=200), "1Day" ),
            "1Y": ( timedelta(days=370), "1Day" ),
            "5Y": ( timedelta(days=365 * 5), "1Week" ),
        }
        delta, timeframe = mapping.get(rk, (timedelta(days=60), "1Day"))
        start = (now - delta).isoformat()

        if is_crypto_symbol(symbol):
            alp_sym = to_alpaca_crypto(symbol)
            data = await self._request(
                "GET",
                f"{self.settings.alpaca_data_url}/v1beta3/crypto/us/bars",
                params={
                    "symbols": alp_sym,
                    "timeframe": timeframe,
                    "start": start,
                    "limit": 1000,
                    "sort": "desc",
                },
            )
            bars = list(reversed((data or {}).get("bars", {}).get(alp_sym, [])))
        else:
            data = await self._request(
                "GET",
                f"{self.settings.alpaca_data_url}/v2/stocks/{symbol.upper()}/bars",
                params={
                    "timeframe": timeframe,
                    "start": start,
                    "limit": 1000,
                    "sort": "desc",
                    "adjustment": "raw",
                    "feed": self.settings.alpaca_data_feed,
                },
            )
            bars = list(reversed((data or {}).get("bars") or []))

        return [
            {
                "t": b.get("t"),
                "o": b.get("o"),
                "h": b.get("h"),
                "l": b.get("l"),
                "c": b.get("c"),
                "v": b.get("v"),
            }
            for b in bars
        ]

    async def get_news(self, symbol: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"limit": limit}
        if symbol:
            params["symbols"] = to_alpaca_crypto(symbol).replace("/", "") if is_crypto_symbol(symbol) else symbol.upper()
        try:
            data = await self._request(
                "GET", f"{self.settings.alpaca_data_url}/v1beta1/news", params=params
            )
        except Exception:
            return []
        items = (data or {}).get("news") or []
        return [
            {
                "id": n.get("id"),
                "headline": n.get("headline"),
                "summary": n.get("summary"),
                "source": n.get("source"),
                "url": n.get("url"),
                "created_at": n.get("created_at"),
                "symbols": n.get("symbols") or [],
            }
            for n in items
        ]

    async def get_movers(self, market_type: str = "stocks", top: int = 8) -> Dict[str, List[Dict[str, Any]]]:
        m_type = "crypto" if market_type == "crypto" else "stocks"
        try:
            data = await self._request(
                "GET",
                f"{self.settings.alpaca_data_url}/v1beta1/screener/{m_type}/movers",
                params={"top": top},
            )
            gainers = data.get("gainers") or []
            losers = data.get("losers") or []
            for item in gainers + losers:
                if m_type == "crypto" and item.get("symbol"):
                    item["symbol"] = to_ui_symbol(item["symbol"])
            return {"gainers": gainers, "losers": losers}
        except Exception:
            return {"gainers": [], "losers": []}


alpaca = AlpacaClient()
