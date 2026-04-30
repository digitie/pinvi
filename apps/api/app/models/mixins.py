from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

KST = ZoneInfo("Asia/Seoul")


def kst_now() -> datetime:
    return datetime.now(KST)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=kst_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=kst_now,
        onupdate=kst_now,
        nullable=False,
    )
