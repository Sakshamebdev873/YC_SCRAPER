"""FastAPI dependencies. Tests override get_db with their temp connection."""

from app.db import get_conn

_conn = None


def get_db():
    global _conn
    if _conn is None:
        _conn = get_conn()
    return _conn
