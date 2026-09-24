using System.Text.Json;
using System.Text.Json.Nodes;
using OoplesFinance.YahooFinanceAPI;

internal static class QuoteCommands
{
    internal static async Task<int> HandleChartInfoAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
        }

        var rangeText = CliArgHelpers.TryGetOptionValue(args, "--range", "-r") ?? "1mo";
        if (!CliArgHelpers.TryParseTimeRange(rangeText, out var range))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --range '{rangeText}'. {CliArgHelpers.TimeRangeAliasesHelp}", serializerOptions);
        }

        var intervalText = CliArgHelpers.TryGetOptionValue(args, "--interval", "-I") ?? "1d";
        if (!CliArgHelpers.TryParseTimeInterval(intervalText, out var interval))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --interval '{intervalText}'. {CliArgHelpers.TimeIntervalAliasesHelp}", serializerOptions);
        }

        var result = await yahoo.GetChartInfoAsync(symbol, range, interval);

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "chart-info",
            request = new { symbol, range = rangeText, interval = intervalText },
            data = result
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    internal static async Task<int> HandleSparkChartAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var symbols = CliArgHelpers.GetOptionValues(args, ["--symbol", "-s"], "--symbols");
        if (symbols.Length == 0)
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol/--symbols.", serializerOptions);
        }

        var rangeText = CliArgHelpers.TryGetOptionValue(args, "--range", "-r") ?? "1mo";
        if (!CliArgHelpers.TryParseTimeRange(rangeText, out var range))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --range '{rangeText}'. {CliArgHelpers.TimeRangeAliasesHelp}", serializerOptions);
        }

        var intervalText = CliArgHelpers.TryGetOptionValue(args, "--interval", "-I") ?? "1d";
        if (!CliArgHelpers.TryParseTimeInterval(intervalText, out var interval))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --interval '{intervalText}'. {CliArgHelpers.TimeIntervalAliasesHelp}", serializerOptions);
        }

        var request = BuildSymbolRequestEcho(symbols);
        request["range"] = rangeText;
        request["interval"] = intervalText;

        // Single-symbol overload returns one SparkInfo (no count); multi-symbol overload returns a list.
        if (symbols.Length == 1)
        {
            var result = await yahoo.GetSparkChartInfoAsync(symbols[0], range, interval);
            JsonEnvelope.WriteJson(new { ok = true, command = "spark-chart", request, data = result }, serializerOptions);
        }
        else
        {
            var rows = await yahoo.GetSparkChartInfoAsync(symbols, range, interval);
            var materialized = rows.ToArray();
            JsonEnvelope.WriteJson(new { ok = true, command = "spark-chart", request, count = materialized.Length, data = materialized }, serializerOptions);
        }

        return JsonEnvelope.ExitSuccess;
    }

    internal static async Task<int> HandleRealTimeQuotesAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var symbols = CliArgHelpers.GetOptionValues(args, ["--symbol", "-s"], "--symbols");
        if (symbols.Length == 0)
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol/--symbols.", serializerOptions);
        }

        var request = BuildSymbolRequestEcho(symbols);

        // Single-symbol overload returns one RealTimeQuoteResult (no count); multi-symbol overload returns a list.
        if (symbols.Length == 1)
        {
            var result = await yahoo.GetRealTimeQuotesAsync(symbols[0]);
            JsonEnvelope.WriteJson(new { ok = true, command = "real-time-quotes", request, data = result }, serializerOptions);
        }
        else
        {
            var rows = await yahoo.GetRealTimeQuotesAsync(symbols);
            var materialized = rows.ToArray();
            JsonEnvelope.WriteJson(new { ok = true, command = "real-time-quotes", request, count = materialized.Length, data = materialized }, serializerOptions);
        }

        return JsonEnvelope.ExitSuccess;
    }

    internal static async Task<int> HandleMarketSummaryAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var rows = await yahoo.GetMarketSummaryAsync();
        var materialized = rows.ToArray();

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "market-summary",
            request = new { },
            count = materialized.Length,
            data = materialized
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    internal static async Task<int> HandleAutoCompleteAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var searchTerm = CliArgHelpers.TryGetOptionValue(args, "--search-term", "-q");
        if (string.IsNullOrWhiteSpace(searchTerm))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --search-term.", serializerOptions);
        }

        var rows = await yahoo.GetAutoCompleteInfoAsync(searchTerm);
        var materialized = rows.ToArray();

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "auto-complete",
            request = new { searchTerm },
            count = materialized.Length,
            data = materialized
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    internal static async Task<int> HandleStockRecommendationsAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
        }

        var rows = await yahoo.GetStockRecommendationsAsync(symbol);
        var materialized = rows.ToArray();

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "stock-recommendations",
            request = new { symbol },
            count = materialized.Length,
            data = materialized
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    internal static async Task<int> HandleTopTrendingStocksAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var countryText = CliArgHelpers.TryGetOptionValue(args, "--country", "-c") ?? "UnitedStates";
        if (!CliArgHelpers.TryParseCountry(countryText, out var country))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --country '{countryText}'. {CliArgHelpers.CountryAliasesHelp}", serializerOptions);
        }

        var countText = CliArgHelpers.TryGetOptionValue(args, "--count", "-n");
        if (!int.TryParse(countText, out var trendingCount) || trendingCount <= 0)
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing or invalid required option --count. Expected a positive integer.", serializerOptions);
        }

        var rows = await yahoo.GetTopTrendingStocksAsync(country, trendingCount);
        var materialized = rows.ToArray();

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "top-trending-stocks",
            request = new { country = countryText, count = trendingCount },
            count = materialized.Length,
            data = materialized
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    // Mirrors real-time-quotes' echo convention: "symbol" for exactly one, "symbols" array when several were resolved.
    private static JsonObject BuildSymbolRequestEcho(string[] symbols)
    {
        var echo = new JsonObject();
        if (symbols.Length == 1)
        {
            echo["symbol"] = symbols[0];
        }
        else
        {
            echo["symbols"] = new JsonArray(symbols.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray());
        }

        return echo;
    }
}
