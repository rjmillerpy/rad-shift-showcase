"""Request and response shapes for community notes."""

from pydantic import BaseModel, Field, HttpUrl

from app.common.schema import FrozenModel

from .constants import MAX_NOTE_LENGTH, MAX_SOURCE_URL_LENGTH


class NoteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_NOTE_LENGTH)
    # http(s) only: shown to readers as a link.
    source_url: HttpUrl | None = Field(None, max_length=MAX_SOURCE_URL_LENGTH)


class RatingRequest(BaseModel):
    helpful: bool


class NoteResponse(FrozenModel):
    id: int
    post_id: int
    text: str
    source_url: str | None
    status: str
    created_at: int
    is_mine: bool
    # True / False once the viewer has rated it, else None.
    my_rating: bool | None


class NotesResponse(FrozenModel):
    notes: list[NoteResponse]


class RatingResponse(FrozenModel):
    note_id: int
    helpful: bool
