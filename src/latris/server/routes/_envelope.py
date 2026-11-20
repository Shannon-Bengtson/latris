"""The response envelope most routes share: ``{"result": …, "commit_sha": …}``. Typed (``Result[StoryDoc]``)
so the API description — and the app's generated types — say what ``result`` is."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    result: T
    commit_sha: str | None = None  # the change's commit, for a route that makes one
