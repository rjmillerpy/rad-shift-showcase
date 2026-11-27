"""Bridging-based scoring: which notes are helpful to people who usually disagree.

A plain helpful-vote count lets one large group put a note on the other
side's posts. Instead each rating is modelled as

    rating ≈ mu + rater_intercept + note_intercept + rater_factor × note_factor

The factors learn the main axis raters split along (no labels needed: it
falls out of who agrees with whom). Helpfulness that one side's agreement
explains goes into the note's factor; only helpfulness from both sides is
left in its intercept, and the intercept decides the status.

Pure Python with no database, so it can be tested on made-up raters. The
cost is EPOCHS × ratings, fine for thousands of ratings; past that, rescoring
would move from each rating request to a scheduled job.
"""

import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .constants import (
    EPOCHS,
    FACTOR_REGULARIZATION,
    HELPFUL_INTERCEPT,
    HELPFUL_RATING,
    INITIAL_FACTOR_SCALE,
    INTERCEPT_REGULARIZATION,
    LEANING_FACTOR,
    LEARNING_RATE,
    MAX_HELPFUL_FACTOR,
    MIN_RATINGS,
    NEUTRAL_RATING,
    NOT_HELPFUL_FACTOR_SLOPE,
    NOT_HELPFUL_INTERCEPT,
    SEED,
    NoteStatus,
)


@dataclass(frozen=True)
class Rating:
    rater_id: int
    note_id: int
    value: float  # HELPFUL_RATING or NOT_HELPFUL_RATING


@dataclass(frozen=True)
class NoteScore:
    status: NoteStatus
    intercept: float | None  # None until the note has MIN_RATINGS ratings
    factor: float | None


def score_notes(ratings: Iterable[Rating]) -> dict[int, NoteScore]:
    """A score for every note that has at least one rating."""
    ratings = list(ratings)
    counts = Counter(rating.note_id for rating in ratings)
    params = _fit(ratings)
    sides = _helpful_sides(ratings, params.rater_factor if params else {})
    return {
        note_id: _score(
            count,
            params.note_intercept.get(note_id) if params else None,
            params.note_factor.get(note_id) if params else None,
            sides.get(note_id, (0, 0)),
        )
        for note_id, count in counts.items()
    }


def _helpful_sides(
    ratings: list[Rating], rater_factor: dict[int, float]
) -> dict[int, tuple[int, int]]:
    """Per note: helpful ratings from clearly leaning raters, (leaning negative, leaning positive)."""
    sides: dict[int, list[int]] = {}
    for rating in ratings:
        lean = rater_factor[rating.rater_id]
        if rating.value == HELPFUL_RATING and abs(lean) >= LEANING_FACTOR:
            side = sides.setdefault(rating.note_id, [0, 0])
            side[lean > 0] += 1
    return {note_id: (neg, pos) for note_id, (neg, pos) in sides.items()}


def _score(
    count: int, intercept: float | None, factor: float | None, sides: tuple[int, int]
) -> NoteScore:
    if count < MIN_RATINGS or intercept is None or factor is None:
        return NoteScore(NoteStatus.NEEDS_MORE_RATINGS, None, None)
    # Leaning raters found it helpful, and all from one side: not bridged.
    bridged = min(sides) > 0 or max(sides) == 0
    if intercept >= HELPFUL_INTERCEPT and abs(factor) < MAX_HELPFUL_FACTOR and bridged:
        status = NoteStatus.HELPFUL
    elif intercept < NOT_HELPFUL_INTERCEPT - NOT_HELPFUL_FACTOR_SLOPE * abs(factor):
        status = NoteStatus.NOT_HELPFUL
    else:
        status = NoteStatus.NEEDS_MORE_RATINGS
    return NoteScore(status, round(intercept, 4), round(factor, 4))


def _fit(ratings: list[Rating]) -> "_Params | None":
    """Note intercepts and factors that minimise squared error plus regularisation.

    Full-batch gradient descent. Each parameter's step is divided by how many
    ratings it appears in, so a note with 200 ratings takes no bigger steps
    than one with 5 (plain summed gradients diverge as ratings grow).
    """
    if not ratings:
        return None
    rng = random.Random(SEED)  # nosec B311 - seeded starting weights for a fit, not security
    raters = sorted({rating.rater_id for rating in ratings})
    notes = sorted({rating.note_id for rating in ratings})
    rater_counts = Counter(rating.rater_id for rating in ratings)
    note_counts = Counter(rating.note_id for rating in ratings)
    params = _Params(
        mu=NEUTRAL_RATING,
        rater_intercept=dict.fromkeys(raters, 0.0),
        note_intercept=dict.fromkeys(notes, 0.0),
        rater_factor={r: rng.uniform(-1, 1) * INITIAL_FACTOR_SCALE for r in raters},
        note_factor={n: rng.uniform(-1, 1) * INITIAL_FACTOR_SCALE for n in notes},
    )
    for _ in range(EPOCHS):
        _step(params, ratings, rater_counts, note_counts)
    return params


@dataclass
class _Params:
    mu: float
    rater_intercept: dict[int, float]
    note_intercept: dict[int, float]
    rater_factor: dict[int, float]
    note_factor: dict[int, float]


def _step(
    p: _Params, ratings: list[Rating], rater_counts: Counter[int], note_counts: Counter[int]
) -> None:
    ri_grad = dict.fromkeys(p.rater_intercept, 0.0)
    ni_grad = dict.fromkeys(p.note_intercept, 0.0)
    rf_grad = dict.fromkeys(p.rater_factor, 0.0)
    nf_grad = dict.fromkeys(p.note_factor, 0.0)
    for rating in ratings:
        r, n = rating.rater_id, rating.note_id
        error = (
            p.mu + p.rater_intercept[r] + p.note_intercept[n] + p.rater_factor[r] * p.note_factor[n]
        ) - rating.value
        ri_grad[r] += error
        ni_grad[n] += error
        rf_grad[r] += error * p.note_factor[n]
        nf_grad[n] += error * p.rater_factor[r]
    for r, count in rater_counts.items():
        p.rater_intercept[r] -= (
            LEARNING_RATE * (ri_grad[r] + INTERCEPT_REGULARIZATION * p.rater_intercept[r]) / count
        )
        p.rater_factor[r] -= (
            LEARNING_RATE * (rf_grad[r] + FACTOR_REGULARIZATION * p.rater_factor[r]) / count
        )
    for n, count in note_counts.items():
        p.note_intercept[n] -= (
            LEARNING_RATE * (ni_grad[n] + INTERCEPT_REGULARIZATION * p.note_intercept[n]) / count
        )
        p.note_factor[n] -= (
            LEARNING_RATE * (nf_grad[n] + FACTOR_REGULARIZATION * p.note_factor[n]) / count
        )
