using OoplesFinance.YahooFinanceAPI.Enums;

namespace YFinance.Models;

/// <summary>
/// The stock query parameter data.
/// </summary>
public class StockQueryParameterData
{
    /// <summary>
    /// Gets or sets the symbol.
    /// </summary>
    public required string Symbol { get; set; }

    /// <summary>
    /// Gets or sets the start date.
    /// </summary>
    public DateTime StartDate { get; set; } = DateTime.Now.AddDays(-1);

    /// <summary>
    /// Gets or sets the data frequency.
    /// </summary>
    public DataFrequency DataFrequency { get; set; } = DataFrequency.Daily;
}