#!/usr/bin/env python3
"""Contract score calculator for Orchestrator subagent responses.

Reads a response from stdin (or --text) and produces a score in the form
``NN/100`` on stdout.  Detail lines go to stderr so callers can capture just
the score with::

    score=$(echo "$response" | python src/score.py --role developer)
    # -> "83/100"

Usage
-----
    python src/score.py --role architect   < response.md
    python src/score.py --role developer   --text "my response text"
    python src/score.py --role reviewer    --file response.md
    python src/score.py                    < response.md   # auto-detects role

Exit codes
----------
    0  score >= threshold (default 70)
    1  score < threshold
    2  usage / argument error
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Checklist definitions
# Each item has a name and one or more regex patterns.  An item is considered
# PRESENT when *any* pattern matches anywhere in the response text (case-
# insensitive, DOTALL).  Use word-boundary patterns where possible to avoid
# false positives.
# ---------------------------------------------------------------------------

@dataclass
class CheckItem:
    name: str
    patterns: list[str]

    def present(self, text: str) -> bool:
        for pat in self.patterns:
            if re.search(pat, text, re.IGNORECASE | re.DOTALL):
                return True
        return False


@dataclass
class Checklist:
    role: str
    items: list[CheckItem] = field(default_factory=list)

    def score(self, text: str) -> tuple[int, int, list[tuple[str, bool]]]:
        """Return (passed, total, [(name, passed), ...])."""
        results = [(item.name, item.present(text)) for item in self.items]
        passed = sum(1 for _, ok in results if ok)
        return passed, len(results), results


FORMAT_ITEMS = [
    CheckItem("Status field present",
              [r"\bstatus\s*[:=]\s*(success|partial|failure)\b"]),
    CheckItem("Artifacts field present",
              [r"\bartifacts?\s*:", r"## artifacts?\b"]),
    CheckItem("Uncertainties field present",
              [r"\buncertainties?\s*:", r"## uncertainties?\b"]),
    CheckItem("Follow-up recommendations present",
              [r"\bfollow.?up\b", r"\brecommendations?\s*:"]),
]

CHECKLISTS: dict[str, Checklist] = {
    "architect": Checklist(
        role="Software Architect",
        items=[
            CheckItem("Problem framing (scope, constraints, non-goals)",
                      [r"\b(scope|constraints?|non.goals?|problem\s+framing|problem\s+statement)\b"]),
            CheckItem("At least 2 viable approaches with trade-offs",
                      [r"\b(approach|option|alternative)\s*[#\d]",
                       r"\btrade.?offs?\b",
                       r"\b(approach|option)\s*(one|two|three|1|2|3)\b",
                       r"##\s+approach",
                       r"option\s+[ab12]"]),
            CheckItem("Recommended architecture decision with rationale",
                      [r"\b(recommend|decision|rationale|chosen|selected|preferred|we\s+will\s+use)\b"]),
            CheckItem("Interface and boundary definitions",
                      [r"\b(interface|boundary|component|service|module|api|endpoint|contract)\b"]),
            CheckItem("Risk register and mitigation plan",
                      [r"\b(risk|mitigation|mitigate|risk\s+register|risk\s+plan)\b"]),
            CheckItem("Validation strategy",
                      [r"\b(validation\s+strategy|acceptance\s+criteria?|test\s+strategy|verified?\s+by|validated?\s+via)\b"]),
        ],
    ),
    "developer": Checklist(
        role="Senior Developer",
        items=[
            CheckItem("Implementation summary",
                      [r"\b(implementation\s+summary|summary\s+of\s+changes?|implemented|changes?\s+made)\b"]),
            CheckItem("Files / components changed",
                      [r"\b(changed?|modified|created|updated|deleted)\b.{0,80}\.(cs|py|ts|js|md|json|xml|xaml|csproj)\b",
                       r"files?\s+(changed?|modified|updated|created)"]),
            CheckItem("Test evidence (run, passed, failed)",
                      [r"\b(test(s|ed|ing)?|passed|failed|assert|coverage)\b",
                       r"\b(dotnet\s+test|vstest|pytest|jest)\b"]),
            CheckItem("Error handling and rollback / guardrail notes",
                      [r"\b(error\s+handling|exception|rollback|guardrail|catch|finally|try\s*{)\b"]),
            CheckItem("Known limitations and follow-up actions",
                      [r"\b(limitation|caveat|known\s+issue|follow.?up|todo)\b"]),
            CheckItem("Commenting and Region compliance statement",
                      [r"\b(comment(ing)?|region|#region|xml\s+doc|summary\s+tag|compliance)\b"]),
        ],
    ),
    "reviewer": Checklist(
        role="Code Reviewer",
        items=[
            CheckItem("Correctness assessment",
                      [r"\b(correct(ness)?|logic|functional(ity)?|behav(es?|iour))\b"]),
            CheckItem("Maintainability assessment",
                      [r"\b(maintainab(le|ility)|readab(le|ility)|clean\s+code|naming|coupling)\b"]),
            CheckItem("Security assessment",
                      [r"\b(security|vulnerab(le|ility)|injection|xss|csrf|owasp|sanitize|safe)\b"]),
            CheckItem("Performance assessment",
                      [r"\b(performance|efficient|complexity|O\(|throughput|latency|allocat)\b"]),
            CheckItem("Specific findings with file or line references",
                      [r"\bL?\d{1,4}\b.{0,60}\.(cs|py|ts|js|md)\b",
                       r"\b(line\s+\d+|file\s+\w+|finding|issue)\b"]),
            CheckItem("Recommendations for improvement",
                      [r"\b(recommend|suggest|should|consider|improve|refactor)\b"]),
            CheckItem("Approval or rejection decision with justification",
                      [r"\b(approve(d)?|reject(ed)?|lgtm|not\s+approved|conditional\s+approval)\b"]),
        ],
    ),
}


def auto_detect_role(text: str) -> str | None:
    """Heuristic: look for strong role-specific signals."""
    lower = text.lower()
    signals = {
        "architect": ["architecture", "trade-off", "system design", "boundary", "risk register"],
        "developer":  ["implementation summary", "files changed", "test evidence", "region compliance"],
        "reviewer":   ["correctness assessment", "security assessment", "approve", "reject", "lgtm"],
    }
    scores = {role: sum(1 for sig in sigs if sig in lower)
              for role, sigs in signals.items()}
    best, count = max(scores.items(), key=lambda kv: kv[1])
    return best if count >= 1 else None


def compute_score(text: str, role: str) -> tuple[int, int, list[tuple[str, bool]], list[tuple[str, bool]]]:
    """Return (passed, total, role_results, format_results)."""
    checklist = CHECKLISTS[role]
    role_passed, role_total, role_results = checklist.score(text)

    format_checklist = Checklist(role="format", items=FORMAT_ITEMS)
    fmt_passed, fmt_total, fmt_results = format_checklist.score(text)

    total = role_total + fmt_total
    passed = role_passed + fmt_passed
    return passed, total, role_results, fmt_results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a subagent response against the contract-validator checklist.")
    parser.add_argument("--role", choices=["architect", "developer", "reviewer"],
                        help="Subagent role (auto-detected if omitted)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="Response text (inline)")
    source.add_argument("--file", help="Path to response text file")
    parser.add_argument("--threshold", type=int, default=70,
                        help="Minimum passing score 0-100 (default: 70)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-item detail to stderr")
    args = parser.parse_args(argv)

    if args.text:
        text = args.text
    elif args.file:
        try:
            text = open(args.file, encoding="utf-8").read()
        except OSError as exc:
            print(f"error: cannot read file: {exc}", file=sys.stderr)
            return 2
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        parser.print_help(sys.stderr)
        return 2

    role = args.role
    if not role:
        role = auto_detect_role(text)
        if not role:
            print("error: could not auto-detect role; pass --role architect|developer|reviewer",
                  file=sys.stderr)
            return 2
        print(f"Auto-detected role: {role}", file=sys.stderr)

    passed, total, role_results, fmt_results = compute_score(text, role)
    pct = round(passed / total * 100) if total else 0
    score_str = f"{pct}/100"

    # Always print score on stdout so callers can capture it cleanly
    print(score_str)

    # Print detail to stderr
    role_label = CHECKLISTS[role].role
    print(f"\n=== Contract Score: {score_str} ({passed}/{total}) — {role_label} ===", file=sys.stderr)

    print("\n  Role checklist:", file=sys.stderr)
    for name, ok in role_results:
        mark = "✓" if ok else "✗"
        print(f"    [{mark}] {name}", file=sys.stderr)

    print("\n  Format compliance:", file=sys.stderr)
    for name, ok in fmt_results:
        mark = "✓" if ok else "✗"
        print(f"    [{mark}] {name}", file=sys.stderr)

    missing = [name for name, ok in role_results + fmt_results if not ok]
    if missing:
        print("\n  Missing items:", file=sys.stderr)
        for name in missing:
            print(f"    - {name}", file=sys.stderr)

    threshold = args.threshold
    if pct < threshold:
        print(f"\n  FAIL: {pct} < threshold {threshold}", file=sys.stderr)
        return 1

    print(f"\n  PASS: {pct} >= threshold {threshold}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())