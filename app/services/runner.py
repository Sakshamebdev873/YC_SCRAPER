"""Background runs and their event streams.

Domain-agnostic: a run is an id, a status row, and a fan-out of events to
any number of SSE subscribers. The actual work lives in jobs.py.
"""

import queue as queuelib
import threading
import time

from app.db import get_conn, now_iso

_RUNS: dict = {}
_RUNS_LOCK = threading.Lock()


class RunState:
    def __init__(self, run_id: int):
        self.run_id = run_id
        self.stop_requested = False
        self.finished = False
        self._listeners: list = []
        self._lock = threading.Lock()

    def subscribe(self) -> queuelib.Queue:
        q = queuelib.Queue()
        with self._lock:
            self._listeners.append(q)
        return q

    def emit(self, event: dict) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for q in listeners:
            q.put(event)

    def close(self) -> None:
        self.finished = True


def create_run(conn, kind: str, domain: str, total: int) -> int:
    cur = conn.execute(
        """INSERT INTO runs (kind, domain, status, total, completed, started_at)
           VALUES (?, ?, 'running', ?, 0, ?)""",
        (kind, domain, total, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def get_run(conn, run_id: int):
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(conn, limit: int = 10) -> list:
    rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def bump(conn, run_id: int, completed: int) -> None:
    conn.execute("UPDATE runs SET completed = ? WHERE id = ?", (completed, run_id))
    conn.commit()


def finish_run(conn, run_id: int, status: str, error=None) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
        (status, now_iso(), error, run_id),
    )
    conn.commit()


def get_state(run_id: int):
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


def request_stop(run_id: int) -> bool:
    state = get_state(run_id)
    if state is None or state.finished:
        return False
    state.stop_requested = True
    return True


def sleep_interruptible(state: RunState, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if state.stop_requested:
            return
        time.sleep(min(0.5, max(0.0, deadline - time.time())))


def start_run(run_id: int, worker) -> RunState:
    """Runs worker(state, conn) on a daemon thread with its own connection."""
    state = RunState(run_id)
    with _RUNS_LOCK:
        _RUNS[run_id] = state

    def target():
        conn = get_conn()
        status, error = "done", None
        try:
            worker(state, conn)
            if state.stop_requested:
                status = "stopped"
        except Exception as exc:  # noqa: BLE001 — surfaced to the UI, not swallowed
            status, error = "error", str(exc)
            state.emit({"type": "error", "message": str(exc)})
        finally:
            try:
                finish_run(conn, run_id, status, error)
            finally:
                conn.close()
            state.close()
            with _RUNS_LOCK:
                _RUNS.pop(run_id, None)
            state.emit({"type": "done", "status": status, "error": error})

    threading.Thread(target=target, daemon=True).start()
    return state
