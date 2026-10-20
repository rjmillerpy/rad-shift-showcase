"""SQLAlchemy model tests — real DB rows through the shared conftest engine."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.amble.avatar.models import AmbleAvatar

CONFIG_A = {
    "left": {"gender": "boy", "skin_tone": "warm", "hairstyle": "short", "clothing": "hoodie"},
    "right": {"gender": "girl", "skin_tone": "warm", "hairstyle": "long", "clothing": "dress"},
}


def test_row_persists_and_reads_back(db_session, create_user) -> None:
    user = create_user(username="ambler_a")
    row = AmbleAvatar(user_id=user.id, config=CONFIG_A)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    fetched = db_session.query(AmbleAvatar).filter(AmbleAvatar.user_id == user.id).one()
    assert fetched.config == CONFIG_A
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_unique_user_id_constraint_enforced(db_session, create_user) -> None:
    user = create_user(username="ambler_b")
    db_session.add(AmbleAvatar(user_id=user.id, config=CONFIG_A))
    db_session.commit()

    db_session.add(AmbleAvatar(user_id=user.id, config=CONFIG_A))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
