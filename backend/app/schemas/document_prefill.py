"""Response shape for a matter's document readiness record."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentPrefillTemplate(BaseModel):
    template_id: str
    title: str
    format: str = "markdown"
    category: Optional[str] = None
    status: str
    reason: Optional[str] = None
    fields: int = 0
    filled: int = 0
    percent: int = 0
    missing_required: int = 0
    missing_required_names: list[str] = Field(default_factory=list)
    review: int = 0
    review_names: list[str] = Field(default_factory=list)
    rank_reasons: list[str] = Field(default_factory=list)
    coverage: dict[str, Any] = Field(default_factory=dict)


class DocumentPrefillReadiness(BaseModel):
    """What the last prefill run prepared, and whether the matter moved since."""

    event_id: str
    prepared_at: str
    trigger_event: Optional[str] = None
    #: The matter's fill-relevant facts changed after this run. Opening a
    #: document still fills from live data; only these counts are old.
    stale: bool = False
    ready: int = 0
    templates: list[DocumentPrefillTemplate] = Field(default_factory=list)
