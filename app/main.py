"""FastAPI app factory. Binds 127.0.0.1 only — see app.py at the repo root."""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

load_dotenv()

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Serves the built bundle, falling back to index.html for client routes.

    The router owns /contacts, /compose and friends; without this a browser
    refresh or a pasted deep link would 404 because no such file exists on
    disk. API routes are registered before the mount, so they still win.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # A path with an extension is asking for a real file — let a missing
            # bundle 404 honestly rather than handing the browser an HTML page.
            if exc.status_code != 404 or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


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
        app.mount("/", SPAStaticFiles(directory=DIST, html=True), name="frontend")
    return app
