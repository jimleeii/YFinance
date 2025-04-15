using OoplesFinance.YahooFinanceAPI;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Services;

/// <summary>
/// The stock query service.
/// </summary>
public class StockQueryService : IStockQueryService
{
    /// <summary>
    /// The yahoo client.
    /// </summary>
    private readonly YahooClient _yahooClient;

    /// <summary>
    /// Initializes a new instance of the <see cref="StockQueryService"/> class.
    /// </summary>
    public StockQueryService()
    {
        _yahooClient = new YahooClient();
    }

    /// <summary>
    /// Query historical data asynchronously.
    /// </summary>
    /// <param name="queryData">The query data.</param>
    /// <returns>A ValueTask of a list of historical data</returns>
    public async ValueTask<IEnumerable<HistoricalChartInfo>> QueryHistoricalDataAsync(StockQueryParameterData queryData)
    {
        IEnumerable<HistoricalChartInfo> results = await _yahooClient.GetHistoricalDataAsync(queryData.Symbol, queryData.DataFrequency, queryData.StartDate);
        return results;
    }
}