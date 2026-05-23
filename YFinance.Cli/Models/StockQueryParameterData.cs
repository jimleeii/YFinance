using System;
using OoplesFinance.YahooFinanceAPI.Enums;

namespace YFinance.Cli.Models
{
    public class StockQueryParameterData
    {
        public required string Symbol { get; set; }

        public DateTime StartDate { get; set; } = DateTime.Now.AddDays(-1);

        public DataFrequency DataFrequency { get; set; } = DataFrequency.Daily;
    }
}
