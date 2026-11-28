"""Source templates: a generator from one or two fields instead of raw config.

A template knows its platform, the fields to ask for, and how they become a
source (name, URL, platform_config, topics, how often it runs). Creating
from one also makes the bot account the source posts as, so a new source
works without a trip to the profiles screen.

Only the templates whose platform this edition has are offered
(app/plugins.py). None use the "web" platform: its AI selector analysis
is a paid model call. A field marked `takes_topic` can be filled from a
topic readers want (app/generators/demand.py).
"""

import re
import secrets
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.constants import MAX_USERNAME_LEN
from app.auth.models import User

from . import service
from .models import GeneratorSource
from .platforms import is_platform_supported
from .schema import MAX_SOURCE_TOPICS

BOT_SUFFIX = "_bot"
_USERNAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_.-]+")
_SLUG = r"^[A-Za-z0-9_]{2,50}$"
_SLUG_HELP = "letters, digits and _ only"


@dataclass(frozen=True)
class TemplateField:
    key: str
    label: str
    placeholder: str
    pattern: str  # the whole value must match
    help: str
    required: bool = True
    takes_topic: bool = False  # a topic readers want can fill it


@dataclass(frozen=True)
class SourcePlan:
    """What a template turns its fields into (the arguments of service.create_source)."""

    name: str
    site_url: str
    platform: str
    platform_config: dict
    run_interval_minutes: int
    topics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceTemplate:
    id: str
    name: str
    description: str
    platform: str
    fields: tuple[TemplateField, ...]
    plan: Callable[[dict[str, str]], SourcePlan]


def _subreddit(sort: str, time_filter: str | None, interval: int, suffix: str):
    def plan(values: dict[str, str]) -> SourcePlan:
        name = values["subreddit"].removeprefix("r/")
        config = {"subreddit": name, "sort": sort} | (
            {"time_filter": time_filter} if time_filter else {}
        )
        return SourcePlan(
            name=f"r/{name}{suffix}",
            site_url=f"https://www.reddit.com/r/{name}",
            platform="reddit",
            platform_config=config,
            run_interval_minutes=interval,
            topics=[name],
        )

    return plan


def _rss(values: dict[str, str]) -> SourcePlan:
    return SourcePlan(
        name=values["name"],
        site_url=values["feed_url"],
        platform="rss",
        platform_config={"feed_url": values["feed_url"]},
        run_interval_minutes=60,
    )


def _x_topic(values: dict[str, str]) -> SourcePlan:
    topic = values["topic"]
    return SourcePlan(
        name=f"{topic} on X",
        site_url=f"https://x.com/search?q={quote(topic)}",
        platform="x_search",
        # Popular posts only, so the feed isn't a firehose.
        platform_config={"query": f"{topic} min_faves:100"},
        run_interval_minutes=120,
        topics=[topic],
    )


def _x_user(values: dict[str, str]) -> SourcePlan:
    username = values["username"].lstrip("@")
    return SourcePlan(
        name=f"@{username} on X",
        site_url=f"https://x.com/{username}",
        platform="x",
        platform_config={"username": username},
        run_interval_minutes=120,
    )


def _pinterest(values: dict[str, str]) -> SourcePlan:
    username, board = values["username"], values.get("board") or ""
    path = f"{username}/{board}" if board else username
    return SourcePlan(
        name=f"Pinterest {path}",
        site_url=f"https://www.pinterest.com/{path}/",
        platform="pinterest",
        platform_config={"username": username} | ({"board": board} if board else {}),
        run_interval_minutes=240,
    )


_SUBREDDIT_FIELD = TemplateField(
    "subreddit",
    "Subreddit",
    "python",
    r"^(r/)?[A-Za-z0-9_]{2,21}$",
    "without the r/",
    takes_topic=True,
)
_TOPICS_FIELD = TemplateField(
    "topics",
    "Topics",
    "news, world",
    r"^[^,]{1,50}(,[^,]{1,50}){0,9}$",
    "comma-separated, tagged on every post",
    required=False,
)

TEMPLATES: tuple[SourceTemplate, ...] = (
    SourceTemplate(
        "rss_feed",
        "News site or blog",
        "Any RSS or Atom feed: most news sites, blogs and podcasts have one.",
        "rss",
        (
            TemplateField("name", "Name", "BBC World", r"^.{1,200}$", "shown on its posts"),
            TemplateField(
                "feed_url",
                "Feed URL",
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                r"^https?://\S{1,2000}$",
                "an http(s) link to the feed",
            ),
            _TOPICS_FIELD,
        ),
        _rss,
    ),
    SourceTemplate(
        "subreddit_hot",
        "Subreddit",
        "What's hot in a subreddit, checked every hour.",
        "reddit",
        (_SUBREDDIT_FIELD,),
        _subreddit("hot", None, 60, ""),
    ),
    SourceTemplate(
        "subreddit_top_daily",
        "Subreddit's best of the day",
        "A subreddit's top posts of the day, checked every six hours.",
        "reddit",
        (_SUBREDDIT_FIELD,),
        _subreddit("top", "day", 360, " (top today)"),
    ),
    SourceTemplate(
        "x_topic",
        "Topic on X",
        "Popular posts (100+ likes) about a topic, read through Nitter, which is often down.",
        "x_search",
        (
            TemplateField(
                "topic", "Topic", "#AI", r"^.{2,100}$", "words or a #hashtag", takes_topic=True
            ),
        ),
        _x_topic,
    ),
    SourceTemplate(
        "x_user",
        "Account on X",
        "One account's posts, read through Nitter, which is often down.",
        "x",
        (
            TemplateField(
                "username", "Username", "nasa", r"^@?[A-Za-z0-9_]{1,15}$", "with or without @"
            ),
        ),
        _x_user,
    ),
    SourceTemplate(
        "pinterest",
        "Pinterest user or board",
        "A public Pinterest user's pins, or one of their boards.",
        "pinterest",
        (
            TemplateField("username", "Username", "nasa", _SLUG, _SLUG_HELP),
            TemplateField(
                "board",
                "Board",
                "space",
                r"^[a-z0-9_-]{1,100}$",
                "optional: the board's name in its URL",
                required=False,
            ),
        ),
        _pinterest,
    ),
)


def available_templates() -> list[SourceTemplate]:
    return [t for t in TEMPLATES if is_platform_supported(t.platform)]


def get_template(template_id: str) -> SourceTemplate:
    for template in available_templates():
        if template.id == template_id:
            return template
    raise HTTPException(status_code=404, detail="No such template")


def create_from_template(
    template_id: str, raw_values: dict[str, str], db: Session
) -> tuple[GeneratorSource, User]:
    """Make the source and its bot account. 422 names the first bad field."""
    template = get_template(template_id)
    values = _checked(template, raw_values)
    plan = template.plan(values)
    topics = plan.topics + _split_topics(values.get("topics", ""))
    source = service.create_source(
        plan.name,
        plan.site_url,
        db,
        description=template.description,
        config={"topics": list(dict.fromkeys(topics))[:MAX_SOURCE_TOPICS]},
        run_interval_minutes=plan.run_interval_minutes,
        platform=plan.platform,
        platform_config=plan.platform_config,
    )
    bot = _make_bot(plan.name, db)
    service.attach_profile(typing.cast(int, source.id), typing.cast(int, bot.id), db)
    return source, bot


def _checked(template: SourceTemplate, raw: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for f in template.fields:
        value = (raw.get(f.key) or "").strip()
        if not value:
            if f.required:
                raise HTTPException(status_code=422, detail=f"{f.label} is required")
            continue
        if not re.fullmatch(f.pattern, value):
            raise HTTPException(status_code=422, detail=f"{f.label}: {f.help}")
        values[f.key] = value
    return values


def _split_topics(raw: str) -> list[str]:
    return [t.strip() for t in raw.split(",") if t.strip()]


def _make_bot(source_name: str, db: Session) -> User:
    """An account to post as. Its password is random and never shown, so no one signs in as it."""
    base = _USERNAME_UNSAFE.sub("_", source_name).strip("_.-").lower() or "source"
    base = base[: MAX_USERNAME_LEN - len(BOT_SUFFIX) - 4]
    username, n = f"{base}{BOT_SUFFIX}", 1
    while db.query(User.id).filter(User.username == username).first() is not None:
        n += 1
        username = f"{base}{BOT_SUFFIX}{n}"
    bot = User(username=username, email=None, email_verified=True)
    bot.set_password(secrets.token_urlsafe(32))
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot
