#!/usr/bin/env python3
"""Operator: move a tenant's Google root from My Drive into an org Shared Drive.

Non-destructive: Google preserves folder IDs across the move, so matter and
subfolder bindings keep working. Run with --dry-run first. Exits 2 when the
tenant is refused or the provider fails.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.database import async_session_maker  # noqa: E402
from app.services.google_root_migration import (  # noqa: E402
    migrate_google_root_to_shared_drive,
)


async def _run(tenant_id: str, dry_run: bool) -> dict:
    async with async_session_maker() as db:
        return await migrate_google_root_to_shared_drive(
            db, tenant_id, dry_run=dry_run
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant_id", help="Tenant UUID whose Google root to move")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the plan without moving or writing anything",
    )
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_run(args.tenant_id, args.dry_run))
    except Exception as exc:  # provider failure after the decision to move
        result = {"status": "failed", "tenant_id": args.tenant_id, "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"migrated", "noop", "dry_run"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
