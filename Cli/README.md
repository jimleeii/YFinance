# YFinance Native CLI

This CLI is a **native direct client** for Yahoo historical stock data.
It does **not** call the MCP server and does **not** proxy through `src/` endpoints.

## Why this CLI is LLM-friendly

- Deterministic machine-readable JSON on stdout
- Stable exit codes (`0`, `1`, `2`)
- Supports both argument-driven and JSON payload-driven invocation
- No interactive prompts required

## Commands

- `query --symbol <SYM> [--start-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly]`
- `query-today --symbol <SYM>`
- `query-json [--input <path>]` (if no `--input`, reads JSON payload from stdin)

## Output contract

Success shape:

- `ok`: `true`
- `command`: command name
- `request`: normalized request object
- `count`: number of rows
- `data`: array of Yahoo rows

Error shape:

- `ok`: `false`
- `error.code`: `validation_error` or `runtime_error`
- `error.message`: human-readable detail

Exit codes:

- `0` = success
- `2` = validation error
- `1` = runtime error

## Example JSON payload (for `query-json`)

```json
{
  "symbol": "AAPL",
  "startDate": "2026-05-01T00:00:00Z",
  "dataFrequency": "Daily"
}
```
