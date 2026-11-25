"""Limits for the widget store (app/widgets/)."""

# Distinct users' reports that send an approved widget back to admin review.
WIDGET_REPORTS_FOR_REVIEW = 3
# A report's reason, as long as the widget_reports.reason column allows.
MAX_WIDGET_REPORT_REASON_LENGTH = 500
# A review's text.
MAX_WIDGET_REVIEW_LENGTH = 2000
# Reviews shown on a widget's page, newest first.
WIDGET_REVIEWS_SHOWN = 50
