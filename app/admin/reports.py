"""Filing a report on any kind of user content, for the moderators' queue.

One open report per reporter and target: reporting the same thing again
updates the reason instead of piling up duplicates.
"""

import logging
import time

from sqlalchemy.orm import InstrumentedAttribute, Session

from app.auth.models import User

from .models import REPORT_STATUS_PENDING, Report, ReportTarget

logger = logging.getLogger(__name__)

# The Report column that holds each target's id.
_TARGET_COLUMNS: dict[ReportTarget, InstrumentedAttribute[int | None]] = {
    ReportTarget.POST: Report.post_id,
    ReportTarget.BLOG: Report.blog_id,
    ReportTarget.PROFILE_PICTURE: Report.reported_user_id,
}


def file_report(
    target: ReportTarget, target_id: int, reporter: User, reason: str, db: Session
) -> str:
    """Record the report; "created" or "updated" (the reporter's open one got the new reason)."""
    column = _TARGET_COLUMNS[target]
    existing = (
        db.query(Report)
        .filter(
            Report.reporter_user_id == reporter.id,
            Report.target_type == target.value,
            column == target_id,
            Report.status == REPORT_STATUS_PENDING,
        )
        .first()
    )
    if existing:
        existing.reason = reason
        db.commit()
        return "updated"
    db.add(
        Report(
            reporter_user_id=reporter.id,
            target_type=target.value,
            reason=reason,
            status=REPORT_STATUS_PENDING,
            unix_timestamp=int(time.time()),
            **{column.key: target_id},
        )
    )
    db.commit()
    logger.info("%s %s reported by user %s", target.value, target_id, reporter.id)
    return "created"
