"""Widget starter templates for common widget categories."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.widgets.models import WidgetTemplate
from app.widgets.template_code import (
    API_CODE,
    C_WASM_CODE,
    DB_CONNECTOR_CODE,
    DISPLAY_MOD_CODE,
    GAME_CODE,
    LAMBDA_CODE_NODE,
    LAMBDA_CODE_PY,
    PHP_CODE,
    REACT_CODE,
    RUBY_CODE,
    SOCIAL_CODE,
    TOOL_CODE,
    VIZ_CODE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template definitions (metadata + code references)
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: list[dict] = [
    {
        "name": "Simple Game",
        "category": "game",
        "language": "html",
        "description": "A basic canvas game with score tracking. Click falling objects before they hit the bottom.",
        "icon_emoji": "\U0001f3ae",
        "starter_code": GAME_CODE,
        "starter_css": "",
    },
    {
        "name": "API Connector",
        "category": "api_connector",
        "language": "javascript",
        "description": "Fetch and display data from a public API with loading states and error handling.",
        "icon_emoji": "\U0001f310",
        "starter_code": API_CODE,
        "starter_css": "",
    },
    {
        "name": "Lambda Function (Python)",
        "category": "lambda",
        "language": "python",
        "description": "Serverless-style function with input/output processing.",
        "icon_emoji": "\u26a1",
        "starter_code": LAMBDA_CODE_PY,
        "starter_css": "",
    },
    {
        "name": "Lambda Function (Node.js)",
        "category": "lambda",
        "language": "nodejs",
        "description": "Node.js-style Lambda handler with event/context pattern.",
        "icon_emoji": "\u26a1",
        "starter_code": LAMBDA_CODE_NODE,
        "starter_css": "",
    },
    {
        "name": "Database Explorer",
        "category": "db_connector",
        "language": "sql",
        "description": "Query and visualize database results with a SQL-like interface.",
        "icon_emoji": "\U0001f5c4\ufe0f",
        "starter_code": DB_CONNECTOR_CODE,
        "starter_css": "",
    },
    {
        "name": "Data Visualization",
        "category": "visualization",
        "language": "javascript",
        "description": "Canvas-based bar and line charts with animated transitions.",
        "icon_emoji": "\U0001f4ca",
        "starter_code": VIZ_CODE,
        "starter_css": "",
    },
    {
        "name": "Social Widget",
        "category": "social",
        "language": "html",
        "description": "Styled social content card with share buttons and engagement metrics.",
        "icon_emoji": "\U0001f4ac",
        "starter_code": SOCIAL_CODE,
        "starter_css": "",
    },
    {
        "name": "Tool / Calculator",
        "category": "tool",
        "language": "html",
        "description": "Interactive unit converter supporting length, weight, and temperature.",
        "icon_emoji": "\U0001f9ee",
        "starter_code": TOOL_CODE,
        "starter_css": "",
    },
    {
        "name": "Display Modifier",
        "category": "display_modifier",
        "language": "javascript",
        "description": "Renders Twitter/Reddit/YouTube links as rich preview cards.",
        "icon_emoji": "\U0001f3a8",
        "starter_code": DISPLAY_MOD_CODE,
        "starter_css": "",
    },
    {
        "name": "React Component",
        "category": "tool",
        "language": "react",
        "description": "React-based task manager widget with hooks, filtering, and responsive UI.",
        "icon_emoji": "\u269b",
        "starter_code": REACT_CODE,
        "starter_css": "",
    },
    {
        "name": "C/C++ Calculator (WASM)",
        "category": "tool",
        "language": "c",
        "description": "Simulated C-compiled WASM calculator with arithmetic operations.",
        "icon_emoji": "\u2699\ufe0f",
        "starter_code": C_WASM_CODE,
        "starter_css": "",
    },
    {
        "name": "Ruby Interactive Console",
        "category": "tool",
        "language": "ruby",
        "description": "Interactive Ruby-style REPL with string methods, math, and output.",
        "icon_emoji": "\U0001f48e",
        "starter_code": RUBY_CODE,
        "starter_css": "",
    },
    {
        "name": "PHP Form Processor",
        "category": "tool",
        "language": "php",
        "description": "Form submission handler simulating PHP $_POST processing.",
        "icon_emoji": "\U0001f418",
        "starter_code": PHP_CODE,
        "starter_css": "",
    },
]


def seed_templates(db: Session) -> int:
    """Insert builtin templates if they don't exist yet. Returns count added."""
    rows: list[Any] = db.query(WidgetTemplate.name).all()
    existing: set[str] = {row[0] for row in rows}
    added = 0
    for t in BUILTIN_TEMPLATES:
        if t["name"] in existing:
            continue
        db.add(
            WidgetTemplate(
                name=t["name"],
                category=t["category"],
                language=t["language"],
                description=t["description"],
                starter_code=t["starter_code"],
                starter_css=t.get("starter_css", ""),
                icon_emoji=t.get("icon_emoji"),
            )
        )
        added += 1
    if added:
        db.commit()
        logger.info("Seeded %d widget templates", added)
    return added
