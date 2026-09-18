#!/usr/bin/env python3
"""Reconcile an OWASP ZAP baseline report into labeled GitHub issues.

One issue per (plugin, parameter) finding, deduplicated by a fingerprint
buried in the issue body. New findings open an issue; still-present findings
update only when their evidence changes; disappeared findings close. This is
report-only: it never fails because of a finding, and it only ever reads or
writes issues carrying the ``dast`` label and the ``[dast-alert]`` marker.

Runs on a GitHub-hosted job with ``issues: write``; the self-hosted scan job
that produced the report never receives a write token.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

LABEL = "dast"
LABEL_COLOR = "b60205"
LABEL_DESCRIPTION = "Finding from the scheduled OWASP ZAP baseline scan"
SCAN_ALERT_TITLE = (
    "[dast-alert] Scheduled production DAST scan did not produce a report"
)
TARGET = "https://getlawhand.com"
MAX_AFFECTED_URLS = 50

_RISK_NAMES = {"0": "Informational", "1": "Low", "2": "Medium", "3": "High"}
_MIN_RISK = {"informational": 0, "low": 1, "medium": 2, "high": 3}
_FINGERPRINT_RE = re.compile(r"<!-- dast-fingerprint: ([0-9a-f]{40}) -->")
_CONTENT_RE = re.compile(r"<!-- dast-content: ([0-9a-f]{40}) -->")
_TAG_RE = re.compile(r"<[^>]+>")


class GitHubError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"GitHub API error {code}: {message}")
        self.code = code


@dataclass
class Finding:
    plugin_id: str
    name: str
    risk: str
    confidence: str
    cwe: str
    description: str
    solution: str
    reference: str
    param: str
    affected: dict[str, set[str]] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        # Rule-scoped, not URL-scoped. The baseline spider discovers a slightly
        # different URL set each run; a per-URL fingerprint turned that variance
        # into a storm of opened and closed issues.
        key = f"{self.plugin_id}|{self.param}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        affected = {
            uri: sorted(methods) for uri, methods in sorted(self.affected.items())
        }
        key = json.dumps(
            [
                self.name,
                self.risk,
                self.confidence,
                self.cwe,
                self.description,
                self.solution,
                self.reference,
                self.param,
                affected,
            ],
            sort_keys=True,
        )
        return hashlib.sha1(key.encode("utf-8")).hexdigest()


def html_to_text(value: str) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    return re.sub(r"\s+", " ", text).strip()


def normalize_report(report: dict, min_risk: int = 1) -> list[Finding]:
    findings: dict[tuple[str, str], Finding] = {}
    for site in report.get("site", []) or []:
        default_uri = site.get("@name", "") or ""
        for alert in site.get("alerts", []) or []:
            risk = _RISK_NAMES.get(str(alert.get("riskcode", "0")), "Informational")
            if _MIN_RISK.get(risk.lower(), 0) < min_risk:
                continue
            plugin_id = str(alert.get("pluginid", ""))
            for instance in alert.get("instances") or [{}]:
                param = str(instance.get("param", "") or "")
                key = (plugin_id, param)
                finding = findings.get(key)
                if finding is None:
                    finding = Finding(
                        plugin_id=plugin_id,
                        name=str(alert.get("alert") or alert.get("name") or "Unknown"),
                        risk=risk,
                        confidence=str(alert.get("confidence", "")),
                        cwe=str(alert.get("cweid", "") or ""),
                        description=html_to_text(str(alert.get("desc", ""))),
                        solution=html_to_text(str(alert.get("solution", ""))),
                        reference=html_to_text(str(alert.get("reference", ""))),
                        param=param,
                    )
                    findings[key] = finding
                uri = str(instance.get("uri") or default_uri)
                method = str(instance.get("method", "GET") or "GET").upper()
                finding.affected.setdefault(uri, set()).add(method)
    return sorted(findings.values(), key=lambda finding: (finding.name, finding.param))


def render_title(finding: Finding) -> str:
    title = f"[dast] {finding.name} [{finding.plugin_id}]"
    if finding.param:
        title += f" ({finding.param})"
    return title[:200]


def render_body(finding: Finding, run_url: str) -> str:
    meta = f"**Risk:** {finding.risk}"
    if finding.confidence:
        meta += f" · **Confidence:** {finding.confidence}"
    meta += f" · **Plugin:** `{finding.plugin_id}`"
    if finding.cwe:
        meta += f" · **CWE:** {finding.cwe}"
    lines = [
        f"<!-- dast-fingerprint: {finding.fingerprint} -->",
        f"<!-- dast-content: {finding.content_hash} -->",
        "",
        meta,
        "",
        finding.description or "_No description supplied by the scanner._",
        "",
        "**Solution**",
        "",
        finding.solution or "_No remediation supplied by the scanner._",
        "",
        "**References**",
        "",
        finding.reference or "_None._",
        "",
        "**Affected URLs**",
        "",
    ]
    uris = sorted(finding.affected)
    for uri in uris[:MAX_AFFECTED_URLS]:
        methods = ", ".join(sorted(finding.affected[uri]))
        lines.append(f"- `{methods} {uri}`")
    if len(uris) > MAX_AFFECTED_URLS:
        lines.append(f"- ...and {len(uris) - MAX_AFFECTED_URLS} more")
    lines += [
        "",
        "---",
        "Detected by the scheduled OWASP ZAP baseline scan.",
        f"- Target: `{TARGET}`",
        f"- Run: {run_url or '_n/a_'}",
    ]
    return "\n".join(lines)


def _marker(body: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(body or "")
    return match.group(1) if match else None


class GitHub:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"https://api.github.com{path}", data=data, method=method
        )
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("User-Agent", "LawHand-dast-reconcile/1.0")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            raise GitHubError(exc.code, exc.read().decode("utf-8", "replace")) from exc

    def ensure_label(self) -> None:
        try:
            self.request(
                "GET", f"/repos/{self.repo}/labels/{urllib.parse.quote(LABEL)}"
            )
            return
        except GitHubError as exc:
            if exc.code != 404:
                raise
        self.request(
            "POST",
            f"/repos/{self.repo}/labels",
            {"name": LABEL, "color": LABEL_COLOR, "description": LABEL_DESCRIPTION},
        )

    def list_labeled_issues(self) -> list[dict]:
        issues: list[dict] = []
        page = 1
        while True:
            batch = self.request(
                "GET",
                f"/repos/{self.repo}/issues"
                f"?state=all&labels={urllib.parse.quote(LABEL)}&per_page=100&page={page}",
            )
            if not batch:
                break
            issues.extend(item for item in batch if "pull_request" not in item)
            if len(batch) < 100:
                break
            page += 1
        return issues

    def open_issues_by_title(self, title: str) -> list[dict]:
        matches = []
        page = 1
        while True:
            batch = self.request(
                "GET",
                f"/repos/{self.repo}/issues?state=open&per_page=100&page={page}",
            )
            if not batch:
                break
            matches.extend(
                item
                for item in batch
                if "pull_request" not in item and item.get("title") == title
            )
            if len(batch) < 100:
                break
            page += 1
        return matches


def reconcile(
    gh: GitHub,
    findings: list[Finding],
    run_url: str,
    *,
    zap_exit_code: int = 0,
    dry_run: bool = False,
) -> dict:
    gh.ensure_label()
    issues = gh.list_labeled_issues()
    by_fingerprint: dict[str, list[dict]] = {}
    for issue in issues:
        fingerprint = _marker(issue.get("body") or "", _FINGERPRINT_RE)
        if fingerprint:
            by_fingerprint.setdefault(fingerprint, []).append(issue)

    present = {finding.fingerprint for finding in findings}
    counts = {"created": 0, "updated": 0, "reopened": 0, "closed": 0}

    for finding in findings:
        candidates = by_fingerprint.get(finding.fingerprint, [])
        open_issue = next((i for i in candidates if i["state"] == "open"), None)
        closed_issue = next((i for i in candidates if i["state"] != "open"), None)
        target = open_issue or closed_issue
        title = render_title(finding)
        body = render_body(finding, run_url)
        if target is None:
            if not dry_run:
                gh.request(
                    "POST",
                    f"/repos/{gh.repo}/issues",
                    {"title": title, "body": body, "labels": [LABEL]},
                )
            counts["created"] += 1
        elif open_issue is None:
            if not dry_run:
                gh.request(
                    "PATCH",
                    f"/repos/{gh.repo}/issues/{target['number']}",
                    {"state": "open", "body": body},
                )
            counts["reopened"] += 1
        elif _marker(target.get("body") or "", _CONTENT_RE) != finding.content_hash:
            if not dry_run:
                gh.request(
                    "PATCH",
                    f"/repos/{gh.repo}/issues/{target['number']}",
                    {"body": body},
                )
            counts["updated"] += 1

    # Close resolved findings only when the scan completed cleanly. A non-zero
    # ZAP exit with no parsed findings is contradictory evidence, so leave the
    # existing issues open rather than reporting a false recovery.
    may_close = bool(findings) or zap_exit_code == 0
    for fingerprint, candidates in by_fingerprint.items():
        if fingerprint in present or not may_close:
            continue
        for issue in candidates:
            if issue["state"] != "open":
                continue
            if not dry_run:
                gh.request(
                    "POST",
                    f"/repos/{gh.repo}/issues/{issue['number']}/comments",
                    {
                        "body": "Not detected in the latest baseline scan "
                        f"({run_url or 'no run URL'}). Closing."
                    },
                )
                gh.request(
                    "PATCH",
                    f"/repos/{gh.repo}/issues/{issue['number']}",
                    {"state": "closed"},
                )
            counts["closed"] += 1

    close_scan_alert(gh, run_url, dry_run=dry_run)
    counts["findings"] = len(findings)
    return counts


def reconcile_scan_alert(gh: GitHub, run_url: str, *, dry_run: bool = False) -> dict:
    gh.ensure_label()
    body = (
        "The scheduled OWASP ZAP baseline scan did not produce a report. "
        "Findings for this run are unknown; check the runner and the "
        "`lawhand-dast-scan` entrypoint on Skynet.\n\n"
        f"- Target: `{TARGET}`\n"
        f"- Run: {run_url or '_n/a_'}"
    )
    existing = gh.open_issues_by_title(SCAN_ALERT_TITLE)
    if existing:
        if not dry_run:
            gh.request(
                "PATCH",
                f"/repos/{gh.repo}/issues/{existing[0]['number']}",
                {"body": body, "labels": [LABEL]},
            )
        return {"scan_alert": "updated"}
    if not dry_run:
        gh.request(
            "POST",
            f"/repos/{gh.repo}/issues",
            {"title": SCAN_ALERT_TITLE, "body": body, "labels": [LABEL]},
        )
    return {"scan_alert": "created"}


def close_scan_alert(gh: GitHub, run_url: str, *, dry_run: bool = False) -> None:
    for issue in gh.open_issues_by_title(SCAN_ALERT_TITLE):
        if not dry_run:
            gh.request(
                "POST",
                f"/repos/{gh.repo}/issues/{issue['number']}/comments",
                {
                    "body": f"The DAST scan produced a report again ({run_url or 'no run URL'})."
                },
            )
            gh.request(
                "PATCH",
                f"/repos/{gh.repo}/issues/{issue['number']}",
                {"state": "closed"},
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", help="Path to the ZAP JSON report")
    parser.add_argument("--run-url", default="", help="URL of the scan workflow run")
    parser.add_argument(
        "--min-risk",
        choices=sorted(_MIN_RISK),
        default="low",
        help="Lowest risk level to file",
    )
    parser.add_argument(
        "--zap-exit-code",
        type=int,
        default=0,
        help="ZAP baseline exit code from the scan job",
    )
    parser.add_argument(
        "--scan-missing",
        action="store_true",
        help="Record that the scan produced no report instead of reconciling findings",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise SystemExit("GITHUB_TOKEN and GITHUB_REPOSITORY are required")
    gh = GitHub(repo, token)
    if args.scan_missing:
        result = reconcile_scan_alert(gh, args.run_url, dry_run=args.dry_run)
    else:
        if not args.report or not os.path.isfile(args.report):
            raise SystemExit(f"report not found: {args.report!r}")
        with open(args.report, encoding="utf-8") as handle:
            report = json.load(handle)
        findings = normalize_report(report, _MIN_RISK[args.min_risk])
        result = reconcile(
            gh,
            findings,
            args.run_url,
            zap_exit_code=args.zap_exit_code,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
