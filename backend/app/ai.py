from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import get_settings

SYSTEM_PROMPT = """أنت محلل فني ومساعد تداول خبير في الأسهم الأمريكية والعملات الرقمية (Crypto) تعمل داخل منصة تداول احترافية شبيهة بـ TradingView.
تحدث دائماً باللغة العربية الواضحة والمهنية.

مهمتك الأساسية عند تحليل أي رمز أو الإجابة عن أي سؤال تداول:
1. تقديم تحليل فني ومالي مركز يعتمد على الشموع السعرية (OHLCV)، مناطق العرض والطلب، الزخم، والأخبار المرفقة في السياق.
2. فرض خطة تداول رقمية واضحة ومحددة (دخول، هدف أول TP1، هدف ثاني TP2، وقف خسارة SL) بعد التحليل مباشرة لكي يعتمدها المستخدم بضغطة زر.

يجب عليك دائماً وفي كل رد إرفاق كائن JSON في نهاية رسالتك تماماً بين وسمي <TRADE_PLAN> و </TRADE_PLAN> بالصيغة الإلزامية التالية (بدون أي نقص في الحقول):

<TRADE_PLAN>
{
  "symbol": "AAPL",
  "action": "BUY",
  "order_type": "market",
  "entry": 100.50,
  "tp1": 105.00,
  "tp2": 110.00,
  "sl": 97.50,
  "qty": 1,
  "confidence": "مرتفعة",
  "summary": "ملخص سبب الصفقة في سطر واحد"
}
</TRADE_PLAN>

قواعد حساب الأرقام:
- في حالة الشراء (BUY): يجب أن يكون tp2 > tp1 > entry > sl.
- في حالة البيع (SELL): يجب أن يكون sl > entry > tp1 > tp2.
- التزم بالأرقام الحقيقية القريبة من السعر الحالي المرفق في السياق."""


def _format_context(context: Dict[str, Any]) -> str:
    parts: List[str] = []
    sym = context.get("symbol")
    snap = context.get("snapshot") or {}
    if sym:
        parts.append(f"الرمز الحالي المفتوح على الشارت: {sym} (الفئة: {snap.get('asset_class', 'stock')})")
    if snap:
        parts.append(
            "بيانات السعر اللحظية:\n"
            + json.dumps(
                {
                    "price": snap.get("price"),
                    "change": snap.get("change"),
                    "change_pct": snap.get("change_pct"),
                    "open": snap.get("open"),
                    "high": snap.get("high"),
                    "low": snap.get("low"),
                    "prev_close": snap.get("prev_close"),
                    "volume": snap.get("volume"),
                },
                ensure_ascii=False,
            )
        )
    bars = context.get("recent_bars") or []
    if bars:
        parts.append(
            f"آخر {len(bars)} شمعة سعرية (OHLCV) للتحليل الفني واستخراج الدعوم والمقاومات:\n"
            + json.dumps(bars[-25:], ensure_ascii=False)
        )
    news = context.get("news") or []
    if news:
        headlines = [
            f"- {n.get('headline')} ({n.get('source')}, {n.get('created_at')})"
            for n in news[:6]
        ]
        parts.append("آخر الأخبار:\n" + "\n".join(headlines))
    account = context.get("account")
    if account:
        parts.append(
            "ملخص المحفظة:\n"
            + json.dumps(
                {
                    "equity": account.get("equity"),
                    "cash": account.get("cash"),
                    "buying_power": account.get("buying_power"),
                },
                ensure_ascii=False,
            )
        )
    positions = context.get("positions")
    if positions:
        slim = [
            {
                "symbol": p.get("ui_symbol") or p.get("symbol"),
                "qty": p.get("qty"),
                "avg_entry_price": p.get("avg_entry_price"),
                "current_price": p.get("current_price"),
                "unrealized_pl": p.get("unrealized_pl"),
                "unrealized_plpc": p.get("unrealized_plpc"),
            }
            for p in positions[:15]
        ]
        parts.append("المراكز المفتوحة حالياً:\n" + json.dumps(slim, ensure_ascii=False))
    return "\n\n".join(parts)


def extract_trade_plan(
    text: str,
    default_symbol: Optional[str] = None,
    current_price: Optional[float] = None,
) -> tuple[str, Optional[Dict[str, Any]]]:
    plan: Optional[Dict[str, Any]] = None
    clean_text = text

    match = re.search(r"<TRADE_PLAN>\s*(\{[\s\S]*?\})\s*</TRADE_PLAN>", text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            plan = parsed.get("trade_plan") or parsed
            clean_text = (text[: match.start()] + text[match.end() :]).strip()
        except Exception:
            pass

    if not plan:
        match_brace = re.search(r'(\{\s*"(?:trade_plan|symbol|action)"[\s\S]*?\})', text)
        if match_brace:
            try:
                parsed = json.loads(match_brace.group(1))
                plan = parsed.get("trade_plan") or parsed
                clean_text = (text[: match_brace.start()] + text[match_brace.end() :]).strip()
            except Exception:
                pass

    if not plan and current_price and default_symbol:
        p = float(current_price)
        is_crypto = "-USD" in default_symbol or "/" in default_symbol
        decimals = 4 if (is_crypto and p < 10) else 2
        plan = {
            "symbol": default_symbol,
            "action": "BUY",
            "order_type": "market",
            "entry": round(p, decimals),
            "tp1": round(p * 1.025, decimals),
            "tp2": round(p * 1.05, decimals),
            "sl": round(p * 0.985, decimals),
            "qty": 0.01 if (is_crypto and p > 1000) else 1,
            "confidence": "متوسطة",
            "summary": "خطة تداول قياسية مبنية على السعر الحالي ونسبة عائد إلى مخاطرة 2:1",
        }

    return clean_text, plan


async def ask_claude(
    history: List[Dict[str, str]],
    user_message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.gemini_api_key or settings.anthropic_api_key
    default_sym = (context or {}).get("symbol") or "AAPL"
    snap = (context or {}).get("snapshot") or {}
    curr_price = snap.get("price")

    if not api_key:
        msg = (
            "مفتاح GEMINI_API_KEY غير مضبوط حالياً في إعدادات الخادم على Render.\n"
            "لتفعيل التحليل الذكي، أضف متغير GEMINI_API_KEY في تبويب Environment داخل خدمة stocks-api.\n\n"
            "ومع ذلك، تم تجهيز بطاقة تداول أولية بناءً على السعر الحالي لتجربة أزرار التنفيذ والأهداف:"
        )
        _, fallback_plan = extract_trade_plan("", default_sym, curr_price)
        return {"reply": msg, "trade_plan": fallback_plan}

    ctx_block = _format_context(context or {})
    contents: List[Dict[str, Any]] = []

    for m in history[-10:]:
        role = "user" if m.get("role") == "user" else "model"
        text_val = (m.get("content") or "").strip()
        if text_val:
            contents.append({"role": role, "parts": [{"text": text_val}]})

    final_user = user_message
    if ctx_block:
        final_user = f"[سياق السوق والشارت اللحظي]\n{ctx_block}\n\n[طلب المتداول]\n{user_message}"
    contents.append({"role": "user", "parts": [{"text": final_user}]})

    model_name = (settings.gemini_model or "gemini-2.5-flash").strip()
    if model_name.startswith("models/"):
        model_name = model_name[len("models/") :]

    models_to_try = [model_name]
    for fallback in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }

    last_error = ""
    async with httpx.AsyncClient(timeout=60.0) as client:
        for m_name in models_to_try:
            url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){m_name}:generateContent"
            try:
                resp = await client.post(url, params={"key": api_key}, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts") or []
                        raw_text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
                        if raw_text:
                            clean_reply, plan = extract_trade_plan(raw_text, default_sym, curr_price)
                            return {"reply": clean_reply, "trade_plan": plan}
                else:
                    last_error = f"{resp.status_code}: {resp.text[:200]}"
            except Exception as exc:
                last_error = str(exc)

    _, fallback_plan = extract_trade_plan("", default_sym, curr_price)
    return {
        "reply": f"تعذر الوصول إلى Gemini API ({last_error}). تم توليد خطة رقمية افتراضية بناءً على السعر الحالي:",
        "trade_plan": fallback_plan,
    }
