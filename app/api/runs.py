import json
import os
import queue as queuelib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.deps import get_db
from app.services import jobs
from app.services.drafts import get_draft
from app.services.runner import (
    create_run, get_run, get_state, list_runs, request_stop, start_run,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Indirection so tests can inject fake workers.
generate_worker_factory = jobs.make_generate_worker
send_worker_factory = jobs.make_send_worker
scrape_worker_factory = jobs.make_scrape_worker


class GenerateBody(BaseModel):
    contact_ids: list[int]
    domain: str = "job"
    round: int = 0


class SendBody(BaseModel):
    draft_ids: list[int]
    test_mode: bool = True
    delay: float = jobs.DEFAULT_SEND_DELAY
    test_email: str = ""


class ScrapeBody(BaseModel):
    batch: str = ""
    max: int = 20


@router.get("/config")
def config():
    return {
        "test_email": os.environ.get("TEST_EMAIL", "").strip(),
        "default_delay": jobs.DEFAULT_SEND_DELAY,
        "gmail_configured": bool(os.environ.get("GMAIL_EMAIL", "").strip()
                                 and os.environ.get("GMAIL_PASSWORD", "").strip()),
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
    }


@router.get("")
def read_runs(limit: int = 10, conn=Depends(get_db)):
    return list_runs(conn, limit=limit)


@router.get("/{run_id}")
def read_run(run_id: int, conn=Depends(get_db)):
    run = get_run(conn, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/generate")
def start_generate(body: GenerateBody, conn=Depends(get_db)):
    if not body.contact_ids:
        raise HTTPException(status_code=400, detail="No contacts selected")
    if body.round not in (0, 1, 2, 3):
        raise HTTPException(status_code=400, detail="round must be 0, 1, 2 or 3")
    run_id = create_run(conn, "generate", body.domain, len(body.contact_ids))
    start_run(run_id, generate_worker_factory(body.contact_ids, body.domain, body.round))
    return {"run_id": run_id}


@router.post("/send")
def start_send(body: SendBody, conn=Depends(get_db)):
    if not body.draft_ids:
        raise HTTPException(status_code=400, detail="No drafts selected")
    for draft_id in body.draft_ids:
        draft = get_draft(conn, draft_id)
        if draft is None:
            raise HTTPException(status_code=400, detail=f"Draft {draft_id} not found")
        if draft["status"] != "approved":
            raise HTTPException(
                status_code=400,
                detail=f"Draft {draft_id} is '{draft['status']}' — only approved drafts can be sent",
            )

    test_addr = (body.test_email or os.environ.get("TEST_EMAIL", "")).strip()
    if body.test_mode and not test_addr:
        raise HTTPException(
            status_code=400,
            detail="Test mode needs an address — set TEST_EMAIL in .env or pass test_email.",
        )

    domain = get_draft(conn, body.draft_ids[0])["domain"]
    run_id = create_run(conn, "send", domain, len(body.draft_ids))
    start_run(run_id, send_worker_factory(body.draft_ids, body.test_mode,
                                          body.delay, test_addr))
    return {
        "run_id": run_id,
        "count": len(body.draft_ids),
        "test_mode": body.test_mode,
        "to": test_addr if body.test_mode else "real recipients",
    }


@router.post("/scrape")
def start_scrape(body: ScrapeBody, conn=Depends(get_db)):
    run_id = create_run(conn, "scrape", "job", body.max)
    start_run(run_id, scrape_worker_factory(body.batch, body.max))
    return {"run_id": run_id}


@router.post("/{run_id}/stop")
def stop(run_id: int):
    return {"stopped": request_stop(run_id)}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("/{run_id}/events")
def events(run_id: int, conn=Depends(get_db)):
    run = get_run(conn, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    state = get_state(run_id)

    def stream():
        yield _sse({"type": "snapshot", "run": run})
        if state is None or state.finished:
            yield _sse({"type": "done", "status": run["status"], "error": run["error"]})
            return
        listener = state.subscribe()
        while True:
            try:
                event = listener.get(timeout=1.0)
            except queuelib.Empty:
                yield ": keepalive\n\n"
                continue
            yield _sse(event)
            if event.get("type") == "done":
                return

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
