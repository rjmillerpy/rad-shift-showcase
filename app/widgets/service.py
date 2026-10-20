"""Widget CRUD and review pipeline."""

import logging
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.widgets.compiler import compile_to_html
from app.widgets.models import Widget, WidgetInstall, WidgetReview, WidgetTemplate
from app.widgets.security import scan_widget_code

logger = logging.getLogger(__name__)

WIDGET_CATEGORIES = {
    "game",
    "tool",
    "api_connector",
    "display_modifier",
    "lambda",
    "visualization",
    "social",
    "db_connector",
}

WIDGET_LANGUAGES = {
    "html",
    "javascript",
    "typescript",
    "python",
    "react",
    "vue",
    "angular",
    "svelte",
    "rust",
    "golang",
    "sql",
    "nodejs",
    "nextjs",
    "c",
    "cpp",
    "csharp",
    "ruby",
    "php",
    "fortran",
    "basic",
    "cobol",
    "assembly",
    "visual_basic",
}

_WIDGET_FIELDS = [
    "id",
    "author_id",
    "title",
    "description",
    "category",
    "language",
    "code",
    "html_panel",
    "css_panel",
    "compute_panel",
    "compute_language",
    "execution_mode",
    "html_output",
    "css",
    "config",
    "version",
    "icon_emoji",
    "thumbnail_url",
    "tags",
    "status",
    "review_notes",
    "reviewed_by",
    "reviewed_at",
    "security_score",
    "security_issues",
    "scan_passed",
    "install_count",
    "likes",
    "saves",
    "shares",
    "permissions",
    "default_width",
    "default_height",
    "resizable",
    "created_at",
    "updated_at",
    "published_at",
]


def _widget_to_dict(w: Widget) -> dict:
    """Serialize a Widget ORM instance to a plain dict."""
    d = {f: getattr(w, f) for f in _WIDGET_FIELDS}
    d["author_username"] = w.author.username if w.author else None
    return d


def compile_widget(widget: Widget) -> str:
    """Produce the HTML output for a widget by wrapping its code with the
    appropriate browser runtime.  The result is stored in ``html_output``."""
    return compile_to_html(widget.code, widget.language, css=widget.css)


def create_widget(user: User, data: dict, db: Session) -> dict:
    """Create a new draft widget."""
    category = data.get("category", "")
    if category not in WIDGET_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    language = data.get("language", "")
    if language not in WIDGET_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Invalid language: {language}")

    now = int(time.time())
    widget = Widget(
        author_id=user.id,
        title=data["title"],
        description=data.get("description"),
        category=category,
        language=language,
        code=data["code"],
        css=data.get("css"),
        config=data.get("config"),
        icon_emoji=data.get("icon_emoji"),
        tags=data.get("tags"),
        permissions=data.get("permissions"),
        default_width=data.get("default_width", 400),
        default_height=data.get("default_height", 300),
        resizable=data.get("resizable", False),
        status="draft",
        version="1.0.0",
        install_count=0,
        likes=0,
        saves=0,
        shares=0,
        created_at=now,
    )
    template_id = data.get("template_id")
    if template_id:
        tpl = db.query(WidgetTemplate).filter(WidgetTemplate.id == template_id).first()
        if tpl and not widget.icon_emoji:
            widget.icon_emoji = tpl.icon_emoji

    db.add(widget)
    db.commit()
    db.refresh(widget)
    logger.info("Widget %d created by user %s", widget.id, user.username)
    return _widget_to_dict(widget)


# A widget can be changed by its author only while it isn't published or
# awaiting review.
EDITABLE_STATUSES = ("draft", "rejected")


def _own_widget(user: User, widget_id: int, db: Session, changing: str | None = None) -> Widget:
    """The user's own widget, or 404 (missing or someone else's: don't reveal
    which). With `changing` (the action, e.g. "edit"), also 400 unless the
    widget is still editable."""
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if not widget or widget.author_id != user.id:
        raise HTTPException(status_code=404, detail="Widget not found")
    if changing and widget.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"Cannot {changing} widget in '{widget.status}' status"
        )
    return widget


def update_widget(user: User, widget_id: int, data: dict, db: Session) -> dict:
    """Update own widget (only if draft/rejected)."""
    widget = _own_widget(user, widget_id, db, changing="edit")

    for field in (
        "title",
        "description",
        "code",
        "css",
        "config",
        "icon_emoji",
        "tags",
        "permissions",
        "default_width",
        "default_height",
        "resizable",
    ):
        if field in data and data[field] is not None:
            setattr(widget, field, data[field])

    widget.updated_at = int(time.time())
    if widget.status == "rejected":
        widget.status = "draft"
        widget.review_notes = widget.security_score = widget.security_issues = (
            widget.scan_passed
        ) = None

    db.commit()
    db.refresh(widget)
    logger.info("Widget %d updated by user %s", widget.id, user.username)
    return _widget_to_dict(widget)


def delete_widget(user: User, widget_id: int, db: Session) -> dict:
    """Delete own widget and related records."""
    widget = _own_widget(user, widget_id, db)
    db.query(WidgetInstall).filter(WidgetInstall.widget_id == widget_id).delete()
    db.query(WidgetReview).filter(WidgetReview.widget_id == widget_id).delete()
    db.delete(widget)
    db.commit()
    logger.info("Widget %d deleted by user %s", widget_id, user.username)
    return {"status": "deleted", "widget_id": widget_id}


def get_widget(widget_id: int, db: Session) -> dict | None:
    """Get a single widget by ID, or None."""
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    return _widget_to_dict(widget) if widget else None


def list_widgets(
    db: Session,
    status: str = "approved",
    category: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[dict], bool]:
    """Paginated widget listing filtered by status and optional category."""
    query = db.query(Widget).filter(Widget.status == status)
    if category:
        if category not in WIDGET_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        query = query.filter(Widget.category == category)
    query = query.order_by(Widget.install_count.desc(), Widget.created_at.desc())
    widgets = query.offset(offset).limit(limit + 1).all()
    has_more = len(widgets) > limit
    return [_widget_to_dict(w) for w in widgets[:limit]], has_more


def list_my_widgets(user: User, db: Session) -> list[dict]:
    """List all of the user's own widgets (all statuses)."""
    widgets = (
        db.query(Widget)
        .filter(Widget.author_id == user.id)
        .order_by(Widget.created_at.desc())
        .all()
    )
    return [_widget_to_dict(w) for w in widgets]


def submit_for_review(user: User, widget_id: int, db: Session) -> dict:
    """Submit widget for review; runs automated security scan first."""
    widget = _own_widget(user, widget_id, db, changing="submit")

    scan = scan_widget_code(widget.code, css=widget.css)
    widget.security_score = scan["score"]
    widget.security_issues = scan["issues"]
    widget.scan_passed = scan["passed"]

    if not scan["passed"]:
        widget.status = "rejected"
        widget.review_notes = (
            f"Automated security scan failed (score: {scan['score']}/100). "
            f"Found {len(scan['issues'])} issue(s). Fix issues and resubmit."
        )
        db.commit()
        db.refresh(widget)
        logger.warning("Widget %d failed security scan (score=%d)", widget.id, scan["score"])
        return _widget_to_dict(widget)

    widget.status = "submitted"
    widget.updated_at = int(time.time())
    db.commit()
    db.refresh(widget)
    logger.info("Widget %d submitted for review (scan score=%d)", widget.id, scan["score"])
    return _widget_to_dict(widget)


def review_widget(admin: User, widget_id: int, action: str, notes: str | None, db: Session) -> dict:
    """Admin approve/reject/suspend a widget."""
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    if action not in ("approve", "reject", "suspend"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    if action == "approve" and widget.status != "submitted":
        raise HTTPException(
            status_code=400, detail=f"Cannot approve widget in '{widget.status}' status"
        )

    now = int(time.time())
    if action == "approve":
        widget.status = "approved"
        widget.published_at = now
        widget.html_output = compile_widget(widget)
    elif action == "reject":
        widget.status = "rejected"
    else:
        widget.status = "suspended"

    widget.review_notes = notes
    widget.reviewed_by = admin.id
    widget.reviewed_at = now
    widget.updated_at = now
    db.commit()
    db.refresh(widget)
    logger.info("Widget %d %s by admin %s", widget.id, action, admin.username)
    return _widget_to_dict(widget)


def install_widget(user: User, widget_id: int, db: Session) -> dict:
    """Install/save a widget for the user."""
    widget = db.query(Widget).filter(Widget.id == widget_id, Widget.status == "approved").first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found or not approved")
    exists = (
        db.query(WidgetInstall)
        .filter(WidgetInstall.user_id == user.id, WidgetInstall.widget_id == widget_id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Widget already installed")

    db.add(WidgetInstall(user_id=user.id, widget_id=widget_id, installed_at=int(time.time())))
    widget.install_count = (widget.install_count or 0) + 1
    db.commit()
    logger.info("User %s installed widget %d", user.username, widget_id)
    return {"status": "installed", "widget_id": widget_id, "install_count": widget.install_count}


def uninstall_widget(user: User, widget_id: int, db: Session) -> dict:
    """Uninstall/remove a widget for the user."""
    inst = (
        db.query(WidgetInstall)
        .filter(WidgetInstall.user_id == user.id, WidgetInstall.widget_id == widget_id)
        .first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="Widget not installed")
    db.delete(inst)
    widget = db.query(Widget).filter(Widget.id == widget_id).first()
    if widget and widget.install_count and widget.install_count > 0:
        widget.install_count -= 1
    db.commit()
    logger.info("User %s uninstalled widget %d", user.username, widget_id)
    return {"status": "uninstalled", "widget_id": widget_id}


def get_installed_widgets(user: User, db: Session) -> list[dict]:
    """Get all widgets installed by the user, in install order."""
    installs = (
        db.query(WidgetInstall)
        .filter(WidgetInstall.user_id == user.id)
        .order_by(WidgetInstall.installed_at.desc())
        .all()
    )
    wids = [i.widget_id for i in installs]
    if not wids:
        return []
    wmap = {w.id: w for w in db.query(Widget).filter(Widget.id.in_(wids)).all()}
    return [_widget_to_dict(wmap[wid]) for wid in wids if wid in wmap]


def rate_widget(user: User, widget_id: int, rating: int, comment: str | None, db: Session) -> dict:
    """Rate/review a widget (1-5 stars). Updates existing review if present."""
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    widget = db.query(Widget).filter(Widget.id == widget_id, Widget.status == "approved").first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found or not approved")

    now = int(time.time())
    existing = (
        db.query(WidgetReview)
        .filter(WidgetReview.user_id == user.id, WidgetReview.widget_id == widget_id)
        .first()
    )

    if existing:
        existing.rating = rating
        existing.comment = comment
        existing.created_at = now
        db.commit()
        logger.info("User %s updated review for widget %d", user.username, widget_id)
        return {"status": "updated", "widget_id": widget_id, "rating": rating, "comment": comment}

    db.add(
        WidgetReview(
            user_id=user.id, widget_id=widget_id, rating=rating, comment=comment, created_at=now
        )
    )
    db.commit()
    logger.info("User %s rated widget %d (%d stars)", user.username, widget_id, rating)
    return {"status": "created", "widget_id": widget_id, "rating": rating, "comment": comment}
