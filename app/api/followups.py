from fastapi import APIRouter, Depends

from app.deps import get_db
from app.services.queue import eligible_followup

router = APIRouter(prefix="/api/followups", tags=["followups"])


@router.get("/due")
def due(domain: str = "job", conn=Depends(get_db)):
    out = {}
    for round_num in (1, 2, 3):
        items = eligible_followup(conn, domain=domain, round_num=round_num)
        out[str(round_num)] = {"count": len(items), "items": items}
    return out
