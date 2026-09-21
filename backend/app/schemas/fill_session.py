"""Schemas for resumable fill sessions and the background packet save."""

import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FillSessionMemberInput(BaseModel):
    """One document of the packet as the browser last previewed it."""

    model_config = ConfigDict(extra="forbid")

    template_id: uuid.UUID
    variables: dict[str, str] = Field(default_factory=dict, max_length=400)
    preview_id: Optional[uuid.UUID] = None
    convert_to_pdf: bool = False
    output_format: Optional[str] = Field(default=None, max_length=20)
    #: The field names of this document that the preparer verified in the
    #: interview, mapped by the client from the shared interview key. Each must
    #: be a key of ``variables``; the render endpoint validates that.
    verified_fields: list[str] = Field(default_factory=list, max_length=400)


class FillSessionWrite(BaseModel):
    """Create or update the caller's own session; answers are stored encrypted."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[uuid.UUID] = None
    matter_id: Optional[uuid.UUID] = None
    template_id: Optional[uuid.UUID] = None
    set_id: Optional[uuid.UUID] = None
    title: str = Field(default="", max_length=300)
    versions: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, str] = Field(default_factory=dict, max_length=400)
    verified: list[str] = Field(default_factory=list, max_length=400)
    folder_id: Optional[uuid.UUID] = None


class FillSessionRenderRequest(BaseModel):
    """Save the packet in the background from the previews the user reviewed."""

    model_config = ConfigDict(extra="forbid")

    members: list[FillSessionMemberInput] = Field(default_factory=list, max_length=20)
    folder_id: Optional[uuid.UUID] = None


class FillSessionMemberStatus(BaseModel):
    template_id: str
    status: str
    matter_document_id: Optional[str] = None
    output_filename: Optional[str] = None
    output_format: Optional[str] = None
    #: Carried from the render response so a background-saved PDF can still be
    #: sent for signature after the page is reopened.
    signing_roles: list[str] = Field(default_factory=list)
    positioned_fields: list[dict[str, Any]] = Field(default_factory=list)
    signing_placement_required: bool = False
    detail: Optional[str] = None


class FillSessionResponse(BaseModel):
    id: uuid.UUID
    matter_id: Optional[uuid.UUID] = None
    template_id: Optional[uuid.UUID] = None
    set_id: Optional[uuid.UUID] = None
    title: str = ""
    status: str
    versions: dict[str, Any] = Field(default_factory=dict)
    #: Present only on a single-session read by its owner; never in a list.
    answers: Optional[dict[str, str]] = None
    verified: list[str] = Field(default_factory=list)
    members: list[FillSessionMemberStatus] = Field(default_factory=list)
    last_error: Optional[str] = None
    expires_at: str
    updated_at: str


class FillSessionListResponse(BaseModel):
    items: list[FillSessionResponse]
