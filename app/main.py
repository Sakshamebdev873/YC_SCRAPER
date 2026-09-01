"""FastAPI app factory. Binds 127.0.0.1 only — see app.py at the repo root."""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app() -> FastAPI:
    from app.api import contacts, drafts, followups, queue, runs, stats, templates

    app = FastAPI(title="Cold Email Applier")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(stats.router)
    app.include_router(contacts.router)
    app.include_router(templates.router)
    app.include_router(queue.router)
    app.include_router(drafts.router)
    app.include_router(followups.router)
    app.include_router(runs.router)

    if DIST.exists():
        app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
    return app
