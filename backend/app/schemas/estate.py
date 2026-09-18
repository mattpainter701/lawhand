"""Pydantic schemas for the Trust & Estate administration module."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrmResponse(BaseModel):
    """A response read straight from an ORM row.

    The estate sub-entity responses declare their identifiers as ``str`` while
    the rows carry ``uuid.UUID``; pydantic v2 does not coerce one to the other,
    so every child endpoint that returned a row failed response validation.
    Converting here keeps the wire format the frontend already reads.
    """

    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="before")
    @classmethod
    def _uuid_to_str(cls, value):
        return str(value) if isinstance(value, uuid.UUID) else value


# ── Events (activity log) ─────────────────────────────────────────────────────


class EstateEventCreate(BaseModel):
    event_type: str
    title: str
    content: Optional[str] = None


class EstateEventResponse(OrmResponse):
    id: str
    event_type: str
    title: str
    content: Optional[str]
    created_at: datetime


# ── Estate ────────────────────────────────────────────────────────────────────


class EstateCreate(BaseModel):
    estate_name: str
    estate_type: Optional[
        Literal[
            "probate",
            "trust_administration",
            "estate_planning",
            "guardianship",
            "conservatorship",
            "small_estate",
        ]
    ] = None
    representative_type: Optional[str] = None
    grantor: Optional[str] = None
    summary: Optional[str] = None
    jurisdiction: Optional[str] = None
    domicile_state: Optional[str] = None
    date_of_death: Optional[date] = None
    court_name: Optional[str] = None
    case_number: Optional[str] = None
    gross_estate_value: Optional[Decimal] = None
    net_estate_value: Optional[Decimal] = None
    matter_id: Optional[str] = None
    client_contact_id: Optional[str] = None


class EstateUpdate(BaseModel):
    estate_name: Optional[str] = None
    estate_type: Optional[
        Literal[
            "probate",
            "trust_administration",
            "estate_planning",
            "guardianship",
            "conservatorship",
            "small_estate",
        ]
    ] = None
    representative_type: Optional[str] = None
    grantor: Optional[str] = None
    status: Optional[Literal["active", "in_probate", "draft", "closed"]] = None
    summary: Optional[str] = None
    jurisdiction: Optional[str] = None
    domicile_state: Optional[str] = None
    date_of_death: Optional[date] = None
    court_name: Optional[str] = None
    case_number: Optional[str] = None
    gross_estate_value: Optional[Decimal] = None
    net_estate_value: Optional[Decimal] = None
    matter_id: Optional[str] = None
    client_contact_id: Optional[str] = None
    domicile_county: Optional[str] = None
    will_execution_date: Optional[date] = None
    appointment_date: Optional[date] = None
    first_publication_date: Optional[date] = None
    letters_issued_date: Optional[date] = None
    closing_statement_filed_date: Optional[date] = None


class KeyDate(BaseModel):
    label: str
    date: date


class EstateResponse(BaseModel):
    id: str
    estate_name: Optional[str]
    title: str
    estate_type: Optional[str]
    representative_type: Optional[str]
    grantor: Optional[str]
    status: str
    summary: Optional[str]
    jurisdiction: Optional[str]
    domicile_state: Optional[str]
    date_of_death: Optional[date]
    court_name: Optional[str]
    case_number: Optional[str]
    gross_estate_value: Optional[Decimal]
    net_estate_value: Optional[Decimal]
    estimated_value: Optional[
        str
    ]  # display-formatted gross value (frontend convenience)
    matter_id: Optional[str]
    client_contact_id: Optional[str]
    client_name: Optional[str]
    domicile_county: Optional[str] = None
    will_execution_date: Optional[date] = None
    probate_track: Optional[str] = None
    probate_determined_at: Optional[datetime] = None
    appointment_date: Optional[date] = None
    first_publication_date: Optional[date] = None
    letters_issued_date: Optional[date] = None
    closing_statement_filed_date: Optional[date] = None
    beneficiaries_count: int = 0
    missing_facts: List[str] = []
    unvalued_assets_count: int = 0
    unresolved_claims_count: int = 0
    pending_distributions_count: int = 0
    overdue_deadlines_count: int = 0
    attention_count: int = 0
    next_action: Optional[str] = None
    next_key_date: Optional[date]
    key_dates: List[KeyDate] = []
    created_at: datetime
    updated_at: datetime
    events: List[EstateEventResponse] = []


class EstateStats(BaseModel):
    total: int
    active: int
    in_probate: int
    draft: int
    closed: int
    total_beneficiaries: int
    total_gross_value: Decimal
    upcoming_deadlines: int


# ── Fiduciaries ───────────────────────────────────────────────────────────────


class FiduciaryCreate(BaseModel):
    name: str
    role: str = "executor"
    contact_id: Optional[str] = None
    appointment_date: Optional[date] = None
    is_primary: bool = False
    compensation_basis: Optional[str] = None
    compensation_amount: Optional[Decimal] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class FiduciaryUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    contact_id: Optional[str] = None
    appointment_date: Optional[date] = None
    is_primary: Optional[bool] = None
    compensation_basis: Optional[str] = None
    compensation_amount: Optional[Decimal] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class FiduciaryResponse(OrmResponse):
    id: str
    estate_id: str
    name: str
    role: str
    contact_id: Optional[str]
    appointment_date: Optional[date]
    is_primary: bool
    compensation_basis: Optional[str]
    compensation_amount: Optional[Decimal]
    email: Optional[str]
    phone: Optional[str]
    notes: Optional[str]
    created_at: datetime


# ── Beneficiaries ─────────────────────────────────────────────────────────────


class BeneficiaryCreate(BaseModel):
    name: str
    relationship: Optional[str] = None
    contact_id: Optional[str] = None
    beneficiary_type: Literal["specific", "residuary", "percentage", "contingent"] = (
        "residuary"
    )
    share_percentage: Optional[Decimal] = Field(default=None, ge=0, le=100)
    bequest_description: Optional[str] = None
    is_charity: bool = False
    charity_ein: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    distribution_status: Literal["pending", "partial", "complete"] = "pending"
    notes: Optional[str] = None


class BeneficiaryUpdate(BaseModel):
    name: Optional[str] = None
    relationship: Optional[str] = None
    contact_id: Optional[str] = None
    beneficiary_type: Optional[
        Literal["specific", "residuary", "percentage", "contingent"]
    ] = None
    share_percentage: Optional[Decimal] = Field(default=None, ge=0, le=100)
    bequest_description: Optional[str] = None
    is_charity: Optional[bool] = None
    charity_ein: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    distribution_status: Optional[Literal["pending", "partial", "complete"]] = None
    notes: Optional[str] = None


class BeneficiaryResponse(OrmResponse):
    id: str
    estate_id: str
    name: str
    relationship: Optional[str]
    contact_id: Optional[str]
    beneficiary_type: str
    share_percentage: Optional[Decimal]
    bequest_description: Optional[str]
    is_charity: bool
    charity_ein: Optional[str]
    email: Optional[str]
    address: Optional[str]
    distribution_status: str
    notes: Optional[str]
    created_at: datetime


# ── Assets ────────────────────────────────────────────────────────────────────


class AssetCreate(BaseModel):
    name: str
    category: str = "other"
    ownership_type: Optional[str] = None
    date_of_death_value: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    is_probate: bool = True
    institution: Optional[str] = None
    account_number_masked: Optional[str] = None
    valuation_date: Optional[date] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    ownership_type: Optional[str] = None
    date_of_death_value: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    is_probate: Optional[bool] = None
    institution: Optional[str] = None
    account_number_masked: Optional[str] = None
    valuation_date: Optional[date] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class AssetVerify(BaseModel):
    verification_status: Literal["verified", "unverified", "rejected"] = "verified"
    note: Optional[str] = Field(None, max_length=1000)


class AssetResponse(OrmResponse):
    source: str = "staff"
    verification_status: str = "verified"
    submitted_at: Optional[datetime] = None
    artifact_document_id: Optional[str] = None
    id: str
    estate_id: str
    name: str
    category: str
    ownership_type: Optional[str]
    date_of_death_value: Optional[Decimal]
    current_value: Optional[Decimal]
    is_probate: bool
    institution: Optional[str]
    account_number_masked: Optional[str]
    valuation_date: Optional[date]
    location: Optional[str]
    notes: Optional[str]
    created_at: datetime


# ── Liabilities / claims ──────────────────────────────────────────────────────


class LiabilityCreate(BaseModel):
    creditor_name: str
    claim_type: Literal[
        "debt", "funeral", "administration_expense", "tax", "secured", "unsecured"
    ] = "debt"
    amount: Decimal = Decimal("0")
    date_filed: Optional[date] = None
    bar_date: Optional[date] = None
    status: Literal["pending", "allowed", "disputed", "paid", "rejected"] = "pending"
    notes: Optional[str] = None


class LiabilityUpdate(BaseModel):
    creditor_name: Optional[str] = None
    claim_type: Optional[
        Literal[
            "debt", "funeral", "administration_expense", "tax", "secured", "unsecured"
        ]
    ] = None
    amount: Optional[Decimal] = None
    date_filed: Optional[date] = None
    bar_date: Optional[date] = None
    status: Optional[Literal["pending", "allowed", "disputed", "paid", "rejected"]] = (
        None
    )
    notes: Optional[str] = None


class LiabilityResponse(OrmResponse):
    id: str
    estate_id: str
    creditor_name: str
    claim_type: str
    amount: Decimal
    date_filed: Optional[date]
    bar_date: Optional[date]
    status: str
    notes: Optional[str]
    created_at: datetime


# ── Distributions ─────────────────────────────────────────────────────────────


class DistributionCreate(BaseModel):
    beneficiary_id: str
    asset_id: Optional[str] = None
    amount: Decimal = Decimal("0")
    distribution_type: str = "interim"
    distribution_date: Optional[date] = None
    status: str = "planned"
    check_number: Optional[str] = None
    notes: Optional[str] = None


class DistributionUpdate(BaseModel):
    beneficiary_id: Optional[str] = None
    asset_id: Optional[str] = None
    amount: Optional[Decimal] = None
    distribution_type: Optional[str] = None
    distribution_date: Optional[date] = None
    status: Optional[str] = None
    check_number: Optional[str] = None
    notes: Optional[str] = None


class DistributionResponse(OrmResponse):
    id: str
    estate_id: str
    beneficiary_id: str
    beneficiary_name: Optional[str] = None
    asset_id: Optional[str]
    amount: Decimal
    distribution_type: str
    distribution_date: Optional[date]
    status: str
    check_number: Optional[str]
    notes: Optional[str]
    created_at: datetime


# ── Deadlines ─────────────────────────────────────────────────────────────────


class DeadlineCreate(BaseModel):
    title: str
    deadline_type: Literal[
        "court_filing",
        "tax_706",
        "tax_1041",
        "tax_709",
        "tax_1040",
        "inventory",
        "accounting",
        "creditor_bar",
        "notice_heirs",
        "hhs_affidavit",
        "creditor_publication",
        "claims_disallowance",
        "nd_estate_tax",
        "elective_share",
        "closing_earliest",
        "pr_termination",
        "distribution",
        "task",
        "other",
    ] = "other"
    due_date: date
    status: Literal["pending", "in_progress", "complete", "overdue", "na"] = "pending"
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class DeadlineUpdate(BaseModel):
    title: Optional[str] = None
    deadline_type: Optional[
        Literal[
            "court_filing",
            "tax_706",
            "tax_1041",
            "tax_709",
            "tax_1040",
            "inventory",
            "accounting",
            "creditor_bar",
            "notice_heirs",
            "hhs_affidavit",
            "creditor_publication",
            "claims_disallowance",
            "nd_estate_tax",
            "elective_share",
            "closing_earliest",
            "pr_termination",
            "distribution",
            "task",
            "other",
        ]
    ] = None
    due_date: Optional[date] = None
    status: Optional[Literal["pending", "in_progress", "complete", "overdue", "na"]] = (
        None
    )
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class DeadlineResponse(OrmResponse):
    id: str
    estate_id: str
    title: str
    deadline_type: str
    due_date: date
    status: str
    assigned_to: Optional[str]
    completed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime


# ── Fiduciary accounting ──────────────────────────────────────────────────────


class AccountingEntryCreate(BaseModel):
    entry_date: date
    entry_type: Literal["receipt", "disbursement", "gain", "loss", "distribution"] = (
        "receipt"
    )
    account_class: Literal["principal", "income"] = "principal"
    amount: Decimal = Decimal("0")
    description: str
    payee_payor: Optional[str] = None
    asset_id: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class AccountingEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    entry_type: Optional[
        Literal["receipt", "disbursement", "gain", "loss", "distribution"]
    ] = None
    account_class: Optional[Literal["principal", "income"]] = None
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    payee_payor: Optional[str] = None
    asset_id: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class AccountingEntryResponse(OrmResponse):
    id: str
    estate_id: str
    entry_date: date
    entry_type: str
    account_class: str
    amount: Decimal
    description: str
    payee_payor: Optional[str]
    asset_id: Optional[str]
    reference_number: Optional[str]
    notes: Optional[str]
    created_at: datetime


class AccountingSummary(BaseModel):
    principal_balance: Decimal
    income_balance: Decimal
    total_receipts: Decimal
    total_disbursements: Decimal
    total_gains: Decimal
    total_losses: Decimal
    total_distributions: Decimal
    entry_count: int


# ── Probate ───────────────────────────────────────────────────────────────────


class HeirRowInput(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    age: Optional[str] = Field(None, max_length=20)
    relationship: Optional[str] = Field(None, max_length=150)
    address: Optional[str] = Field(None, max_length=500)


class ProbateFactsInput(BaseModel):
    """The probate facts as staff edit them on the Probate tab.

    Dates and money arrive as strings and are parsed server-side with the same
    tolerant readers the intake uses, so a phone-call entry of ``3/4/25`` or
    ``about 80k`` lands as a value rather than a validation error.
    """

    decedent_name: Optional[str] = Field(None, max_length=300)
    decedent_aka: Optional[str] = Field(None, max_length=300)
    date_of_death: Optional[str] = Field(None, max_length=40)
    date_of_birth: Optional[str] = Field(None, max_length=40)
    age_at_death: Optional[int] = Field(None, ge=0, le=130)
    domicile_state: Optional[str] = Field(None, max_length=100)
    domicile_county: Optional[str] = Field(None, max_length=150)
    real_property_in_nd: Optional[bool] = None
    nd_property_counties: Optional[List[str]] = Field(None, max_length=20)
    probate_property_value: Optional[str] = Field(None, max_length=40)
    will_exists: Optional[bool] = None
    will_original_available: Optional[bool] = None
    will_execution_date: Optional[str] = Field(None, max_length=40)
    applicant_name: Optional[str] = Field(None, max_length=300)
    applicant_relationship: Optional[str] = Field(None, max_length=150)
    applicant_is_nominee: Optional[bool] = None
    applicant_address: Optional[str] = Field(None, max_length=500)
    applicant_phone: Optional[str] = Field(None, max_length=50)
    applicant_email: Optional[str] = Field(None, max_length=300)
    persons_with_prior_or_equal_priority: Optional[List[str]] = Field(
        None, max_length=50
    )
    heirs: Optional[List[HeirRowInput]] = Field(None, max_length=100)
    probate_opened_elsewhere: Optional[bool] = None
    prior_appointment: Optional[bool] = None
    prior_appointment_details: Optional[str] = Field(None, max_length=1000)
    demand_for_notice: Optional[bool] = None
    demand_for_notice_details: Optional[str] = Field(None, max_length=1000)
    bond_amount: Optional[str] = Field(None, max_length=40)
    assets_summary: Optional[str] = Field(None, max_length=5000)
    debts_summary: Optional[str] = Field(None, max_length=5000)
    funeral_expenses: Optional[str] = Field(None, max_length=40)
    inventory_open: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class ProbateAnchorsInput(BaseModel):
    appointment_date: Optional[date] = None
    first_publication_date: Optional[date] = None
    letters_issued_date: Optional[date] = None
    closing_statement_filed_date: Optional[date] = None
    date_of_death: Optional[date] = None


class ProbateFromIntakeInput(BaseModel):
    overwrite: bool = False


class ProbateDeadlineSyncInput(BaseModel):
    mirror_tasks: bool = False


class ProbateStateResponse(BaseModel):
    estate_id: str
    matter_id: Optional[str]
    facts: dict
    determination: Optional[dict]
    determined_at: Optional[datetime]
    anchors: dict
    forms: List[dict]
    deadlines_preview: dict
    sources: List[dict]
    intake: Optional[dict] = None
    jurisdiction: Optional[str] = None
    jurisdiction_label: Optional[str] = None
    jurisdiction_supported: bool = True
