using System.Text.Json;
using OoplesFinance.YahooFinanceAPI;
using OoplesFinance.YahooFinanceAPI.Enums;
using OoplesFinance.YahooFinanceAPI.Models;

const int ExitSuccess = 0;
const int ExitRuntimeError = 1;
const int ExitValidationError = 2;

var serializerOptions = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    WriteIndented = IsSwitchOn(args, "--pretty")
};

try
{
    if (args.Length == 0 || IsSwitchOn(args, "--help") || IsSwitchOn(args, "-h"))
    {
        WriteHelp();
        return ExitSuccess;
    }

    var command = args[0].Trim().ToLowerInvariant();
    var commandArgs = args.Skip(1).ToArray();

    var yahoo = new YahooClient();

    return command switch
    {
        "query" => await HandleQueryAsync(yahoo, commandArgs, serializerOptions),
        "query-today" => await HandleQueryTodayAsync(yahoo, commandArgs, serializerOptions),
        "query-json" => await HandleQueryJsonAsync(yahoo, commandArgs, serializerOptions),
        _ => WriteValidationErrorAndReturn($"Unknown command '{command}'.", serializerOptions)
    };
}
catch (Exception ex)
{
    WriteJson(new
    {
        ok = false,
        error = new
        {
            code = "runtime_error",
            message = ex.Message
        }
    }, serializerOptions);

    return ExitRuntimeError;
}

static async Task<int> HandleQueryAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
{
    var symbol = TryGetOptionValue(args, "--symbol", "-s");
    if (string.IsNullOrWhiteSpace(symbol))
    {
        return WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
    }

    var startDateText = TryGetOptionValue(args, "--start-date", "-S");
    DateTime startDate = DateTime.UtcNow.Date.AddDays(-1);
    if (!string.IsNullOrWhiteSpace(startDateText) && !DateTime.TryParse(startDateText, out startDate))
    {
        return WriteValidationErrorAndReturn("Invalid --start-date. Expected yyyy-MM-dd.", serializerOptions);
    }

    var frequencyText = TryGetOptionValue(args, "--frequency", "-f") ?? "daily";
    if (!TryParseFrequency(frequencyText, out var frequency))
    {
        return WriteValidationErrorAndReturn("Invalid --frequency. Use daily|weekly|monthly.", serializerOptions);
    }

    return await RunQueryAsync(yahoo, "query", symbol, startDate, frequency, serializerOptions);
}

static async Task<int> HandleQueryTodayAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
{
    var symbol = TryGetOptionValue(args, "--symbol", "-s");
    if (string.IsNullOrWhiteSpace(symbol))
    {
        return WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
    }

    var startDate = DateTime.UtcNow.Date.AddDays(-1);
    var frequency = DataFrequency.Daily;

    return await RunQueryAsync(yahoo, "query-today", symbol, startDate, frequency, serializerOptions);
}

static async Task<int> HandleQueryJsonAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
{
    var inputPath = TryGetOptionValue(args, "--input", "-i");
    var payload = string.IsNullOrWhiteSpace(inputPath)
        ? await Console.In.ReadToEndAsync()
        : await File.ReadAllTextAsync(inputPath);

    if (string.IsNullOrWhiteSpace(payload))
    {
        return WriteValidationErrorAndReturn("query-json requires a JSON payload via stdin or --input.", serializerOptions);
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
        return WriteValidationErrorAndReturn($"Invalid JSON payload: {jsonEx.Message}", serializerOptions);
    }

    if (request is null || string.IsNullOrWhiteSpace(request.Symbol))
    {
        return WriteValidationErrorAndReturn("JSON payload must include a non-empty 'symbol'.", serializerOptions);
    }

    var startDate = request.StartDate ?? DateTime.UtcNow.Date.AddDays(-1);
    var frequency = request.DataFrequency ?? DataFrequency.Daily;

    return await RunQueryAsync(yahoo, "query-json", request.Symbol, startDate, frequency, serializerOptions);
}

static async Task<int> RunQueryAsync(
    YahooClient yahoo,
    string command,
    string symbol,
    DateTime startDate,
    DataFrequency frequency,
    JsonSerializerOptions serializerOptions)
{
    IEnumerable<HistoricalChartInfo> rows = await yahoo.GetHistoricalDataAsync(symbol, frequency, startDate);
    var materializedRows = rows as HistoricalChartInfo[] ?? rows.ToArray();

    WriteJson(new
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

    return ExitSuccess;
}

static bool TryParseFrequency(string? value, out DataFrequency frequency)
{
    frequency = DataFrequency.Daily;
    if (string.IsNullOrWhiteSpace(value))
    {
        return true;
    }

    var normalized = value.Trim().ToLowerInvariant();
    switch (normalized)
    {
        case "d":
        case "daily":
            frequency = DataFrequency.Daily;
            return true;
        case "w":
        case "weekly":
            frequency = DataFrequency.Weekly;
            return true;
        case "m":
        case "monthly":
            frequency = DataFrequency.Monthly;
            return true;
        default:
            return false;
    }
}

static bool IsSwitchOn(string[] args, string switchName)
    => args.Any(arg => string.Equals(arg, switchName, StringComparison.OrdinalIgnoreCase));

static string? TryGetOptionValue(string[] args, params string[] optionNames)
{
    for (var i = 0; i < args.Length; i++)
    {
        foreach (var optionName in optionNames)
        {
            if (!string.Equals(args[i], optionName, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (i + 1 >= args.Length)
            {
                return null;
            }

            return args[i + 1];
        }
    }

    return null;
}

static int WriteValidationErrorAndReturn(string message, JsonSerializerOptions serializerOptions)
{
    WriteJson(new
    {
        ok = false,
        error = new
        {
            code = "validation_error",
            message
        }
    }, serializerOptions);

    return ExitValidationError;
}

static void WriteJson(object payload, JsonSerializerOptions serializerOptions)
{
    Console.WriteLine(JsonSerializer.Serialize(payload, serializerOptions));
}

static void WriteHelp()
{
    var help = """
    yfinance-native-cli: Native stock query CLI for LLM/tooling use

    Commands:
      query       --symbol <SYM> [--start-date <yyyy-MM-dd>] [--frequency daily|weekly|monthly]
      query-today --symbol <SYM>
      query-json  [--input <path>]   # if --input not provided, reads JSON from stdin

    Global options:
      --pretty    Pretty-print JSON output
      --help|-h   Show this help

    Output contract:
      - stdout: JSON only
      - exit 0: success
      - exit 2: validation error
      - exit 1: runtime error
    """;

    Console.WriteLine(help);
}

internal sealed class QueryRequest
{
    public string? Symbol { get; init; }

    public DateTime? StartDate { get; init; }

    public DataFrequency? DataFrequency { get; init; }
}
