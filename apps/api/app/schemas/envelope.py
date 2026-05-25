"""API 응답 wrapper — `docs/api/common.md` §2.1."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T

    @classmethod
    def of(cls, data: T) -> Envelope[T]:
        return cls(data=data)
