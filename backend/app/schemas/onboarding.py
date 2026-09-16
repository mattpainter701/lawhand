"""Schemas for tenant onboarding wizard."""

from pydantic import BaseModel


class IntegrationConnectionStatus(BaseModel):
    connected: bool
    scopes: str | None = None
    service_account_email: str | None = None
    granted_by_user_id: str | None = None
    account_type: str | None = None


class OnboardingStatusResponse(BaseModel):
    onboarding_completed: bool
    onboarding_step: int
    integrations: dict[str, IntegrationConnectionStatus]  # "microsoft", "google"
    synced_users: dict[str, int]  # "microsoft": N, "google": N
    total_users: int
    # Storage step state: the chosen provider, the saved root bindings keyed by
    # provider, and whether at least one usable root exists.
    primary_cloud_provider: str | None = None
    cloud_root: dict | None = None
    storage_ready: bool = False
    # Whether the bound document root is org-owned (survives staff turnover)
    # or lives in one person's drive. Derived read-only from cloud_root.
    root_ownership: dict | None = None
    agreements_configured: bool = False
    agreements_blocking: bool = False
    setup_deferred: bool = False
    setup_reentry_active: bool = False


class OnboardingCompleteResponse(BaseModel):
    status: str
    cloud_root: dict | None = None


class OnboardingStepUpdate(BaseModel):
    step: int


class OnboardingStorageRequest(BaseModel):
    provider: str  # google_drive | onedrive | sharepoint


class OnboardingStorageResponse(BaseModel):
    status: str  # ready | failed | repair_needed
    provider: str
    cloud_root: dict | None = None
    root: dict | None = None  # the chosen provider's binding when ready
    created: bool = False
    root_repair_needed: list[str] = []
    error: str | None = None
