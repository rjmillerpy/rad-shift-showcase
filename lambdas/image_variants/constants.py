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

# Every S3 and SQS call gives up instead of hanging until the Lambda timeout (rule 67).
AWS_CONNECT_TIMEOUT_SECONDS = 5
AWS_READ_TIMEOUT_SECONDS = 30
AWS_MAX_ATTEMPTS = 3

# Where finished work is reported for the API to record (item 28); set by
# infra/media-pipeline/lambda.tf. The message is RESULT_* keys as JSON.
RESULTS_QUEUE_URL_ENV = "RESULTS_QUEUE_URL"
RESULT_BUCKET = "bucket"
RESULT_SOURCE_KEY = "source_key"
# {"480": "variants/posts/x-480.webp", ...}; widths as strings (JSON keys).
RESULT_VARIANTS = "variants"
# The original's width as displayed (after EXIF rotation), so a browser can
# weigh it against the variants in a srcset.
RESULT_WIDTH = "width"

# S3 sends this once when a notification target is saved, to prove it can
# deliver. It names no object.
S3_TEST_EVENT = "s3:TestEvent"
