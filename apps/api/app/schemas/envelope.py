"""API 응답 wrapper — `docs/api/common.md` §2.1."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Envelope[T](BaseModel):
    data: T

    @classmethod
    def of(cls, data: T) -> Envelope[T]:
        return cls(data=data)


class EnvelopeMeta(BaseModel):
    cursor: str | None = None
    has_more: bool | None = None
    total: int | None = None
    page: int | None = None
    limit: int | None = None
    version: int | None = None


class EnvelopeWithMeta[T](BaseModel):
    data: T
    meta: EnvelopeMeta = Field(default_factory=EnvelopeMeta)

    @classmethod
    def of(cls, data: T, *, meta: EnvelopeMeta) -> EnvelopeWithMeta[T]:
        return cls(data=data, meta=meta)
