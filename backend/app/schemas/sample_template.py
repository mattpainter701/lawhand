"""Pydantic schemas for the global SampleTemplate catalog."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.matter_document import MatterDocumentResponse


class SampleTemplateResponse(BaseModel):
    id: str
    slug: str
    title: str
    category: str
    jurisdictions: Optional[list[str]] = None
    description: Optional[str] = None
    format: str
    field_count: Optional[int] = None
    variable_schema: Optional[dict[str, Any]] = None
    provenance: Optional[dict[str, Any]] = None
    source_filename: Optional[str] = None
    source_sha256: Optional[str] = None
    source_file_size: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def stringify_id(cls, value: Any) -> Any:
        return str(value) if value is not None else None

    class Config:
        from_attributes = True


class SampleTemplateListResponse(BaseModel):
    items: list[SampleTemplateResponse]
    total: int


class SampleTemplateRenderRequest(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict, max_length=200)
    matter_id: Optional[str] = Field(default=None, max_length=100)

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if len(key) > 100:
                raise ValueError("Variable names may not exceed 100 characters")
            if len(item) > 10_000:
                raise ValueError(f"Variable {key!r} exceeds 10,000 characters")
        return value


class SampleTemplateSmartFillRequest(BaseModel):
    matter_id: str = Field(min_length=1, max_length=100)
    variables: Optional[list[str]] = Field(default=None, max_length=200)


class SampleTemplateSmartFillResponse(BaseModel):
    sample_id: str
    matter_id: Optional[str] = None
    variables: list[dict[str, Any]]


class SampleTemplateSaveToMatterRequest(SampleTemplateRenderRequest):
    """Fill a global library form and file the PDF on one matter."""

    matter_id: str = Field(min_length=1, max_length=100)
    folder_id: Optional[uuid.UUID] = None
    verified_fields: list[str] = Field(default_factory=list, max_length=200)


class SampleTemplateSaveToMatterResponse(BaseModel):
    sample_id: str
    matter_id: str
    matter_document_id: str
    matter_document: Optional[MatterDocumentResponse] = None
    output_filename: str
    storage_backend: Optional[str] = None
    storage_warning: Optional[str] = None
