using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.Cli.Output
{
    public static class CsvOutputFormatter
    {
        public static async Task WriteCsvAsync(IEnumerable<HistoricalChartInfo> data, Stream stream, CancellationToken ct = default)
        {
            using var writer = new StreamWriter(stream, leaveOpen: true);

            // simple header
            await writer.WriteLineAsync("Date,Open,High,Low,Close,AdjustedClose,Volume");

            foreach (var item in data)
            {
                var date = Escape(item.Date);
                var open = Escape(item.Open);
                var high = Escape(item.High);
                var low = Escape(item.Low);
                var close = Escape(item.Close);
                var adj = Escape(item.AdjustedClose);
                var vol = Escape(item.Volume);

                await writer.WriteLineAsync(string.Join(',', new[] { date, open, high, low, close, adj, vol }));
            }

            await writer.FlushAsync();
        }

        static string Escape(object? o)
        {
            if (o == null) return string.Empty;
            var s = Convert.ToString(o, CultureInfo.InvariantCulture) ?? string.Empty;
            if (s.Contains('"')) s = s.Replace("\"", "\"\"");
            if (s.IndexOfAny(new[] { ',', '"', '\n', '\r' }) >= 0) s = '"' + s + '"';
            return s;
        }
    }
}
