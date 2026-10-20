"""Generator platforms: the adapter contract (base.py), shared RSS plumbing
(feeds.py) and the public RSS adapter (rss.py). Which adapters a running app
has is decided by its edition (app/plugins.py).
"""

from .base import (
    PLATFORM_WEB,
    PlatformAdapter,
    PlatformConfigError,
    get_adapter,
    is_platform_supported,
    supported_platforms,
)

__all__ = [
    "PLATFORM_WEB",
    "PlatformAdapter",
    "PlatformConfigError",
    "get_adapter",
    "is_platform_supported",
    "supported_platforms",
]
