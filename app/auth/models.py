import bcrypt as _bcrypt
from sqlalchemy import JSON, Boolean, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from app.auth import constants as auth_constants
from app.auth.constants import MAX_PASSWORD_BYTES
from app.common.db import Base

followers = Table(
    "followers",
    Base.metadata,
    Column("follower_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("followed_id", Integer, ForeignKey("users.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    verification_token_expires = Column(Integer, nullable=True)
    bio = Column(Text, nullable=True)
    profile_picture_url = Column(String, nullable=True)
    algo_settings = Column(JSON, nullable=True)
    bubble_settings = Column(JSON, nullable=True)
    chronicle_settings = Column(JSON, nullable=True)
    agora_settings = Column(JSON, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)

    posts = relationship("PostModel", back_populates="user", cascade="all, delete-orphan")
    followed = relationship(
        "User",
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref="followers",
    )
    reposts = relationship("Repost", back_populates="user")

    def set_password(self, password: str) -> None:
        encoded = password.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            # Signup validation rejects these first; this guards other callers
            # from silently hashing only a prefix of the password.
            raise ValueError(f"password longer than {MAX_PASSWORD_BYTES} bytes")
        self.password_hash = _bcrypt.hashpw(
            encoded, _bcrypt.gensalt(rounds=auth_constants.BCRYPT_ROUNDS)
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        # Truncate exactly as bcrypt 4 did implicitly: accounts created before
        # the 72-byte limit was enforced were hashed from the first 72 bytes,
        # and bcrypt 5 raises on longer input instead of truncating.
        return _bcrypt.checkpw(
            password.encode("utf-8")[:MAX_PASSWORD_BYTES],
            self.password_hash.encode("utf-8"),
        )
