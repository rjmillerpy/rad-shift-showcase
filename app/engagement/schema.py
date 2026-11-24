"""The post event: what the API publishes and the aggregator reads.

Schema evolution: consumers ignore fields they don't know (Pydantic's
default), so a producer may add a field without breaking an older consumer.
Removing or retyping one needs a new schema_version and a consumer that
reads both first (expand, then contract, as with database migrations).
"""

import time
import uuid
from enum import StrEnum

from pydantic import Field

from app.common.schema import FrozenModel

SCHEMA_VERSION = 1


class PostEventType(StrEnum):
    CREATED = "post.created"
    LIKED = "post.liked"
    UNLIKED = "post.unliked"
    LAUGHED = "post.laughed"
    UNLAUGHED = "post.unlaughed"
    REPOSTED = "post.reposted"
    UNREPOSTED = "post.unreposted"
    SAVED = "post.saved"
    UNSAVED = "post.unsaved"
    SHARED = "post.shared"


# How much each event moves a post's trending score. Undo events cancel
# their counterpart exactly.
EVENT_WEIGHTS: dict[PostEventType, float] = {
    PostEventType.CREATED: 1.0,
    PostEventType.LIKED: 1.0,
    PostEventType.UNLIKED: -1.0,
    PostEventType.LAUGHED: 1.0,
    PostEventType.UNLAUGHED: -1.0,
    PostEventType.SAVED: 2.0,
    PostEventType.UNSAVED: -2.0,
    PostEventType.REPOSTED: 3.0,
    PostEventType.UNREPOSTED: -3.0,
    PostEventType.SHARED: 3.0,
}


class PostEvent(FrozenModel):
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    # Unique per event: the aggregator's deduplication key.
    event_id: str = Field(min_length=1, max_length=64)
    type: PostEventType
    post_id: int = Field(gt=0)
    # None for an anonymous share.
    user_id: int | None = Field(default=None, gt=0)
    # Unix seconds, when the API committed the change.
    occurred_at: float = Field(gt=0)

    @classmethod
    def new(cls, event_type: PostEventType, post_id: int, user_id: int | None) -> "PostEvent":
        return cls(
            event_id=uuid.uuid4().hex,
            type=event_type,
            post_id=post_id,
            user_id=user_id,
            occurred_at=time.time(),
        )
