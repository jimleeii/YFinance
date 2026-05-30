using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace YFinance.Cli.Tests
{
    public class FundamentalsProxyTests
    {
        [Fact]
        public async Task QueryFundamentalsAsync_UsesExpectedEndpointAndDeserializesPayload()
        {
            const string responseJson = """
            {
              "symbol": "AAPL",
              "retrievedAtUtc": "2026-05-30T00:00:00Z",
              "operatingCashFlow": { "field": "Operating cash flow", "bestSource": "Cash flow statement in annual/interim filings", "backupSource": "yfinance.cashflow", "selectedSource": "best", "selectedSourceDetail": "cashflowStatementHistory.TotalCashFromOperatingActivities", "value": 123.0 },
              "capitalExpenditures": { "field": "Capital expenditures", "bestSource": "Cash flow statement in filings", "backupSource": "yfinance.cashflow", "selectedSource": "best", "selectedSourceDetail": "cashflowStatementHistory.CapitalExpenditures", "value": -10.0 },
              "freeCashFlow": { "field": "Free cash flow", "bestSource": "Compute from filings, or use disclosed FCF if available", "backupSource": "info[\"freeCashFlow\"] if present", "selectedSource": "best", "selectedSourceDetail": "computedFromStatements", "value": 113.0 },
              "totalCash": { "field": "Total cash", "bestSource": "Balance sheet / key stats in filings", "backupSource": "info[\"totalCash\"]", "selectedSource": "backup", "selectedSourceDetail": "financialData.TotalCash", "value": 50.0 },
              "totalDebt": { "field": "Total debt", "bestSource": "Balance sheet / notes / key stats", "backupSource": "info[\"totalDebt\"]", "selectedSource": "best", "selectedSourceDetail": "balanceSheetHistory.LongTermDebt + balanceSheetHistory.ShortLongTermDebt", "value": 70.0 },
              "sharesOutstanding": { "field": "Shares outstanding", "bestSource": "Notes/share capital section / key stats", "backupSource": "info[\"sharesOutstanding\"]", "selectedSource": "best", "selectedSourceDetail": "keyStatistics.SharesOutstanding", "value": 1000.0 },
              "revenueEbitMargins": {
                "field": "Revenue / EBIT / margins",
                "bestSource": "Income statement / MD&A",
                "backupSource": "financials",
                "revenue": { "field": "Revenue", "bestSource": "Income statement / MD&A", "backupSource": "financials", "selectedSource": "best", "selectedSourceDetail": "incomeStatementHistory.TotalRevenue", "value": 300.0 },
                "ebit": { "field": "EBIT", "bestSource": "Income statement / MD&A", "backupSource": "financials", "selectedSource": "best", "selectedSourceDetail": "incomeStatementHistory.Ebit", "value": 75.0 },
                "grossMargin": { "field": "Gross margin", "bestSource": "Income statement / MD&A", "backupSource": "financials", "selectedSource": "best", "selectedSourceDetail": "incomeStatementHistory.GrossProfit / incomeStatementHistory.TotalRevenue", "value": 0.4 },
                "operatingMargin": { "field": "Operating margin", "bestSource": "Income statement / MD&A", "backupSource": "financials", "selectedSource": "best", "selectedSourceDetail": "incomeStatementHistory.OperatingIncome / incomeStatementHistory.TotalRevenue", "value": 0.3 },
                "profitMargin": { "field": "Profit margin", "bestSource": "Income statement / MD&A", "backupSource": "financials", "selectedSource": "best", "selectedSourceDetail": "incomeStatementHistory.NetIncome / incomeStatementHistory.TotalRevenue", "value": 0.2 }
              }
            }
            """;

            var handler = new StubHttpMessageHandler((request, cancellationToken) =>
            {
                Assert.Equal(HttpMethod.Put, request.Method);
                Assert.Equal("http://localhost/api/Fundamentals", request.RequestUri?.ToString());

                var body = request.Content!.ReadAsStringAsync(cancellationToken).GetAwaiter().GetResult();
                using var doc = JsonDocument.Parse(body);
                Assert.Equal("AAPL", doc.RootElement.GetProperty("Symbol").GetString());

                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(responseJson, Encoding.UTF8, "application/json")
                };

                return response;
            });

            var httpClient = new HttpClient(handler);
            var client = new HttpProxyClient(httpClient, "http://localhost");

            var payload = await client.QueryFundamentalsAsync("AAPL");

            Assert.Equal("AAPL", payload.Symbol);
            Assert.Equal(123d, payload.OperatingCashFlow.Value);
            Assert.Equal("Revenue / EBIT / margins", payload.RevenueEbitMargins.Field);
            Assert.Equal(300d, payload.RevenueEbitMargins.Revenue.Value);
        }

        private sealed class StubHttpMessageHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, CancellationToken, HttpResponseMessage> _handler;

            public StubHttpMessageHandler(Func<HttpRequestMessage, CancellationToken, HttpResponseMessage> handler)
            {
                _handler = handler;
            }

            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                return Task.FromResult(_handler(request, cancellationToken));
            }
        }
    }
}
