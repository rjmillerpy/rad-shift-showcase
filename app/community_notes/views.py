"""Community notes endpoints, under /notes."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.db import get_db
from app.common.deps import optional_user, verified_user

from .models import CommunityNote
from .schema import NoteRequest, NoteResponse, NotesResponse, RatingRequest, RatingResponse
from .service import (
    my_ratings,
    notes_for_post,
    rate_note,
    rating_queue,
    rescore,
    write_note,
)

community_notes_router = APIRouter()


@community_notes_router.post("/posts/{post_id}")
def add_note(
    post_id: int,
    body: NoteRequest,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> NoteResponse:
    source = str(body.source_url) if body.source_url else None
    note = write_note(post_id, user, body.text, source, db)
    return _response(note, user, {})


@community_notes_router.get("/posts/{post_id}")
def list_notes(
    post_id: int,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> NotesResponse:
    return _responses(notes_for_post(post_id, db), user, db)


@community_notes_router.get("/needs-ratings")
def needs_ratings(
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> NotesResponse:
    return _responses(rating_queue(user, db), user, db)


@community_notes_router.post("/{note_id}/rating")
def rate(
    note_id: int,
    body: RatingRequest,
    background: BackgroundTasks,
    user: User = Depends(verified_user),
    db: Session = Depends(get_db),
) -> RatingResponse:
    rating = rate_note(note_id, user, body.helpful, db)
    # After the response: a fit over every rating can take seconds.
    background.add_task(rescore, db.get_bind())
    return RatingResponse(note_id=rating.note_id, helpful=rating.helpful)


def _responses(notes: list[CommunityNote], user: User | None, db: Session) -> NotesResponse:
    ratings = my_ratings([note.id for note in notes], user, db)
    return NotesResponse(notes=[_response(note, user, ratings) for note in notes])


def _response(note: CommunityNote, user: User | None, ratings: dict[int, bool]) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        post_id=note.post_id,
        text=note.text,
        source_url=note.source_url,
        status=note.status,
        created_at=note.created_at,
        is_mine=user is not None and note.author_id == user.id,
        my_rating=ratings.get(note.id),
    )
