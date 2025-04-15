using OoplesFinance.YahooFinanceAPI.Models;
using YFinance.Models;

namespace YFinance.Services;

/// <summary>
/// The stock query service interface.
/// </summary>
public interface IStockQueryService
{
    /// <summary>
    /// Query historical data asynchronously.
    /// </summary>
    /// <param name="queryData">The query data.</param>
    /// <returns>A ValueTask of a list of historicalchartinfos</returns>
    ValueTask<IEnumerable<HistoricalChartInfo>> QueryHistoricalDataAsync(StockQueryParameterData queryData);
}