"""The random feed: a shuffle that takes turns between where posts come from.

Each pool (people's posts, scraped posts) is shuffled by the reader's seed,
then the pools take turns, so a flood of scraped posts can't crowd out
people and an empty pool is skipped. Generated content joins as a third
pool once Content Branch Generation exists (product roadmap, Phase 3).

The seed fixes the shuffle, so paging with the same seed never repeats or
skips a post; a new seed is a new shuffle. Each page re-reads its pools up
to the page's end, which is why the offset is capped.

The reader's slop, AI and topic settings still apply (app/posts/tailoring.py).
"""

from sqlalchemy import Select, select
from sqlalchemy.orm import Query, Session

from app.auth.models import User
from app.generators.models import GeneratorProfile

from .feeds import _base_feed_query, visible_to
from .models import PostModel
from .schema import PostResponse
from .serializer import build_post_responses
from .tailoring import jitter

MAX_RANDOM_OFFSET = 500


def get_random_posts_formatted(
    db: Session,
    seed: int,
    current_user: User | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PostResponse], bool]:
    visible = visible_to(_base_feed_query(db), current_user, db)
    needed = offset + limit + 1
    streams = [_shuffled(pool, seed, needed) for pool in _pools(visible)]
    merged = _take_turns(streams)
    page = merged[offset : offset + limit]
    return build_post_responses(page, current_user, db), len(merged) > offset + limit


def _pools(visible: Query[PostModel]) -> list[Query[PostModel]]:
    bots: Select[tuple[int]] = select(GeneratorProfile.user_id)
    return [
        visible.filter(PostModel.user_id.not_in(bots)),  # people
        visible.filter(PostModel.user_id.in_(bots)),  # scraped sources
    ]


def _shuffled(pool: Query[PostModel], seed: int, count: int) -> list[PostModel]:
    return pool.order_by(jitter(seed), PostModel.id).limit(count).all()


def _take_turns(streams: list[list[PostModel]]) -> list[PostModel]:
    merged: list[PostModel] = []
    for position in range(max((len(stream) for stream in streams), default=0)):
        merged.extend(stream[position] for stream in streams if position < len(stream))
    return merged
