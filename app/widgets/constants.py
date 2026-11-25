"""Limits for the widget store (app/widgets/)."""

# Distinct users' reports that send an approved widget back to admin review.
WIDGET_REPORTS_FOR_REVIEW = 3
# A report's reason, as long as the widget_reports.reason column allows.
MAX_WIDGET_REPORT_REASON_LENGTH = 500
# A review's text.
MAX_WIDGET_REVIEW_LENGTH = 2000
# Reviews shown on a widget's page, newest first.
WIDGET_REVIEWS_SHOWN = 50

# Widget storage (app/widgets/storage.py): what one user may keep per widget.
WIDGET_STORAGE_MAX_KEYS = 100
WIDGET_STORAGE_MAX_VALUE_BYTES = 10_000  # the value as JSON, UTF-8
# Letters, digits and _ . : - ; up to 64 characters.
WIDGET_STORAGE_KEY_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"
