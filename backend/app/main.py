from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .alpaca import AlpacaError, alpaca, is_crypto_symbol
from .config import get_settings
from .db import PriceAlert, SessionLocal, TradePlan, init_db, utcnow
from .routes import router

logger = logging.getLogger("stocks")
logging.basicConfig(level=logging.INFO)


async def _check_alerts_and_plans_once() -> None:
    with SessionLocal() as db:
        active_alerts = db.query(PriceAlert).filter(PriceAlert.active.is_(True)).all()
        active_plans = db.query(TradePlan).filter(TradePlan.status == "active").all()

        symbols = sorted(
            {a.symbol for a in active_alerts} | {p.symbol for p in active_plans}
        )
        if not symbols:
            return

        try:
            snaps = await alpaca.get_snapshots(symbols)
        except Exception as exc:
            logger.warning("Monitor snapshot fetch failed: %s", exc)
            return

        now = utcnow()

        # 1. فحص التنبيهات السعرية
        for alert in active_alerts:
            snap = snaps.get(alert.symbol) or {}
            price = snap.get("price")
            if price is None:
                continue
            hit = (alert.direction == "above" and price >= alert.target_price) or (
                alert.direction == "below" and price <= alert.target_price
            )
            if hit:
                alert.active = False
                alert.triggered_at = now
                alert.triggered_price = float(price)

        # 2. فحص وتنفيذ أهداف ووقف خسارة البوت الذكي (TP1 / TP2 / SL)
        for plan in active_plans:
            # لا نبيع/نغلق شيئاً قبل التأكد أن أمر الدخول نُفِّذ فعلاً (وإلا ينتج مركز بيع على المكشوف)
            if not plan.entry_filled:
                if not plan.entry_order_id:
                    plan.entry_filled = True
                else:
                    try:
                        order = await alpaca.get_order(plan.entry_order_id)
                    except AlpacaError as exc:
                        logger.warning("Entry order check failed for %s: %s", plan.symbol, exc)
                        continue
                    st = (order or {}).get("status")
                    if st == "filled":
                        plan.entry_filled = True
                        filled_qty = float((order or {}).get("filled_qty") or plan.qty)
                        plan.qty = filled_qty
                        plan.remaining_qty = filled_qty
                        avg = (order or {}).get("filled_avg_price")
                        if avg:
                            plan.entry_price = float(avg)
                        plan.notes = "تم تنفيذ أمر الدخول، المراقبة فعّالة"
                    elif st in ("canceled", "expired", "rejected", "done_for_day"):
                        plan.status = "canceled"
                        plan.closed_at = now
                        plan.notes = f"لم يُنفَّذ أمر الدخول ({st}) فأُلغيت الخطة"
                        continue
                    else:
                        continue  # ما زال الأمر معلقاً (أو منفذاً جزئياً)

            snap = snaps.get(plan.symbol) or {}
            price = snap.get("price")
            if price is None or plan.remaining_qty <= 0:
                continue

            p = float(price)
            is_buy = plan.side.lower() == "buy"
            close_side = "sell" if is_buy else "buy"
            is_crypto = is_crypto_symbol(plan.symbol)
            tif = "gtc" if is_crypto else "day"

            # فحص وقف الخسارة (SL)
            sl_hit = False
            if plan.sl_price:
                sl_hit = (is_buy and p <= plan.sl_price) or (not is_buy and p >= plan.sl_price)

            if sl_hit:
                try:
                    await alpaca.submit_order(
                        symbol=plan.symbol,
                        qty=plan.remaining_qty,
                        side=close_side,
                        order_type="market",
                        time_in_force=tif,
                    )
                    plan.remaining_qty = 0.0
                    plan.status = "stopped"
                    plan.closed_at = now
                    plan.notes = f"تم تفعيل وقف الخسارة آلياً عند السعر {p}"
                except Exception as exc:
                    logger.warning("SL order failed for %s: %s", plan.symbol, exc)
                continue

            # فحص الهدف الثاني (TP2)
            tp2_hit = False
            if plan.tp2_price:
                tp2_hit = (is_buy and p >= plan.tp2_price) or (not is_buy and p <= plan.tp2_price)

            if tp2_hit:
                try:
                    await alpaca.submit_order(
                        symbol=plan.symbol,
                        qty=plan.remaining_qty,
                        side=close_side,
                        order_type="market",
                        time_in_force=tif,
                    )
                    plan.remaining_qty = 0.0
                    plan.tp1_hit = True
                    plan.status = "completed"
                    plan.closed_at = now
                    plan.notes = f"تحقق الهدف الثاني (TP2) آلياً عند السعر {p}"
                except Exception as exc:
                    logger.warning("TP2 order failed for %s: %s", plan.symbol, exc)
                continue

            # فحص الهدف الأول (TP1) - جني ربح نصف الكمية
            if plan.tp1_price and not plan.tp1_hit:
                tp1_cond = (is_buy and p >= plan.tp1_price) or (not is_buy and p <= plan.tp1_price)
                if tp1_cond:
                    half_qty = (
                        round(plan.remaining_qty / 2.0, 4)
                        if is_crypto
                        else max(1.0, float(int(plan.remaining_qty // 2)))
                    )
                    if half_qty >= plan.remaining_qty:
                        half_qty = plan.remaining_qty
                    try:
                        await alpaca.submit_order(
                            symbol=plan.symbol,
                            qty=half_qty,
                            side=close_side,
                            order_type="market",
                            time_in_force=tif,
                        )
                        plan.tp1_hit = True
                        plan.remaining_qty = round(plan.remaining_qty - half_qty, 6)
                        if plan.remaining_qty <= 0 or not plan.tp2_price:
                            plan.status = "completed"
                            plan.closed_at = now
                            plan.notes = f"تحقق الهدف الأول (TP1) وأغلقت الصفقة عند {p}"
                        else:
                            plan.notes = f"تحقق الهدف الأول (TP1) عند {p} وبانتظار الهدف الثاني"
                    except Exception as exc:
                        logger.warning("TP1 order failed for %s: %s", plan.symbol, exc)

        db.commit()


async def _alert_loop() -> None:
    interval = max(15, get_settings().alert_check_interval_seconds)
    while True:
        try:
            await _check_alerts_and_plans_once()
        except Exception as exc:
            logger.warning("Monitor loop error: %s", exc)
        await asyncio.sleep(interval)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    task = asyncio.create_task(_alert_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Trind AI Trading Platform API", lifespan=lifespan)
    origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()
