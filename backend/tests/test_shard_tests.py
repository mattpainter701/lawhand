"""Unit tests for the CI test sharder's weighting and packing helpers.

These exercise the pure functions only; the module's pytest collection step is
not run here, so the suite stays fast and database-free.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "shard_tests.py"
_spec = importlib.util.spec_from_file_location("shard_tests", _SCRIPT)
assert _spec and _spec.loader
shard_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shard_tests)


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_parse_durations_accepts_seconds_and_list_forms(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "durations.json",
        {"tests/a.py::test_one": 1.5, "tests/a.py::test_two": [1.0, 0.25]},
    )

    durations = shard_tests.parse_durations(target)

    assert durations == {"tests/a.py::test_one": 1.5, "tests/a.py::test_two": 1.25}


def test_parse_durations_skips_unusable_entries(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "durations.json",
        {"tests/a.py::ok": 2.0, "tests/a.py::bool": True, "tests/a.py::empty": []},
    )

    assert shard_tests.parse_durations(target) == {"tests/a.py::ok": 2.0}


def test_parse_durations_fails_closed_on_empty_map(tmp_path: Path) -> None:
    target = _write(tmp_path / "durations.json", {})

    with pytest.raises(SystemExit):
        shard_tests.parse_durations(target)


def test_parse_durations_fails_closed_on_bad_json(tmp_path: Path) -> None:
    target = tmp_path / "durations.json"
    target.write_text("not json", encoding="utf-8")

    with pytest.raises(SystemExit):
        shard_tests.parse_durations(target)


def test_measured_weights_use_seconds_and_median_fallback() -> None:
    counts = Counter({"tests/a.py": 2, "tests/b.py": 10})
    durations = {"tests/a.py::t1": 1.0, "tests/a.py::t2": 3.0}

    weights = shard_tests.measured_weights(counts, durations)

    # a.py is measured directly; b.py has no timings, so it falls back to the
    # median measured per-test cost (4.0s / 2 tests = 2.0s).
    assert weights == {"tests/a.py": 4.0, "tests/b.py": 20.0}


def test_shard_fixed_load_reserves_room_for_pinned_work() -> None:
    weights = {
        "tests/a.py": 10.0,
        "tests/b.py": 1.0,
        "tests/c.py": 1.0,
        "tests/d.py": 1.0,
    }

    buckets = shard_tests.shard(weights, 2, [0.0, 9.0])

    # The 9s fixed load on shard 2 changes the packing: without it the 10s file
    # would sit alone on shard 1 and the three small files would fill shard 2.
    assert sorted(buckets[0]) == ["tests/a.py", "tests/c.py"]
    assert sorted(buckets[1]) == ["tests/b.py", "tests/d.py"]


def test_shard_balances_without_fixed_load() -> None:
    weights = {"tests/a.py": 10.0, "tests/b.py": 1.0, "tests/c.py": 1.0}

    buckets = shard_tests.shard(weights, 2)

    assert sorted(buckets[0]) == ["tests/a.py"]
    assert sorted(buckets[1]) == ["tests/b.py", "tests/c.py"]


def test_shard_rejects_fixed_load_length_mismatch() -> None:
    with pytest.raises(SystemExit):
        shard_tests.shard({"tests/a.py": 1.0}, 2, [0.0])


@pytest.mark.parametrize(
    "value",
    ["2:18.5", "1:0", "4:120"],
)
def test_parse_fixed_load_accepts_shard_and_seconds(value: str) -> None:
    index, load = shard_tests.parse_fixed_load(value)

    assert index == int(value.split(":", 1)[0])
    assert load == float(value.split(":", 1)[1])


@pytest.mark.parametrize("value", ["x", "1", "1:", "0:5", "1:-2", "1:abc"])
def test_parse_fixed_load_rejects_bad_values(value: str) -> None:
    with pytest.raises(SystemExit):
        shard_tests.parse_fixed_load(value)
