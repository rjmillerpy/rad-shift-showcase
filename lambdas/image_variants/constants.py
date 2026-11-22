"""Settings for the image variants Lambda (lambdas/image_variants/handler.py).

The prefixes are the safety-critical part: the function is triggered by new
objects under SOURCE_PREFIX and writes under VARIANT_PREFIX. If it ever
wrote under its own trigger prefix, each output would trigger another run,
an infinite loop billed per invocation (tests/lambdas pins that it can't).
"""

SOURCE_PREFIX = "posts/"
VARIANT_PREFIX = "variants/"

# Widths written for each image, never upscaled: a phone-feed size and a
# desktop size. Smaller originals get only the widths below their own.
VARIANT_WIDTHS = (480, 1280)
WEBP_QUALITY = 80
VARIANT_CONTENT_TYPE = "image/webp"
# Each variant key is derived from its source, so a new upload means a new
# key and the cached copy never goes stale.
CACHE_CONTROL = "public, max-age=31536000, immutable"
# Readable by anyone, like the app's own uploads (app/common/s3.py).
PUBLIC_ACL = "public-read"

# The formats the S3 notification sends (infra/media-pipeline/lambda.tf);
# the API stores HEIC as JPEG already (app/common/images.py).
IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})

# Uploads are capped at 50 MB; a decompression bomb is refused, not resized.
MAX_IMAGE_PIXELS = 100_000_000

# Every S3 call gives up instead of hanging until the Lambda timeout (rule 67).
S3_CONNECT_TIMEOUT_SECONDS = 5
S3_READ_TIMEOUT_SECONDS = 30
S3_MAX_ATTEMPTS = 3
