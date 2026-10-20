"""The Chronicle prompt: its contract, and the public baseline.

The narration prompt production uses is private; the service reaches
whichever one the edition supplies (app/plugins.py) through `ChroniclePrompt`.
`PlainPrompt` is the public edition's: it asks for the same JSON segments the
parser reads (parsing.py), with no style guidance.
"""

from typing import Protocol

from app.posts.schema import PostResponse


class ChroniclePrompt(Protocol):
    @property
    def system(self) -> str:
        """The system prompt sent with every batch."""
        ...

    def build_batch_prompt(
        self,
        batch: list[PostResponse],
        batch_start: int,
        total: int,
        prev_context: str = "",
    ) -> str:
        """The user prompt for one batch; `prev_context` is the last narration's tail."""
        ...


PLAIN_SYSTEM_PROMPT = """Turn the numbered social media posts into a short story chapter.

Reply with only a JSON array of segments, no markdown:
- {"type":"narrative","text":"..."} for your own narration;
- {"type":"post","index":N} where post N appears (use "media" instead of "post" for a post marked [media]).

Every index appears exactly once, in any order. Start and end with a narrative segment."""


class PlainPrompt:
    """The public baseline: a numbered list of posts and the output format."""

    system = PLAIN_SYSTEM_PROMPT

    def build_batch_prompt(
        self,
        batch: list[PostResponse],
        batch_start: int,
        total: int,
        prev_context: str = "",
    ) -> str:
        lines = [
            f'{i}. @{post.username}: "{post.text}"{_media_mark(post)}'
            for i, post in enumerate(batch)
        ]
        continuation = f'The story so far ends: "{prev_context}"\n' if prev_context else ""
        return (
            f"{continuation}Posts {batch_start + 1}-{batch_start + len(batch)} of {total}:\n"
            + "\n".join(lines)
        )


def _media_mark(post: PostResponse) -> str:
    return " [media]" if post.image_url or post.video_url or post.audio_url else ""
