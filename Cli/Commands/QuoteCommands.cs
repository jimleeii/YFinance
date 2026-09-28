using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using OoplesFinance.YahooFinanceAPI.Enums;
using OoplesFinance.YahooFinanceAPI.Models;
using OoplesFinance.YahooFinanceAPI;

/// <summary>
/// Handles quote-related native CLI commands.
/// </summary>
/// <remarks>
/// Keeps quote command parsing and envelope shaping together so downstream contracts remain stable.
/// </remarks>
internal static class QuoteCommands
{

    #region Public Methods

    /// <summary>
    /// Emits the chart-info response using a Yahoo Finance client.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve chart information.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
    internal static async Task<int> HandleChartInfoAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        return await HandleChartInfoAsync(
            (symbol, range, interval) => yahoo.GetChartInfoAsync(symbol, range, interval),
            args,
            serializerOptions);
    }

    /// <summary>
    /// Emits the chart-info response using the supplied provider seam.
    /// </summary>
    /// <param name="getChartInfoAsync">Provider delegate returning chart information for a symbol and interval.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
    internal static async Task<int> HandleChartInfoAsync(
        Func<string, TimeRange, TimeInterval, Task<ChartInfo>> getChartInfoAsync,
        string[] args,
        JsonSerializerOptions serializerOptions)
    {
        return await HandleChartInfoAsync(
            getChartInfoAsync,
            args,
            serializerOptions,
            () => DateTimeOffset.UtcNow,
            writer: null);
    }

    /// <summary>
    /// Emits the chart-info response using deterministic UTC clock and output-writer seams.
    /// </summary>
    /// <param name="getChartInfoAsync">Provider delegate returning chart information for a symbol and interval.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <param name="utcNowProvider">Clock seam used to compute completion metadata.</param>
    /// <param name="writer">Optional output writer seam used by contract tests.</param>
    /// <returns>The CLI exit code.</returns>
    internal static async Task<int> HandleChartInfoAsync(
        Func<string, TimeRange, TimeInterval, Task<ChartInfo>> getChartInfoAsync,
        string[] args,
        JsonSerializerOptions serializerOptions,
        Func<DateTimeOffset> utcNowProvider,
        TextWriter? writer)
    {
        ArgumentNullException.ThrowIfNull(getChartInfoAsync);
        ArgumentNullException.ThrowIfNull(utcNowProvider);

        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions, writer);
        }

        var rangeText = CliArgHelpers.TryGetOptionValue(args, "--range", "-r") ?? "1mo";
        if (!CliArgHelpers.TryParseTimeRange(rangeText, out var range))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --range '{rangeText}'. {CliArgHelpers.TimeRangeAliasesHelp}", serializerOptions, writer);
        }

        var intervalText = CliArgHelpers.TryGetOptionValue(args, "--interval", "-I") ?? "1d";
        if (!CliArgHelpers.TryParseTimeInterval(intervalText, out var interval))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid --interval '{intervalText}'. {CliArgHelpers.TimeIntervalAliasesHelp}", serializerOptions, writer);
        }

        var result = await getChartInfoAsync(symbol, range, interval);

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "chart-info",
            request = new { symbol, range = rangeText, interval = intervalText },
            data = result,
            normalizedData = BuildNormalizedChartInfoData(result, ToCanonicalIntervalAlias(interval), utcNowProvider)
        }, serializerOptions, writer);

        return JsonEnvelope.ExitSuccess;
    }

    /// <summary>
    /// Emits spark-chart data for one or more symbols.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve spark-chart information.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
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

    /// <summary>
    /// Emits real-time quote data for one or more symbols.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve quote information.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
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

    /// <summary>
    /// Emits the market-summary response.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve market-summary rows.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
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

    /// <summary>
    /// Emits auto-complete results for the requested search term.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve auto-complete matches.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
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

    /// <summary>
    /// Emits stock recommendation rows for the requested symbol.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve recommendation rows.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
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

    /// <summary>
    /// Emits top-trending stocks for a requested country and count.
    /// </summary>
    /// <param name="yahoo">Yahoo Finance client used to retrieve trending stocks.</param>
    /// <param name="args">Command arguments to parse.</param>
    /// <param name="serializerOptions">JSON serialization settings for the emitted envelope.</param>
    /// <returns>The CLI exit code.</returns>
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

    #endregion Public Methods

    #region Private Methods

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

    // Emits the RSI-facing chart contract without mutating the existing raw provider payload.
    private static NormalizedChartInfoData BuildNormalizedChartInfoData(
        ChartInfo result,
        string intervalAlias,
        Func<DateTimeOffset> utcNowProvider)
    {
        ArgumentNullException.ThrowIfNull(result);
        ArgumentException.ThrowIfNullOrWhiteSpace(intervalAlias);
        ArgumentNullException.ThrowIfNull(utcNowProvider);

        var dateList = result.DateList?.ToArray()
            ?? throw new InvalidOperationException("The chart-info response is missing dateList.");
        var openList = result.OpenList?.Select(value => (double?)value).ToArray()
            ?? throw new InvalidOperationException("The chart-info response is missing openList.");
        var highList = result.HighList?.Select(value => (double?)value).ToArray()
            ?? throw new InvalidOperationException("The chart-info response is missing highList.");
        var lowList = result.LowList?.Select(value => (double?)value).ToArray()
            ?? throw new InvalidOperationException("The chart-info response is missing lowList.");
        var closeList = result.CloseList?.Select(value => (double?)value).ToArray()
            ?? throw new InvalidOperationException("The chart-info response is missing closeList.");
        var volumeList = result.VolumeList?.Select(value => (double?)value).ToArray()
            ?? throw new InvalidOperationException("The chart-info response is missing volumeList.");

        var count = dateList.Length;
        if (new[] { openList.Length, highList.Length, lowList.Length, closeList.Length, volumeList.Length }
            .Any(length => length != count))
        {
            throw new InvalidOperationException("The chart-info response contains parallel arrays with different lengths.");
        }

        var intervalDuration = GetIntervalDuration(intervalAlias);
        var nowUtc = utcNowProvider();
        var utcStarts = dateList.Select(ToExplicitUtcStart).ToArray();
        var completedList = utcStarts
            .Select(intervalStart => intervalStart.Add(intervalDuration) <= nowUtc)
            .ToArray();

        return new NormalizedChartInfoData
        {
            DateList = utcStarts.Select(value => value.UtcDateTime.ToString("O", CultureInfo.InvariantCulture)).ToArray(),
            Interval = intervalAlias,
            OpenList = openList,
            HighList = highList,
            LowList = lowList,
            CloseList = closeList,
            VolumeList = volumeList,
            CompletedList = completedList
        };
    }

    // Refuses to infer timezone offsets for timestamps that do not carry explicit DateTime kind metadata.
    private static DateTimeOffset ToExplicitUtcStart(DateTime value)
    {
        return value.Kind switch
        {
            DateTimeKind.Utc => new DateTimeOffset(value, TimeSpan.Zero),
            DateTimeKind.Local => throw new InvalidOperationException("The chart-info response contains local timestamps; the explicit UTC contract requires provider-supplied offsets."),
            DateTimeKind.Unspecified => throw new InvalidOperationException("The chart-info response contains timestamps without explicit timezone metadata."),
            _ => throw new InvalidOperationException("The chart-info response contains timestamps with an unsupported DateTime kind.")
        };
    }

    // Resolves canonical interval aliases to durations used for active-candle completion checks.
    private static TimeSpan GetIntervalDuration(string intervalAlias)
    {
        return intervalAlias switch
        {
            "1m" => TimeSpan.FromMinutes(1),
            "2m" => TimeSpan.FromMinutes(2),
            "5m" => TimeSpan.FromMinutes(5),
            "15m" => TimeSpan.FromMinutes(15),
            "30m" => TimeSpan.FromMinutes(30),
            "60m" => TimeSpan.FromMinutes(60),
            "90m" => TimeSpan.FromMinutes(90),
            "1h" => TimeSpan.FromHours(1),
            "1d" => TimeSpan.FromDays(1),
            "5d" => TimeSpan.FromDays(5),
            "1w" => TimeSpan.FromDays(7),
            "1mo" => TimeSpan.FromDays(30),
            "3mo" => TimeSpan.FromDays(90),
            _ => throw new InvalidOperationException($"Unsupported interval alias '{intervalAlias}' for completion metadata.")
        };
    }

    // Canonicalizes accepted interval aliases so downstream consumers see one stable contract identity.
    private static string ToCanonicalIntervalAlias(TimeInterval interval)
    {
        return interval switch
        {
            TimeInterval._1Minute => "1m",
            TimeInterval._2Minutes => "2m",
            TimeInterval._5Minutes => "5m",
            TimeInterval._15Minutes => "15m",
            TimeInterval._30Minutes => "30m",
            TimeInterval._60Minutes => "60m",
            TimeInterval._90Minutes => "90m",
            TimeInterval._1Hour => "1h",
            TimeInterval._1Day => "1d",
            TimeInterval._5Days => "5d",
            TimeInterval._1Week => "1w",
            TimeInterval._1Month => "1mo",
            TimeInterval._3Months => "3mo",
            _ => throw new ArgumentOutOfRangeException(nameof(interval))
        };
    }

    #endregion Private Methods

    #region Nested Types

    /// <summary>
    /// Represents the additive normalized chart-info contract consumed by the RSI workspace.
    /// </summary>
    /// <remarks>
    /// Remains nested beside the command helpers so the emitted contract can evolve with the chart-info command in one place.
    /// </remarks>
    private sealed class NormalizedChartInfoData
    {
        /// <summary>
        /// Gets or sets the UTC-designated candle timestamps.
        /// </summary>
        [JsonPropertyName("dateList")]
        public IReadOnlyList<string>? DateList { get; set; }

        /// <summary>
        /// Gets or sets the canonical interval identity.
        /// </summary>
        [JsonPropertyName("interval")]
        public string? Interval { get; set; }

        /// <summary>
        /// Gets or sets the opening values aligned with <see cref="DateList"/>.
        /// </summary>
        [JsonPropertyName("openList")]
        public IReadOnlyList<double?>? OpenList { get; set; }

        /// <summary>
        /// Gets or sets the high values aligned with <see cref="DateList"/>.
        /// </summary>
        [JsonPropertyName("highList")]
        public IReadOnlyList<double?>? HighList { get; set; }

        /// <summary>
        /// Gets or sets the low values aligned with <see cref="DateList"/>.
        /// </summary>
        [JsonPropertyName("lowList")]
        public IReadOnlyList<double?>? LowList { get; set; }

        /// <summary>
        /// Gets or sets the close values aligned with <see cref="DateList"/>.
        /// </summary>
        [JsonPropertyName("closeList")]
        public IReadOnlyList<double?>? CloseList { get; set; }

        /// <summary>
        /// Gets or sets the volume values aligned with <see cref="DateList"/>.
        /// </summary>
        [JsonPropertyName("volumeList")]
        public IReadOnlyList<double?>? VolumeList { get; set; }

        /// <summary>
        /// Gets or sets required provider completion flags aligned with <see cref="DateList"/>.
        /// </summary>
        [JsonPropertyName("completedList")]
        public IReadOnlyList<bool> CompletedList { get; set; } = [];
    }

    #endregion Nested Types
}
