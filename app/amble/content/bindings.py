"""Entity-binding YAML loader (Phase 1.4b, D1).

Reads the edition's bindings file (app/plugins.py) once, parses it via the
Pydantic schemas, and exposes a keyed registry that service.py queries per
request. Failures at load time are fatal: `preload()` runs at startup, so a
malformed binding file crashes the process rather than silently returning
"unknown entity" 404s in prod. Tests can re-load a temporary file via
`load_bindings_from_path`.
"""

import logging
from functools import cache
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.plugins import edition

from .constants import (
    LOG_EVENT_BINDINGS_ERROR,
    LOG_EVENT_BINDINGS_LOADED,
)
from .models import AmbleBindingOverride
from .schema import EntityConfig

logger = logging.getLogger(__name__)


class BindingsLoadError(Exception):
    """Raised when the YAML file can't be parsed. Caller decides whether to
    fail fast (module import) or degrade (return 404 for every entity)."""


def load_bindings_from_path(path: Path) -> dict[str, EntityConfig]:
    """Read + parse the YAML at `path`, return a dict keyed by entity_id.

    File shape:
        entities:
          <entity_id>:
            binding: {...}
            empty_state_text: "..."   # optional
    """
    if not path.exists():
        # An empty registry is fine — every entity 404s and the frontend
        # falls back to its sync handlers. Prod deploys must ship the file.
        logger.warning(LOG_EVENT_BINDINGS_ERROR, extra={"reason": "missing", "path": str(path)})
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except yaml.YAMLError as cause:
        raise BindingsLoadError(f"YAML parse failed: {cause}") from cause

    entities_raw = raw.get("entities") or {}
    if not isinstance(entities_raw, dict):
        raise BindingsLoadError("`entities:` must be a mapping of entity_id → config")

    registry: dict[str, EntityConfig] = {}
    for entity_id, entry in entities_raw.items():
        if not isinstance(entry, dict):
            raise BindingsLoadError(f"entity `{entity_id}` config must be a mapping")
        try:
            registry[entity_id] = EntityConfig.model_validate({"entity_id": entity_id, **entry})
        except ValidationError as cause:
            raise BindingsLoadError(f"entity `{entity_id}`: {cause}") from cause

    logger.info(LOG_EVENT_BINDINGS_LOADED, extra={"count": len(registry)})
    return registry


# The edition's YAML, parsed once per file. Phase 2.2a adds a DB override
# table (`AmbleBindingOverride`) that takes precedence when a row exists for
# the same entity_id — see `get_binding`.
_load_cached = cache(load_bindings_from_path)
_replacement: dict[str, EntityConfig] | None = None


def _registry() -> dict[str, EntityConfig]:
    if _replacement is not None:
        return _replacement
    return _load_cached(edition().amble_bindings_path)


def preload() -> None:
    """Parse the edition's bindings now, so a broken file fails at startup."""
    _registry()


def _override_to_entity_config(row: AmbleBindingOverride) -> EntityConfig | None:
    """Parse a DB override row back into an EntityConfig. Returns None if
    the stored JSON is malformed — caller falls back to YAML so a corrupt
    override doesn't 404 the endpoint."""
    try:
        return EntityConfig.model_validate(
            {
                "entity_id": row.entity_id,
                "binding": row.binding_json,
                "empty_state_text": row.empty_state_text,
                "freshness_bias": float(row.freshness_bias or 0.0),
                "personalise_by_follow": bool(row.personalise_by_follow),
            }
        )
    except ValidationError as cause:
        logger.warning(
            LOG_EVENT_BINDINGS_ERROR,
            extra={
                "reason": "override_parse_failed",
                "entity_id": row.entity_id,
                "cause": str(cause),
            },
        )
        return None


def get_binding(entity_id: str, db: Session | None = None) -> EntityConfig | None:
    """Return the effective binding for `entity_id`.

    Precedence: DB override (if `db` provided and a row exists) > YAML
    registry > None. The `db` param is optional so tests and non-request
    callsites can query the YAML directly; production callsites pass the
    request session so admin overrides win.
    """
    if db is not None:
        row = db.query(AmbleBindingOverride).filter_by(entity_id=entity_id).first()
        if row is not None:
            parsed = _override_to_entity_config(row)
            if parsed is not None:
                return parsed
            # Fall through on parse failure — YAML is still valid.
    return _registry().get(entity_id)


def get_yaml_binding(entity_id: str) -> EntityConfig | None:
    """YAML-only lookup — bypasses DB overrides. Admin UI uses this to
    show "default vs overridden" side-by-side."""
    return _registry().get(entity_id)


def yaml_bindings() -> dict[str, EntityConfig]:
    """Every YAML binding by entity id (no DB overrides)."""
    return dict(_registry())


def all_yaml_entity_ids() -> list[str]:
    """All entity ids the YAML file knows about, sorted. Admin list view
    uses this to enumerate anchors even when they have no override yet."""
    return sorted(_registry())


def override_bindings(replacement: dict[str, EntityConfig] | None) -> None:
    """Test hook — replace the YAML registry (None goes back to the edition's
    file). Callers are responsible for restoring the prior state (or
    fixture-scope this). Does NOT touch the DB override table."""
    global _replacement
    _replacement = replacement
