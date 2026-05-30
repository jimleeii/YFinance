using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Cli
{
    public interface IYFinanceSdk
    {
        Task<IEnumerable<HistoricalChartInfo>> QueryAsync(Models.StockQueryParameterData parameters, CancellationToken ct = default);

        Task<Models.FundamentalsPayload> QueryFundamentalsAsync(string symbol, CancellationToken ct = default);
    }
}
