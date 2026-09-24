# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Table of contents

- [1. Think Before Coding](#1-think-before-coding)
- [2. Simplicity First](#2-simplicity-first)
- [3. Surgical Changes](#3-surgical-changes)
- [4. Goal-Driven Execution](#4-goal-driven-execution)
- [Appendix: Agent template (quick) and Karpathy guidance](#appendix-agent-template-quick-and-karpathy-guidance)

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

``` text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Appendix: Agent template (quick) and Karpathy guidance

This repository follows the AGENTS.md template recommendations and Karpathy behavioral guidelines. Use this quick appendix when authoring or updating agent instructions.

- **AGENTS.md quick template:**
  - **Project overview:** short purpose and key tech.
  - **Setup commands:** exact install/build/test commands agents can run.
  - **Dev workflow:** how to run, watch, and build.
  - **Testing:** commands for unit/integration tests and how to run subsets.
  - **Code style & PRs:** linters, formatting, and PR checklist.
  - **Build & deploy:** CI notes and deployment commands.

- **Karpathy (behavioral) checklist for edits:**
  - **Think first:** state assumptions and ask clarifying questions when uncertain.
  - **Simplicity:** implement the minimal change that satisfies the request.
  - **Surgical edits:** change only the lines necessary; avoid unrelated refactors.
  - **Goal-driven:** define success criteria (how to verify) and loop until verified.

Use this appendix as a quick reminder; keep the main sections above specific and actionable for agents. When in doubt, prefer short, tested commands and explicit verification steps.

Local Copilot skills discovery: Agents can reference locally installed Copilot skills found in the external system folder `%USERPROFILE%\\.copilot\\skills`. Treat it as read-only metadata for skill usage logging and routing rules; do not treat it as a workspace path.

## Orchestrator Agent (When using)

> - Use all policy skills from `skills/*/SKILL.md`
> - Use all templates from `.github/agents/templates/` folder
