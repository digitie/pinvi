"""API 응답 wrapper — `docs/api/common.md` §2.1."""

from __future__ import annotations

from pydantic import BaseModel


class Envelope[T](BaseModel):
    data: T

    @classmethod
    def of(cls, data: T) -> Envelope[T]:
        return cls(data=data)
