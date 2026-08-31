import time

from app.db import get_conn, init_db
from app.services.runner import (
    create_run, get_run, get_state, list_runs, request_stop, start_run,
)


def drain(q, timeout=5.0):
    events, deadline = [], time.time() + timeout
    while time.time() < deadline:
        try:
            event = q.get(timeout=0.2)
        except Exception:
            continue
        events.append(event)
        if event.get("type") == "done":
            break
    return events


def test_run_completes_and_emits_done(conn, db_path):
    run_id = create_run(conn, "generate", "job", 2)

    def worker(state, worker_conn):
        for i in range(2):
            state.emit({"type": "item", "index": i})

    state = start_run(run_id, worker)
    q = state.subscribe()
    events = drain(q)
    assert events[-1]["type"] == "done"
    time.sleep(0.2)
    assert get_run(conn, run_id)["status"] == "done"


def test_worker_exception_marks_run_error(conn):
    run_id = create_run(conn, "send", "job", 1)

    def worker(state, worker_conn):
        raise RuntimeError("boom")

    state = start_run(run_id, worker)
    drain(state.subscribe())
    time.sleep(0.2)
    row = get_run(conn, run_id)
    assert row["status"] == "error"
    assert "boom" in row["error"]


def test_stop_is_observed_by_the_worker(conn):
    run_id = create_run(conn, "send", "job", 100)
    seen = []

    def worker(state, worker_conn):
        for i in range(100):
            if state.stop_requested:
                break
            seen.append(i)
            time.sleep(0.02)

    state = start_run(run_id, worker)
    time.sleep(0.1)
    assert request_stop(run_id) is True
    drain(state.subscribe(), timeout=3)
    time.sleep(0.2)
    assert len(seen) < 100
    assert get_run(conn, run_id)["status"] == "stopped"


def test_get_state_and_list_runs(conn):
    run_id = create_run(conn, "scrape", "job", 0)
    assert get_state(run_id) is None
    assert list_runs(conn)[0]["id"] == run_id


def test_request_stop_unknown_run():
    assert request_stop(123456) is False
