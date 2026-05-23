using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Cli.Output
{
    public static class JsonOutputFormatter
    {
        public static async Task WriteJsonAsync(IEnumerable<HistoricalChartInfo> data, Stream stream, CancellationToken ct = default)
        {
            var options = new JsonSerializerOptions { WriteIndented = true };
            await JsonSerializer.SerializeAsync(stream, data, options, ct);
            await stream.FlushAsync(ct);
        }
    }
}
