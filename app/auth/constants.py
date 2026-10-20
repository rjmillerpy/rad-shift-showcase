"""Shared constants for the auth domain."""

MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 80
MIN_PASSWORD_LEN = 8
# bcrypt only uses the first 72 *bytes* of a password (UTF-8, so accented
# characters and emoji count more than once). bcrypt 4 truncated silently;
# bcrypt 5 raises. New passwords longer than this are rejected at signup.
MAX_PASSWORD_BYTES = 72

# bcrypt work factor (2**12 rounds, about 0.2 s per hash). Login verification
# reads the cost from the stored hash, so raising this later only affects new
# hashes. The test suite lowers it (tests/conftest.py); nothing else should.
BCRYPT_ROUNDS = 12

# Bytes of entropy used when generating email verification tokens.
VERIFICATION_TOKEN_BYTES = 32

# Verification tokens are valid for 24 hours.
VERIFICATION_TOKEN_EXPIRY_SECONDS = 24 * 60 * 60


USERNAME_PATTERN = r"^[a-zA-Z0-9_.-]+$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Admin promotion (POST /auth/promote-admin)
ADMIN_SECRET_ENV_VAR = "ADMIN_SECRET"  # nosec B105 - an env var name, not a secret
