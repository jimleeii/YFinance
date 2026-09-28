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
- `fundamentals-json --symbol <SYM>`
- `all-historical-data --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]`
- `dividends --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]`
- `stock-splits --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]`
- `capital-gains --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]`

`--start-date` defaults to one year before today for the four commands above. `--include-adjusted-close`/`--raw-close` are optional; when neither is passed, the underlying Yahoo API default is used.

### Quote/chart commands

- `chart-info --symbol <SYM> [--range <alias>] [--interval <alias>]` (single object, no `count`). `--range`/`-r` defaults to `1mo`, `--interval`/`-I` defaults to `1d`.
- `spark-chart (--symbol <SYM> [--symbol <SYM> ...] | --symbols <SYM,SYM,...>) [--range <alias>] [--interval <alias>]` — single object when exactly one symbol resolves, list with `count` otherwise. Request echoes `symbol` (single) or `symbols` (array, multiple).
- `real-time-quotes (--symbol <SYM> [--symbol <SYM> ...] | --symbols <SYM,SYM,...>)` — same single-vs-list and `symbol`/`symbols` echo behavior as `spark-chart`.
- `market-summary` (list, no flags besides `--pretty`)
- `auto-complete --search-term <TEXT>` / `-q` (list)
- `stock-recommendations --symbol <SYM>` (list)
- `top-trending-stocks [--country <alias>] --count <N>` — `--country`/`-c` defaults to `us` (UnitedStates); `--count`/`-n` is required and must be a positive integer (list of trending symbol strings).

`--range` aliases: `1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max`.
`--interval` aliases: `1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1w, 1mo, 3mo`.

For `chart-info`, the existing provider response is returned unchanged and the additive
`normalizedData` contract now requires an aligned `completedList` for every candle row.
Completion is computed authoritatively from explicit UTC timestamps and interval duration:
`completed = (timestampUtc + intervalDuration) <= nowUtc`. The active in-progress candle is
therefore `false` by contract. If the provider response is missing arrays, has mismatched lengths,
or contains timestamps without explicit timezone metadata, the command fails fast as
`runtime_error` rather than omitting or inferring completion.
`--country` aliases: `us, uk, au, ca, fr, de, hk, in, it, es`, or the full `Country` enum name case-insensitively (e.g. `UnitedStates`).

### Stats-module commands

These all take only `--symbol <SYM>` and call a single YahooClient stats-module method (`DownloadStatsDataAsync`/`YahooModule`). Single-object commands omit `count`; list commands include it.

- `asset-profile --symbol <SYM>` (single)
- `balance-sheet-history --symbol <SYM>` (list)
- `balance-sheet-history-quarterly --symbol <SYM>` (list)
- `calendar-events --symbol <SYM>` (list)
- `cashflow-statement-history --symbol <SYM>` (list)
- `cashflow-statement-history-quarterly --symbol <SYM>` (list)
- `earnings --symbol <SYM>` (list)
- `earnings-history --symbol <SYM>` (list)
- `earnings-trend --symbol <SYM>` (list)
- `esg-scores --symbol <SYM>` (single)
- `financial-data --symbol <SYM>` (single)
- `fund-ownership --symbol <SYM>` (list)
- `fund-profile --symbol <SYM>` (single)
- `income-statement-history --symbol <SYM>` (list)
- `income-statement-history-quarterly --symbol <SYM>` (list)
- `index-trend --symbol <SYM>` (single)
- `insider-holders --symbol <SYM>` (list)
- `insider-transactions --symbol <SYM>` (list)
- `insights --symbol <SYM>` (single)
- `institution-ownership --symbol <SYM>` (list)
- `key-statistics --symbol <SYM>` (single)
- `major-direct-holders --symbol <SYM>` (list, untyped elements)
- `major-holders-breakdown --symbol <SYM>` (single)
- `net-share-purchase-activity --symbol <SYM>` (single)
- `price-info --symbol <SYM>` (single)
- `quote-type --symbol <SYM>` (single)
- `recommendation-trend --symbol <SYM>` (list)
- `sec-filings --symbol <SYM>` (list)
- `sector-trend --symbol <SYM>` (single)
- `summary-details --symbol <SYM>` (single)
- `upgrade-downgrade-history --symbol <SYM>` (list)

### Screener presets

These all take only `--count <N>`/`-n <N>` (required, must be a positive integer) and call a single
YahooClient screener-preset method. All 36 (verified via reflection against
OoplesFinance.YahooFinanceAPI 1.7.1) return a single aggregate result object, so `count` is omitted
from the response envelope for every command in this group.

- `top-gainers --count <N>` (`ScreenerResult`)
- `top-losers --count <N>` (`ScreenerResult`)
- `small-cap-gainers --count <N>` (`ScreenerResult`)
- `most-active-stocks --count <N>` (`ScreenerResult`)
- `aggressive-small-cap-stocks --count <N>` (`ScreenerResult`)
- `conservative-foreign-funds --count <N>` (`ScreenerResult`)
- `growth-technology-stocks --count <N>` (`ScreenerResult`)
- `high-yield-bonds --count <N>` (`ScreenerResult`)
- `most-shorted-stocks --count <N>` (`ScreenerResult`)
- `portfolio-anchors --count <N>` (`ScreenerResult`)
- `solid-large-growth-funds --count <N>` (`ScreenerResult`)
- `solid-midcap-growth-funds --count <N>` (`ScreenerResult`)
- `top-mutual-funds --count <N>` (`ScreenerResult`)
- `undervalued-growth-stocks --count <N>` (`ScreenerResult`)
- `undervalued-large-cap-stocks --count <N>` (`ScreenerResult`)
- `undervalued-wide-moat-stocks --count <N>` (`ScreenerResult`)
- `morningstar-five-star-stocks --count <N>` (`ScreenerResult`)
- `strong-undervalued-stocks --count <N>` (`ScreenerResult`)
- `analyst-strong-buy-stocks --count <N>` (`AnalystResult`)
- `latest-analyst-upgraded-stocks --count <N>` (`AnalystResult`)
- `most-institutionally-bought-large-cap-stocks --count <N>` (`InstitutionResult`)
- `most-institutionally-held-large-cap-stocks --count <N>` (`InstitutionResult`)
- `most-institutionally-sold-large-cap-stocks --count <N>` (`InstitutionResult`)
- `stocks-with-most-institutional-buyers --count <N>` (`InstitutionResult`)
- `stocks-with-most-institutional-sellers --count <N>` (`InstitutionResult`)
- `stocks-most-bought-by-hedge-funds --count <N>` (`InstitutionResult`)
- `stocks-most-bought-by-pension-funds --count <N>` (`InstitutionResult`)
- `stocks-most-bought-by-private-equity --count <N>` (`InstitutionResult`)
- `stocks-most-bought-by-sovereign-wealth-funds --count <N>` (`InstitutionResult`)
- `top-stocks-owned-by-cathie-wood --count <N>` (`StocksOwnedResult`)
- `top-stocks-owned-by-goldman-sachs --count <N>` (`StocksOwnedResult`)
- `top-stocks-owned-by-warren-buffet --count <N>` (`StocksOwnedResult`)
- `top-stocks-owned-by-ray-dalio --count <N>` (`StocksOwnedResult`)
- `top-bearish-stocks-right-now --count <N>` (`TrendingStocksResult`)
- `top-bullish-stocks-right-now --count <N>` (`TrendingStocksResult`)
- `top-upside-breakout-stocks --count <N>` (`TrendingStocksResult`)

## Output contract

Success shape:

- `ok`: `true`
- `command`: command name
- `request`: normalized request object
- `count`: number of rows (omitted for `all-historical-data`, which returns a single object)
- `data`: array of Yahoo rows, or a single object for `all-historical-data`

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
