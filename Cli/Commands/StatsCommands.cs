using System.Collections;
using System.Text.Json;
using OoplesFinance.YahooFinanceAPI;

// Table-driven dispatcher: every command below only differs by which YahooClient stats-module
// method it calls and whether that method returns a list or a single object, so one generic
// handler serves all of them instead of 31 near-duplicate methods.
internal static class StatsCommands
{
    // Field must be declared before Handlers below: static field initializers run in textual order.
    private static readonly StatsCommandDefinition[] Definitions =
    [
        new("asset-profile", async (c, s) => await c.GetAssetProfileAsync(s), IsList: false),
        new("balance-sheet-history", async (c, s) => await c.GetBalanceSheetHistoryAsync(s), IsList: true),
        new("balance-sheet-history-quarterly", async (c, s) => await c.GetBalanceSheetHistoryQuarterlyAsync(s), IsList: true),
        new("calendar-events", async (c, s) => await c.GetCalendarEventsAsync(s), IsList: true),
        new("cashflow-statement-history", async (c, s) => await c.GetCashflowStatementHistoryAsync(s), IsList: true),
        new("cashflow-statement-history-quarterly", async (c, s) => await c.GetCashflowStatementHistoryQuarterlyAsync(s), IsList: true),
        new("earnings", async (c, s) => await c.GetEarningsAsync(s), IsList: true),
        new("earnings-history", async (c, s) => await c.GetEarningsHistoryAsync(s), IsList: true),
        new("earnings-trend", async (c, s) => await c.GetEarningsTrendAsync(s), IsList: true),
        new("esg-scores", async (c, s) => await c.GetEsgScoresAsync(s), IsList: false),
        new("financial-data", async (c, s) => await c.GetFinancialDataAsync(s), IsList: false),
        new("fund-ownership", async (c, s) => await c.GetFundOwnershipAsync(s), IsList: true),
        new("fund-profile", async (c, s) => await c.GetFundProfileAsync(s), IsList: false),
        new("income-statement-history", async (c, s) => await c.GetIncomeStatementHistoryAsync(s), IsList: true),
        new("income-statement-history-quarterly", async (c, s) => await c.GetIncomeStatementHistoryQuarterlyAsync(s), IsList: true),
        new("index-trend", async (c, s) => await c.GetIndexTrendAsync(s), IsList: false),
        new("insider-holders", async (c, s) => await c.GetInsiderHoldersAsync(s), IsList: true),
        new("insider-transactions", async (c, s) => await c.GetInsiderTransactionsAsync(s), IsList: true),
        new("insights", async (c, s) => await c.GetInsightsAsync(s), IsList: false),
        new("institution-ownership", async (c, s) => await c.GetInstitutionOwnershipAsync(s), IsList: true),
        new("key-statistics", async (c, s) => await c.GetKeyStatisticsAsync(s), IsList: false),
        new("major-direct-holders", async (c, s) => await c.GetMajorDirectHoldersAsync(s), IsList: true),
        new("major-holders-breakdown", async (c, s) => await c.GetMajorHoldersBreakdownAsync(s), IsList: false),
        new("net-share-purchase-activity", async (c, s) => await c.GetNetSharePurchaseActivityAsync(s), IsList: false),
        new("price-info", async (c, s) => await c.GetPriceInfoAsync(s), IsList: false),
        new("quote-type", async (c, s) => await c.GetQuoteTypeAsync(s), IsList: false),
        new("recommendation-trend", async (c, s) => await c.GetRecommendationTrendAsync(s), IsList: true),
        new("sec-filings", async (c, s) => await c.GetSecFilingsAsync(s), IsList: true),
        new("sector-trend", async (c, s) => await c.GetSectorTrendAsync(s), IsList: false),
        new("summary-details", async (c, s) => await c.GetSummaryDetailsAsync(s), IsList: false),
        new("upgrade-downgrade-history", async (c, s) => await c.GetUpgradeDowngradeHistoryAsync(s), IsList: true)
    ];

    public static readonly IReadOnlyDictionary<string, Func<YahooClient, string[], JsonSerializerOptions, Task<int>>> Handlers =
        Definitions.ToDictionary(
            d => d.Name,
            Func<YahooClient, string[], JsonSerializerOptions, Task<int>> (d) => (yahoo, args, serializerOptions) => HandleAsync(yahoo, args, serializerOptions, d),
            StringComparer.OrdinalIgnoreCase);

    private static async Task<int> HandleAsync(
        YahooClient yahoo,
        string[] args,
        JsonSerializerOptions serializerOptions,
        StatsCommandDefinition definition)
    {
        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
        }

        var result = await definition.Invoke(yahoo, symbol);

        if (definition.IsList)
        {
            var materialized = ((IEnumerable)result!).Cast<object>().ToArray();
            JsonEnvelope.WriteJson(new
            {
                ok = true,
                command = definition.Name,
                request = new { symbol },
                count = materialized.Length,
                data = materialized
            }, serializerOptions);
        }
        else
        {
            JsonEnvelope.WriteJson(new
            {
                ok = true,
                command = definition.Name,
                request = new { symbol },
                data = result
            }, serializerOptions);
        }

        return JsonEnvelope.ExitSuccess;
    }

    private readonly record struct StatsCommandDefinition(string Name, Func<YahooClient, string, Task<object?>> Invoke, bool IsList);
}
