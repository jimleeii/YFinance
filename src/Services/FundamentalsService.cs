using OoplesFinance.YahooFinanceAPI;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Services;

/// <summary>
/// Fundamentals service implementation.
/// </summary>
public class FundamentalsService : IFundamentalsService
{
    private readonly YahooClient _yahooClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="FundamentalsService"/> class.
    /// </summary>
    public FundamentalsService()
    {
        _yahooClient = new YahooClient();
    }

    /// <inheritdoc/>
    public async Task<FundamentalsPayload> GetFundamentalsAsync(string symbol)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(symbol);

        var cashflowStatements = await TryGetAsync(() => _yahooClient.GetCashflowStatementHistoryAsync(symbol)) ?? [];
        var balanceSheetStatements = await TryGetAsync(() => _yahooClient.GetBalanceSheetHistoryAsync(symbol)) ?? [];
        var incomeStatements = await TryGetAsync(() => _yahooClient.GetIncomeStatementHistoryAsync(symbol)) ?? [];
        var financialData = await TryGetAsync(() => _yahooClient.GetFinancialDataAsync(symbol));
        var keyStatistics = await TryGetAsync(() => _yahooClient.GetKeyStatisticsAsync(symbol));

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

    private static async Task<T?> TryGetAsync<T>(Func<Task<T>> action)
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

    private static T? GetLatestStatement<T>(IEnumerable<T> statements, Func<T, object?> endDateSelector)
        where T : class
    {
        return statements
            .Select(statement => new { Statement = statement, UnixDate = ReadRawNumber(endDateSelector(statement)) })
            .OrderByDescending(x => x.UnixDate ?? double.MinValue)
            .Select(x => x.Statement)
            .FirstOrDefault();
    }

    private static FundamentalMetricPayload BuildMetric(
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

    private static double? ComputeRatio(double? numerator, double? denominator)
    {
        if (!numerator.HasValue || !denominator.HasValue || denominator.Value == 0)
        {
            return null;
        }

        return numerator.Value / denominator.Value;
    }

    private static double? ReadRawNumber(object? wrapper)
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
}
