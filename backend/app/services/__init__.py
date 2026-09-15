"""Service package.

Re-exports are resolved lazily. Importing them eagerly made every service
submodule pull in the whole application: ``from app.services.pdf_templates
import discover_pdf_fields`` — a module whose only real dependency is pypdf —
transitively required the embeddings stack, SQLAlchemy, pgvector, Stripe,
Redis, tiktoken and the JWT middleware, so any build or analysis script that
wanted PDF field discovery needed a full runtime environment to read a file.

PEP 562 keeps every name in ``__all__`` importable exactly as before; the
underlying module is only imported when the name is actually used.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

#: Exported name -> module that defines it.
_LAZY_EXPORTS = {
    "EmbeddingService": "app.services.embeddings",
    "search_chunks": "app.services.rag",
    "build_rag_context": "app.services.rag",
    "full_rag_query": "app.services.rag",
    "LLMService": "app.services.llm",
    "BillingService": "app.services.billing",
    "calculate_cost": "app.services.billing",
    "QBOSyncService": "app.services.qbo_sync",
    "export_ledes_1998b": "app.services.ledes_export",
    "generate_invoice_pdf": "app.services.invoice_pdf",
}

__all__ = list(_LAZY_EXPORTS)

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    # Redundant aliases mark these as re-exports: ``__all__`` is built from
    # _LAZY_EXPORTS at runtime, which a linter reading the source cannot see.
    from app.services.billing import BillingService as BillingService
    from app.services.billing import calculate_cost as calculate_cost
    from app.services.embeddings import EmbeddingService as EmbeddingService
    from app.services.invoice_pdf import generate_invoice_pdf as generate_invoice_pdf
    from app.services.ledes_export import export_ledes_1998b as export_ledes_1998b
    from app.services.llm import LLMService as LLMService
    from app.services.qbo_sync import QBOSyncService as QBOSyncService
    from app.services.rag import build_rag_context as build_rag_context
    from app.services.rag import full_rag_query as full_rag_query
    from app.services.rag import search_chunks as search_chunks


def __getattr__(name: str):
    """Import the defining module on first use of a re-exported name."""

    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    return sorted([*globals(), *_LAZY_EXPORTS])
