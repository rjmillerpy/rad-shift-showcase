"""CRUD service for `AmbleBindingOverride` (Phase 2.2a).

Thin wrapper around the model so views stay free of ORM calls. Every
write goes through here so any future audit-log / cache-invalidation
logic has one hook to attach to.
"""

from sqlalchemy.orm import Session

from .models import AmbleBindingOverride
from .schema import Binding


def get_override(db: Session, entity_id: str) -> AmbleBindingOverride | None:
    return db.query(AmbleBindingOverride).filter_by(entity_id=entity_id).first()


def list_all_overrides(db: Session) -> list[AmbleBindingOverride]:
    return db.query(AmbleBindingOverride).order_by(AmbleBindingOverride.entity_id.asc()).all()


def upsert_override(
    db: Session,
    entity_id: str,
    binding: Binding,
    updated_by_user_id: int,
    empty_state_text: str | None = None,
    freshness_bias: float = 0.0,
    personalise_by_follow: bool = False,
) -> AmbleBindingOverride:
    """Insert or replace the override row for `entity_id`. Serializes the
    Pydantic binding to plain JSON via `.model_dump()` so it round-trips
    through the JSON column. Commits eagerly.

    Phase 2.3 — accepts freshness_bias / personalise_by_follow so the
    admin API can flip feed-tuning options without editing YAML."""
    row = get_override(db, entity_id)
    binding_json = binding.model_dump()
    if row is None:
        row = AmbleBindingOverride(
            entity_id=entity_id,
            binding_json=binding_json,
            empty_state_text=empty_state_text,
            freshness_bias=freshness_bias,
            personalise_by_follow=personalise_by_follow,
            updated_by=updated_by_user_id,
        )
        db.add(row)
    else:
        row.binding_json = binding_json
        row.empty_state_text = empty_state_text
        row.freshness_bias = freshness_bias
        row.personalise_by_follow = personalise_by_follow
        row.updated_by = updated_by_user_id
    db.commit()
    db.refresh(row)
    return row


def delete_override(db: Session, entity_id: str) -> bool:
    """Remove the override for `entity_id`. Returns True if a row was
    deleted, False if there was no override to begin with (idempotent).
    Callers surface either as HTTP 204."""
    row = get_override(db, entity_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
