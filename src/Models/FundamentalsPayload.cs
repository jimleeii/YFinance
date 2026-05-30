namespace YFinance.Models;

/// <summary>
/// The fundamentals payload.
/// </summary>
public class FundamentalsPayload
{
    /// <summary>
    /// Gets or sets the symbol.
    /// </summary>
    public required string Symbol { get; set; }

    /// <summary>
    /// Gets or sets the retrieval timestamp in UTC.
    /// </summary>
    public DateTime RetrievedAtUtc { get; set; }

    /// <summary>
    /// Gets or sets operating cash flow.
    /// </summary>
    public required FundamentalMetricPayload OperatingCashFlow { get; set; }

    /// <summary>
    /// Gets or sets capital expenditures.
    /// </summary>
    public required FundamentalMetricPayload CapitalExpenditures { get; set; }

    /// <summary>
    /// Gets or sets free cash flow.
    /// </summary>
    public required FundamentalMetricPayload FreeCashFlow { get; set; }

    /// <summary>
    /// Gets or sets total cash.
    /// </summary>
    public required FundamentalMetricPayload TotalCash { get; set; }

    /// <summary>
    /// Gets or sets total debt.
    /// </summary>
    public required FundamentalMetricPayload TotalDebt { get; set; }

    /// <summary>
    /// Gets or sets shares outstanding.
    /// </summary>
    public required FundamentalMetricPayload SharesOutstanding { get; set; }

    /// <summary>
    /// Gets or sets revenue, ebit, and margins data.
    /// </summary>
    public required RevenueEbitMarginsPayload RevenueEbitMargins { get; set; }
}

/// <summary>
/// A metric payload that includes best and backup source metadata.
/// </summary>
public class FundamentalMetricPayload
{
    /// <summary>
    /// Gets or sets the field display name.
    /// </summary>
    public required string Field { get; set; }

    /// <summary>
    /// Gets or sets the best source description.
    /// </summary>
    public required string BestSource { get; set; }

    /// <summary>
    /// Gets or sets the backup source description.
    /// </summary>
    public required string BackupSource { get; set; }

    /// <summary>
    /// Gets or sets the selected source label.
    /// </summary>
    public string? SelectedSource { get; set; }

    /// <summary>
    /// Gets or sets the selected source detail.
    /// </summary>
    public string? SelectedSourceDetail { get; set; }

    /// <summary>
    /// Gets or sets the value.
    /// </summary>
    public double? Value { get; set; }
}

/// <summary>
/// Revenue, ebit and margins payload with best/backup source metadata.
/// </summary>
public class RevenueEbitMarginsPayload
{
    /// <summary>
    /// Gets or sets the field display name.
    /// </summary>
    public string Field { get; set; } = "Revenue / EBIT / margins";

    /// <summary>
    /// Gets or sets the best source description.
    /// </summary>
    public string BestSource { get; set; } = "Income statement / MD&A";

    /// <summary>
    /// Gets or sets the backup source description.
    /// </summary>
    public string BackupSource { get; set; } = "financials";

    /// <summary>
    /// Gets or sets revenue.
    /// </summary>
    public required FundamentalMetricPayload Revenue { get; set; }

    /// <summary>
    /// Gets or sets ebit.
    /// </summary>
    public required FundamentalMetricPayload Ebit { get; set; }

    /// <summary>
    /// Gets or sets gross margin.
    /// </summary>
    public required FundamentalMetricPayload GrossMargin { get; set; }

    /// <summary>
    /// Gets or sets operating margin.
    /// </summary>
    public required FundamentalMetricPayload OperatingMargin { get; set; }

    /// <summary>
    /// Gets or sets profit margin.
    /// </summary>
    public required FundamentalMetricPayload ProfitMargin { get; set; }
}
