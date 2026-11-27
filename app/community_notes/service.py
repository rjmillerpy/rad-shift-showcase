"""Writing, rating, rescoring and showing community notes.

Anyone signed in and verified can write a note on someone else's published
post, and rate other people's notes. A note appears on the post only once
scoring.py finds it helpful to raters on both sides of the fitted divide.
Rescoring runs after the rating response is sent (see views.py), because a
fit over every rating takes seconds once there are thousands of them.
"""

import logging
import threading
import time

from fastapi import HTTPException
from sqlalchemy import Connection, Engine
from sqlalchemy.orm import Session

from app.auth.models import User
from app.posts.models import PostModel
from app.posts.serializer import by_active_authors

from .constants import HELPFUL_RATING, NOT_HELPFUL_RATING, RATING_QUEUE_SIZE, NoteStatus
from .models import CommunityNote, NoteRating
from .scoring import Rating, score_notes

logger = logging.getLogger(__name__)

# One rescore at a time per process: two at once would each write a full set
# of statuses, and the one that read older ratings could land last.
_rescore_lock = threading.Lock()


def write_note(
    post_id: int, author: User, text: str, source_url: str | None, db: Session
) -> CommunityNote:
    """Add a note to a post, or replace the author's existing one (its ratings reset)."""
    post = _published_post_or_404(post_id, db)
    if post.user_id == author.id:
        raise HTTPException(status_code=400, detail="You can't add a note to your own post")
    note = db.query(CommunityNote).filter_by(post_id=post_id, author_id=author.id).first()
    if note is None:
        note = CommunityNote(post_id=post_id, author_id=author.id)
        db.add(note)
    else:
        # Ratings were for the old wording.
        db.query(NoteRating).filter_by(note_id=note.id).delete()
    note.text = text.strip()
    note.source_url = source_url
    note.created_at = int(time.time())
    note.status = NoteStatus.NEEDS_MORE_RATINGS.value
    note.intercept = note.factor = None
    db.commit()
    logger.info("Community note %s on post %s by user %s", note.id, post_id, author.id)
    return note


def rate_note(note_id: int, rater: User, helpful: bool, db: Session) -> NoteRating:
    note = _live_note_or_404(note_id, db)
    if note.author_id == rater.id:
        raise HTTPException(status_code=400, detail="You can't rate your own note")
    rating = db.get(NoteRating, (note_id, rater.id))
    if rating is None:
        rating = NoteRating(note_id=note_id, rater_id=rater.id)
        db.add(rating)
    rating.helpful = helpful
    rating.rated_at = int(time.time())
    db.commit()
    return rating


def rescore(engine: Engine | Connection) -> None:
    """Refit every live note's status from all ratings, in a session of its own."""
    with _rescore_lock, Session(bind=engine) as db:
        rows = (
            db.query(NoteRating.rater_id, NoteRating.note_id, NoteRating.helpful)
            .join(CommunityNote, CommunityNote.id == NoteRating.note_id)
            .filter(CommunityNote.is_removed.is_(False))
            .all()
        )
        scores = score_notes(
            Rating(rater, note, HELPFUL_RATING if helpful else NOT_HELPFUL_RATING)
            for rater, note, helpful in rows
        )
        for note in db.query(CommunityNote).filter(CommunityNote.id.in_(scores)).all():
            score = scores[note.id]
            note.status, note.intercept, note.factor = (
                score.status.value,
                score.intercept,
                score.factor,
            )
        db.commit()
        logger.info("Rescored %d community notes from %d ratings", len(scores), len(rows))


def notes_for_post(post_id: int, db: Session) -> list[CommunityNote]:
    """Every live note on a post, shown or not, for the post's notes page."""
    _published_post_or_404(post_id, db)
    return (
        db.query(CommunityNote)
        .filter_by(post_id=post_id, is_removed=False)
        .order_by(CommunityNote.created_at.desc())
        .all()
    )


def rating_queue(viewer: User, db: Session) -> list[CommunityNote]:
    """Notes still waiting for ratings that the viewer neither wrote nor rated."""
    rated = db.query(NoteRating.note_id).filter(NoteRating.rater_id == viewer.id)
    live_posts = by_active_authors(db.query(PostModel.id).filter(PostModel.is_draft.is_(False)))
    return (
        db.query(CommunityNote)
        .filter(
            CommunityNote.status == NoteStatus.NEEDS_MORE_RATINGS.value,
            CommunityNote.is_removed.is_(False),
            CommunityNote.author_id != viewer.id,
            CommunityNote.id.not_in(rated),
            CommunityNote.post_id.in_(live_posts),
        )
        .order_by(CommunityNote.created_at.desc())
        .limit(RATING_QUEUE_SIZE)
        .all()
    )


def my_ratings(note_ids: list[int], viewer: User | None, db: Session) -> dict[int, bool]:
    if viewer is None or not note_ids:
        return {}
    rows = db.query(NoteRating.note_id, NoteRating.helpful).filter(
        NoteRating.rater_id == viewer.id, NoteRating.note_id.in_(note_ids)
    )
    return dict(rows.all())


def remove_note(note_id: int, db: Session) -> CommunityNote:
    """A moderator takes a note down (abuse, spam); it stops counting at once.

    Not committed here: the caller commits it together with its audit-log entry.
    """
    note = _live_note_or_404(note_id, db)
    note.is_removed = True
    note.status = NoteStatus.NEEDS_MORE_RATINGS.value
    return note


def _published_post_or_404(post_id: int, db: Session) -> PostModel:
    post = (
        by_active_authors(db.query(PostModel))
        .filter(PostModel.id == post_id, PostModel.is_draft.is_(False))
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


def _live_note_or_404(note_id: int, db: Session) -> CommunityNote:
    note = db.query(CommunityNote).filter_by(id=note_id, is_removed=False).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note
