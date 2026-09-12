from typing import Any

from pydantic import BaseModel, Field


class ResearchTask(BaseModel):
    id: str
    title: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    query: str = Field(min_length=1)
    status: str = "pending"


class SearchSource(BaseModel):
    id: str
    title: str
    url: str
    content: str = ""
    task_id: str


class TaskFact(BaseModel):
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class TaskSummary(BaseModel):
    task_id: str
    summary: str
    facts: list[TaskFact] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ResearchEvent(BaseModel):
    type: str
    status: str
    progress: int
    message: str
    topic: str
    task_id: str | None = None
    report: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
