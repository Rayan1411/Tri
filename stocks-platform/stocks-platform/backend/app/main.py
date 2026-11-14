import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from . import alpaca, auth, routes
from .db import Alert, SessionLocal, init_db, now_utc

log = logging.getLogger("stocks")


async def alert_loop() -> None:
    """Every 30s: check active price alerts and mark the ones that were hit."""
    while True:
        await asyncio.sleep(30)
        try:
            with SessionLocal() as db:
                active = db.scalars(select(Alert).where(Alert.active.is_(True))).all()
                if not active:
                    continue
                quotes = await alpaca.quotes(sorted({a.symbol for a in active}))
                changed = False
                for a in active:
                    price = (quotes.get(a.symbol) or {}).get("price")
                    if price is None:
                        continue
                    hit = price >= a.price if a.direction == "above" else price <= a.price
                    if hit:
                        a.active = False
                        a.triggered_at = now_utc()
                        a.triggered_price = price
                        changed = True
                if changed:
                    db.commit()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # keep the loop alive
            log.warning("alert loop error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(alert_loop())
    yield
    task.cancel()


app = FastAPI(title="stocks-api", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(routes.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}
