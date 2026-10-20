"""Pydantic request and response schemas for auth endpoints."""

from pydantic import BaseModel, Field

from app.common.schema import FrozenModel


class AuthData(BaseModel):
    username: str
    password: str
    email: str | None = None


class PromoteAdminRequest(BaseModel):
    secret: str = Field(..., min_length=1)


class LoginResponse(FrozenModel):
    access_token: str
    email_verified: bool
