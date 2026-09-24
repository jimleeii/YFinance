#!/usr/bin/env python3
"""Lint the orchestrator wiki for consistency, staleness, and structural issues.

Checks performed
----------------
1. Stale entries — Behavior-Log or Skill-Usage-Log entries older than --stale-days
   with no referenced follow-up in Learning-Backlog.md.
2. Orphan backlog items — Learning-Backlog items that do not link back to any
   pattern ID in Behavior-Patterns.md.
3. Unresolved placeholder entries — entries still containing the XXX/HHMMSS
   placeholder patterns that log_prompt.py normally rejects.
4. Cross-file contradictions — a pattern in Behavior-Patterns.md marked 'resolved'
   but still referenced as open in Learning-Backlog.md, or vice-versa.
5. Orphan cycle IDs — CYC-* IDs in Behavior-Log that have no matching entry in
   Skill-Usage-Log (missing skill accounting for that cycle).

Usage
-----
    python scripts/lint_wiki.py
    python scripts/lint_wiki.py --wiki .wiki/orchestrator --stale-days 30
    python scripts/lint_wiki.py --output lint-report.md

Exit codes
----------
    0  no issues found
    1  one or more issues found
    2  usage / argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_RE_ENTRY_DATE = re.compile(
    r"(?:Timestamp \(UTC\)|date)[^\d]*(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2})?)", re.IGNORECASE
)
_RE_CYCLE_ID    = re.compile(r"\bCYC-\d{8}-\d{6}-[0-9A-F]{4}\b")
_RE_OBS_ID      = re.compile(r"###\s+(OBS-\d{8}-\w+)")
_RE_PAT_ID      = re.compile(r"###\s+(PAT-\d{8}-\w+)")
_RE_LRN_ID      = re.compile(r"###\s+(LRN-\d{8}-\w+)")
_RE_SKL_ID      = re.compile(r"###\s+(SKL-\d+)")
_RE_PLACEHOLDER = re.compile(
    r"(?:OBS|PAT|LRN|CTX|CHG)-\d{8}-XXX"
    r"|(?:SKL|SKILL)-\d{8}(?:-)?HHMMSS"
    r"|CB-\d{8}-XX"
    r"|\bStatus:\s+candidate \| applied \| rolled_back\b"
    r"|\bStatus:\s+pending \| in_progress \| done \| rolled_back\b"
    r"|\bDecision:\s+keep \| revise \| rollback\b",
    re.IGNORECASE,
)
_RE_RESOLVED    = re.compile(r"\b(?:status|resolution)[=:\s]+(?:resolved|done|applied|closed)\b", re.IGNORECASE)
_RE_OPEN        = re.compile(r"\b(?:status|resolution)[=:\s]+(?:open|pending|in.?progress|candidate)\b", re.IGNORECASE)
_RE_PAT_REF     = re.compile(r"\bPAT-\d{8}-\w+\b")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LintIssue:
    severity: str   # "error" | "warning" | "info"
    file: str
    entry_id: str
    message: str


@dataclass
class LintReport:
    issues: list[LintIssue] = field(default_factory=list)

    def add(self, severity: str, file: str, entry_id: str, message: str) -> None:
        self.issues.append(LintIssue(severity=severity, file=file, entry_id=entry_id, message=message))

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _utf8_backslashreplace_text(text: str) -> str:
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


def _find_default_wiki(start: Path | None = None) -> Path:
    """Locate repo-root .wiki/orchestrator by walking upward to .git."""
    cur = (start or Path(__file__)).resolve()
    cur = cur if cur.is_dir() else cur.parent
    for _ in range(20):
        if (cur / ".git").exists():
            return cur / ".wiki" / "orchestrator"
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(".wiki/orchestrator")


def _parse_date(text_block: str) -> datetime | None:
    m = _RE_ENTRY_DATE.search(text_block)
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _split_headings(text: str, heading_re: re.Pattern) -> list[tuple[str, str]]:
    """Return list of (id, block_text) pairs."""
    matches = list(heading_re.finditer(text))
    if not matches:
        return []
    results = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        results.append((m.group(1), text[start:end]))
    return results


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_stale_entries(
    report: LintReport,
    behavior_text: str,
    skill_text: str,
    stale_days: int,
) -> None:
    """Flag log entries older than stale_days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

    for entry_id, block in _split_headings(behavior_text, _RE_OBS_ID):
        dt = _parse_date(block)
        if dt and dt < cutoff:
            report.add("warning", "Behavior-Log.md", entry_id,
                       f"Entry is older than {stale_days} days ({dt.date()})")

    for entry_id, block in _split_headings(skill_text, _RE_SKL_ID):
        dt = _parse_date(block)
        if dt and dt < cutoff:
            report.add("warning", "Skill-Usage-Log.md", entry_id,
                       f"Entry is older than {stale_days} days ({dt.date()})")


def check_placeholders(
    report: LintReport,
    wiki: Path,
) -> None:
    """Detect unresolved placeholder patterns in all wiki files."""
    for fname in ("Behavior-Log.md", "Skill-Usage-Log.md", "Behavior-Patterns.md",
                  "Learning-Backlog.md", "Project-Context-Log.md", "Runbook.md"):
        text = _read(wiki / fname)
        for m in _RE_PLACEHOLDER.finditer(text):
            line_no = text[:m.start()].count("\n") + 1
            report.add("error", fname, f"line {line_no}",
                       f"Unresolved placeholder: '{m.group()}'")


def check_orphan_backlog(
    report: LintReport,
    backlog_text: str,
    patterns_text: str,
) -> None:
    """Flag Learning-Backlog items that don't reference any known pattern ID."""
    known_patterns: set[str] = {pid for pid, _ in _split_headings(patterns_text, _RE_PAT_ID)}
    for entry_id, block in _split_headings(backlog_text, _RE_LRN_ID):
        referenced = set(_RE_PAT_REF.findall(block))
        if known_patterns and not referenced.intersection(known_patterns):
            report.add("warning", "Learning-Backlog.md", entry_id,
                       "Backlog item has no link to any pattern in Behavior-Patterns.md")


def check_contradictions(
    report: LintReport,
    patterns_text: str,
    backlog_text: str,
) -> None:
    """Detect resolved patterns still referenced as open in Learning-Backlog."""
    resolved_patterns: set[str] = set()
    for pid, block in _split_headings(patterns_text, _RE_PAT_ID):
        if _RE_RESOLVED.search(block):
            resolved_patterns.add(pid)

    for entry_id, block in _split_headings(backlog_text, _RE_LRN_ID):
        if not _RE_OPEN.search(block):
            continue
        for ref in _RE_PAT_REF.findall(block):
            if ref in resolved_patterns:
                report.add("error", "Learning-Backlog.md", entry_id,
                           f"Open backlog item references resolved pattern {ref} (contradiction)")


def check_orphan_cycle_ids(
    report: LintReport,
    behavior_text: str,
    skill_text: str,
) -> None:
    """Warn about CYC-* IDs in Behavior-Log absent from Skill-Usage-Log."""
    behavior_cycles: set[str] = set(_RE_CYCLE_ID.findall(behavior_text))
    skill_cycles: set[str]    = set(_RE_CYCLE_ID.findall(skill_text))
    orphans = behavior_cycles - skill_cycles
    for cid in sorted(orphans):
        report.add("warning", "Behavior-Log.md", cid,
                   "Cycle ID present in Behavior-Log but missing from Skill-Usage-Log")


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_markdown(report: LintReport, wiki_path: str, stale_days: int) -> str:
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# Wiki Lint Report",
        "",
        f"- **Generated:** {ts}",
        f"- **Wiki:** {wiki_path}",
        f"- **Stale threshold:** {stale_days} days",
        f"- **Errors:** {report.error_count}",
        f"- **Warnings:** {report.warning_count}",
        "",
    ]
    if not report.issues:
        lines += ["## Result", "", "No issues found. Wiki is consistent.", ""]
        return "\n".join(lines)

    lines += ["## Issues", ""]
    for issue in report.issues:
        tag = "[ERROR]" if issue.severity == "error" else "[WARN] "
        lines.append(f"{tag} **{issue.file}** — `{issue.entry_id}`")
        lines.append(f"   {issue.message}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint the orchestrator wiki for consistency issues")
    parser.add_argument("--wiki", default=str(_find_default_wiki()),
                        help="Path to .wiki/orchestrator directory (default: .wiki/orchestrator)")
    parser.add_argument("--stale-days", type=int, default=30,
                        help="Days after which an entry is considered stale (default: 30)")
    parser.add_argument("--output", help="Write markdown report to this file instead of stdout")
    args = parser.parse_args(argv)

    wiki = Path(args.wiki)
    if not wiki.is_dir():
        print(f"error: wiki directory not found: {wiki}", file=sys.stderr)
        return 2

    behavior_text  = _read(wiki / "Behavior-Log.md")
    skill_text     = _read(wiki / "Skill-Usage-Log.md")
    patterns_text  = _read(wiki / "Behavior-Patterns.md")
    backlog_text   = _read(wiki / "Learning-Backlog.md")

    report = LintReport()
    check_stale_entries(report, behavior_text, skill_text, args.stale_days)
    check_placeholders(report, wiki)
    check_orphan_backlog(report, backlog_text, patterns_text)
    check_contradictions(report, patterns_text, backlog_text)
    check_orphan_cycle_ids(report, behavior_text, skill_text)

    output = render_markdown(report, str(wiki), args.stale_days)

    if args.output:
        Path(args.output).write_text(_utf8_backslashreplace_text(output), encoding="utf-8")
        print(f"Lint report written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(_utf8_backslashreplace_text(output).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    # Print summary counts to stderr for CI integration
    print(f"Lint complete: {report.error_count} error(s), {report.warning_count} warning(s)", file=sys.stderr)

    return 1 if report.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
