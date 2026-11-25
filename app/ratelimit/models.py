"""One counter per key and window (a fixed window: e.g. one per minute)."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import Base


class RateLimitWindow(Base):
    __tablename__ = "rate_limit_windows"

    # "<policy>:user:<username>" or "<policy>:ip:<address>"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    count: Mapped[int] = mapped_column(Integer)
