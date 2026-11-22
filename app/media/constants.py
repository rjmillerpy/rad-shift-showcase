"""Names and limits for recording image variants (app/media/, roadmap item 28).

The image-variants Lambda (lambdas/image_variants/) sends one message per
resized upload to a results queue; the API polls it and records the
variants on the post, so clients can load a 480 or 1280 px WebP instead of
the original. tests/media/test_constants.py keeps the message keys equal to
the Lambda's.
"""

# The results queue (infra/media-pipeline output results_queue_url). Unset:
# no polling, and posts are served with their originals only.
MEDIA_RESULTS_QUEUE_URL_ENV_VAR = "MEDIA_RESULTS_QUEUE_URL"

# Message keys, as the Lambda writes them.
RESULT_BUCKET = "bucket"
RESULT_SOURCE_KEY = "source_key"
RESULT_VARIANTS = "variants"
RESULT_WIDTH = "width"

# Long polling: one request waits up to 20 s for a message, so an idle
# poller costs ~130,000 requests a month (SQS includes 1M free).
RECEIVE_WAIT_SECONDS = 20
RECEIVE_MAX_MESSAGES = 10
# The read timeout must outlast the long poll, or every idle poll "times out".
SQS_CONNECT_TIMEOUT_SECONDS = 5
SQS_READ_TIMEOUT_SECONDS = RECEIVE_WAIT_SECONDS + 10
# After an SQS error, wait before polling again instead of spinning.
ERROR_BACKOFF_SECONDS = 30
# Shutdown waits this long, not for a 20 s long poll: Docker kills the
# container 10 s after asking it to stop. Nothing is lost by not waiting:
# a message received but not yet recorded is never deleted, so SQS makes it
# visible again after the queue's visibility timeout. (The thread is a
# daemon, so it never keeps the process alive.)
WORKER_JOIN_TIMEOUT_SECONDS = 2
WORKER_THREAD_NAME = "media-results"

LOG_EVENT_RECORDED = "media.variants.recorded"
LOG_EVENT_NO_POST = "media.variants.no_post"
LOG_EVENT_BAD_MESSAGE = "media.variants.bad_message"
LOG_EVENT_POLL_FAILED = "media.variants.poll_failed"
