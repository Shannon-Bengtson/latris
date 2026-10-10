"""Help documentation endpoints.

These routes serve static help topics — no project root required.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from latris.server.help import get_topic, list_topics

router = APIRouter(prefix="/api/help", tags=["help"])


@router.get("/topics")
def get_help_topics() -> dict[str, Any]:
    topics = list_topics()
    return {"topics": topics, "count": len(topics)}


@router.get("/topics/{topic_id}")
def get_help_topic(topic_id: str) -> dict[str, Any]:
    topic = get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Help topic '{topic_id}' not found")
    return {"topic": topic.model_dump(mode="json")}
