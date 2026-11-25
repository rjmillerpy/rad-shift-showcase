"""Widget storage: a small key-value store per user, per widget.

Widgets run in a sandboxed iframe with an opaque origin, where the browser
refuses localStorage. A widget calls radshift.storage (app/widgets/sdk.js);
the page relays the call here with the viewer's login. The widget never sees
the login, and the page decides which widget is asking from which iframe sent
the message, so a widget can only reach its own keys.

Limits (constants.py): 100 keys and 10 KB per value, per user per widget.
"""

import json
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.auth.models import User
from app.widgets.constants import WIDGET_STORAGE_MAX_KEYS, WIDGET_STORAGE_MAX_VALUE_BYTES
from app.widgets.models import Widget, WidgetData


def _usable_widget(user: User, widget_id: int, db: Session) -> Widget:
    """An approved widget, or the user's own (so authors can test before review)."""
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if widget is None or (widget.status != "approved" and widget.author_id != user.id):
        raise HTTPException(status_code=404, detail="Widget not found or not approved")
    return widget


def _rows(user: User, widget_id: int, db: Session) -> Query[WidgetData]:
    return db.query(WidgetData).filter_by(user_id=user.id, widget_id=widget_id)


def list_items(user: User, widget_id: int, db: Session) -> dict[str, Any]:
    _usable_widget(user, widget_id, db)
    return {row.key: json.loads(row.value) for row in _rows(user, widget_id, db).all()}


def get_item(user: User, widget_id: int, key: str, db: Session) -> Any:
    _usable_widget(user, widget_id, db)
    row = _rows(user, widget_id, db).filter_by(key=key).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No value saved under that key")
    return json.loads(row.value)


def set_item(user: User, widget_id: int, key: str, value: Any, db: Session) -> None:
    """Save a JSON value; 413 if it's too big, 409 if the widget has used all its keys."""
    _usable_widget(user, widget_id, db)
    encoded = json.dumps(value, separators=(",", ":"))
    if len(encoded.encode()) > WIDGET_STORAGE_MAX_VALUE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"A value can be at most {WIDGET_STORAGE_MAX_VALUE_BYTES} bytes as JSON",
        )
    row = _rows(user, widget_id, db).filter_by(key=key).first()
    if row is None:
        used = _rows(user, widget_id, db).with_entities(func.count(WidgetData.id)).scalar() or 0
        if used >= WIDGET_STORAGE_MAX_KEYS:
            raise HTTPException(
                status_code=409,
                detail=f"This widget already keeps {WIDGET_STORAGE_MAX_KEYS} keys for you",
            )
        row = WidgetData(user_id=user.id, widget_id=widget_id, key=key)
        db.add(row)
    row.value = encoded
    row.updated_at = int(time.time())
    db.commit()


def remove_item(user: User, widget_id: int, key: str, db: Session) -> None:
    """Delete a key; removing one that isn't there is fine (idempotent)."""
    _usable_widget(user, widget_id, db)
    _rows(user, widget_id, db).filter_by(key=key).delete()
    db.commit()
