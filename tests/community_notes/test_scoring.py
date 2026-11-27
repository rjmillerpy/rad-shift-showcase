"""Tests for app/community_notes/scoring.py on made-up raters in two camps.

Camp A (raters 1-20) and camp B (21-40) disagree: each rates its own side's
notes helpful and the other side's not. The point of bridging is that only a
note both camps find helpful is shown, however many votes a one-sided note gets.
"""

import pytest

from app.community_notes.constants import MIN_RATINGS, NoteStatus
from app.community_notes.scoring import Rating, score_notes

CAMP_A = range(1, 21)
CAMP_B = range(21, 41)
PRO_A, PRO_B, BRIDGING, BAD, ONLY_A = 1, 2, 3, 4, 5


def _ratings(rows: list[tuple[range | list[int], int, float]]) -> list[Rating]:
    return [Rating(rater, note, value) for raters, note, value in rows for rater in raters]


@pytest.fixture(scope="module")
def scores():
    a, b = list(CAMP_A), list(CAMP_B)
    return score_notes(
        _ratings(
            [
                (a, PRO_A, 1.0),
                (b, PRO_A, 0.0),
                (a, PRO_B, 0.0),
                (b, PRO_B, 1.0),
                (a[:8] + b[:8], BRIDGING, 1.0),
                (a[:6] + b[:6], BAD, 0.0),
                (a[:15], ONLY_A, 1.0),
            ]
        )
    )


def test_a_note_both_camps_find_helpful_is_shown(scores):
    assert scores[BRIDGING].status is NoteStatus.HELPFUL
    assert abs(scores[BRIDGING].factor) < 0.1


@pytest.mark.parametrize("note", [PRO_A, PRO_B])
def test_a_partisan_note_is_not_shown_despite_half_the_votes(scores, note):
    assert scores[note].status is not NoteStatus.HELPFUL
    assert abs(scores[note].factor) > 0.5


def test_fifteen_votes_from_one_camp_only_are_not_enough(scores):
    """The case a vote count gets wrong."""
    assert scores[ONLY_A].status is not NoteStatus.HELPFUL


def test_a_note_both_camps_reject_is_not_helpful(scores):
    assert scores[BAD].status is NoteStatus.NOT_HELPFUL


def test_too_few_ratings_are_not_judged():
    ratings = [Rating(rater, 9, 1.0) for rater in range(MIN_RATINGS - 1)]
    assert score_notes(ratings)[9].status is NoteStatus.NEEDS_MORE_RATINGS
    assert score_notes(ratings)[9].intercept is None


def test_the_same_ratings_always_give_the_same_scores():
    ratings = _ratings([(list(CAMP_A)[:6] + list(CAMP_B)[:6], 1, 1.0), (list(CAMP_B), 2, 1.0)])
    assert score_notes(ratings) == score_notes(list(reversed(ratings)))


def test_no_ratings_no_scores():
    assert score_notes([]) == {}


def test_early_on_a_note_everyone_finds_helpful_is_shown():
    """One note, no divide in the data yet: nothing to bridge, so agreement is enough.
    (A learned global average once absorbed all of it, and the note never showed.)"""
    scores = score_notes([Rating(rater, 1, 1.0) for rater in range(MIN_RATINGS + 3)])
    assert scores[1].status is NoteStatus.HELPFUL
