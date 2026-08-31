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
