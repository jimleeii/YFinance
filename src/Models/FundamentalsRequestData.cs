namespace YFinance.Models;

/// <summary>
/// The fundamentals request data.
/// </summary>
public class FundamentalsRequestData
{
    /// <summary>
    /// Gets or sets the stock symbol.
    /// </summary>
    public required string Symbol { get; set; }
}
