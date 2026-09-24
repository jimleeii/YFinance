using System.Text.Json;
using OoplesFinance.YahooFinanceAPI;

internal static class CommandRegistry
{
    public static readonly IReadOnlyDictionary<string, Func<YahooClient, string[], JsonSerializerOptions, Task<int>>> Commands = BuildCommands();

    private static Dictionary<string, Func<YahooClient, string[], JsonSerializerOptions, Task<int>>> BuildCommands()
    {
        var commands = new Dictionary<string, Func<YahooClient, string[], JsonSerializerOptions, Task<int>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["query"] = HistoricalCommands.HandleQueryAsync,
            ["query-today"] = HistoricalCommands.HandleQueryTodayAsync,
            ["query-json"] = HistoricalCommands.HandleQueryJsonAsync,
            ["all-historical-data"] = HistoricalCommands.HandleAllHistoricalDataAsync,
            ["dividends"] = HistoricalCommands.HandleDividendsAsync,
            ["stock-splits"] = HistoricalCommands.HandleStockSplitsAsync,
            ["capital-gains"] = HistoricalCommands.HandleCapitalGainsAsync,
            ["fundamentals-json"] = FundamentalsCommands.HandleFundamentalsJsonAsync,
            ["chart-info"] = QuoteCommands.HandleChartInfoAsync,
            ["spark-chart"] = QuoteCommands.HandleSparkChartAsync,
            ["real-time-quotes"] = QuoteCommands.HandleRealTimeQuotesAsync,
            ["market-summary"] = QuoteCommands.HandleMarketSummaryAsync,
            ["auto-complete"] = QuoteCommands.HandleAutoCompleteAsync,
            ["stock-recommendations"] = QuoteCommands.HandleStockRecommendationsAsync,
            ["top-trending-stocks"] = QuoteCommands.HandleTopTrendingStocksAsync
        };

        // Stats-module commands are data-driven (StatsCommands.Definitions); merge rather than list 31 near-duplicate entries here.
        foreach (var (name, handler) in StatsCommands.Handlers)
        {
            commands[name] = handler;
        }

        // Screener-preset commands are data-driven (ScreenerCommands.Definitions); merge rather than list 36 near-duplicate entries here.
        foreach (var (name, handler) in ScreenerCommands.Handlers)
        {
            commands[name] = handler;
        }

        return commands;
    }

    public const string HelpText = """
    yfinance-native-cli: Native stock query CLI for LLM/tooling use

    Commands:
      query                --symbol <SYM> [--start-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly]
      query-today          --symbol <SYM>
      query-json           [--input <path>]   # if --input not provided, reads JSON from stdin
      fundamentals-json    --symbol <SYM>
      all-historical-data  --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]
      dividends            --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]
      stock-splits         --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]
      capital-gains        --symbol <SYM> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly] [--include-adjusted-close|--raw-close]

      chart-info            --symbol <SYM> [--range <1d|5d|1mo|3mo|6mo|1y|2y|5y|10y|ytd|max>] [--interval <1m|2m|5m|15m|30m|60m|90m|1h|1d|5d|1w|1mo|3mo>]
      spark-chart           (--symbol <SYM> [--symbol <SYM> ...] | --symbols <SYM,SYM,...>) [--range ...] [--interval ...]
      real-time-quotes      (--symbol <SYM> [--symbol <SYM> ...] | --symbols <SYM,SYM,...>)
      market-summary
      auto-complete         --search-term <TEXT>
      stock-recommendations --symbol <SYM>
      top-trending-stocks   [--country <us|uk|au|ca|fr|de|hk|in|it|es|FullName>] --count <N>

      Stats-module commands (all take --symbol <SYM> only):
      asset-profile, balance-sheet-history, balance-sheet-history-quarterly, calendar-events,
      cashflow-statement-history, cashflow-statement-history-quarterly, earnings, earnings-history,
      earnings-trend, esg-scores, financial-data, fund-ownership, fund-profile,
      income-statement-history, income-statement-history-quarterly, index-trend, insider-holders,
      insider-transactions, insights, institution-ownership, key-statistics, major-direct-holders,
      major-holders-breakdown, net-share-purchase-activity, price-info, quote-type,
      recommendation-trend, sec-filings, sector-trend, summary-details, upgrade-downgrade-history

      Screener presets (all take --count/-n <N>, a required positive integer, only):
      aggressive-small-cap-stocks, analyst-strong-buy-stocks, conservative-foreign-funds,
      growth-technology-stocks, high-yield-bonds, latest-analyst-upgraded-stocks,
      morningstar-five-star-stocks, most-active-stocks, most-institutionally-bought-large-cap-stocks,
      most-institutionally-held-large-cap-stocks, most-institutionally-sold-large-cap-stocks,
      most-shorted-stocks, portfolio-anchors, small-cap-gainers, solid-large-growth-funds,
      solid-midcap-growth-funds, stocks-most-bought-by-hedge-funds, stocks-most-bought-by-pension-funds,
      stocks-most-bought-by-private-equity, stocks-most-bought-by-sovereign-wealth-funds,
      stocks-with-most-institutional-buyers, stocks-with-most-institutional-sellers,
      strong-undervalued-stocks, top-bearish-stocks-right-now, top-bullish-stocks-right-now,
      top-gainers, top-losers, top-mutual-funds, top-stocks-owned-by-cathie-wood,
      top-stocks-owned-by-goldman-sachs, top-stocks-owned-by-ray-dalio, top-stocks-owned-by-warren-buffet,
      top-upside-breakout-stocks, undervalued-growth-stocks, undervalued-large-cap-stocks,
      undervalued-wide-moat-stocks

    Global options:
      --pretty    Pretty-print JSON output
      --help|-h   Show this help

    Output contract:
      - stdout: JSON only
      - exit 0: success
      - exit 2: validation error
      - exit 1: runtime error
    """;
}
