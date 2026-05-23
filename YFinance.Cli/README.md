# YFinance CLI (MVP)

A small CLI wrapper for the YFinance project. It can query historical stock data locally
via the bundled Yahoo client or proxy requests to a running YFinance server.

Quick install (local testing)

```powershell
# Build and pack the CLI (repo root)
dotnet pack src/YFinance.Cli/YFinance.Cli.csproj -c Release -o ./artifacts

# Install the packed tool locally
dotnet tool install --global --add-source ./artifacts YFinance.Cli

# Update later:
dotnet tool update --global --add-source ./artifacts YFinance.Cli
```

Usage

```powershell
yfinance query --symbol AAPL --start 2026-05-01 --format csv --output aapl.csv
yfinance query --symbol AAPL --server http://localhost:5005

# short form example
yfinance query -s MSFT -S 2026-01-01 -f weekly -F json
```

Options (MVP)

- `--symbol`, `-s` : Stock symbol (required)
- `--start`, `-S` : Start date (yyyy-MM-dd). Defaults to yesterday
- `--frequency`, `-f` : `daily|weekly|monthly` or `d|w|m` (case-insensitive)
- `--format`, `-F` : `json|csv` (default: `json`)
- `--output`, `-o` : Output file path (defaults to stdout)
- `--server` : Proxy to a running YFinance server (http(s) URL)
- `--verbose`, `-v` : Verbose logging to stderr

Helpful commands

- `yfinance examples` — show curated usage examples and notes
- `yfinance --help` — show command and option descriptions

Packaging & publishing

To publish to NuGet.org from CI, pack and push with your API key:

```bash
dotnet pack src/YFinance.Cli/YFinance.Cli.csproj -c Release -o ./artifacts
dotnet nuget push ./artifacts/*.nupkg -k <NUGET_API_KEY> -s https://api.nuget.org/v3/index.json
```

See also: [docs/CLI_USAGE.md](docs/CLI_USAGE.md) for more examples and sample output.

Notes

- This is an MVP scaffold. For production use, extract shared DTOs into a `YFinance.Core` library,
  add robust retries, logging controls, authentication, and additional tests.

