"""Unit tests for the JUnit XML to shard-durations converter."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "junit_to_durations.py"
_spec = importlib.util.spec_from_file_location("junit_to_durations", _SCRIPT)
assert _spec and _spec.loader
junit_to_durations = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(junit_to_durations)


def _report(path: Path, *cases: tuple[str, str, str | None, str]) -> Path:
    rows = []
    for classname, name, file_attr, seconds in cases:
        file_part = f' file="{file_attr}"' if file_attr else ""
        rows.append(
            f'<testcase classname="{classname}" name="{name}"{file_part} '
            f'time="{seconds}"/>'
        )
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        + "".join(rows)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def test_collect_durations_uses_file_and_time(tmp_path: Path) -> None:
    report = _report(
        tmp_path / "s1.xml",
        ("tests.test_chat", "test_a", "tests/test_chat.py", "1.25"),
        ("tests.test_chat", "test_b", "tests/test_chat.py", "0.5"),
    )

    durations = junit_to_durations.collect_durations([report])

    assert durations == {
        "tests/test_chat.py::test_a": 1.25,
        "tests/test_chat.py::test_b": 0.5,
    }


def test_collect_durations_keeps_slowest_of_duplicates(tmp_path: Path) -> None:
    first = _report(
        tmp_path / "s1.xml",
        ("tests.test_chat", "test_a", "tests/test_chat.py", "1.0"),
    )
    second = _report(
        tmp_path / "s2.xml",
        ("tests.test_chat", "test_a", "tests/test_chat.py", "3.0"),
    )

    durations = junit_to_durations.collect_durations([first, second])

    assert durations == {"tests/test_chat.py::test_a": 3.0}


def test_collect_durations_falls_back_to_existing_classname_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_chat.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(junit_to_durations, "REPO_ROOT", tmp_path)
    report = _report(
        tmp_path / "s1.xml",
        ("tests.test_chat.TestChat", "test_method", None, "0.75"),
    )

    durations = junit_to_durations.collect_durations([report])

    assert durations == {"tests/test_chat.py::test_method": 0.75}


def test_main_fails_closed_on_missing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "junit_to_durations.py",
            "--output",
            str(tmp_path / "out.json"),
            str(tmp_path / "absent.xml"),
        ],
    )

    with pytest.raises(SystemExit):
        junit_to_durations.main()


def test_main_writes_sorted_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(
        tmp_path / "s1.xml",
        ("tests.test_chat", "test_b", "tests/test_chat.py", "0.5"),
        ("tests.test_chat", "test_a", "tests/test_chat.py", "1.25"),
    )
    output = tmp_path / "out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["junit_to_durations.py", "--output", str(output), str(report)],
    )

    junit_to_durations.main()

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "tests/test_chat.py::test_a": 1.25,
        "tests/test_chat.py::test_b": 0.5,
    }
