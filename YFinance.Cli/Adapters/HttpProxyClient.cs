using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Cli
{
    public class HttpProxyClient : IYFinanceSdk
    {
        private readonly HttpClient _http;
        private readonly string _server;

        public HttpProxyClient(HttpClient http, string server)
        {
            _http = http;
            _server = server.TrimEnd('/');
        }

        public async Task<IEnumerable<HistoricalChartInfo>> QueryAsync(Models.StockQueryParameterData parameters, CancellationToken ct = default)
        {
            var url = $"{_server}/api/StockQuery";
            var json = JsonSerializer.Serialize(parameters);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            using var resp = await _http.PutAsync(url, content, ct);
            resp.EnsureSuccessStatusCode();
            var stream = await resp.Content.ReadAsStreamAsync(ct);
            var items = await JsonSerializer.DeserializeAsync<IEnumerable<HistoricalChartInfo>>(stream, new JsonSerializerOptions { PropertyNameCaseInsensitive = true }, ct);
            return items ?? System.Linq.Enumerable.Empty<HistoricalChartInfo>();
        }

        public async Task<Models.FundamentalsPayload> QueryFundamentalsAsync(string symbol, CancellationToken ct = default)
        {
            var url = $"{_server}/api/Fundamentals";
            var json = JsonSerializer.Serialize(new Models.FundamentalsRequestData { Symbol = symbol });
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            using var resp = await _http.PutAsync(url, content, ct);
            resp.EnsureSuccessStatusCode();
            var stream = await resp.Content.ReadAsStreamAsync(ct);
            var item = await JsonSerializer.DeserializeAsync<Models.FundamentalsPayload>(stream, new JsonSerializerOptions { PropertyNameCaseInsensitive = true }, ct);
            return item ?? throw new InvalidOperationException("Server returned an empty fundamentals response.");
        }
    }
}
