from fastapi import APIRouter, Depends

from app.deps import get_db
from app.services.queue import followup_due_counts
from app.services.runner import list_runs

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(conn=Depends(get_db)):
    def scalar(sql, params=()):
        return conn.execute(sql, params).fetchone()["c"]

    due = followup_due_counts(conn)
    return {
        "contacts": scalar("SELECT COUNT(*) c FROM contacts"),
        "active_contacts": scalar("SELECT COUNT(*) c FROM contacts WHERE status='active'"),
        "contacted": scalar(
            "SELECT COUNT(DISTINCT real_addr) c FROM sends WHERE test_mode=0 AND error IS NULL"
        ),
        "pending_drafts": scalar("SELECT COUNT(*) c FROM drafts WHERE status='pending'"),
        "approved_drafts": scalar("SELECT COUNT(*) c FROM drafts WHERE status='approved'"),
        "followups_due": {str(k): v for k, v in due.items()},
        "recent_runs": list_runs(conn, limit=5),
    }
