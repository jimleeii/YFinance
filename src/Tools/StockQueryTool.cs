using ModelContextProtocol.Server;
using OoplesFinance.YahooFinanceAPI.Models;
using System.ComponentModel;
using YFinance.Models;
using YFinance.Services;

namespace YFinance.Tools;

/// <summary>
/// The stock query tool.
/// </summary>
[McpServerToolType]
public static class StockQueryTool
{
    /// <summary>
    /// Queries historical stock data asynchronously and returns the results to the client.
    /// </summary>
    /// <param name="stockQueryService">The stock query service used to fetch historical data.</param>
    /// <param name="message">The stock query parameter data containing the query details.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an IEnumerable of HistoricalChartInfo.</returns>
    [McpServerTool, Description("Queries historical data and returns the results back to the client.")]
    public static async Task<IEnumerable<HistoricalChartInfo>> QueryAsync(
        IStockQueryService stockQueryService,
        [Description("The stock query parameter data.")] StockQueryParameterData message)
    {
        IEnumerable<HistoricalChartInfo> data = await stockQueryService.QueryHistoricalDataAsync(message);
        return data;
    }
}