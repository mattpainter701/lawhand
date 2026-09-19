from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "prod-dast.yml"
ENTRYPOINT = ROOT / "scripts" / "lawhand-dast-scan"
INSTALLER = ROOT / "scripts" / "install_dast_scan_entrypoint.sh"
RECONCILE_PATH = ROOT / "scripts" / "reconcile_dast_findings.py"


def _load_reconcile():
    spec = importlib.util.spec_from_file_location(
        "reconcile_dast_findings", RECONCILE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


reconcile = _load_reconcile()


def test_prod_dast_workflow_scans_from_skynet_and_reports_on_github_hosted() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Production DAST" in workflow
    assert "schedule:" in workflow
    assert "cron:" in workflow
    assert "workflow_dispatch:" in workflow
    # A scanner must never run on pull-request code, and it takes no target
    # input that a caller could repoint at another host.
    assert "pull_request" not in workflow
    assert "inputs:" not in workflow
    assert "target" not in workflow.lower().split("jobs:", 1)[0]

    parsed = yaml.safe_load(workflow)
    jobs = parsed["jobs"]
    scan = jobs["zap-baseline"]
    report = jobs["report"]

    assert scan["runs-on"] == [
        "self-hosted",
        "Linux",
        "X64",
        "skynet",
        "lawhand-prod",
    ]
    assert scan["permissions"] == {}
    assert report["runs-on"] == "ubuntu-latest"
    assert report["permissions"] == {"contents": "read", "issues": "write"}
    assert report["needs"] == "zap-baseline"
    assert report["if"] == "always()"

    scan_block = workflow.split("  zap-baseline:", 1)[1].split("\n  report:", 1)[0]
    assert "actions/checkout" not in scan_block
    assert "sudo -n /usr/local/sbin/lawhand-dast-scan" in scan_block
    assert "secrets." not in scan_block
    assert "GITHUB_TOKEN" not in scan_block
    assert "continue-on-error: true" in scan_block

    report_block = workflow.split("  report:", 1)[1]
    assert "ref: main" in report_block
    assert "issues: write" in workflow
    assert "python scripts/reconcile_dast_findings.py" in report_block


def test_dast_entrypoint_is_argument_free_root_owned_and_digest_pinned() -> None:
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")

    assert 'readonly TARGET="https://getlawhand.com"' in entrypoint
    assert '[[ "$#" -eq 0 ]]' in entrypoint
    assert '"$(id -u)" -eq 0' in entrypoint
    assert "zaproxy/zap-stable@sha256:" in entrypoint
    assert re.search(r'IMAGE="zaproxy/zap-stable@sha256:[0-9a-f]{64}"', entrypoint)
    assert '"$IMAGE" zap-baseline.py' in entrypoint
    # The Automation Framework resolves report paths under /zap/wrk, so they
    # must stay relative or the report job writes to a doubled path.
    assert "-J zap-report.json" in entrypoint
    assert "-J /zap/wrk/" not in entrypoint
    # The image's configured HOME (/home/zap) is absent, so ZAP cannot write
    # its generated plan unless HOME points at a writable directory.
    assert "-e HOME=/tmp" in entrypoint
    # The runner must not be able to point the scanner at another host.
    assert 'TARGET="${' not in entrypoint
    assert "TARGET=" not in entrypoint.split("readonly TARGET=", 1)[1].split("\n", 1)[0]
    # Root-owned report directory plus a symlink check close the bind-mount
    # symlink escalation from a compromised runner.
    assert "install -d -m 0755 -o root -g root" in entrypoint
    assert '! -L "$REPORT_DIR"' in entrypoint
    assert "flock -n 9" in entrypoint
    # A finding (non-zero ZAP exit) is not an error; only a missing report is.
    assert "zap-baseline.py exits non-zero" in entrypoint
    assert 'if [[ ! -s "$json" ]]' in entrypoint
    assert "exit 3" in entrypoint


def test_dast_installer_grants_only_the_fixed_entrypoint() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "entrypoint=/usr/local/sbin/lawhand-dast-scan" in installer
    assert "NOPASSWD: $entrypoint" in installer
    assert "runner_user" in installer
    assert "visudo -cf" in installer
    assert "chmod 0440" in installer
    assert "install -m 0755 -o root -g root" in installer


def _report(riskcode: str = "2", uri: str = "https://getlawhand.com/") -> dict:
    return {
        "site": [
            {
                "@name": "https://getlawhand.com",
                "alerts": [
                    {
                        "pluginid": "10020",
                        "alert": "Missing Anti-clickjacking Header",
                        "riskcode": riskcode,
                        "confidence": "2",
                        "cweid": "1021",
                        "desc": "<p>Missing <b>header</b> &amp; more</p>",
                        "solution": "<p>Add the header.</p>",
                        "reference": "<p>https://example.test</p>",
                        "instances": [{"uri": uri, "method": "GET", "param": ""}],
                    }
                ],
            }
        ]
    }


def test_normalize_report_filters_risk_and_strips_html() -> None:
    findings = reconcile.normalize_report(_report("1"), min_risk=1)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.risk == "Low"
    assert finding.description == "Missing header & more"
    assert set(finding.affected) == {"https://getlawhand.com/"}
    assert finding.affected["https://getlawhand.com/"] == {"GET"}

    assert reconcile.normalize_report(_report("0"), min_risk=1) == []
    assert len(reconcile.normalize_report(_report("3"), min_risk=2)) == 1


def test_finding_is_rule_scoped_so_spider_variance_does_not_churn() -> None:
    one = reconcile.normalize_report(_report("2"), min_risk=1)[0]

    # A different URL set for the same rule is the same finding, so a baseline
    # spider that discovers a slightly different page set cannot open and close
    # issues on every run.
    report = _report("2")
    report["site"][0]["alerts"][0]["instances"] = [
        {"uri": "https://getlawhand.com/", "method": "GET", "param": ""},
        {"uri": "https://getlawhand.com/", "method": "POST", "param": ""},
        {"uri": "https://getlawhand.com/other", "method": "GET", "param": ""},
    ]
    two = reconcile.normalize_report(report, min_risk=1)[0]
    assert two.fingerprint == one.fingerprint
    assert set(two.affected) == {
        "https://getlawhand.com/",
        "https://getlawhand.com/other",
    }
    assert two.affected["https://getlawhand.com/"] == {"GET", "POST"}

    # A different rule is a different finding.
    other_rule = _report("2", uri="https://getlawhand.com/x")
    other_rule["site"][0]["alerts"][0]["pluginid"] = "99999"
    assert (
        reconcile.normalize_report(other_rule, min_risk=1)[0].fingerprint
        != one.fingerprint
    )


class _FakeGitHub:
    def __init__(self, issues: list[dict] | None = None) -> None:
        self.repo = "owner/repo"
        self.issues = [dict(issue) for issue in (issues or [])]
        self.calls: list[tuple[str, str, dict | None]] = []

    def ensure_label(self, name: str, color: str, description: str) -> None:
        self.calls.append(
            ("ENSURE", name, {"color": color, "description": description})
        )

    def list_labeled_issues(self) -> list[dict]:
        return [dict(issue) for issue in self.issues]

    def open_issues_by_title(self, title: str) -> list[dict]:
        return [
            dict(issue)
            for issue in self.issues
            if issue["state"] == "open" and issue.get("title") == title
        ]

    def request(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        if method == "POST" and path.endswith("/issues"):
            self.issues.append(
                {
                    "number": 100 + len(self.issues),
                    "state": "open",
                    "title": payload["title"],
                    "body": payload["body"],
                    "labels": [{"name": n} for n in payload.get("labels", [])],
                }
            )
        elif method == "PATCH":
            number = int(path.rsplit("/", 1)[1])
            for issue in self.issues:
                if issue["number"] == number:
                    update = dict(payload)
                    if "labels" in update:
                        update["labels"] = [{"name": n} for n in update["labels"]]
                    issue.update(update)
        return None


def _issue(body: str, *, state: str = "open", number: int = 1) -> dict:
    return {
        "number": number,
        "state": state,
        "title": "[dast] Missing Anti-clickjacking Header — https://getlawhand.com/",
        "body": body,
        "labels": [{"name": reconcile.LABEL}],
    }


def test_reconcile_creates_deduplicates_and_closes_findings() -> None:
    findings = reconcile.normalize_report(_report("2"), min_risk=1)
    finding = findings[0]

    created = _FakeGitHub()
    result = reconcile.reconcile(created, findings, "https://run/1", zap_exit_code=1)
    assert result["created"] == 1
    assert any(
        method == "POST" and path.endswith("/issues")
        for method, path, _ in created.calls
    )

    stale_body = reconcile.render_body(finding, "https://run/0").replace(
        finding.content_hash, "0" * 40
    )
    deduped = _FakeGitHub([_issue(stale_body)])
    result = reconcile.reconcile(deduped, findings, "https://run/2", zap_exit_code=1)
    assert result["created"] == 0
    assert result["updated"] == 1

    resolved = _FakeGitHub([_issue(reconcile.render_body(finding, "https://run/0"))])
    result = reconcile.reconcile(resolved, [], "https://run/3", zap_exit_code=0)
    assert result["closed"] == 1
    assert resolved.issues[0]["state"] == "closed"

    # A non-zero ZAP exit with no parsed findings is contradictory, so an
    # existing issue is left open rather than reporting a false recovery.
    ambiguous = _FakeGitHub([_issue(reconcile.render_body(finding, "https://run/0"))])
    result = reconcile.reconcile(ambiguous, [], "https://run/4", zap_exit_code=2)
    assert result["closed"] == 0
    assert ambiguous.issues[0]["state"] == "open"


def test_reconcile_reopens_a_closed_finding() -> None:
    findings = reconcile.normalize_report(_report("3"), min_risk=1)
    closed = _FakeGitHub(
        [_issue(reconcile.render_body(findings[0], "https://run/0"), state="closed")]
    )
    result = reconcile.reconcile(closed, findings, "https://run/5", zap_exit_code=1)
    assert result["reopened"] == 1
    assert closed.issues[0]["state"] == "open"


def test_criticality_confidence_and_cve_are_defined() -> None:
    report = _report("2")
    alert = report["site"][0]["alerts"][0]
    alert["wascid"] = "15"
    alert["reference"] = "<p>See CVE-2021-44228 and cve-2022-1234.</p>"
    finding = reconcile.normalize_report(report, min_risk=1)[0]

    assert finding.criticality == "Medium"
    assert finding.confidence == "Medium"
    assert finding.cwe == "1021"
    assert finding.wasc == "15"
    assert finding.cves == ("CVE-2021-44228", "CVE-2022-1234")
    assert reconcile.severity_labels(finding) == ["dast", "severity:medium"]
    assert reconcile.render_title(finding).startswith("[dast][Medium]")

    body = reconcile.render_body(finding, "https://run/x")
    assert "| Criticality | Confidence | CWE | WASC | CVE |" in body
    assert "| Medium | Medium | 1021 | 15 | CVE-2021-44228, CVE-2022-1234 |" in body


def test_missing_cve_is_stated_not_faked() -> None:
    finding = reconcile.normalize_report(_report("3"), min_risk=1)[0]
    assert finding.cves == ()
    body = reconcile.render_body(finding, "https://run/x")
    assert "| High | Medium | 1021 | n/a | None |" in body
    assert "not a known CVE" in body

    # A negative WASC sentinel is not rendered as an ID.
    report = _report("1")
    report["site"][0]["alerts"][0]["wascid"] = "-1"
    assert reconcile.normalize_report(report, min_risk=1)[0].wasc == ""


def test_reconcile_labels_criticality_and_repairs_stale_labels() -> None:
    findings = reconcile.normalize_report(_report("2"), min_risk=1)
    gh = _FakeGitHub()
    result = reconcile.reconcile(gh, findings, "https://run/1", zap_exit_code=1)
    assert result["created"] == 1
    assert sorted(label["name"] for label in gh.issues[0]["labels"]) == [
        "dast",
        "severity:medium",
    ]
    assert gh.issues[0]["title"].startswith("[dast][Medium]")

    # An existing open issue with the right fingerprint but the wrong label set
    # is repaired.
    stale = _FakeGitHub([_issue(reconcile.render_body(findings[0], "https://run/0"))])
    result = reconcile.reconcile(stale, findings, "https://run/2", zap_exit_code=1)
    assert result["updated"] == 1
    assert sorted(label["name"] for label in stale.issues[0]["labels"]) == [
        "dast",
        "severity:medium",
    ]


def test_scan_alert_is_filed_and_resolved() -> None:
    gh = _FakeGitHub()
    assert reconcile.reconcile_scan_alert(gh, "https://run/1") == {
        "scan_alert": "created"
    }
    alert_title = reconcile.SCAN_ALERT_TITLE
    assert gh.issues[0]["title"] == alert_title

    reconcile.reconcile_scan_alert(gh, "https://run/2")
    assert len(gh.issues) == 1

    reconcile.close_scan_alert(gh, "https://run/3")
    assert gh.issues[0]["state"] == "closed"
