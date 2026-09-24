using OoplesFinance.YahooFinanceAPI.Enums;

internal static class CliArgHelpers
{
    public static bool IsSwitchOn(string[] args, string switchName)
        => args.Any(arg => string.Equals(arg, switchName, StringComparison.OrdinalIgnoreCase));

    public static string? TryGetOptionValue(string[] args, params string[] optionNames)
    {
        for (var i = 0; i < args.Length; i++)
        {
            foreach (var optionName in optionNames)
            {
                if (!string.Equals(args[i], optionName, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (i + 1 >= args.Length)
                {
                    return null;
                }

                return args[i + 1];
            }
        }

        return null;
    }

    public static bool TryParseFrequency(string? value, out DataFrequency frequency)
    {
        frequency = DataFrequency.Daily;
        if (string.IsNullOrWhiteSpace(value))
        {
            return true;
        }

        var normalized = value.Trim().ToLowerInvariant();
        switch (normalized)
        {
            case "d":
            case "daily":
                frequency = DataFrequency.Daily;
                return true;
            case "w":
            case "weekly":
                frequency = DataFrequency.Weekly;
                return true;
            case "m":
            case "monthly":
                frequency = DataFrequency.Monthly;
                return true;
            default:
                return false;
        }
    }

    // Returns false only when text was supplied but failed to parse; value stays null when text is absent.
    public static bool TryParseDate(string? text, out DateTime? value)
    {
        value = null;
        if (string.IsNullOrWhiteSpace(text))
        {
            return true;
        }

        if (!DateTime.TryParse(text, out var parsed))
        {
            return false;
        }

        value = parsed;
        return true;
    }

    // Merges repeated single-value occurrences (e.g. -s AAPL -s MSFT) with one comma-delimited option
    // (e.g. --symbols AAPL,MSFT), then dedupes case-insensitively so callers get one canonical symbol list.
    public static string[] GetOptionValues(string[] args, string[] repeatableOptionNames, string commaDelimitedOptionName)
    {
        var values = new List<string>();
        for (var i = 0; i < args.Length; i++)
        {
            if (repeatableOptionNames.Any(name => string.Equals(args[i], name, StringComparison.OrdinalIgnoreCase)))
            {
                if (i + 1 < args.Length)
                {
                    values.Add(args[i + 1]);
                }
            }
            else if (string.Equals(args[i], commaDelimitedOptionName, StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
            {
                values.AddRange(args[i + 1].Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
            }
        }

        return values
            .Where(v => !string.IsNullOrWhiteSpace(v))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static readonly Dictionary<string, TimeRange> TimeRangeAliasMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["1d"] = TimeRange._1Day,
        ["5d"] = TimeRange._5Days,
        ["1mo"] = TimeRange._1Month,
        ["3mo"] = TimeRange._3Months,
        ["6mo"] = TimeRange._6Months,
        ["1y"] = TimeRange._1Year,
        ["2y"] = TimeRange._2Years,
        ["5y"] = TimeRange._5Years,
        ["10y"] = TimeRange._10Years,
        ["ytd"] = TimeRange.YearToDate,
        ["max"] = TimeRange.Max
    };

    public const string TimeRangeAliasesHelp = "Valid --range values: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max.";

    public static bool TryParseTimeRange(string? value, out TimeRange range)
    {
        range = TimeRange._1Month;
        return string.IsNullOrWhiteSpace(value) || TimeRangeAliasMap.TryGetValue(value.Trim(), out range);
    }

    private static readonly Dictionary<string, TimeInterval> TimeIntervalAliasMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["1m"] = TimeInterval._1Minute,
        ["2m"] = TimeInterval._2Minutes,
        ["5m"] = TimeInterval._5Minutes,
        ["15m"] = TimeInterval._15Minutes,
        ["30m"] = TimeInterval._30Minutes,
        ["60m"] = TimeInterval._60Minutes,
        ["90m"] = TimeInterval._90Minutes,
        ["1h"] = TimeInterval._1Hour,
        ["1d"] = TimeInterval._1Day,
        ["5d"] = TimeInterval._5Days,
        ["1w"] = TimeInterval._1Week,
        ["1mo"] = TimeInterval._1Month,
        ["3mo"] = TimeInterval._3Months
    };

    public const string TimeIntervalAliasesHelp = "Valid --interval values: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1w, 1mo, 3mo.";

    public static bool TryParseTimeInterval(string? value, out TimeInterval interval)
    {
        interval = TimeInterval._1Day;
        return string.IsNullOrWhiteSpace(value) || TimeIntervalAliasMap.TryGetValue(value.Trim(), out interval);
    }

    private static readonly Dictionary<string, Country> CountryAliasMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["us"] = Country.UnitedStates,
        ["unitedstates"] = Country.UnitedStates,
        ["uk"] = Country.UnitedKingdom,
        ["unitedkingdom"] = Country.UnitedKingdom,
        ["au"] = Country.Australia,
        ["australia"] = Country.Australia,
        ["ca"] = Country.Canada,
        ["canada"] = Country.Canada,
        ["fr"] = Country.France,
        ["france"] = Country.France,
        ["de"] = Country.Germany,
        ["germany"] = Country.Germany,
        ["hk"] = Country.HongKong,
        ["hongkong"] = Country.HongKong,
        ["in"] = Country.India,
        ["india"] = Country.India,
        ["it"] = Country.Italy,
        ["italy"] = Country.Italy,
        ["es"] = Country.Spain,
        ["spain"] = Country.Spain
    };

    public const string CountryAliasesHelp = "Valid --country values: us, uk, au, ca, fr, de, hk, in, it, es (or full names, e.g. UnitedStates).";

    public static bool TryParseCountry(string? value, out Country country)
    {
        country = Country.UnitedStates;
        return string.IsNullOrWhiteSpace(value) || CountryAliasMap.TryGetValue(value.Trim(), out country);
    }
}
