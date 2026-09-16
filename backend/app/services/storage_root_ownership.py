"""Classify who owns a tenant's cloud document root.

The distinction that matters operationally is not which provider a firm uses
but whether the storage is owned by the organisation or by one person. A root
created in an admin's personal drive (OneDrive ``/me/drive`` or Google My
Drive) disappears from the firm's reach the moment that person is deactivated
or leaves. An org-owned root (SharePoint site library, Google Shared Drive)
survives that turnover.

This module is read-only: it inspects the persisted ``Tenant.cloud_root_folder``
binding and reports ownership. It never mutates provider state, so it is safe
to call from health, onboarding, and export paths.
"""

from __future__ import annotations

from app.services import google_service_account

PROVIDER_LABELS = {
    "onedrive": "Microsoft OneDrive",
    "sharepoint": "Microsoft SharePoint",
    "google_drive": "Google Drive",
}

# Binding ``owner_type`` values that mean the resource is organisation-owned.
ORG_OWNED_TYPES = {"org_shared_drive", "org_site_library"}

DURABLE = "durable"
AT_RISK = "at_risk"
UNBOUND = "unbound"


def _binding_id(binding: dict) -> str:
    return str(binding.get("id") or binding.get("folder_id") or "").strip()


def classify_binding(provider: str, binding: object) -> dict:
    """Return the ownership classification for one provider root binding."""
    result = {
        "provider": provider,
        "label": PROVIDER_LABELS.get(provider, provider),
        "status": UNBOUND,
        "org_owned": False,
        "owner_type": None,
        "access_org_owned": False,
        "detail": "No document root is bound for this provider.",
    }
    if not isinstance(binding, dict) or not _binding_id(binding):
        return result

    owner_type = (binding.get("owner_type") or "").strip() or None
    if owner_type is None:
        # Legacy bindings predate explicit ownership. SharePoint is the only
        # provider whose resource is org-owned regardless of the access token;
        # every other legacy binding is a per-user drive.
        if provider == "sharepoint" and binding.get("drive_id"):
            owner_type = "org_site_library"
        elif provider == "onedrive":
            owner_type = "user_personal_drive"
        elif provider == "google_drive":
            owner_type = "user_my_drive"

    result["owner_type"] = owner_type
    if owner_type == "org_shared_drive":
        # Runtime access uses LawHand's own service account only when one is
        # configured; otherwise the org drive is still reached with a person's
        # delegated token and breaks if that account leaves.
        result["access_org_owned"] = google_service_account.is_configured()
    if owner_type in ORG_OWNED_TYPES:
        result["status"] = DURABLE
        result["org_owned"] = True
        if result["access_org_owned"]:
            result["detail"] = (
                "Root is organisation-owned and LawHand reaches it with its own "
                "service account."
            )
        else:
            result["detail"] = (
                "Root is organisation-owned, but LawHand still reaches it with a "
                "user credential; access is at risk until a service identity is "
                "configured."
            )
    elif owner_type:
        result["status"] = AT_RISK
        result["detail"] = (
            "Root lives in one person's drive; if that account is deactivated "
            "or leaves, the firm loses access."
        )
    else:
        result["status"] = AT_RISK
        result["detail"] = "Root ownership could not be determined."
    return result


def classify_cloud_root(cloud_root: object) -> dict:
    """Classify every bound provider root and summarise the overall risk."""
    providers: dict[str, dict] = {}
    if isinstance(cloud_root, dict):
        for provider in PROVIDER_LABELS:
            if provider in cloud_root:
                providers[provider] = classify_binding(provider, cloud_root[provider])

    bound = [item for item in providers.values() if item["status"] != UNBOUND]
    if not bound:
        status = UNBOUND
    elif all(item["org_owned"] for item in bound):
        status = DURABLE
    else:
        status = AT_RISK
    at_risk = [item["label"] for item in bound if not item["org_owned"]]
    access_at_risk = [item["label"] for item in bound if not item["access_org_owned"]]
    return {
        "status": status,
        "org_owned": status == DURABLE,
        "at_risk_providers": at_risk,
        "access_at_risk": access_at_risk,
        "providers": providers,
    }
