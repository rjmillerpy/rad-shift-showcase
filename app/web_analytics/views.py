"""POST /analytics/page-views: the frontend's page-view beacon.

The body is JSON sent as text/plain: navigator.sendBeacon can only send
"simple" requests, which skip the CORS preflight, so it can't set
Content-Type: application/json. The beacon carries no Authorization header,
so a view is never tied to an account.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.common.db import get_db

from .constants import MAX_BODY_BYTES
from .schema import AcceptedResponse, PageViewBatch
from .service import Client, record_page_views

analytics_router = APIRouter()


@analytics_router.post("/page-views")
async def page_views(request: Request, db: Session = Depends(get_db)) -> AcceptedResponse:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Too many page views in one batch")
    try:
        batch = PageViewBatch.model_validate_json(body)
    except ValidationError as err:
        raise HTTPException(status_code=422, detail='Expected {"paths": [...]}') from err
    client = Client(
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    )
    # Off the event loop: the session does blocking database I/O.
    accepted = await run_in_threadpool(record_page_views, batch.paths, client, db)
    return AcceptedResponse(accepted=accepted)
