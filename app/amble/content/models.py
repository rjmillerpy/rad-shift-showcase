"""SQLAlchemy models for Amble content: the per-user per-entity cursor
(Phase 1.4d) and the admin-editable binding override table (Phase 2.2a).
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from app.common.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AmbleContentCursor(Base):
    __tablename__ = "amble_content_cursors"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "entity_id",
            name="uq_amble_content_cursors_user_entity",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Entity ids are short slugs (see the town's map and bindings file);
    # 64 chars mirrors the entity schema.
    entity_id = Column(String(64), nullable=False, index=True)
    # Where the next fetch should start in the ordered post query.
    offset_val = Column("offset", Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class AmbleBindingOverride(Base):
    """Admin-authored override for a single entity's binding (Phase 2.2a).

    When present, the row's `binding_json` takes precedence over whatever
    the same `entity_id` has in `entity-bindings.yaml`. The YAML file is
    still the fallback / source of truth for entities without an override,
    so ops can wipe overrides to revert to the versioned defaults.

    `binding_json` stores the serialized `Binding` union (kind + tags /
    usernames / parts) — Pydantic parses it back on read. `updated_by`
    is the admin user id, kept for audit rather than authz.
    """

    __tablename__ = "amble_binding_overrides"

    # entity_id is the natural PK — one override per entity max.
    entity_id = Column(String(64), primary_key=True)
    binding_json = Column(JSON, nullable=False)
    # Optional custom empty-state override; falls through to per-type
    # frontend default when null, same as EntityConfig.empty_state_text.
    empty_state_text = Column(String(280), nullable=True)
    # Phase 2.3b — per-entity freshness bias, 0..1. Mirrors
    # EntityConfig.freshness_bias so overrides can flip a newsstand to
    # time-decay ordering without editing the YAML.
    freshness_bias = Column(Float, nullable=False, default=0.0)
    # Phase 2.3c — per-entity follow-graph personalisation toggle.
    personalise_by_follow = Column(Boolean, nullable=False, default=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
