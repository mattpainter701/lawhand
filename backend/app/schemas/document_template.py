"""Pydantic schemas for DocumentTemplate."""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

CATEGORIES = ["engagement_letter", "retainer", "NDA", "motion", "other"]


class DocumentTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str
    category: str = "other"
    description: Optional[str] = None
    visibility: Optional[str] = "tenant"
    layer: Optional[str] = None
    status: Optional[str] = "draft"
    format: Optional[str] = "markdown"
    module: Optional[str] = None
    stage: Optional[str] = None
    jurisdiction: Optional[str] = None
    kind: Optional[str] = None
    variable_schema: Optional[dict[str, Any]] = None
    signer_roles: Optional[list[dict[str, Any]]] = None
    branding_profile: Optional[dict[str, Any]] = None


class DocumentTemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    body: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[str] = None
    layer: Optional[str] = None
    format: Optional[str] = None
    module: Optional[str] = None
    stage: Optional[str] = None
    jurisdiction: Optional[str] = None
    kind: Optional[str] = None
    variable_schema: Optional[dict[str, Any]] = None
    signer_roles: Optional[list[dict[str, Any]]] = None
    branding_profile: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    #: Version metadata, not a template attribute: it labels the history row
    #: this edit creates rather than anything stored on the template itself.
    change_summary: Optional[str] = Field(None, max_length=500)


class DocumentTemplateCopyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a name for the new template")
        return value.strip()


class DocumentTemplateVersionSummary(BaseModel):
    version_no: int
    title: str
    format: Optional[str] = None
    category: Optional[str] = None
    body_sha256: str
    source_sha256: Optional[str] = None
    source_filename: Optional[str] = None
    is_active: bool
    field_count: int
    change_summary: Optional[str] = None
    created_by_user_id: Optional[str] = None
    created_at: str


class DocumentTemplateVersionDetail(DocumentTemplateVersionSummary):
    body: str
    variable_schema: Optional[dict[str, Any]] = None


class DocumentTemplateVersionListResponse(BaseModel):
    template_id: str
    current_version_no: int
    tested_version_no: Optional[int] = None
    published_version_no: Optional[int] = None
    total: int
    versions: list[DocumentTemplateVersionSummary]


class DocumentTemplateFillCoverage(BaseModel):
    """How much of a template arrives filled when a matter is named.

    Both editors already report *discovery* coverage — fields found, fields
    needing review. This is the number that decides whether a template is worth
    having: ``fills`` of ``total`` boxes carry a value without anyone typing
    it. The remaining buckets are reported separately because they fail
    differently, and a firm has to be able to tell them apart:
    ``name_matched`` works today and breaks silently on a rename,
    ``unresolved`` is already broken, and ``manual`` is correct on purpose.
    """

    total: int
    fills: int
    bound: int
    name_matched: int
    manual: int
    signature: int
    unresolved: int
    unbound: int


class DocumentTemplateResponse(BaseModel):
    id: str
    title: str
    body: str
    category: str
    description: Optional[str] = None
    visibility: Optional[str] = "tenant"
    layer: Optional[str] = None
    status: Optional[str] = "draft"
    format: Optional[str] = "markdown"
    module: Optional[str] = None
    stage: Optional[str] = None
    jurisdiction: Optional[str] = None
    kind: Optional[str] = None
    variable_schema: Optional[dict[str, Any]] = None
    #: Derived on read, never accepted on write.
    fill_coverage: Optional[DocumentTemplateFillCoverage] = None
    signer_roles: Optional[list[dict[str, Any]]] = None
    branding_profile: Optional[dict[str, Any]] = None
    source_filename: Optional[str] = None
    source_content_type: Optional[str] = None
    source_sha256: Optional[str] = None
    source_file_size: Optional[int] = None
    source_evidence_sha256: Optional[str] = None
    source_provenance: Optional[dict[str, Any]] = None
    source_ready: bool = True
    last_test_rendered_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[str] = None
    is_active: bool
    current_version_no: int = 0
    tested_version_no: Optional[int] = None
    published_version_no: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "approved_by_user_id", mode="before")
    @classmethod
    def stringify_uuid_fields(cls, value: Any) -> Any:
        return str(value) if value is not None else None

    class Config:
        from_attributes = True


class DocumentTemplateLibrarySummary(BaseModel):
    total: int
    active: int
    inactive: int
    ready: int
    source_missing: int


class DocumentTemplateListResponse(BaseModel):
    items: list[DocumentTemplateResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
    summary: DocumentTemplateLibrarySummary


class DocumentTemplateQueue(BaseModel):
    total: int
    items: list[DocumentTemplateResponse]


class DocumentTemplateQueueResponse(BaseModel):
    needs_attention: DocumentTemplateQueue
    continue_setup: DocumentTemplateQueue
    awaiting_publish: DocumentTemplateQueue
    published: DocumentTemplateQueue


class DocumentTemplateRenderRequest(BaseModel):
    folder_id: Optional[uuid.UUID] = None
    # When supplied, bind the generated matter document to the caller's
    # resumable fill session. Omitted for previews and legacy render callers.
    fill_session_id: Optional[uuid.UUID] = None
    variables: dict[str, str] = Field(default_factory=dict, max_length=400)
    matter_id: Optional[str] = None
    include_suggestions: bool = False
    # Binary PDF previews persist non-PII evidence.  Activation previews must
    # exercise representative values; generation previews bind an exact value
    # set and matter to the later save request.
    preview_purpose: Literal["draft", "activation", "generation"] = "draft"
    preview_id: Optional[uuid.UUID] = None
    # Matter-ready output is non-editable by default. The renderer fails rather
    # than clipping or substituting unsupported glyphs.
    flatten_pdf: bool = True
    # DOCX templates may produce a review-bound PDF suitable for e-signature.
    # The retained template source remains DOCX and is never overwritten.
    convert_to_pdf: bool = False
    # The variables the preparer marked verified before saving. Names only,
    # recorded on the generated document and its event; never a gate.
    verified_fields: list[str] = Field(default_factory=list, max_length=400)

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, value: dict[str, str]) -> dict[str, str]:
        total = 0
        for key, item in value.items():
            if len(key) > 100:
                raise ValueError("Variable names may not exceed 100 characters")
            if len(item) > 10_000:
                raise ValueError(f"Variable {key!r} exceeds 10,000 characters")
            total += len(item)
        if total > 250_000:
            raise ValueError("Combined variable values exceed 250,000 characters")
        return value

    @model_validator(mode="after")
    def validate_verified_fields(self):
        names: list[str] = []
        for name in self.verified_fields:
            if len(name) > 100:
                raise ValueError("Verified field names may not exceed 100 characters")
            if name not in self.variables:
                raise ValueError(
                    "verified_fields names a variable that is not in this request"
                )
            if name not in names:
                names.append(name)
        self.verified_fields = names
        return self


class DocumentTemplatePublishRequest(BaseModel):
    change_summary: Optional[str] = Field(None, max_length=500)


class DocumentTemplateWordDeriveRequest(BaseModel):
    """Explicit Word span selections used to create a fresh draft source."""

    fields: list[dict[str, Any]] = Field(default_factory=list, max_length=400)
    source_review: dict[str, str] = Field(default_factory=dict, max_length=500)
    source_mode: Literal["prose", "form"] | None = None
    reviewed_schema: dict[str, Any] | None = None


class DocumentTemplateWordCleanupRequest(BaseModel):
    expected_source_sha256: Optional[str] = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    expected_version_no: Optional[int] = Field(default=None, ge=0)
    paragraph_ordinal: int = Field(ge=0, le=2000)
    start: int = Field(ge=0, le=20000)
    end: int = Field(gt=0, le=20000)
    original_text: str = Field(min_length=1, max_length=10000)
    replacement_text: str = Field(max_length=10000)


class DocumentTemplateVariableSuggestion(BaseModel):
    variable: str
    suggested_value: Optional[str] = None
    source_type: Optional[str] = None
    source_field: Optional[str] = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    review_required: bool = True


class DocumentTemplateRenderResponse(BaseModel):
    rendered: str
    matter_document_id: Optional[str] = None
    variable_suggestions: Optional[list[DocumentTemplateVariableSuggestion]] = None
    output_format: str = "markdown"
    output_filename: Optional[str] = None
    download_url: Optional[str] = None
    storage_backend: Optional[str] = None
    storage_provider: Optional[str] = None
    storage_warning: Optional[str] = None
    # Signing readiness of the saved document, so the caller that just
    # generated it can offer "Send for signature" without a second listing
    # round trip. Empty until a document is saved into a matter.
    signing_roles: list[str] = Field(default_factory=list)
    signing_placement_required: bool = False
    positioned_fields: list[dict[str, Any]] = Field(default_factory=list)
    signing_placement_problems: list[dict[str, Any]] = Field(default_factory=list)
    # Field, filled and verified counts recorded on the saved document.
    generation_summary: Optional[dict[str, Any]] = None


class DocumentTemplateSmartFillRequest(BaseModel):
    published: bool = False
    matter_id: Optional[str] = None
    variables: Optional[list[str]] = None


class DocumentTemplateSmartFillResponse(BaseModel):
    template_id: str
    matter_id: Optional[str] = None
    variables: list[DocumentTemplateVariableSuggestion]


class DocumentTemplateUploadAnalysisResponse(BaseModel):
    title: str
    format: str
    body: str
    body_preview: str
    extracted_text: str
    source_paragraphs: list[dict[str, Any]] = Field(default_factory=list)
    # Opaque, short-lived handoff from analysis to creation.  Reusing it keeps
    # an expensive OCR pass from running a second time while the reviewed
    # schema is still validated against the server-discovered field map.
    analysis_token: Optional[str] = None
    suggested_variable_schema: dict[str, Any] = Field(default_factory=dict)
    detected_branding_profile: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DocumentTemplateBindingOption(BaseModel):
    path: str
    label: str
    group: str
    field_type: str | None = None
    options: list[str] = Field(default_factory=list)


class DocumentTemplateCollectionOption(BaseModel):
    name: str
    label: str
    item_fields: list[str]


class DocumentTemplateLibraryField(DocumentTemplateBindingOption):
    template_count: int
    suggested_name: str | None = None


class DocumentTemplateFieldLibrary(BaseModel):
    fields: list[DocumentTemplateLibraryField]


class DocumentTemplateFieldUsagePlacement(BaseModel):
    name: str
    label: str | None = None


class DocumentTemplateFieldUsageItem(BaseModel):
    template_id: uuid.UUID
    title: str
    status: str | None = None
    current_version_no: int
    fields: list[DocumentTemplateFieldUsagePlacement]


class DocumentTemplateFieldUsage(BaseModel):
    items: list[DocumentTemplateFieldUsageItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class DocumentTemplateCardField(BaseModel):
    """One field on a card, as the editor rail presents it."""

    key: str
    label: str
    path: str
    value_kind: str = "text"
    #: The candidate alias, offered as a starting automation key so a customer
    #: does not have to invent a name that happens to make Smart Fill fire.
    suggested_name: Optional[str] = None
    #: Whether this field has an "every instance, joined" form.
    supports_all_instances: bool = False
    #: The pre-card paths that resolve to this field. Sent so a client can map
    #: a stored binding — which may be either spelling — back to its card
    #: without keeping a second copy of the legacy table and letting it drift.
    legacy_paths: list[str] = Field(default_factory=list)


class DocumentTemplateCard(BaseModel):
    """One addressable subject and the fields that belong to it."""

    key: str
    label: str
    kind: str
    group: str
    max_instances: int
    #: How many instances exist on the requested matter. ``None`` when no
    #: matter was named — which is not the same as zero, and the editor must
    #: not render it as "no defendants on this matter".
    instance_count: Optional[int] = None
    fields: list[DocumentTemplateCardField]


class DocumentTemplateCardCatalogue(BaseModel):
    """The card vocabulary a template author may draw on.

    Served alongside the flat binding catalogue rather than replacing it: the
    editor migrates to cards surface by surface, and a template published
    before cards keeps resolving through exactly the paths it was reviewed with.
    """

    cards: list[DocumentTemplateCard]
    operators: list[str]


class DocumentTemplateBindingCatalogue(BaseModel):
    """The closed vocabulary a template author may draw on.

    Served to the editor so a customer picks a data source from a list instead
    of guessing the field name that happens to make Smart Fill fire.
    """

    bindings: list[DocumentTemplateBindingOption]
    collections: list[DocumentTemplateCollectionOption]
    operators: list[str]
    #: Every normalised field name Smart Fill can fill without a declared
    #: binding. The editor needs this to tell an author which fields are
    #: relying on a name match — the state that works today and stops working
    #: the moment the field is renamed. Served rather than reimplemented so
    #: the client cannot hold a second, drifting copy of the rule.
    smart_fill_names: list[str] = Field(default_factory=list)


class DocumentTemplateOutlineRun(BaseModel):
    text: str
    start: int
    end: int
    bold: bool = False
    italic: bool = False
    underline: bool = False


class DocumentTemplateOutlineMarker(BaseModel):
    kind: str
    keyword: str
    name: str = ""


class DocumentTemplateOutlineParagraph(BaseModel):
    ordinal: int
    text: str
    style: str
    container: str
    runs: list[DocumentTemplateOutlineRun] = Field(default_factory=list)
    marker: Optional[DocumentTemplateOutlineMarker] = None
    alignment: str = "left"
    numbering: Optional[str] = None
    dynamic_field: bool = False


class DocumentTemplateSourceReviewCandidate(BaseModel):
    id: str
    source_text: str
    docx_anchor: dict[str, int]
    kind: str
    context: str


class DocumentTemplateOutlineResponse(BaseModel):
    """A Word template's paragraphs, addressed the way its fields are.

    Ordinals match the iterator that fills the template, so a span selected
    against this outline anchors to the same paragraph at generation time.
    """

    template_id: str
    paragraphs: list[DocumentTemplateOutlineParagraph]
    paragraph_count: int
    truncated: bool = False
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    review_candidates: list[DocumentTemplateSourceReviewCandidate] = Field(
        default_factory=list
    )
    review_truncated: bool = False
    source_mode_suggestion: Optional[dict[str, Any]] = None
