# Orchestrator Operational Truth

This document is the canonical operational reference for the mirrored Orchestrator package under `.github/agents/Orchestrator/`.

## Canonical Sources

- Command registry: `scripts/prompt_registry.py`
- Append/log CLI: `scripts/log_prompt.py`
- Prompt/template alignment check: `scripts/validate_prompt_mappings.py`
- Metrics and quality signals: `scripts/analyze_logs.py`
- Knowledge synthesis: `scripts/synthesize_wiki.py`
- Search/retrieval: `scripts/search_wiki.py`
- Dispatch + logging runtime behavior: `DISPATCH_AND_LOGGING_API.md`

## Prompt Commands

### Prompt-backed append commands

| Command | Prompt file | Targets |
| --- | --- | --- |
| `/full-log` | `.github/prompts/full-log.prompt.md` | `Behavior-Log.md`, `Behavior-Patterns.md`, `Learning-Backlog.md`, `Project-Context-Log.md`, `Runbook.md`, `Skill-Usage-Log.md` |
| `/info` | `.github/prompts/info.prompt.md` | `Behavior-Log.md`, `Skill-Usage-Log.md` |
| `/error` | `.github/prompts/error.prompt.md` | `Behavior-Log.md`, `Project-Context-Log.md` |
| `/warning` | `.github/prompts/warning.prompt.md` | `Behavior-Log.md`, `Behavior-Patterns.md` |
| `/warn` | `.github/prompts/warn.prompt.md` | `Behavior-Log.md`, `Behavior-Patterns.md` |
| `/debug` | `.github/prompts/debug.prompt.md` | `Runbook.md`, `Learning-Backlog.md` |
| `/trace` | `.github/prompts/trace.prompt.md` | `Learning-Backlog.md` |
| `/behavior` | `.github/prompts/behavior.prompt.md` | `Behavior-Log.md` |
| `/patterns-log` | `.github/prompts/patterns-log.prompt.md` | `Behavior-Patterns.md` |
| `/learning-backlog` | `.github/prompts/learning-backlog.prompt.md` | `Learning-Backlog.md` |
| `/project-context` | `.github/prompts/project-context.prompt.md` | `Project-Context-Log.md` |
| `/runbook` | `.github/prompts/runbook.prompt.md` | `Runbook.md` |
| `/skill-usage` | `.github/prompts/skill-usage.prompt.md` | `Skill-Usage-Log.md` |

### Prompt-backed workflow command

| Command | Prompt file | Operational scope |
| --- | --- | --- |
| `/cleanup` | `.github/prompts/cleanup.prompt.md` | Cleanup/audit workflow over `Behavior-Log.md`, `Skill-Usage-Log.md`, `Project-Context-Log.md`, `Runbook.md`, `Home.md`, and `audits/orchestrator-wiki-audit-<YYYY-MM-DD>.md` |

`/cleanup` is intentionally **not** handled by the append-only log writer. It is a workflow/audit command, not a simple append command.

### Internal aliases kept for runtime compatibility

- `/all-log` → `/full-log`
- `/behavior-log` → `/behavior`
- `/pattern` → `/patterns-log`
- `/critical` remains internal-only and writes to `Behavior-Log.md`, `Project-Context-Log.md`, and `Runbook.md`

## Operational Workflow

1. Prompt-backed commands are defined in `scripts/prompt_registry.py`.
2. `scripts/validate_prompt_mappings.py` verifies prompt/template alignment and catches orphan prompt files.
3. `scripts/log_prompt.py` renders append-capable commands into `.wiki/orchestrator/` targets.
4. `scripts/analyze_logs.py` converts logs into measurable quality signals:
   - pattern signals
   - backlog status/priority summaries
   - routing quality
   - model selection quality
   - contract-score feedback candidates
5. `scripts/synthesize_wiki.py` generates the knowledge layer under `.wiki/orchestrator/knowledge/`:
   - `Index.md`
   - `Glossary.md`
   - `Learned-Skills.md`
   - `Learned-Routing.md`
   - `Learned-Model-Selection.md`
6. `scripts/search_wiki.py` provides lightweight search/retrieval over the wiki layer, excluding transcripts by default.

## Verification Commands

- Validate prompt mappings: `python .github/agents/Orchestrator/scripts/validate_prompt_mappings.py`
- Analyze logs: `python .github/agents/Orchestrator/scripts/analyze_logs.py --wiki .wiki/orchestrator`
- Generate knowledge pages: `python .github/agents/Orchestrator/scripts/synthesize_wiki.py --wiki .wiki/orchestrator`
- Search wiki knowledge: `python .github/agents/Orchestrator/scripts/search_wiki.py --wiki .wiki/orchestrator "routing quality"`
- Run mirrored tests: `python -m pytest .github/agents/Orchestrator/hooks -q --tb=short`

## Guardrails

- Only prompt-backed append commands should be executed through `scripts/log_prompt.py`.
- Prompt/template drift should be treated as a failing validation condition.
- Knowledge pages are generated artifacts derived from `.wiki/orchestrator/`; the scripts under `.github/agents/Orchestrator/` are the maintained source.
- Search results should prefer the generated knowledge pages and top-level wiki logs over transcript noise unless transcripts are explicitly requested.
