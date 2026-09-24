# Log Prompt Commands

This document describes prompt-style commands that are exposed to Copilot Chat from `.github/prompts/*.prompt.md` and append timestamped entries to the repository template logs under the `templates/` folder.

Note: Entry templates have been extracted into dedicated prompt files under the repository `.github/prompts/` directory (for example, `.github/prompts/behavior.prompt.md`). The `templates/` files now point to those prompt files instead of embedding YAML template blocks.

Commands and target files
- `/full-log` — Appends the entry to: `Behavior-Log.md`, `Behavior-Patterns.md`, `Learning-Backlog.md`, `Project-Context-Log.md`, `Runbook.md`, `Skill-Usage-Log.md`.
- `/info` — Appends to: `Skill-Usage-Log.md`, `Behavior-Log.md`.
- `/error` — Appends to: `Behavior-Log.md`, `Project-Context-Log.md`.
- `/warning` or `/warn` — Appends to: `Behavior-Log.md`, `Behavior-Patterns.md`.
- `/debug` — Appends to: `Runbook.md`, `Learning-Backlog.md`.
- `/trace` — Appends to: `Learning-Backlog.md`.
- Short commands: `/behavior`, `/patterns-log`, `/learning-backlog`, `/project-context`, `/runbook`, `/skill-usage` map to their corresponding single files.

How entries are formatted
- Each entry is appended with a header like:

  `### 2026-05-08T14:03:00+07:00 — /full-log — Wei Li`

- Followed by optional `Tags:` and the message body. Files are created if missing.

Usage examples

Bash / cross-platform:

```bash
python scripts/log_prompt.py /full-log "Deployed routing fix" -a "Wei Li"
echo "Long detail message" | python scripts/log_prompt.py /info
python scripts/log_prompt.py /debug --preview "This will be shown but not written"
```

PowerShell:

```powershell
.\scripts\log_prompt.ps1 -Command '/full-log' -Message 'Deployed fix' -Author 'Wei Li'
```

Copilot Chat:

```text
/full-log
/info
/warn
```

If the prompt does not appear in the slash menu, reload the workspace or restart Copilot Chat after adding the `.github/prompts/` files.

Notes
- The CLI tries to infer author from `git config user.name`, then environment variables, then the local account name.
- Use `--preview` to see what will be written without changing files.
