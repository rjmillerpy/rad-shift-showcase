"""Limits, statuses and scoring parameters for community notes (app/community_notes/).

The scoring parameters follow X's open-source Community Notes algorithm
(github.com/twitter/communitynotes, "matrix factorization"): a note is shown
when its intercept (helpfulness that the raters' viewpoint factor doesn't
explain) clears 0.40 and its own factor is small, so it is helpful to raters
on both sides of whatever divides them, not just popular with one side.
"""

from enum import StrEnum

MAX_NOTE_LENGTH = 500
MAX_SOURCE_URL_LENGTH = 500


class NoteStatus(StrEnum):
    NEEDS_MORE_RATINGS = "needs_more_ratings"
    HELPFUL = "helpful"  # shown on the post
    NOT_HELPFUL = "not_helpful"


# A note isn't judged on fewer ratings than this.
MIN_RATINGS = 5
# And it isn't shown if every clearly leaning rater who found it helpful
# leans the same way (|factor| at least LEANING_FACTOR): a guard on top of the
# intercept, so one side alone can never put a note on a post. Raters with
# smaller factors don't count: with no real divide in the data (early on,
# few notes) every factor is near zero and its sign is noise.
LEANING_FACTOR = 0.3
# Shown: intercept at least this, and |factor| below MAX_HELPFUL_FACTOR.
HELPFUL_INTERCEPT = 0.40
MAX_HELPFUL_FACTOR = 0.50
# Rated not helpful: intercept below this minus NOT_HELPFUL_FACTOR_SLOPE × |factor|.
NOT_HELPFUL_INTERCEPT = -0.05
NOT_HELPFUL_FACTOR_SLOPE = 0.8

# The model: rating ≈ mu + rater_intercept + note_intercept + rater_factor × note_factor,
# fitted by full-batch gradient descent. Intercepts are regularised harder
# than factors, so agreement that the viewpoint factor can explain is credited
# to the factor, not to the note's intercept.
INTERCEPT_REGULARIZATION = 0.15
FACTOR_REGULARIZATION = 0.03
LEARNING_RATE = 0.2
# Tested on two-camp data: at 400 epochs a note rated helpful by one camp only
# was still shown; from ~2,000 the fit attributes it to the camp's factor.
EPOCHS = 2000
# Fixed seed: the same ratings always give the same statuses.
SEED = 7
INITIAL_FACTOR_SCALE = 0.1

# Ratings are 1 (helpful) or 0 (not helpful).
HELPFUL_RATING = 1.0
NOT_HELPFUL_RATING = 0.0
# The model's global average, held at the midpoint instead of learned: with
# few notes a learned average soaks up everything (one note rated helpful by
# everyone gave average 1.0 and note intercept 0, so it could never show).
# Generous or harsh raters are absorbed by their own intercepts instead.
NEUTRAL_RATING = 0.5

# How many notes the "needs your rating" queue returns at once.
RATING_QUEUE_SIZE = 20
