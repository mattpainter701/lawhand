"""Native e-signature service package.

Exposes the ``internal`` provider (in-document signing in the client portal)
behind a small provider interface. Orchestration helpers (recording a
signature or an uploaded signed copy, finalizing a completed request into an
executed copy and evidence certificate, retrying failed filing) live in
``service.py``; where a signer signs is decided in ``plan.py`` and the executed
PDF is drawn in ``render.py``.

Re-exports resolve lazily, for the same reason ``app.services`` does: importing
``app.services.esign.placement`` — stdlib only — otherwise pulled in
``service.py`` and with it FastAPI, the ORM models and pgvector. ``plan.py`` and
``placement.py`` are read by the PDF template pipeline, so that cost landed on
anything touching a form field.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

#: Exported name -> module that defines it.
_LAZY_EXPORTS = {
    "ESignProvider": "app.services.esign.base",
    "get_provider": "app.services.esign.base",
    "accept_submission": "app.services.esign.service",
    "after_completion": "app.services.esign.service",
    "awaiting_review": "app.services.esign.service",
    "complete_request_if_done": "app.services.esign.service",
    "completion_pending": "app.services.esign.service",
    "decline_event": "app.services.esign.service",
    "mark_request_expired_if_needed": "app.services.esign.service",
    "next_pending_signers": "app.services.esign.service",
    "record_portal_decline": "app.services.esign.service",
    "record_portal_signature": "app.services.esign.service",
    "record_uploaded_copy": "app.services.esign.service",
    "reject_submission": "app.services.esign.service",
    "retry_pending_completions": "app.services.esign.service",
    "signer_can_act_now": "app.services.esign.service",
}

__all__ = list(_LAZY_EXPORTS)

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    # Redundant aliases mark these as re-exports: ``__all__`` is built from
    # _LAZY_EXPORTS at runtime, which a linter reading the source cannot see.
    from app.services.esign.base import ESignProvider as ESignProvider
    from app.services.esign.base import get_provider as get_provider
    from app.services.esign.service import accept_submission as accept_submission
    from app.services.esign.service import after_completion as after_completion
    from app.services.esign.service import awaiting_review as awaiting_review
    from app.services.esign.service import (
        complete_request_if_done as complete_request_if_done,
    )
    from app.services.esign.service import completion_pending as completion_pending
    from app.services.esign.service import decline_event as decline_event
    from app.services.esign.service import (
        mark_request_expired_if_needed as mark_request_expired_if_needed,
    )
    from app.services.esign.service import next_pending_signers as next_pending_signers
    from app.services.esign.service import (
        record_portal_decline as record_portal_decline,
    )
    from app.services.esign.service import (
        record_portal_signature as record_portal_signature,
    )
    from app.services.esign.service import record_uploaded_copy as record_uploaded_copy
    from app.services.esign.service import reject_submission as reject_submission
    from app.services.esign.service import (
        retry_pending_completions as retry_pending_completions,
    )
    from app.services.esign.service import signer_can_act_now as signer_can_act_now


def __getattr__(name: str):
    """Import the defining module on first use of a re-exported name."""

    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    return sorted([*globals(), *_LAZY_EXPORTS])
