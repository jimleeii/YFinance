using System.Text.Json;
using System.Text.Json.Nodes;
using OoplesFinance.YahooFinanceAPI;
using OoplesFinance.YahooFinanceAPI.Enums;
using OoplesFinance.YahooFinanceAPI.Models;

internal static class HistoricalCommands
{
    // All-history commands share the same historical default lookback window used by the original `query` command's fallback logic.
    private static readonly DateTime DefaultHistoryStartDate = DateTime.UtcNow.Date.AddYears(-1);

    internal static async Task<int> HandleQueryAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
        }

        var startDateText = CliArgHelpers.TryGetOptionValue(args, "--start-date", "-S");
        DateTime startDate = DateTime.UtcNow.Date.AddDays(-1);
        if (!string.IsNullOrWhiteSpace(startDateText) && !DateTime.TryParse(startDateText, out startDate))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Invalid --start-date. Expected yyyy-MM-dd.", serializerOptions);
        }

        var frequencyText = CliArgHelpers.TryGetOptionValue(args, "--frequency", "-f") ?? "daily";
        if (!CliArgHelpers.TryParseFrequency(frequencyText, out var frequency))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Invalid --frequency. Use daily|weekly|monthly.", serializerOptions);
        }

        return await RunQueryAsync(yahoo, "query", symbol, startDate, frequency, serializerOptions);
    }

    internal static async Task<int> HandleQueryTodayAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
        }

        var startDate = DateTime.UtcNow.Date.AddDays(-1);
        var frequency = DataFrequency.Daily;

        return await RunQueryAsync(yahoo, "query-today", symbol, startDate, frequency, serializerOptions);
    }

    internal static async Task<int> HandleQueryJsonAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var inputPath = CliArgHelpers.TryGetOptionValue(args, "--input", "-i");
        var payload = string.IsNullOrWhiteSpace(inputPath)
            ? await Console.In.ReadToEndAsync()
            : await File.ReadAllTextAsync(inputPath);

        if (string.IsNullOrWhiteSpace(payload))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("query-json requires a JSON payload via stdin or --input.", serializerOptions);
        }

        QueryRequest? request;
        try
        {
            request = JsonSerializer.Deserialize<QueryRequest>(payload, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
        }
        catch (JsonException jsonEx)
        {
            return JsonEnvelope.WriteValidationErrorAndReturn($"Invalid JSON payload: {jsonEx.Message}", serializerOptions);
        }

        if (request is null || string.IsNullOrWhiteSpace(request.Symbol))
        {
            return JsonEnvelope.WriteValidationErrorAndReturn("JSON payload must include a non-empty 'symbol'.", serializerOptions);
        }

        var startDate = request.StartDate ?? DateTime.UtcNow.Date.AddDays(-1);
        var frequency = request.DataFrequency ?? DataFrequency.Daily;

        return await RunQueryAsync(yahoo, "query-json", request.Symbol, startDate, frequency, serializerOptions);
    }

    internal static Task<int> HandleAllHistoricalDataAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
    {
        var options = ParseHistoricalOptions(args, DefaultHistoryStartDate);
        if (options.Error is not null)
        {
            return Task.FromResult(JsonEnvelope.WriteValidationErrorAndReturn(options.Error, serializerOptions));
        }

        return RunAllHistoricalDataAsync(yahoo, options, serializerOptions);
    }

    internal static Task<int> HandleDividendsAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
        => HandleEnumerableHistoricalCommandAsync<DividendResult>(
            yahoo, args, serializerOptions, "dividends",
            (client, symbol, freq, start, end, includeAdjustedClose) => includeAdjustedClose.HasValue
                ? client.GetDividendDataAsync(symbol, freq, start, end, includeAdjustedClose.Value)
                : end.HasValue
                    ? client.GetDividendDataAsync(symbol, freq, start, end)
                    : client.GetDividendDataAsync(symbol, freq, start));

    internal static Task<int> HandleStockSplitsAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
        => HandleEnumerableHistoricalCommandAsync<StockSplitResult>(
            yahoo, args, serializerOptions, "stock-splits",
            (client, symbol, freq, start, end, includeAdjustedClose) => includeAdjustedClose.HasValue
                ? client.GetStockSplitDataAsync(symbol, freq, start, end, includeAdjustedClose.Value)
                : end.HasValue
                    ? client.GetStockSplitDataAsync(symbol, freq, start, end)
                    : client.GetStockSplitDataAsync(symbol, freq, start));

    internal static Task<int> HandleCapitalGainsAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
        => HandleEnumerableHistoricalCommandAsync<OoplesFinance.YahooFinanceAPI.Models.Result>(
            yahoo, args, serializerOptions, "capital-gains",
            (client, symbol, freq, start, end, includeAdjustedClose) => includeAdjustedClose.HasValue
                ? client.GetCapitalGainDataAsync(symbol, freq, start, end, includeAdjustedClose.Value)
                : end.HasValue
                    ? client.GetCapitalGainDataAsync(symbol, freq, start, end)
                    : client.GetCapitalGainDataAsync(symbol, freq, start));

    private static async Task<int> RunAllHistoricalDataAsync(YahooClient yahoo, HistoricalOptions options, JsonSerializerOptions serializerOptions)
    {
        HistoricalFullData data = options.IncludeAdjustedClose.HasValue
            ? await yahoo.GetAllHistoricalDataAsync(options.Symbol!, options.Frequency, options.StartDate, options.EndDate, options.IncludeAdjustedClose.Value)
            : options.EndDate.HasValue
                ? await yahoo.GetAllHistoricalDataAsync(options.Symbol!, options.Frequency, options.StartDate, options.EndDate)
                : await yahoo.GetAllHistoricalDataAsync(options.Symbol!, options.Frequency, options.StartDate);

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = "all-historical-data",
            request = BuildHistoricalRequestEcho(options),
            data
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    private static async Task<int> HandleEnumerableHistoricalCommandAsync<T>(
        YahooClient yahoo,
        string[] args,
        JsonSerializerOptions serializerOptions,
        string commandName,
        Func<YahooClient, string, DataFrequency, DateTime, DateTime?, bool?, Task<IEnumerable<T>>> fetch)
    {
        var options = ParseHistoricalOptions(args, DefaultHistoryStartDate);
        if (options.Error is not null)
        {
            return JsonEnvelope.WriteValidationErrorAndReturn(options.Error, serializerOptions);
        }

        var rows = await fetch(yahoo, options.Symbol!, options.Frequency, options.StartDate, options.EndDate, options.IncludeAdjustedClose);
        var materialized = rows as T[] ?? rows.ToArray();

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command = commandName,
            request = BuildHistoricalRequestEcho(options),
            count = materialized.Length,
            data = materialized
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    private static HistoricalOptions ParseHistoricalOptions(string[] args, DateTime defaultStartDate)
    {
        var symbol = CliArgHelpers.TryGetOptionValue(args, "--symbol", "-s");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return HistoricalOptions.Invalid("Missing required option --symbol.");
        }

        var startDateText = CliArgHelpers.TryGetOptionValue(args, "--start-date", "-S");
        if (!CliArgHelpers.TryParseDate(startDateText, out var parsedStartDate))
        {
            return HistoricalOptions.Invalid("Invalid --start-date. Expected yyyy-MM-dd.");
        }

        var endDateText = CliArgHelpers.TryGetOptionValue(args, "--end-date", "-E");
        if (!CliArgHelpers.TryParseDate(endDateText, out var endDate))
        {
            return HistoricalOptions.Invalid("Invalid --end-date. Expected yyyy-MM-dd.");
        }

        var frequencyText = CliArgHelpers.TryGetOptionValue(args, "--frequency", "-f") ?? "daily";
        if (!CliArgHelpers.TryParseFrequency(frequencyText, out var frequency))
        {
            return HistoricalOptions.Invalid("Invalid --frequency. Use daily|weekly|monthly.");
        }

        bool? includeAdjustedClose = null;
        if (CliArgHelpers.IsSwitchOn(args, "--include-adjusted-close"))
        {
            includeAdjustedClose = true;
        }
        else if (CliArgHelpers.IsSwitchOn(args, "--raw-close"))
        {
            includeAdjustedClose = false;
        }

        return new HistoricalOptions(symbol, parsedStartDate ?? defaultStartDate, endDate, frequency, includeAdjustedClose, null);
    }

    private static JsonObject BuildHistoricalRequestEcho(HistoricalOptions options)
    {
        var echo = new JsonObject
        {
            ["symbol"] = options.Symbol,
            ["startDate"] = JsonValue.Create(options.StartDate),
            ["dataFrequency"] = options.Frequency.ToString()
        };

        if (options.EndDate.HasValue)
        {
            echo["endDate"] = JsonValue.Create(options.EndDate.Value);
        }

        if (options.IncludeAdjustedClose.HasValue)
        {
            echo["includeAdjustedClose"] = options.IncludeAdjustedClose.Value;
        }

        return echo;
    }

    private static async Task<int> RunQueryAsync(
        YahooClient yahoo,
        string command,
        string symbol,
        DateTime startDate,
        DataFrequency frequency,
        JsonSerializerOptions serializerOptions)
    {
        IEnumerable<HistoricalChartInfo> rows = await yahoo.GetHistoricalDataAsync(symbol, frequency, startDate);
        var materializedRows = rows as HistoricalChartInfo[] ?? rows.ToArray();

        JsonEnvelope.WriteJson(new
        {
            ok = true,
            command,
            request = new
            {
                symbol,
                startDate,
                dataFrequency = frequency.ToString()
            },
            count = materializedRows.Length,
            data = materializedRows
        }, serializerOptions);

        return JsonEnvelope.ExitSuccess;
    }

    private readonly record struct HistoricalOptions(
        string? Symbol,
        DateTime StartDate,
        DateTime? EndDate,
        DataFrequency Frequency,
        bool? IncludeAdjustedClose,
        string? Error)
    {
        public static HistoricalOptions Invalid(string error) => new(null, default, null, DataFrequency.Daily, null, error);
    }
}
