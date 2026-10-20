"""Profile API endpoints — /me, /me/*-settings, /me/upload-profile-pic, /{username}."""

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.auth_jwt import AuthJWT, AuthJWTException
from app.common.db import get_db
from app.common.deps import required_user
from app.common.schema import MessageResponse
from app.common.utils import get_user

from .constants import (
    DEFAULT_AGORA_SETTINGS,
    DEFAULT_ALGO_SETTINGS,
    DEFAULT_BUBBLE_SETTINGS,
    DEFAULT_CHRONICLE_SETTINGS,
    MAX_USERNAME_PATH_LEN,
)
from .schema import (
    AgoraSettingsRequest,
    AgoraSettingsResponse,
    AlgoSettingsRequest,
    AlgoSettingsResponse,
    BubbleSettingsRequest,
    BubbleSettingsResponse,
    ChronicleSettingsRequest,
    ChronicleSettingsResponse,
    ProfileData,
    ProfilePictureResponse,
    ProfileResponse,
)
from .service import (
    _get_user_profile,
    _update_profile,
    _upload_profile_picture,
    apply_settings_update,
    get_merged_settings,
)

profile_router = APIRouter()


@profile_router.get("/me")
def get_my_profile(
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    return ProfileResponse.model_validate(_get_user_profile(user, current_user=user, db=db))


@profile_router.put("/me")
def update_profile(
    data: ProfileData,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    _update_profile(user, data, db)
    return MessageResponse(message="Profile updated")


@profile_router.post("/me/upload-profile-pic")
def upload_profile_picture(
    file: UploadFile = File(...),
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> ProfilePictureResponse:
    if file.filename == "":
        raise HTTPException(status_code=400, detail="Empty filename")

    success, url_or_error = _upload_profile_picture(user, {"file": file}, db)
    if not success:
        raise HTTPException(status_code=500, detail=url_or_error)
    return ProfilePictureResponse(message="Profile picture uploaded", url=url_or_error)


# ── Settings (algo / bubble / chronicle / agora) ────────────────────────────
#
# The four settings surfaces are otherwise-identical GET+PUT pairs. We keep
# the routes explicit so the OpenAPI docs stay clean, but each handler is a
# two-line delegation to the shared service helpers.


@profile_router.get("/me/algo-settings")
def get_algo_settings(user: User = Depends(required_user)) -> AlgoSettingsResponse:
    return AlgoSettingsResponse.model_validate(
        get_merged_settings(user, "algo_settings", DEFAULT_ALGO_SETTINGS)
    )


@profile_router.put("/me/algo-settings")
def update_algo_settings(
    body: AlgoSettingsRequest,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> AlgoSettingsResponse:
    return AlgoSettingsResponse.model_validate(
        apply_settings_update(user, "algo_settings", DEFAULT_ALGO_SETTINGS, body, db)
    )


@profile_router.get("/me/bubble-settings")
def get_bubble_settings(user: User = Depends(required_user)) -> BubbleSettingsResponse:
    return BubbleSettingsResponse.model_validate(
        get_merged_settings(user, "bubble_settings", DEFAULT_BUBBLE_SETTINGS)
    )


@profile_router.put("/me/bubble-settings")
def update_bubble_settings(
    body: BubbleSettingsRequest,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> BubbleSettingsResponse:
    return BubbleSettingsResponse.model_validate(
        apply_settings_update(user, "bubble_settings", DEFAULT_BUBBLE_SETTINGS, body, db)
    )


@profile_router.get("/me/chronicle-settings")
def get_chronicle_settings(user: User = Depends(required_user)) -> ChronicleSettingsResponse:
    return ChronicleSettingsResponse.model_validate(
        get_merged_settings(user, "chronicle_settings", DEFAULT_CHRONICLE_SETTINGS)
    )


@profile_router.put("/me/chronicle-settings")
def update_chronicle_settings(
    body: ChronicleSettingsRequest,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> ChronicleSettingsResponse:
    return ChronicleSettingsResponse.model_validate(
        apply_settings_update(user, "chronicle_settings", DEFAULT_CHRONICLE_SETTINGS, body, db)
    )


@profile_router.get("/me/agora-settings")
def get_agora_settings(user: User = Depends(required_user)) -> AgoraSettingsResponse:
    return AgoraSettingsResponse.model_validate(
        get_merged_settings(user, "agora_settings", DEFAULT_AGORA_SETTINGS)
    )


@profile_router.put("/me/agora-settings")
def update_agora_settings(
    body: AgoraSettingsRequest,
    user: User = Depends(required_user),
    db: Session = Depends(get_db),
) -> AgoraSettingsResponse:
    return AgoraSettingsResponse.model_validate(
        apply_settings_update(user, "agora_settings", DEFAULT_AGORA_SETTINGS, body, db)
    )


# ── Public profile — /{username} is a catch-all so it stays LAST ───────────


@profile_router.get("/{username}")
def get_user_profile(
    username: str = Path(..., min_length=1, max_length=MAX_USERNAME_PATH_LEN),
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    user = get_user(username, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current_user = None
    try:
        Authorize.jwt_optional()
        subject = Authorize.get_jwt_subject()
        if subject:
            current_user = get_user(subject, db)
    except AuthJWTException:
        current_user = None  # Public read; unauth OK by design.
    return ProfileResponse.model_validate(_get_user_profile(user, current_user=current_user, db=db))
