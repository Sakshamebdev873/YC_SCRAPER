from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_db
from app.services import personalize
from app.services.drafts import (
    DRAFT_STATUSES, get_draft, list_drafts, update_draft, upsert_draft,
)
from app.services.templates import get_templates

router = APIRouter(prefix="/api/drafts", tags=["drafts"])

# Indirection so tests can inject a fake Gemini client.
regenerate_client_factory = personalize.gemini_client


class DraftPatch(BaseModel):
    subject: str | None = None
    body: str | None = None
    status: str | None = None


class BulkStatus(BaseModel):
    draft_ids: list[int]
    status: str


@router.get("")
def read_drafts(status: str = "", round: int | None = None, domain: str = "",
                limit: int = 0, conn=Depends(get_db)):
    return list_drafts(conn, status=status or None, round_num=round,
                       domain=domain or None, limit=limit)


@router.patch("/{draft_id}")
def patch_draft(draft_id: int, patch: DraftPatch, conn=Depends(get_db)):
    if patch.status is not None and patch.status not in DRAFT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status '{patch.status}'")
    try:
        return update_draft(conn, draft_id, subject=patch.subject,
                            body=patch.body, status=patch.status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bulk-status")
def bulk_status(body: BulkStatus, conn=Depends(get_db)):
    if body.status not in DRAFT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status '{body.status}'")
    updated = 0
    for draft_id in body.draft_ids:
        try:
            update_draft(conn, draft_id, status=body.status)
            updated += 1
        except ValueError:
            continue
    return {"updated": updated}


@router.post("/{draft_id}/regenerate")
def regenerate(draft_id: int, conn=Depends(get_db)):
    draft = get_draft(conn, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    contact = dict(conn.execute(
        "SELECT * FROM contacts WHERE id = ?", (draft["contact_id"],)
    ).fetchone())
    templates = get_templates(conn, draft["domain"])
    subject = personalize.render_subject(templates, contact, draft["round"])
    try:
        if draft["round"] == 0:
            body = personalize.generate_body(regenerate_client_factory(), templates, contact)
        else:
            body = personalize.render_followup_body(templates, contact, draft["round"])
    except Exception as e:  # noqa: BLE001 — surfaced to the card
        raise HTTPException(status_code=502, detail=f"Gemini error: {e}")

    new_id = upsert_draft(conn, draft["contact_id"], draft["domain"],
                          draft["round"], subject, body)
    return get_draft(conn, new_id)
