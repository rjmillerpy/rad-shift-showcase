"""Tests for app/chronicle/prompt.py — the prompt contract and the public PlainPrompt."""

import pytest

from app.chronicle.prompt import ChroniclePrompt, PlainPrompt
from tests.chronicle.helpers import make_post


class ChroniclePromptContract:
    """What every ChroniclePrompt must do; the private edition's tests run it on production's too."""

    @pytest.fixture()
    def prompt(self) -> ChroniclePrompt:
        raise NotImplementedError

    def test_system_prompt_asks_for_json_segments(self, prompt: ChroniclePrompt) -> None:
        assert "JSON" in prompt.system
        assert '"narrative"' in prompt.system and '"post"' in prompt.system

    def test_every_post_appears_with_its_author(self, prompt: ChroniclePrompt) -> None:
        posts = [
            make_post(id=1, username="alice", text="hi"),
            make_post(id=2, username="bob", text="yo"),
        ]
        built = prompt.build_batch_prompt(posts, 0, 2)
        for post in posts:
            assert f"@{post.username}" in built
            assert post.text in built

    def test_previous_context_is_carried_over(self, prompt: ChroniclePrompt) -> None:
        built = prompt.build_batch_prompt([make_post()], 4, 8, "the rain stopped")
        assert "the rain stopped" in built

    def test_deterministic(self, prompt: ChroniclePrompt) -> None:
        posts = [make_post(tags=["cats"])]
        assert prompt.build_batch_prompt(posts, 0, 1) == prompt.build_batch_prompt(posts, 0, 1)


class TestPlainPromptContract(ChroniclePromptContract):
    @pytest.fixture()
    def prompt(self) -> ChroniclePrompt:
        return PlainPrompt()


class TestPlainPrompt:
    def test_numbers_posts_from_zero_within_the_batch(self) -> None:
        built = PlainPrompt().build_batch_prompt(
            [make_post(username="a", text="one"), make_post(username="b", text="two")], 4, 10
        )
        assert '0. @a: "one"' in built
        assert '1. @b: "two"' in built
        assert "Posts 5-6 of 10" in built

    @pytest.mark.parametrize(
        "media",
        [{"image_url": "i"}, {"video_url": "v"}, {"audio_url": "a"}],
        ids=["image", "video", "audio"],
    )
    def test_marks_media_posts(self, media: dict) -> None:
        assert "[media]" in PlainPrompt().build_batch_prompt([make_post(**media)], 0, 1)

    def test_text_posts_are_not_marked(self) -> None:
        assert "[media]" not in PlainPrompt().build_batch_prompt([make_post()], 0, 1)

    def test_no_continuation_line_without_context(self) -> None:
        assert "so far" not in PlainPrompt().build_batch_prompt([make_post()], 0, 1)
