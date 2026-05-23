using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using OoplesFinance.YahooFinanceAPI;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Cli
{
    public class YahooClientAdapter : IYFinanceSdk
    {
        private readonly YahooClient _client;

        public YahooClientAdapter()
        {
            _client = new YahooClient();
        }

        public async Task<IEnumerable<HistoricalChartInfo>> QueryAsync(Models.StockQueryParameterData parameters, CancellationToken ct = default)
        {
            return await _client.GetHistoricalDataAsync(parameters.Symbol, parameters.DataFrequency, parameters.StartDate);
        }
    }
}
