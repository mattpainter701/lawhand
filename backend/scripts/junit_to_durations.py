"""Convert pytest JUnit XML reports into a durations file for shard_tests.py.

``shard_tests.py --durations`` wants a JSON map of test node id to seconds.
pytest already records each test's wall time in the JUnit XML every shard job
uploads, so this turns those artifacts into that map without a second,
instrumented run of the suite.

The ``file`` attribute is used when pytest provides it; otherwise the classname
is resolved to the longest existing ``.py`` prefix, which handles both function
tests (``tests.test_chat``) and class-based tests
(``tests.test_chat.TestChat``). When the same node id appears in more than one
report, the slowest observation wins, so a test that landed in two shards can
never be counted twice.

Run with:
    python scripts/junit_to_durations.py --output tests/ci_durations.json \
        shard-1.xml shard-2.xml shard-3.xml shard-4.xml
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _node_file(testcase: ET.Element) -> str:
    """Resolve a testcase's suite-relative file path."""

    file_attr = testcase.get("file")
    if file_attr:
        return file_attr.lstrip("./")

    classname = testcase.get("classname") or ""
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end]) + ".py"
        if (REPO_ROOT / candidate).is_file():
            return candidate
    return classname.replace(".", "/") + ".py"


def collect_durations(paths: list[Path]) -> dict[str, float]:
    durations: dict[str, float] = {}
    for path in paths:
        tree = ET.parse(path)
        for testcase in tree.iter("testcase"):
            name = testcase.get("name")
            if not name:
                continue
            try:
                seconds = float(testcase.get("time") or 0.0)
            except ValueError:
                continue
            if seconds < 0:
                continue
            nodeid = f"{_node_file(testcase)}::{name}"
            # max(), not sum(): a test that appears in two shard reports must
            # not have its cost counted twice.
            durations[nodeid] = max(durations.get(nodeid, 0.0), seconds)
    return durations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="durations JSON path to write")
    parser.add_argument("reports", nargs="+", help="JUnit XML report(s) to read")
    args = parser.parse_args()

    reports = [Path(p) for p in args.reports]
    missing = [str(p) for p in reports if not p.is_file()]
    if missing:
        raise SystemExit(f"missing JUnit report(s): {', '.join(missing)}")

    durations = collect_durations(reports)
    if not durations:
        raise SystemExit("no testcase timings found in the supplied reports")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(dict(sorted(durations.items())), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    total = sum(durations.values())
    print(
        f"wrote {len(durations)} test timings from {len(reports)} report(s) "
        f"to {output} ({total:.1f}s total)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
