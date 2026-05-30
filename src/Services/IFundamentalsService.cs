namespace YFinance.Services;

/// <summary>
/// Fundamentals service interface.
/// </summary>
public interface IFundamentalsService
{
    /// <summary>
    /// Gets fundamentals asynchronously for a stock symbol.
    /// </summary>
    /// <param name="symbol">The stock symbol.</param>
    /// <returns>The fundamentals payload.</returns>
    Task<FundamentalsPayload> GetFundamentalsAsync(string symbol);
}
