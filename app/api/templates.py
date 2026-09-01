from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_db
from app.services import personalize
from app.services.templates import (
    DOMAIN_KEYS, TEMPLATE_KEYS, get_templates, list_versions,
    restore_version, save_template,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])

# Indirection so tests can inject a fake Gemini client.
preview_client_factory = personalize.gemini_client


class TemplateBody(BaseModel):
    content: str


class PreviewBody(BaseModel):
    domain: str
    key: str
    content: str
    contact_id: int | None = None
    round: int = 0


@router.get("/domains")
def domains():
    return DOMAIN_KEYS


@router.get("/{domain}")
def read_domain(domain: str, conn=Depends(get_db)):
    try:
        templates = get_templates(conn, domain)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"domain": domain, "keys": TEMPLATE_KEYS, "templates": templates}


@router.put("/{domain}/{key}")
def write_template(domain: str, key: str, body: TemplateBody, conn=Depends(get_db)):
    try:
        version_id = save_template(conn, domain, key, body.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"saved": True, "version_id": version_id}


@router.get("/{domain}/{key}/versions")
def versions(domain: str, key: str, conn=Depends(get_db)):
    try:
        return list_versions(conn, domain, key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{domain}/{key}/restore/{version_id}")
def restore(domain: str, key: str, version_id: int, conn=Depends(get_db)):
    try:
        return restore_version(conn, version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/preview")
def preview(body: PreviewBody, conn=Depends(get_db)):
    try:
        templates = dict(get_templates(conn, body.domain))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if body.key not in TEMPLATE_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown template key '{body.key}'")

    # The edit under review wins for this render only — nothing is saved.
    templates[body.key] = body.content

    if body.contact_id:
        row = conn.execute(
            "SELECT * FROM contacts WHERE id = ?", (body.contact_id,)
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT * FROM contacts WHERE domain = ? AND status = 'active'
               ORDER BY id LIMIT 1""",
            (body.domain,),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=400,
            detail="No contact available to preview against — import contacts first.",
        )
    contact = dict(row)

    subject = personalize.render_subject(templates, contact, body.round)
    if body.round == 0:
        try:
            content = personalize.generate_body(preview_client_factory(), templates, contact)
        except Exception as e:  # noqa: BLE001 — surfaced to the editor
            raise HTTPException(status_code=502, detail=f"Gemini error: {e}")
    else:
        try:
            content = personalize.render_followup_body(templates, contact, body.round)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"subject": subject, "body": content, "contact": contact}
