"""Shared constants for common/ boundary code."""

DEFAULT_ALLOWED_ORIGIN = "http://localhost:3000"

# HS256 signing keys shorter than the 256-bit hash output weaken the signature
# (RFC 7518 section 3.2; PyJWT warns below this). Refuse to start with one.
MIN_JWT_SECRET_BYTES = 32

# Email delivery
EMAIL_TIMEOUT_SECONDS = 10
DEFAULT_FROM_EMAIL = "noreply@radshift.app"

# S3 client tuning — explicit timeouts so uploads/downloads fail fast rather
# than waiting on the botocore 60-second default (rule 67).
S3_CONNECT_TIMEOUT_SECONDS = 5
S3_READ_TIMEOUT_SECONDS = 15
S3_PUBLIC_ACL = "public-read"
S3_URL_TEMPLATE = "https://{bucket}.s3.amazonaws.com/{key}"

# Database connections (rule 67). Managed Postgres closes idle connections:
# Neon's free plan suspends after 5 minutes idle, and RDS failovers and
# restarts drop every connection. Check each pooled connection before use,
# retire connections before an idle cutoff, and fail fast if the server is
# unreachable instead of hanging a request.
DB_CONNECT_TIMEOUT_SECONDS = 10
DB_POOL_RECYCLE_SECONDS = 300

# Logging
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
