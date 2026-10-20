"""Tests for app/chronicle/grouping.py — theme-based greedy reordering."""

from app.chronicle.grouping import group_posts_by_theme
from tests.chronicle.helpers import make_post as _post


class TestGroupPostsByTheme:
    def test_short_lists_unchanged(self):
        posts = [_post(id=1, username="alice"), _post(id=2, username="bob")]
        assert group_posts_by_theme(posts) == posts

    def test_same_author_clusters_together(self):
        alice_1 = _post(id=1, username="alice", text="apples")
        bob = _post(id=2, username="bob", text="clouds")
        alice_2 = _post(id=3, username="alice", text="pears")
        # Seed is alice_1; the next should be alice_2 (same author beats bob).
        ordered = group_posts_by_theme([alice_1, bob, alice_2])
        assert [p.id for p in ordered[:2]] == [1, 3]

    def test_tag_overlap_pulls_similar_topics_together(self):
        seed = _post(id=1, username="a", tags=["cats"], text="unrelated")
        different = _post(id=2, username="b", tags=["politics"], text="senate reform")
        similar = _post(id=3, username="c", tags=["cats", "photography"], text="tabby")
        ordered = group_posts_by_theme([seed, different, similar])
        assert [p.id for p in ordered[:2]] == [1, 3]

    def test_word_overlap_only_helps_when_no_stronger_signal(self):
        seed = _post(id=1, username="a", text="quick brown fox")
        similar_words = _post(id=2, username="b", text="brown foxes running")
        unrelated = _post(id=3, username="c", text="oceanic sunset")
        ordered = group_posts_by_theme([seed, unrelated, similar_words])
        assert [p.id for p in ordered[:2]] == [1, 2]

    def test_output_length_matches_input(self):
        posts = [_post(id=i, username=f"u{i}", text=f"txt {i}") for i in range(6)]
        ordered = group_posts_by_theme(posts)
        assert sorted(p.id for p in ordered) == sorted(p.id for p in posts)
