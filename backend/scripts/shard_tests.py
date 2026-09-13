"""Split the backend test suite into balanced shards for parallel CI jobs.

Splitting is by file, never within a file, so module-level fixtures and any
ordering a file relies on internally are preserved.

Two weighting modes are supported:

* **Measured durations** (``--durations``), the preferred mode. Each file is
  weighted by the summed per-test wall time recorded in a durations JSON
  produced from a real CI run (see ``scripts/junit_to_durations.py``), so a file
  with one slow database test is not mistaken for one with many cheap tests. A
  file with no recorded timings (new or renamed) falls back to the median
  measured per-test cost, so every weight stays in the same unit — seconds.
* **Heuristic** (the default, and the fallback when no durations file exists).
  Weight is collected test count times a per-test cost that reflects whether the
  file uses the ``db_session``/``client`` fixtures and the per-test TRUNCATE they
  trigger (roughly fifty times a pure unit test).

``--fixed-load`` adds a known per-shard wall-time cost that is not part of the
packed files (for example the LibreOffice install and pinned special-database
suites that shards 1 and 2 run in addition to their sharded files), so those
shards receive proportionally fewer files. It is expressed in the same unit as
the weights, so use it with ``--durations``.

Run with: python scripts/shard_tests.py --shards 4 --index 1
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests"

# Requesting any of these fixtures pulls in the per-test TRUNCATE of every
# table, which is what makes a test expensive.
_DATABASE_FIXTURES = re.compile(
    r"\b(db_session|client|auth_headers|test_tenant|test_user)\b"
)

# A file can also reach PostgreSQL without those fixtures — by taking the
# session-scoped engine or building its own. Such a file is not expensive in
# the same way, but it still cannot run in the database-free job, so
# ``--database-free`` must exclude it too.
_DATABASE_ACCESS = re.compile(
    r"\b(test_engine|create_async_engine|TEST_DATABASE_URL"
    r"|RLS_TEST_DATABASE_URL|DATABASE_URL|asyncpg|test_redis)\b"
)

# Measured on CI: a database-backed test costs about a second, a pure unit
# test about twenty milliseconds. The exact ratio does not matter, only that
# database tests dominate the packing. Used only when no measured durations
# are available.
_DATABASE_WEIGHT = 1.0
_UNIT_WEIGHT = 0.02


def collected_test_counts() -> Counter[str]:
    """Count collected tests per file, so shards balance on real test counts."""

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=TESTS_DIR.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(
            "collection failed; refusing to shard a suite that cannot be collected"
        )
    counts: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        line = line.strip()
        if "::" not in line or not line.startswith("tests/"):
            continue
        counts[line.split("::", 1)[0]] += 1
    if not counts:
        raise SystemExit("collection produced no tests; refusing to shard")
    return counts


def _read_source(path: str) -> str:
    try:
        return (TESTS_DIR.parent / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def heuristic_weights(counts: Counter[str]) -> dict[str, float]:
    """Weight each file by test count times a database/unit cost estimate."""

    weights: dict[str, float] = {}
    for path, count in counts.items():
        per_test = (
            _DATABASE_WEIGHT
            if _DATABASE_FIXTURES.search(_read_source(path))
            else _UNIT_WEIGHT
        )
        weights[path] = count * per_test
    return weights


def parse_durations(path: Path) -> dict[str, float]:
    """Read per-test durations from a JSON map of node id to seconds.

    Accepts both ``{"tests/a.py::test_x": 1.2}`` and pytest-split's list form
    ``{"tests/a.py::test_x": [1.2, 1.3]}`` (summed). Fails closed on a missing or
    unusable file rather than silently falling back mid-run.
    """

    try:
        # utf-8-sig tolerates a BOM from an editor or a Windows tool; the
        # converter writes plain utf-8.
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"could not read durations file {path}: {exc}")
    if not isinstance(raw, dict):
        raise SystemExit(f"durations file {path} must contain a JSON object")

    durations: dict[str, float] = {}
    for nodeid, value in raw.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            seconds = float(value)
        elif isinstance(value, list) and value:
            try:
                seconds = float(sum(value))
            except (TypeError, ValueError):
                continue
        else:
            continue
        if seconds >= 0:
            durations[str(nodeid)] = seconds
    if not durations:
        raise SystemExit(f"durations file {path} contained no usable timings")
    return durations


def measured_weights(
    counts: Counter[str], durations: dict[str, float]
) -> dict[str, float]:
    """Weight each file by its measured seconds, falling back per file.

    A file with no recorded timings gets its test count times the median
    measured per-test cost, so an added or renamed file keeps the same unit as
    the rest of the suite instead of being treated as free.
    """

    per_file: dict[str, float] = defaultdict(float)
    for nodeid, seconds in durations.items():
        per_file[nodeid.split("::", 1)[0]] += seconds

    samples = [per_file[path] / counts[path] for path in per_file if counts.get(path)]
    fallback = statistics.median(samples) if samples else _DATABASE_WEIGHT

    weights: dict[str, float] = {}
    for path, count in counts.items():
        if path in per_file:
            weights[path] = per_file[path]
        else:
            weights[path] = count * fallback
    return weights


def parse_fixed_load(value: str) -> tuple[int, float]:
    """Parse a ``SHARD:SECONDS`` fixed-load argument into (1-based index, seconds)."""

    shard, separator, seconds = value.partition(":")
    if not separator or not shard.isdigit() or not seconds:
        raise SystemExit(f"--fixed-load expects SHARD:SECONDS, got {value!r}")
    try:
        load = float(seconds)
    except ValueError:
        raise SystemExit(f"--fixed-load seconds must be a number, got {value!r}")
    index = int(shard)
    if index < 1 or load < 0:
        raise SystemExit(
            f"--fixed-load must be a 1-based shard and a non-negative cost: {value!r}"
        )
    return index, load


def shard(
    weights: dict[str, float], shards: int, fixed_loads: list[float] | None = None
) -> list[list[str]]:
    """Greedy longest-processing-time packing; deterministic for a given input."""

    loads = list(fixed_loads) if fixed_loads is not None else [0.0] * shards
    if len(loads) != shards:
        raise SystemExit("fixed load count must match the shard count")
    buckets: list[list[str]] = [[] for _ in range(shards)]
    # Sort by weight descending, then by name so ties never depend on dict order.
    for path in sorted(weights, key=lambda p: (-weights[p], p)):
        target = min(range(shards), key=lambda i: (loads[i], i))
        buckets[target].append(path)
        loads[target] += weights[path]
    return buckets


def database_free_files(counts: Counter[str]) -> list[str]:
    free = []
    for path in sorted(counts):
        source = _read_source(path)
        if _DATABASE_FIXTURES.search(source) or _DATABASE_ACCESS.search(source):
            continue
        free.append(path)
    return free


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int)
    parser.add_argument("--index", type=int, help="1-based shard index")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print the balance of every shard instead of one shard's files",
    )
    parser.add_argument(
        "--database-free",
        action="store_true",
        help="print only the files that use no database fixture",
    )
    parser.add_argument(
        "--durations",
        help="JSON map of test node id to seconds; falls back to heuristic if absent",
    )
    parser.add_argument(
        "--fixed-load",
        action="append",
        metavar="SHARD:SECONDS",
        help="per-shard wall time that is not part of the packed files (repeatable)",
    )
    args = parser.parse_args()

    counts = collected_test_counts()

    if args.database_free:
        free = database_free_files(counts)
        if not free:
            raise SystemExit("no database-free test files found")
        print(" ".join(free))
        return

    if args.shards is None or args.index is None:
        raise SystemExit("--shards and --index are required unless --database-free")
    if args.shards < 1:
        raise SystemExit("--shards must be at least 1")
    if not 1 <= args.index <= args.shards:
        raise SystemExit("--index must be between 1 and --shards")

    if args.durations:
        durations_path = Path(args.durations)
        if durations_path.is_file():
            durations = parse_durations(durations_path)
            weights = measured_weights(counts, durations)
            print(
                f"using measured durations from {durations_path} "
                f"({len(durations)} tests)",
                file=sys.stderr,
            )
        else:
            print(
                f"WARNING: durations file {durations_path} not found; "
                "using heuristic weights",
                file=sys.stderr,
            )
            weights = heuristic_weights(counts)
    else:
        weights = heuristic_weights(counts)

    if len(weights) < args.shards:
        raise SystemExit(
            f"only {len(weights)} test files for {args.shards} shards; "
            "an empty shard would silently test nothing"
        )

    fixed_loads = [0.0] * args.shards
    for item in args.fixed_load or []:
        index, load = parse_fixed_load(item)
        if index > args.shards:
            raise SystemExit(
                f"--fixed-load shard {index} exceeds --shards {args.shards}"
            )
        fixed_loads[index - 1] += load

    buckets = shard(weights, args.shards, fixed_loads)

    if args.summary:
        for number, files in enumerate(buckets, start=1):
            load = fixed_loads[number - 1] + sum(weights[f] for f in files)
            print(f"shard {number}: {len(files):3d} files  weight {load:8.1f}")
        return

    files = buckets[args.index - 1]
    if not files:
        # Never fall through to bare `pytest`, which would run the whole suite
        # in every shard and report a false pass.
        raise SystemExit(f"shard {args.index} is empty; refusing to emit no paths")
    print(" ".join(sorted(files)))


if __name__ == "__main__":
    main()
