"""Pydantic schema validation tests for the widget system."""

import pytest
from pydantic import ValidationError

from app.widgets.schema import (
    WidgetCreateRequest,
    WidgetRatingRequest,
    WidgetReviewRequest,
    WidgetSubmitRequest,
    WidgetUpdateRequest,
)

# ---------------------------------------------------------------------------
# WidgetCreateRequest
# ---------------------------------------------------------------------------


class TestWidgetCreateRequestSchema:
    def test_valid_minimal(self):
        req = WidgetCreateRequest(
            title="Hello",
            category="tool",
            language="html",
            code="<p>hi</p>",
        )
        assert req.title == "Hello"
        assert req.category == "tool"
        assert req.default_width == 400  # default
        assert req.default_height == 300  # default
        assert req.resizable is False

    def test_valid_full(self):
        req = WidgetCreateRequest(
            title="Full Widget",
            description="A full test",
            category="game",
            language="javascript",
            code="console.log('hi');",
            css="body {}",
            config={"key": "val"},
            icon_emoji="X",
            tags=["fun", "game"],
            permissions=["camera"],
            default_width=600,
            default_height=500,
            resizable=True,
            template_id=1,
        )
        assert req.tags == ["fun", "game"]
        assert req.template_id == 1

    def test_title_empty_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            WidgetCreateRequest(title="", category="tool", language="html", code="x")
        assert "title" in str(exc_info.value).lower()

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(title="x" * 201, category="tool", language="html", code="x")

    def test_code_empty_accepted(self):
        """Code can be empty since HTML/CSS/JS panels provide content."""
        req = WidgetCreateRequest(title="T", category="tool", language="html", code="")
        assert req.code == ""

    def test_code_too_large(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(title="T", category="tool", language="html", code="x" * 500001)

    def test_css_too_large(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(
                title="T",
                category="tool",
                language="html",
                code="x",
                css="y" * 100001,
            )

    @pytest.mark.parametrize(
        "category",
        ["game", "tool", "api_connector", "display_modifier", "lambda", "visualization", "social"],
    )
    def test_valid_categories(self, category):
        req = WidgetCreateRequest(title="T", category=category, language="html", code="x")
        assert req.category == category

    @pytest.mark.parametrize(
        "category",
        ["invalid", "GAME", "Tool", "games", "", "api-connector"],
        ids=["invalid", "uppercase", "titlecase", "plural", "empty", "hyphenated"],
    )
    def test_invalid_categories(self, category):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(title="T", category=category, language="html", code="x")

    @pytest.mark.parametrize(
        "language",
        [
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
        ],
    )
    def test_valid_languages(self, language):
        req = WidgetCreateRequest(title="T", category="tool", language=language, code="x")
        assert req.language == language

    @pytest.mark.parametrize(
        "language",
        ["invalid", "HTML", "Javascript", "c++", "", "java"],
        ids=["invalid", "uppercase", "titlecase", "cplusplus", "empty", "java"],
    )
    def test_invalid_languages(self, language):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(title="T", category="tool", language=language, code="x")

    def test_width_too_small(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(
                title="T",
                category="tool",
                language="html",
                code="x",
                default_width=199,
            )

    def test_width_too_large(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(
                title="T",
                category="tool",
                language="html",
                code="x",
                default_width=1201,
            )

    def test_height_too_small(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(
                title="T",
                category="tool",
                language="html",
                code="x",
                default_height=199,
            )

    def test_height_too_large(self):
        with pytest.raises(ValidationError):
            WidgetCreateRequest(
                title="T",
                category="tool",
                language="html",
                code="x",
                default_height=801,
            )

    def test_width_boundary_valid(self):
        req = WidgetCreateRequest(
            title="T",
            category="tool",
            language="html",
            code="x",
            default_width=200,
        )
        assert req.default_width == 200
        req2 = WidgetCreateRequest(
            title="T",
            category="tool",
            language="html",
            code="x",
            default_width=1200,
        )
        assert req2.default_width == 1200

    def test_height_boundary_valid(self):
        req = WidgetCreateRequest(
            title="T",
            category="tool",
            language="html",
            code="x",
            default_height=200,
        )
        assert req.default_height == 200
        req2 = WidgetCreateRequest(
            title="T",
            category="tool",
            language="html",
            code="x",
            default_height=800,
        )
        assert req2.default_height == 800


# ---------------------------------------------------------------------------
# WidgetUpdateRequest
# ---------------------------------------------------------------------------


class TestWidgetUpdateRequestSchema:
    def test_all_fields_optional(self):
        req = WidgetUpdateRequest()
        assert req.title is None
        assert req.code is None

    def test_partial_update(self):
        req = WidgetUpdateRequest(title="New Title")
        assert req.title == "New Title"
        assert req.code is None

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(title="x" * 201)

    def test_code_too_large(self):
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(code="x" * 500001)

    def test_css_too_large(self):
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(css="x" * 100001)

    def test_width_constraints(self):
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(default_width=199)
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(default_width=1201)

    def test_height_constraints(self):
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(default_height=199)
        with pytest.raises(ValidationError):
            WidgetUpdateRequest(default_height=801)


# ---------------------------------------------------------------------------
# WidgetSubmitRequest
# ---------------------------------------------------------------------------


class TestWidgetSubmitRequestSchema:
    def test_valid(self):
        req = WidgetSubmitRequest(widget_id=1)
        assert req.widget_id == 1

    def test_missing_widget_id(self):
        with pytest.raises(ValidationError):
            WidgetSubmitRequest()


# ---------------------------------------------------------------------------
# WidgetReviewRequest
# ---------------------------------------------------------------------------


class TestWidgetReviewRequestSchema:
    @pytest.mark.parametrize("action", ["approve", "reject", "suspend"])
    def test_valid_actions(self, action):
        req = WidgetReviewRequest(widget_id=1, action=action)
        assert req.action == action

    @pytest.mark.parametrize(
        "action",
        ["ban", "delete", "APPROVE", "Reject", ""],
        ids=["ban", "delete", "uppercase", "titlecase", "empty"],
    )
    def test_invalid_actions(self, action):
        with pytest.raises(ValidationError):
            WidgetReviewRequest(widget_id=1, action=action)

    def test_notes_optional(self):
        req = WidgetReviewRequest(widget_id=1, action="approve")
        assert req.notes is None

    def test_notes_provided(self):
        req = WidgetReviewRequest(widget_id=1, action="reject", notes="Bad code")
        assert req.notes == "Bad code"

    def test_missing_widget_id(self):
        with pytest.raises(ValidationError):
            WidgetReviewRequest(action="approve")

    def test_missing_action(self):
        with pytest.raises(ValidationError):
            WidgetReviewRequest(widget_id=1)


# ---------------------------------------------------------------------------
# WidgetRatingRequest
# ---------------------------------------------------------------------------


class TestWidgetRatingRequestSchema:
    @pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
    def test_valid_ratings(self, rating):
        req = WidgetRatingRequest(widget_id=1, rating=rating)
        assert req.rating == rating

    @pytest.mark.parametrize(
        "rating",
        [0, -1, 6, 100, -100],
        ids=["zero", "negative", "six", "hundred", "neg-hundred"],
    )
    def test_invalid_ratings(self, rating):
        with pytest.raises(ValidationError):
            WidgetRatingRequest(widget_id=1, rating=rating)

    def test_comment_optional(self):
        req = WidgetRatingRequest(widget_id=1, rating=5)
        assert req.comment is None

    def test_comment_provided(self):
        req = WidgetRatingRequest(widget_id=1, rating=5, comment="Great!")
        assert req.comment == "Great!"

    def test_missing_widget_id(self):
        with pytest.raises(ValidationError):
            WidgetRatingRequest(rating=5)

    def test_missing_rating(self):
        with pytest.raises(ValidationError):
            WidgetRatingRequest(widget_id=1)
