using ModelContextProtocol.Server;
using OoplesFinance.YahooFinanceAPI.Enums;
using OoplesFinance.YahooFinanceAPI.Models;
using System.ComponentModel;

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

    /// <summary>
    /// Queries today's historical data and returns the results back to the client.
    /// </summary>
    /// <remarks>
    /// <param name="stockQueryService">The stock query service used to fetch historical data.</param>
    /// The <paramref name="message"/> StartDate is set to yesterday and the DataFrequency is set to Daily.
    /// </remarks>
    [McpServerTool, Description("Queries today's historical data and returns the results back to the client.")]
    public static async Task<IEnumerable<HistoricalChartInfo>> QueryTodayAsync(
        IStockQueryService stockQueryService,
        [Description("The stock query parameter data.")] StockQueryParameterData message)
    {
        message.StartDate = DateTime.Today.AddDays(-1);
        message.DataFrequency = DataFrequency.Daily;
        IEnumerable<HistoricalChartInfo> data = await stockQueryService.QueryHistoricalDataAsync(message);
        return data;
    }
}