using System.Text.Json;
using OoplesFinance.YahooFinanceAPI;

// Table-driven dispatcher: every command below only differs by which YahooClient screener-preset
// method it calls; all take a single --count/-n <int> option and (verified via reflection against
// OoplesFinance.YahooFinanceAPI 1.7.1) return one aggregate result object rather than a list, so one
// generic handler serves all 36 instead of 36 near-duplicate methods.
internal static class ScreenerCommands
{
    // Field must be declared before Handlers below: static field initializers run in textual order.
    private static readonly ScreenerCommandDefinition[] Definitions =
    [
        new("aggressive-small-cap-stocks", async (c, n) => await c.GetAggressiveSmallCapStocksAsync(n)),
        new("analyst-strong-buy-stocks", async (c, n) => await c.GetAnalystStrongBuyStocksAsync(n)),
        new("conservative-foreign-funds", async (c, n) => await c.GetConservativeForeignFundsAsync(n)),
        new("growth-technology-stocks", async (c, n) => await c.GetGrowthTechnologyStocksAsync(n)),
        new("high-yield-bonds", async (c, n) => await c.GetHighYieldBondsAsync(n)),
        new("latest-analyst-upgraded-stocks", async (c, n) => await c.GetLatestAnalystUpgradedStocksAsync(n)),
        new("morningstar-five-star-stocks", async (c, n) => await c.GetMorningstarFiveStarStocksAsync(n)),
        new("most-active-stocks", async (c, n) => await c.GetMostActiveStocksAsync(n)),
        new("most-institutionally-bought-large-cap-stocks", async (c, n) => await c.GetMostInstitutionallyBoughtLargeCapStocksAsync(n)),
        new("most-institutionally-held-large-cap-stocks", async (c, n) => await c.GetMostInstitutionallyHeldLargeCapStocksAsync(n)),
        new("most-institutionally-sold-large-cap-stocks", async (c, n) => await c.GetMostInstitutionallySoldLargeCapStocksAsync(n)),
        new("most-shorted-stocks", async (c, n) => await c.GetMostShortedStocksAsync(n)),
        new("portfolio-anchors", async (c, n) => await c.GetPortfolioAnchorsAsync(n)),
        new("small-cap-gainers", async (c, n) => await c.GetSmallCapGainersAsync(n)),
        new("solid-large-growth-funds", async (c, n) => await c.GetSolidLargeGrowthFundsAsync(n)),
        new("solid-midcap-growth-funds", async (c, n) => await c.GetSolidMidcapGrowthFundsAsync(n)),
        new("stocks-most-bought-by-hedge-funds", async (c, n) => await c.GetStocksMostBoughtByHedgeFundsAsync(n)),
        new("stocks-most-bought-by-pension-funds", async (c, n) => await c.GetStocksMostBoughtByPensionFundsAsync(n)),
        new("stocks-most-bought-by-private-equity", async (c, n) => await c.GetStocksMostBoughtByPrivateEquityAsync(n)),
        new("stocks-most-bought-by-sovereign-wealth-funds", async (c, n) => await c.GetStocksMostBoughtBySovereignWealthFundsAsync(n)),
        new("stocks-with-most-institutional-buyers", async (c, n) => await c.GetStocksWithMostInstitutionalBuyersAsync(n)),
        new("stocks-with-most-institutional-sellers", async (c, n) => await c.GetStocksWithMostInstitutionalSellersAsync(n)),
        new("strong-undervalued-stocks", async (c, n) => await c.GetStrongUndervaluedStocksAsync(n)),
        new("top-bearish-stocks-right-now", async (c, n) => await c.GetTopBearishStocksRightNowAsync(n)),
        new("top-bullish-stocks-right-now", async (c, n) => await c.GetTopBullishStocksRightNowAsync(n)),
        new("top-gainers", async (c, n) => await c.GetTopGainersAsync(n)),
        new("top-losers", async (c, n) => await c.GetTopLosersAsync(n)),
        new("top-mutual-funds", async (c, n) => await c.GetTopMutualFundsAsync(n)),
        new("top-stocks-owned-by-cathie-wood", async (c, n) => await c.GetTopStocksOwnedByCathieWoodAsync(n)),
        new("top-stocks-owned-by-goldman-sachs", async (c, n) => await c.GetTopStocksOwnedByGoldmanSachsAsync(n)),
        new("top-stocks-owned-by-ray-dalio", async (c, n) => await c.GetTopStocksOwnedByRayDalioAsync(n)),
        new("top-stocks-owned-by-warren-buffet", async (c, n) => await c.GetTopStocksOwnedByWarrenBuffetAsync(n)),
        new("top-upside-breakout-stocks", async (c, n) => await c.GetTopUpsideBreakoutStocksAsync(n)),
        new("undervalued-growth-stocks", async (c, n) => await c.GetUndervaluedGrowthStocksAsync(n)),
        new("undervalued-large-cap-stocks", async (c, n) => await c.GetUndervaluedLargeCapStocksAsync(n)),
        new("undervalued-wide-moat-stocks", async (c, n) => await c.GetUndervaluedWideMoatStocksAsync(n))
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
        ScreenerCommandDefinition definition)
    {
        var countText = CliArgHelpers.TryGetOptionValue(args, "--count", "-n");
        if (!int.TryParse(countText, out var count) || count <= 0)
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing or invalid required option --count. Expected a positive integer.", serializerOptions);
        }

        var result = await definition.Invoke(yahoo, count);

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = definition.Name,
            request = new { count },
            data = result
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    private readonly record struct ScreenerCommandDefinition(string Name, Func<YahooClient, int, Task<object?>> Invoke);
}
