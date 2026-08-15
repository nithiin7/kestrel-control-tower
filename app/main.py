"""FastAPI entry point. Run: uvicorn app.main:app --port 8000"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.routers import ask, coldchain, meta, money, price_position, service
from config.settings import FRONTEND_PORT

app = FastAPI(title="Kestrel Provisions Control Tower API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{FRONTEND_PORT}"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(service.router)
app.include_router(coldchain.router)
app.include_router(money.router)
app.include_router(price_position.router)
app.include_router(ask.router)
