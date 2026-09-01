import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_conn, init_db


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    c = get_conn(db_path)
    init_db(c)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _point_default_db_at_tmp(monkeypatch, db_path):
    import app.db
    monkeypatch.setattr(app.db, "DEFAULT_DB_PATH", db_path)


@pytest.fixture
def client(conn):
    from fastapi.testclient import TestClient

    from app.deps import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: conn
    return TestClient(app)
