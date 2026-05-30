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
        "fundamentals-json" => await HandleFundamentalsJsonAsync(yahoo, commandArgs, serializerOptions),
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

static async Task<int> HandleFundamentalsJsonAsync(YahooClient yahoo, string[] args, JsonSerializerOptions serializerOptions)
{
    var symbol = TryGetOptionValue(args, "--symbol", "-s");
    if (string.IsNullOrWhiteSpace(symbol))
    {
        return WriteValidationErrorAndReturn("Missing required option --symbol.", serializerOptions);
    }

    var payload = await BuildFundamentalsPayloadAsync(yahoo, symbol);
    WriteJson(payload, serializerOptions);

    return ExitSuccess;
}

static async Task<FundamentalsPayload> BuildFundamentalsPayloadAsync(YahooClient yahoo, string symbol)
{
    var cashflowStatements = await TryGetAsync(() => yahoo.GetCashflowStatementHistoryAsync(symbol)) ?? [];
    var balanceSheetStatements = await TryGetAsync(() => yahoo.GetBalanceSheetHistoryAsync(symbol)) ?? [];
    var incomeStatements = await TryGetAsync(() => yahoo.GetIncomeStatementHistoryAsync(symbol)) ?? [];
    var financialData = await TryGetAsync(() => yahoo.GetFinancialDataAsync(symbol));
    var keyStatistics = await TryGetAsync(() => yahoo.GetKeyStatisticsAsync(symbol));

    var latestCashflow = GetLatestStatement(cashflowStatements, x => x.EndDate);
    var latestBalanceSheet = GetLatestStatement(balanceSheetStatements, x => x.EndDate);
    var latestIncome = GetLatestStatement(incomeStatements, x => x.EndDate);

    var operatingCashFlowBest = ReadRawNumber(latestCashflow?.TotalCashFromOperatingActivities);
    var operatingCashFlowBackup = ReadRawNumber(financialData?.OperatingCashflow);

    var capitalExpendituresBest = ReadRawNumber(latestCashflow?.CapitalExpenditures);
    var capitalExpendituresBackup = ReadRawNumber(financialData?.FreeCashflow);

    var totalCashBest = ReadRawNumber(latestBalanceSheet?.Cash);
    var totalCashBackup = ReadRawNumber(financialData?.TotalCash);

    var longTermDebt = ReadRawNumber(latestBalanceSheet?.LongTermDebt);
    var shortLongTermDebt = ReadRawNumber(latestBalanceSheet?.ShortLongTermDebt);
    var totalDebtBest = longTermDebt.HasValue || shortLongTermDebt.HasValue
        ? (double?)((longTermDebt ?? 0d) + (shortLongTermDebt ?? 0d))
        : null;
    var totalDebtBackup = ReadRawNumber(financialData?.TotalDebt);

    var sharesOutstandingBest = ReadRawNumber(keyStatistics?.SharesOutstanding);
    var sharesOutstandingBackup = ReadRawNumber(keyStatistics?.ImpliedSharesOutstanding);

    var revenueBest = ReadRawNumber(latestIncome?.TotalRevenue);
    var revenueBackup = ReadRawNumber(financialData?.TotalRevenue);

    var ebitBest = ReadRawNumber(latestIncome?.Ebit);
    var ebitBackup = ReadRawNumber(financialData?.Ebitda);

    var grossProfit = ReadRawNumber(latestIncome?.GrossProfit);
    var operatingIncome = ReadRawNumber(latestIncome?.OperatingIncome);
    var netIncome = ReadRawNumber(latestIncome?.NetIncome);
    var grossMarginBest = ComputeRatio(grossProfit, revenueBest);
    var operatingMarginBest = ComputeRatio(operatingIncome, revenueBest);
    var profitMarginBest = ComputeRatio(netIncome, revenueBest);

    var grossMarginBackup = ReadRawNumber(financialData?.GrossMargins);
    var operatingMarginBackup = ReadRawNumber(financialData?.OperatingMargins);
    var profitMarginBackup = ReadRawNumber(financialData?.ProfitMargins);

    var disclosedFreeCashFlow = ReadRawNumber(financialData?.FreeCashflow);
    var computedFreeCashFlow = operatingCashFlowBest.HasValue && capitalExpendituresBest.HasValue
        ? (double?)(operatingCashFlowBest.Value - Math.Abs(capitalExpendituresBest.Value))
        : null;

    var freeCashFlowBest = disclosedFreeCashFlow ?? computedFreeCashFlow;
    var freeCashFlowBestDetail = disclosedFreeCashFlow.HasValue
        ? "financialData.FreeCashflow"
        : (computedFreeCashFlow.HasValue ? "computedFromStatements(operatingCashFlow - |capitalExpenditures|)" : null);

    return new FundamentalsPayload
    {
        Symbol = symbol.ToUpperInvariant(),
        RetrievedAtUtc = DateTime.UtcNow,
        OperatingCashFlow = BuildMetric(
            field: "Operating cash flow",
            bestSource: "Cash flow statement in annual/interim filings",
            backupSource: "yfinance.cashflow",
            bestValue: operatingCashFlowBest,
            bestDetail: "cashflowStatementHistory.TotalCashFromOperatingActivities",
            backupValue: operatingCashFlowBackup,
            backupDetail: "financialData.OperatingCashflow"),
        CapitalExpenditures = BuildMetric(
            field: "Capital expenditures",
            bestSource: "Cash flow statement in filings",
            backupSource: "yfinance.cashflow",
            bestValue: capitalExpendituresBest,
            bestDetail: "cashflowStatementHistory.CapitalExpenditures",
            backupValue: capitalExpendituresBackup,
            backupDetail: "financialData.FreeCashflow (proxy)"),
        FreeCashFlow = BuildMetric(
            field: "Free cash flow",
            bestSource: "Compute from filings, or use disclosed FCF if available",
            backupSource: "info[\"freeCashFlow\"] if present",
            bestValue: freeCashFlowBest,
            bestDetail: freeCashFlowBestDetail,
            backupValue: disclosedFreeCashFlow,
            backupDetail: "financialData.FreeCashflow"),
        TotalCash = BuildMetric(
            field: "Total cash",
            bestSource: "Balance sheet / key stats in filings",
            backupSource: "info[\"totalCash\"]",
            bestValue: totalCashBest,
            bestDetail: "balanceSheetHistory.Cash",
            backupValue: totalCashBackup,
            backupDetail: "financialData.TotalCash"),
        TotalDebt = BuildMetric(
            field: "Total debt",
            bestSource: "Balance sheet / notes / key stats",
            backupSource: "info[\"totalDebt\"]",
            bestValue: totalDebtBest,
            bestDetail: "balanceSheetHistory.LongTermDebt + balanceSheetHistory.ShortLongTermDebt",
            backupValue: totalDebtBackup,
            backupDetail: "financialData.TotalDebt"),
        SharesOutstanding = BuildMetric(
            field: "Shares outstanding",
            bestSource: "Notes/share capital section / key stats",
            backupSource: "info[\"sharesOutstanding\"]",
            bestValue: sharesOutstandingBest,
            bestDetail: "keyStatistics.SharesOutstanding",
            backupValue: sharesOutstandingBackup,
            backupDetail: "keyStatistics.ImpliedSharesOutstanding"),
        RevenueEbitMargins = new RevenueEbitMarginsPayload
        {
            Revenue = BuildMetric(
                field: "Revenue",
                bestSource: "Income statement / MD&A",
                backupSource: "financials",
                bestValue: revenueBest,
                bestDetail: "incomeStatementHistory.TotalRevenue",
                backupValue: revenueBackup,
                backupDetail: "financialData.TotalRevenue"),
            Ebit = BuildMetric(
                field: "EBIT",
                bestSource: "Income statement / MD&A",
                backupSource: "financials",
                bestValue: ebitBest,
                bestDetail: "incomeStatementHistory.Ebit",
                backupValue: ebitBackup,
                backupDetail: "financialData.Ebitda (proxy)"),
            GrossMargin = BuildMetric(
                field: "Gross margin",
                bestSource: "Income statement / MD&A",
                backupSource: "financials",
                bestValue: grossMarginBest,
                bestDetail: "incomeStatementHistory.GrossProfit / incomeStatementHistory.TotalRevenue",
                backupValue: grossMarginBackup,
                backupDetail: "financialData.GrossMargins"),
            OperatingMargin = BuildMetric(
                field: "Operating margin",
                bestSource: "Income statement / MD&A",
                backupSource: "financials",
                bestValue: operatingMarginBest,
                bestDetail: "incomeStatementHistory.OperatingIncome / incomeStatementHistory.TotalRevenue",
                backupValue: operatingMarginBackup,
                backupDetail: "financialData.OperatingMargins"),
            ProfitMargin = BuildMetric(
                field: "Profit margin",
                bestSource: "Income statement / MD&A",
                backupSource: "financials",
                bestValue: profitMarginBest,
                bestDetail: "incomeStatementHistory.NetIncome / incomeStatementHistory.TotalRevenue",
                backupValue: profitMarginBackup,
                backupDetail: "financialData.ProfitMargins")
        }
    };
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

static async Task<T?> TryGetAsync<T>(Func<Task<T>> action)
{
    try
    {
        return await action();
    }
    catch
    {
        return default;
    }
}

static T? GetLatestStatement<T>(IEnumerable<T> statements, Func<T, object?> endDateSelector)
    where T : class
{
    return statements
        .Select(statement => new { Statement = statement, UnixDate = ReadRawNumber(endDateSelector(statement)) })
        .OrderByDescending(x => x.UnixDate ?? double.MinValue)
        .Select(x => x.Statement)
        .FirstOrDefault();
}

static FundamentalMetricPayload BuildMetric(
    string field,
    string bestSource,
    string backupSource,
    double? bestValue,
    string? bestDetail,
    double? backupValue,
    string? backupDetail)
{
    if (bestValue.HasValue)
    {
        return new FundamentalMetricPayload
        {
            Field = field,
            BestSource = bestSource,
            BackupSource = backupSource,
            SelectedSource = "best",
            SelectedSourceDetail = bestDetail,
            Value = bestValue
        };
    }

    return new FundamentalMetricPayload
    {
        Field = field,
        BestSource = bestSource,
        BackupSource = backupSource,
        SelectedSource = backupValue.HasValue ? "backup" : null,
        SelectedSourceDetail = backupValue.HasValue ? backupDetail : null,
        Value = backupValue
    };
}

static double? ComputeRatio(double? numerator, double? denominator)
{
    if (!numerator.HasValue || !denominator.HasValue || denominator.Value == 0)
    {
        return null;
    }

    return numerator.Value / denominator.Value;
}

static double? ReadRawNumber(object? wrapper)
{
    if (wrapper is null)
    {
        return null;
    }

    var wrapperType = wrapper.GetType();
    var rawProperty = wrapperType.GetProperty("Raw");
    var rawValue = rawProperty?.GetValue(wrapper) ?? wrapper;

    if (rawValue is null)
    {
        return null;
    }

    var valueType = rawValue.GetType();
    if (valueType.FullName is not null && valueType.FullName.StartsWith("System.Nullable`1", StringComparison.Ordinal))
    {
        var hasValue = (bool?)valueType.GetProperty("HasValue")?.GetValue(rawValue);
        if (hasValue == false)
        {
            return null;
        }

        rawValue = valueType.GetProperty("Value")?.GetValue(rawValue);
    }

    if (rawValue is null)
    {
        return null;
    }

    if (rawValue is IConvertible)
    {
        return Convert.ToDouble(rawValue);
    }

    return null;
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
            fundamentals-json --symbol <SYM>

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

internal sealed class FundamentalsPayload
{
    public required string Symbol { get; set; }

    public DateTime RetrievedAtUtc { get; set; }

    public required FundamentalMetricPayload OperatingCashFlow { get; set; }

    public required FundamentalMetricPayload CapitalExpenditures { get; set; }

    public required FundamentalMetricPayload FreeCashFlow { get; set; }

    public required FundamentalMetricPayload TotalCash { get; set; }

    public required FundamentalMetricPayload TotalDebt { get; set; }

    public required FundamentalMetricPayload SharesOutstanding { get; set; }

    public required RevenueEbitMarginsPayload RevenueEbitMargins { get; set; }
}

internal sealed class FundamentalMetricPayload
{
    public required string Field { get; set; }

    public required string BestSource { get; set; }

    public required string BackupSource { get; set; }

    public string? SelectedSource { get; set; }

    public string? SelectedSourceDetail { get; set; }

    public double? Value { get; set; }
}

internal sealed class RevenueEbitMarginsPayload
{
    public string Field { get; set; } = "Revenue / EBIT / margins";

    public string BestSource { get; set; } = "Income statement / MD&A";

    public string BackupSource { get; set; } = "financials";

    public required FundamentalMetricPayload Revenue { get; set; }

    public required FundamentalMetricPayload Ebit { get; set; }

    public required FundamentalMetricPayload GrossMargin { get; set; }

    public required FundamentalMetricPayload OperatingMargin { get; set; }

    public required FundamentalMetricPayload ProfitMargin { get; set; }
}
