using OoplesFinance.YahooFinanceAPI.Enums;

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
