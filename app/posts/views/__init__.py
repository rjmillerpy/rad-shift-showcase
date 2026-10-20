"""Posts API surface — aggregates the split views into a single router."""

from fastapi import APIRouter

from .chronicle import router as _chronicle_router
from .crud import router as _crud_router
from .feeds import router as _feeds_router
from .search import router as _search_router
from .toggles import router as _toggles_router

posts_router = APIRouter()
# Router order matters for FastAPI path matching: routes with fixed segments
# ("/algo", "/media", "/following", "/chronicle", "/search/posts", …) must be
# registered BEFORE the /{post_id} catch-all in crud.
posts_router.include_router(_feeds_router)
posts_router.include_router(_chronicle_router)
posts_router.include_router(_search_router)
posts_router.include_router(_toggles_router)
posts_router.include_router(_crud_router)

__all__ = ["posts_router"]
