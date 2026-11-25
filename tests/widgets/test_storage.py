"""app/widgets/storage.py: the per-user, per-widget key-value store."""

import pytest
from fastapi import HTTPException

from app.widgets import storage
from app.widgets.constants import WIDGET_STORAGE_MAX_KEYS, WIDGET_STORAGE_MAX_VALUE_BYTES
from app.widgets.models import Widget


@pytest.fixture()
def make_widget(db_session):
    def _make(author, status="approved"):
        widget = Widget(author_id=author.id, title="W", category="tool", language="html",
                        code="<p>", status=status, created_at=1)  # fmt: skip
        db_session.add(widget)
        db_session.commit()
        return widget

    return _make


@pytest.fixture()
def author(create_user):
    return create_user(username="author")


@pytest.fixture()
def fan(create_user):
    return create_user(username="fan")


def test_a_value_round_trips_as_json(db_session, author, fan, make_widget):
    widget = make_widget(author)
    value = {"best": 42, "names": ["a", "b"], "on": True, "none": None}

    storage.set_item(fan, widget.id, "state", value, db_session)

    assert storage.get_item(fan, widget.id, "state", db_session) == value
    assert storage.list_items(fan, widget.id, db_session) == {"state": value}


def test_setting_again_replaces_the_value(db_session, author, fan, make_widget):
    widget = make_widget(author)
    storage.set_item(fan, widget.id, "n", 1, db_session)
    storage.set_item(fan, widget.id, "n", 2, db_session)
    assert storage.list_items(fan, widget.id, db_session) == {"n": 2}


def test_each_user_and_widget_has_its_own_keys(db_session, author, fan, make_widget):
    first, second = make_widget(author), make_widget(author)
    storage.set_item(fan, first.id, "k", "fan's", db_session)
    storage.set_item(author, first.id, "k", "author's", db_session)

    assert storage.get_item(fan, first.id, "k", db_session) == "fan's"
    assert storage.list_items(fan, second.id, db_session) == {}


def test_a_missing_key_is_404(db_session, author, fan, make_widget):
    with pytest.raises(HTTPException) as exc:
        storage.get_item(fan, make_widget(author).id, "nope", db_session)
    assert exc.value.status_code == 404


def test_removing_is_idempotent(db_session, author, fan, make_widget):
    widget = make_widget(author)
    storage.set_item(fan, widget.id, "k", 1, db_session)
    storage.remove_item(fan, widget.id, "k", db_session)
    storage.remove_item(fan, widget.id, "k", db_session)
    assert storage.list_items(fan, widget.id, db_session) == {}


def test_a_value_over_the_size_limit_is_413(db_session, author, fan, make_widget):
    with pytest.raises(HTTPException) as exc:
        storage.set_item(fan, make_widget(author).id, "big", "x" * WIDGET_STORAGE_MAX_VALUE_BYTES,
                         db_session)  # fmt: skip
    assert exc.value.status_code == 413


def test_a_new_key_past_the_limit_is_409_but_existing_keys_still_update(
    db_session, author, fan, make_widget
):
    widget = make_widget(author)
    for i in range(WIDGET_STORAGE_MAX_KEYS):
        storage.set_item(fan, widget.id, f"k{i}", i, db_session)

    with pytest.raises(HTTPException) as exc:
        storage.set_item(fan, widget.id, "one-more", 0, db_session)
    storage.set_item(fan, widget.id, "k0", "updated", db_session)

    assert exc.value.status_code == 409
    assert storage.get_item(fan, widget.id, "k0", db_session) == "updated"


def test_an_author_can_test_their_own_unapproved_widget(db_session, author, fan, make_widget):
    draft = make_widget(author, status="draft")
    storage.set_item(author, draft.id, "k", 1, db_session)
    with pytest.raises(HTTPException) as exc:
        storage.set_item(fan, draft.id, "k", 1, db_session)
    assert exc.value.status_code == 404
