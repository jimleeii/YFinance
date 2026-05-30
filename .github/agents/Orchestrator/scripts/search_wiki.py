#!/usr/bin/env python3
"""Search and retrieve relevant markdown from the Orchestrator wiki layer."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_TOKEN_RE = re.compile(r'[a-z0-9][a-z0-9_-]+', re.IGNORECASE)


@dataclass
class SearchResult:
    path: str
    score: int
    title: str
    snippet: str


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _iter_markdown_files(wiki_root: Path, include_transcripts: bool = False) -> Iterable[Path]:
    for path in sorted(wiki_root.rglob('*.md')):
        if not include_transcripts and 'transcripts' in path.parts:
            continue
        yield path


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('# '):
            return stripped[2:].strip()
    return fallback


def _extract_snippet(text: str, query_tokens: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in query_tokens):
            return line[:220]
    return lines[0][:220] if lines else ''


def _score_document(path: Path, text: str, query: str, tokens: list[str]) -> int:
    lowered = text.lower()
    title = _extract_title(text, path.stem).lower()
    path_text = path.as_posix().lower()
    score = 0
    if query.lower() in lowered:
        score += 6
    for token in tokens:
        score += lowered.count(token)
        score += title.count(token) * 3
        score += path_text.count(token) * 2
    return score


def search_wiki_pages(wiki_root: Path, query: str, limit: int = 5, include_transcripts: bool = False) -> list[SearchResult]:
    tokens = _tokenize(query)
    if not tokens:
        return []

    results: list[SearchResult] = []
    for path in _iter_markdown_files(wiki_root, include_transcripts=include_transcripts):
        text = path.read_text(encoding='utf-8', errors='replace')
        score = _score_document(path, text, query, tokens)
        if score <= 0:
            continue
        results.append(
            SearchResult(
                path=str(path.relative_to(wiki_root)),
                score=score,
                title=_extract_title(text, path.stem),
                snippet=_extract_snippet(text, tokens),
            )
        )

    results.sort(key=lambda item: (-item.score, item.path))
    return results[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Search the Orchestrator wiki and generated knowledge pages')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--wiki', required=True, help='Path to .wiki/orchestrator')
    parser.add_argument('--limit', type=int, default=5, help='Maximum number of results')
    parser.add_argument('--include-transcripts', action='store_true', help='Include transcript markdown files')
    parser.add_argument('--json', action='store_true', help='Emit JSON results')
    args = parser.parse_args(argv)

    wiki_root = Path(args.wiki)
    results = search_wiki_pages(
        wiki_root,
        args.query,
        limit=args.limit,
        include_transcripts=args.include_transcripts,
    )

    if args.json:
        print(json.dumps([result.__dict__ for result in results], indent=2, ensure_ascii=False))
        return 0

    if not results:
        print('No matching wiki pages found.')
        return 0

    for result in results:
        print(f'- [{result.title}]({result.path}) — score={result.score}')
        if result.snippet:
            print(f'  {result.snippet}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
