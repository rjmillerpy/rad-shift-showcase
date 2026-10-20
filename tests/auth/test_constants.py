"""Tests for app/auth/constants.py — simple invariants on the shared constants."""

import re

from app.auth import constants


class TestNumericConstants:
    def test_username_bounds_sensible(self):
        assert 1 <= constants.MIN_USERNAME_LEN < constants.MAX_USERNAME_LEN

    def test_password_min_length_positive(self):
        assert constants.MIN_PASSWORD_LEN >= 1

    def test_token_bytes_reasonable(self):
        # 16 bytes gives 128 bits of entropy; anything less would be weak.
        assert constants.VERIFICATION_TOKEN_BYTES >= 16

    def test_expiry_positive(self):
        assert constants.VERIFICATION_TOKEN_EXPIRY_SECONDS > 0


class TestPatterns:
    def test_username_pattern_accepts_common_chars(self):
        assert re.match(constants.USERNAME_PATTERN, "user_name.1-2")

    def test_username_pattern_rejects_spaces(self):
        assert not re.match(constants.USERNAME_PATTERN, "has space")

    def test_email_pattern_accepts_valid(self):
        assert re.match(constants.EMAIL_PATTERN, "a@b.co")

    def test_email_pattern_rejects_invalid(self):
        assert not re.match(constants.EMAIL_PATTERN, "not-an-email")


class TestBcryptRounds:
    def test_production_cost_is_at_least_12(self):
        """tests/conftest.py lowers BCRYPT_ROUNDS to 4 for speed, so read the
        value the app ships with from the source, not from the patched module."""
        import ast
        from pathlib import Path

        tree = ast.parse(Path(constants.__file__).read_text())
        shipped = next(
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and getattr(node.targets[0], "id", None) == "BCRYPT_ROUNDS"
            and isinstance(node.value, ast.Constant)
        )
        assert shipped >= 12
