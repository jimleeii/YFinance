using ModelContextProtocol.Server;
using System.ComponentModel;

namespace YFinance.Tools;

/// <summary>
/// The fundamentals tool.
/// </summary>
[McpServerToolType]
public static class FundamentalsTool
{
    /// <summary>
    /// Queries fundamentals data and returns fallback-aware payload fields.
    /// </summary>
    /// <param name="fundamentalsService">The fundamentals service.</param>
    /// <param name="symbol">The stock symbol.</param>
    /// <returns>The fundamentals payload.</returns>
    [McpServerTool, Description("Returns a fundamentals payload with best-source and backup-source fallback behavior for cash flow, debt, shares, and margins.")]
    public static async Task<FundamentalsPayload> GetFundamentalsAsync(
        IFundamentalsService fundamentalsService,
        [Description("The stock symbol, e.g. AAPL.")] string symbol)
    {
        return await fundamentalsService.GetFundamentalsAsync(symbol);
    }
}
