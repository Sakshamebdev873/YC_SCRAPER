import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_db
from app.services.queue import contacted_emails

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

VALID_STATUSES = {"active", "skipped"}


class ContactPatch(BaseModel):
    predicted_email: str | None = None
    status: str | None = None


class ImportBody(BaseModel):
    csv_path: str | None = None
    domain: str = "job"


@router.get("/batches")
def batches(conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT DISTINCT batch FROM contacts WHERE batch != '' ORDER BY batch"
    )
    return [r["batch"] for r in rows]


@router.get("")
def list_contacts(search: str = "", batch: str = "", status: str = "",
                  domain: str = "", page: int = 1, per_page: int = 50,
                  conn=Depends(get_db)):
    clauses, params = [], []
    if search:
        clauses.append(
            "(company_name LIKE ? OR founder_name LIKE ? OR predicted_email LIKE ?)"
        )
        params += [f"%{search}%"] * 3
    if batch:
        clauses.append("batch = ?")
        params.append(batch)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if domain:
        clauses.append("domain = ?")
        params.append(domain)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    total = conn.execute(f"SELECT COUNT(*) c FROM contacts{where}", params).fetchone()["c"]
    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    rows = conn.execute(
        f"SELECT * FROM contacts{where} ORDER BY id LIMIT ? OFFSET ?",
        (*params, per_page, (page - 1) * per_page),
    ).fetchall()

    contacted = contacted_emails(conn)
    items = []
    for row in rows:
        item = dict(row)
        item["contacted"] = item["predicted_email"] in contacted
        items.append(item)
    return {"total": total, "page": page, "per_page": per_page, "items": items}


@router.post("/import")
def import_csv(body: ImportBody, conn=Depends(get_db)):
    from app.seed import DEFAULT_CSV, import_contacts

    try:
        return import_contacts(conn, body.csv_path or DEFAULT_CSV, domain=body.domain)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{contact_id}")
def patch_contact(contact_id: int, patch: ContactPatch, conn=Depends(get_db)):
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    if patch.status is not None and patch.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="status must be 'active' or 'skipped'")

    fields, params = [], []
    if patch.predicted_email is not None:
        fields.append("predicted_email = ?")
        params.append(patch.predicted_email.strip())
    if patch.status is not None:
        fields.append("status = ?")
        params.append(patch.status)
    if fields:
        try:
            conn.execute(
                f"UPDATE contacts SET {', '.join(fields)} WHERE id = ?",
                (*params, contact_id),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=409, detail="That email is already on another contact")
    updated = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return dict(updated)
