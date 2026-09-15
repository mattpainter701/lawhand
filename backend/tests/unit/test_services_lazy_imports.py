"""Importing a service submodule must not drag in the whole application.

``app/services/__init__.py`` used to import ``EmbeddingService`` eagerly, so
``from app.services.pdf_templates import discover_pdf_fields`` — a module whose
only real dependency is pypdf — transitively required the embeddings stack,
SQLAlchemy, pgvector, Stripe, Redis, tiktoken and the JWT middleware. Any build
or analysis script that wanted PDF field discovery needed a full runtime
environment to read a file.

These run in a subprocess because the assertion is about what is *absent* from
``sys.modules``, and the rest of the suite has already imported most of the
application into the test process.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

#: Packages that have no business being loaded by a PDF helper.
HEAVY = ("app.services.embeddings", "openai", "stripe", "redis", "pgvector")


def _run(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("module", ["app.services", "app.services.pdf_templates"])
def test_importing_does_not_load_the_embeddings_stack(module: str) -> None:
    result = _run(f"""
        import sys
        import {module}  # noqa: F401
        loaded = [name for name in {HEAVY!r} if name in sys.modules]
        print(",".join(loaded))
    """)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"importing {module} eagerly loaded: {result.stdout.strip()}"
    )


def test_lazy_re_exports_still_resolve() -> None:
    """PEP 562 keeps every name in ``__all__`` importable exactly as before."""

    result = _run("""
        import app.services as services
        from app.services import EmbeddingService

        assert EmbeddingService is services.EmbeddingService
        assert set(services.__all__) <= set(dir(services))
        print(len(services.__all__))
    """)

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) == 10


def test_unknown_attribute_still_raises_attribute_error() -> None:
    result = _run("""
        import app.services as services
        try:
            services.NotAThing
        except AttributeError as exc:
            print("AttributeError", "NotAThing" in str(exc))
    """)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "AttributeError True"
