"""Auth API endpoints — signup, login, verify, resend, promote-admin."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.schema import AuthData, LoginResponse, PromoteAdminRequest
from app.auth.service import (
    PromotionResult,
    authenticate_user,
    promote_to_admin,
    register_user,
    resend_verification,
    verify_email,
)
from app.common.auth_jwt import AuthJWT
from app.common.db import get_db
from app.common.schema import MessageResponse

auth_router = APIRouter()

_PROMOTION_ERRORS: dict[PromotionResult, tuple[int, str]] = {
    PromotionResult.NOT_CONFIGURED: (503, "Admin promotion not configured"),
    PromotionResult.WRONG_SECRET: (403, "Invalid admin secret"),
    PromotionResult.USER_NOT_FOUND: (404, "User not found"),
}


@auth_router.post("/signup")
def signup(data: AuthData, db: Session = Depends(get_db)) -> MessageResponse:
    success, msg = register_user(data, db)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return MessageResponse(
        message="User created successfully. Please check your email to verify your account."
    )


@auth_router.post("/login")
def login(
    data: AuthData,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> LoginResponse:
    user = authenticate_user(data, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = Authorize.create_access_token(subject=user.username)
    return LoginResponse(access_token=token, email_verified=user.email_verified)


@auth_router.get("/verify")
def verify(token: str = Query(..., min_length=1), db: Session = Depends(get_db)) -> MessageResponse:
    success, msg = verify_email(token, db)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return MessageResponse(message=msg)


@auth_router.post("/resend-verification")
def resend(Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)) -> MessageResponse:
    Authorize.jwt_required()
    username = Authorize.get_jwt_subject()
    success, msg = resend_verification(username, db)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return MessageResponse(message=msg)


@auth_router.get("/protected")
def protected(Authorize: AuthJWT = Depends()) -> MessageResponse:
    Authorize.jwt_required()
    current_user = Authorize.get_jwt_subject()
    return MessageResponse(message=f"Hello {current_user}, you are authorized!")


@auth_router.post("/promote-admin")
def promote_admin(
    body: PromoteAdminRequest,
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Promote the current user to admin. Requires ADMIN_SECRET in request body."""
    Authorize.jwt_required()
    username = Authorize.get_jwt_subject()
    result = promote_to_admin(username, body.secret, db)
    if result is not PromotionResult.PROMOTED:
        status, detail = _PROMOTION_ERRORS[result]
        raise HTTPException(status_code=status, detail=detail)
    return MessageResponse(message=f"{username} is now an admin")
