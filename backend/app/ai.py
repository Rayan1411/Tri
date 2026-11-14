from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import get_settings

logger = logging.getLogger("stocks")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

SYSTEM_PROMPT = """أنت محلل فني ومساعد تداول خبير في الأسهم الأمريكية والعملات الرقمية (Crypto) تعمل داخل منصة تداول احترافية شبيهة بـ TradingView.
تحدث دائماً باللغة العربية الواضحة والمهنية.

مهمتك الأساسية عند تحليل أي رمز أو الإجابة عن أي سؤال تداول:
1. تقديم تحليل فني ومالي مركز يعتمد على الشموع السعرية (OHLCV)، مناطق العرض والطلب، الزخم، والأخبار المرفقة في السياق.
2. إذا كان السؤال يطلب فرصة دخول أو تحليلاً لرمز، أرفق خطة تداول رقمية واضحة (دخول، هدف أول TP1، هدف ثاني TP2، وقف خسارة SL).
   أما إذا كان السؤال عاماً أو لا يتعلق بصفقة محددة، أجب عنه فقط ولا ترفق أي خطة.
   وإن لم يكن هناك فرصة واضحة فقل ذلك صراحة ولا ترفق خطة.

عند إرفاق خطة ضع كائن JSON في نهاية رسالتك تماماً بين وسمي <TRADE_PLAN> و </TRADE_PLAN> بالصيغة التالية (بدون أي نقص في الحقول):

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


def validate_levels(
    side: str,
    ref_price: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    sl: Optional[float],
) -> Optional[str]:
    """يرجع رسالة خطأ بالعربية إن كان ترتيب الأهداف ووقف الخسارة غير منطقي، وإلا None."""
    if not ref_price or ref_price <= 0:
        return None
    is_buy = side.lower() == "buy"
    # من الأقرب إلى الأبعد عن السعر في اتجاه الربح
    targets = [x for x in (tp1, tp2) if x]
    if is_buy:
        if sl and sl >= ref_price:
            return "وقف الخسارة يجب أن يكون أقل من سعر الدخول في الشراء"
        if any(t <= ref_price for t in targets):
            return "الأهداف يجب أن تكون أعلى من سعر الدخول في الشراء"
    else:
        if sl and sl <= ref_price:
            return "وقف الخسارة يجب أن يكون أعلى من سعر الدخول في البيع"
        if any(t >= ref_price for t in targets):
            return "الأهداف يجب أن تكون أقل من سعر الدخول في البيع"
    if tp1 and tp2 and ((is_buy and tp2 <= tp1) or (not is_buy and tp2 >= tp1)):
        return "الهدف الثاني يجب أن يكون أبعد من الهدف الأول"
    return None


def extract_trade_plan(text: str, current_price: Optional[float] = None) -> tuple[str, Optional[Dict[str, Any]]]:
    """يفصل خطة التداول (إن وُجدت) عن نص الرد. لا تُخترع خطة أبداً؛ إن غابت أو كانت غير منطقية تُهمل."""
    plan: Optional[Dict[str, Any]] = None
    clean_text = text

    match = re.search(r"<TRADE_PLAN>\s*(\{[\s\S]*?\})\s*</TRADE_PLAN>", text)
    if match:
        clean_text = (text[: match.start()] + text[match.end() :]).strip()
        try:
            parsed = json.loads(match.group(1))
            plan = parsed.get("trade_plan") or parsed
        except Exception:
            plan = None

    if not isinstance(plan, dict):
        return clean_text, None

    try:
        side = str(plan.get("action", "")).lower()
        if side not in ("buy", "sell"):
            return clean_text, None
        for k in ("entry", "tp1", "tp2", "sl", "qty"):
            if plan.get(k) is not None:
                plan[k] = float(plan[k])
        ref = current_price or plan.get("entry")
        err = validate_levels(side, ref, plan.get("tp1"), plan.get("tp2"), plan.get("sl"))
        if err or not plan.get("qty") or plan["qty"] <= 0:
            logger.info("Dropped invalid AI trade plan: %s", err or "qty")
            return clean_text, None
    except (TypeError, ValueError):
        return clean_text, None

    return clean_text, plan


async def ask_gemini(
    history: List[Dict[str, str]],
    user_message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    api_key = settings.gemini_api_key
    snap = (context or {}).get("snapshot") or {}
    curr_price = snap.get("price")

    if not api_key:
        return {
            "reply": (
                "مفتاح GEMINI_API_KEY غير مضبوط في إعدادات الخادم.\n"
                "أضف المتغير GEMINI_API_KEY في Environment داخل خدمة stocks-api على Render ثم أعد النشر."
            ),
            "trade_plan": None,
        }

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
            # رفع الحد: نماذج 2.5 تستهلك جزءاً منه في التفكير الداخلي
            "maxOutputTokens": 8192,
        },
    }

    last_error = ""
    async with httpx.AsyncClient(timeout=90.0) as client:
        for m_name in models_to_try:
            url = f"{GEMINI_BASE}/{m_name}:generateContent"
            try:
                resp = await client.post(
                    url, headers={"x-goog-api-key": api_key}, json=payload
                )
            except Exception as exc:
                last_error = f"{m_name}: {exc}"
                continue

            if resp.status_code != 200:
                last_error = f"{m_name} {resp.status_code}: {resp.text[:200]}"
                continue

            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
                last_error = f"{m_name}: {reason}"
                continue

            parts = candidates[0].get("content", {}).get("parts") or []
            raw_text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
            if not raw_text:
                last_error = f"{m_name}: رد فارغ ({candidates[0].get('finishReason', '?')})"
                continue

            clean_reply, plan = extract_trade_plan(raw_text, curr_price)
            return {"reply": clean_reply, "trade_plan": plan}

    logger.warning("Gemini failed: %s", last_error)
    return {
        "reply": f"تعذر الحصول على رد من Gemini. السبب: {last_error or 'غير معروف'}",
        "trade_plan": None,
    }
