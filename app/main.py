import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (register tables)
from app.database import Base, engine
from app.routers import auth, bookings, centres, payments

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # simple bootstrap; use Alembic migrations in production
    yield


app = FastAPI(title="EVE Diagnostics API", version="1.0.0", lifespan=lifespan)
for r in (auth.router, centres.router, bookings.router, payments.router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
