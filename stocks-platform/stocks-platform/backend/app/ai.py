"""AI analysis chat. Add ANTHROPIC_API_KEY (and optionally AI_MODEL) to enable it."""
from typing import Any, Dict, List, Optional

import httpx

from . import alpaca
from .config import settings

SYSTEM_PROMPT = """أنت محلل أسهم أمريكية يعمل داخل منصة شخصية لمستخدم واحد. تجيب دائمًا بالعربية، بإيجاز ووضوح.
- اعتمد على البيانات المرفقة في السياق (السعر، الأداء، الأخبار) ولا تخترع أرقامًا غير موجودة فيها.
- إن لم تكفِ البيانات لقول شيء بثقة، قل ذلك صراحة.
- قدّم قراءة متوازنة: نقاط القوة، المخاطر، ومستويات أو سيناريوهات يمكن مراقبتها.
- هذه تحليلات تعليمية وليست توصية مالية؛ اذكر ذلك بجملة قصيرة فقط عند الحاجة، لا في كل رد.
- اجعل الرد في فقرات قصيرة أو نقاط مختصرة، بدون إطالة."""


def configured() -> bool:
    return bool(settings.anthropic_key)


def _pct(a: float, b: float) -> Optional[float]:
    return (a / b - 1) * 100 if b else None


async def build_context(symbol: str) -> str:
    parts: List[str] = [f"الرمز: {symbol}"]
    try:
        info = await alpaca.asset(symbol)
        if info:
            parts.append(f"الشركة: {info['name']} ({info['exchange']})")
    except Exception:
        pass

    try:
        q = (await alpaca.quotes([symbol])).get(symbol)
        if q:
            parts.append(
                "آخر سعر: {price} | الإغلاق السابق: {prev_close} | التغير: {change_pct}% | "
                "افتتاح اليوم: {open} | أعلى: {high} | أدنى: {low} | حجم: {volume}".format(
                    **{k: ("—" if v is None else (round(v, 2) if isinstance(v, float) else v)) for k, v in q.items()}
                )
            )
    except Exception:
        pass

    try:
        daily = await alpaca.bars(symbol, "1d")
        daily = daily[-60:]
        if len(daily) >= 5:
            closes = [b["close"] for b in daily]
            last = closes[-1]
            lines = []
            for n in (5, 20, 60):
                if len(closes) > n:
                    p = _pct(last, closes[-n - 1])
                    lines.append(f"آخر {n} يوم تداول: {p:+.1f}%")
            hi = max(b["high"] for b in daily)
            lo = min(b["low"] for b in daily)
            vols = [b["volume"] for b in daily[-20:]]
            avg_vol = sum(vols) / len(vols) if vols else 0
            parts.append("الأداء: " + " | ".join(lines))
            parts.append(f"أعلى/أدنى آخر {len(daily)} يوم: {hi:.2f} / {lo:.2f} | متوسط حجم 20 يوم: {avg_vol:,.0f}")
            tail = ", ".join(f"{b['close']:.2f}" for b in daily[-10:])
            parts.append(f"آخر 10 إغلاقات: {tail}")
    except Exception:
        pass

    try:
        items = await alpaca.news(symbol, 6)
        if items:
            parts.append("آخر الأخبار:")
            for n in items:
                parts.append(f"- {n['headline']} ({n.get('source') or ''}, {str(n.get('created_at'))[:10]})")
    except Exception:
        pass

    return "\n".join(parts)


async def chat(symbol: Optional[str], messages: List[Dict[str, str]]) -> str:
    system = SYSTEM_PROMPT
    if symbol:
        system += "\n\nسياق السهم الحالي:\n" + await build_context(symbol)

    clean = [
        {"role": m["role"], "content": m["content"][:2000]}
        for m in messages[-12:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    if not clean:
        return "اكتب سؤالك أولًا."

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": clean,
                },
            )
    except httpx.HTTPError as e:
        return f"تعذّر الاتصال بخدمة الذكاء الاصطناعي ({e.__class__.__name__})."

    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            msg = r.text[:200]
        return f"خطأ من خدمة الذكاء الاصطناعي: {msg}"

    blocks: List[Dict[str, Any]] = r.json().get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    return text or "لم أحصل على رد."
