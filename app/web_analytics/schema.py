"""Request and response shapes for analytics collection."""

from pydantic import BaseModel, Field

from app.common.schema import FrozenModel

from .constants import MAX_EVENTS_PER_BATCH, MAX_PATH_LENGTH


class PageViewBatch(BaseModel):
    # Raw paths as the browser saw them; app/web_analytics/service.py cleans them.
    paths: list[str] = Field(..., min_length=1, max_length=MAX_EVENTS_PER_BATCH)

    model_config = {"str_max_length": MAX_PATH_LENGTH * 4}


class AcceptedResponse(FrozenModel):
    accepted: int
