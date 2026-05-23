using System.IO;
using System.Threading.Tasks;
using Xunit;
using OoplesFinance.YahooFinanceAPI.Models;
using YFinance.Cli.Output;
using System.Collections.Generic;

namespace YFinance.Cli.Tests
{
    public class OutputTests
    {
        [Fact]
        public async Task CsvHeaderIsWritten()
        {
            using var ms = new MemoryStream();
            var data = new List<HistoricalChartInfo>();
            await CsvOutputFormatter.WriteCsvAsync(data, ms);
            ms.Position = 0;
            using var sr = new StreamReader(ms);
            var content = await sr.ReadToEndAsync();
            Assert.Contains("Date,Open,High,Low,Close,AdjustedClose,Volume", content);
        }
    }
}
