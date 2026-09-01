from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_db
from app.services.leads import SALES_DOMAIN_ICP, generate_placeholder_leads
from app.services.queue import eligible_followup, eligible_initial

router = APIRouter(prefix="/api/queue", tags=["queue"])


class LeadsBody(BaseModel):
    domain: str
    count: int = 5


@router.get("")
def read_queue(domain: str = "job", batch: str = "", round: int = 0,
               limit: int = 0, conn=Depends(get_db)):
    if round == 0:
        items = eligible_initial(conn, domain=domain, batch=batch, limit=limit)
    elif round in (1, 2, 3):
        items = eligible_followup(conn, domain=domain, round_num=round, limit=limit)
    else:
        raise HTTPException(status_code=400, detail="round must be 0, 1, 2 or 3")
    return {"domain": domain, "round": round, "total": len(items), "items": items}


@router.post("/leads")
def create_leads(body: LeadsBody, conn=Depends(get_db)):
    if body.domain not in SALES_DOMAIN_ICP:
        raise HTTPException(
            status_code=400,
            detail="Placeholder leads only exist for the sales domains.",
        )
    rows = generate_placeholder_leads(conn, body.domain, max(1, min(body.count, 50)))
    return {"created": len(rows)}
