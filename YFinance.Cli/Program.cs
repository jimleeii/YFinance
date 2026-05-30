using System;
using System.CommandLine;
using System.CommandLine.Parsing;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Text.Json;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OoplesFinance.YahooFinanceAPI.Enums;
using YFinance.Cli.Models;
using YFinance.Cli.Output;

namespace YFinance.Cli
{
    internal static class Program
    {
        static async Task<int> Main(string[] args)
        {
            var root = new RootCommand("YFinance CLI (MVP)");

            var query = new Command("query", "Query historical stock data")
            {
                Description = "Query historical stock data. Examples:\n  yfinance query --symbol AAPL --start 2026-05-01 --format csv --output aapl.csv\n  yfinance query --symbol AAPL --server http://localhost:5005"
            };

            var symbolOpt = new Option<string>(new[] { "--symbol", "-s" }, "Stock symbol") { IsRequired = true };
            var startOpt = new Option<string>(new[] { "--start", "-S" }, () => string.Empty, "Start date (yyyy-MM-dd). Defaults to yesterday");
            var freqOpt = new Option<string>(new[] { "--frequency", "-f" }, () => "daily", "Data frequency: daily|weekly|monthly (case-insensitive)");
            var formatOpt = new Option<string>(new[] { "--format", "-F" }, () => "json", "Output format: json|csv (default: json)");
            var outputOpt = new Option<string>(new[] { "--output", "-o" }, () => string.Empty, "Output file path (defaults to stdout)");
            var serverOpt = new Option<string>("--server", () => string.Empty, "Server URL to proxy requests to (optional)");
            var verboseOpt = new Option<bool>(new[] { "--verbose", "-v" }, "Verbose output");

            // Validators
            symbolOpt.AddValidator(result =>
            {
                var token = result.Tokens.Count > 0 ? result.Tokens[0].Value : null;
                if (string.IsNullOrWhiteSpace(token))
                {
                    result.ErrorMessage = "--symbol is required.";
                    return;
                }
                if (token.Length > 12)
                {
                    result.ErrorMessage = "Symbol too long (max 12 characters).";
                    return;
                }
                if (!Regex.IsMatch(token, "^[A-Za-z0-9.-]+$"))
                {
                    result.ErrorMessage = "Symbol contains invalid characters. Use letters, numbers, dot, or hyphen.";
                }
            });

            startOpt.AddValidator(result =>
            {
                if (result.Tokens.Count == 0) return; // default will be used
                var token = result.Tokens[0].Value;
                if (!DateTime.TryParse(token, out var dt))
                {
                    result.ErrorMessage = "Invalid --start date. Use yyyy-MM-dd.";
                    return;
                }
                if (dt > DateTime.UtcNow.AddMinutes(1))
                {
                    result.ErrorMessage = "Start date cannot be in the future.";
                }
            });

            freqOpt.AddValidator(result =>
            {
                if (result.Tokens.Count == 0) return;
                var token = result.Tokens[0].Value;
                if (string.IsNullOrWhiteSpace(token)) return;
                var v = token.ToLowerInvariant();
                if (v != "daily" && v != "d" && v != "weekly" && v != "w" && v != "monthly" && v != "m")
                {
                    result.ErrorMessage = "Invalid --frequency. Use daily|weekly|monthly (or d|w|m).";
                }
            });

            formatOpt.AddValidator(result =>
            {
                if (result.Tokens.Count == 0) return;
                var token = result.Tokens[0].Value;
                if (string.IsNullOrWhiteSpace(token)) return;
                var v = token.ToLowerInvariant();
                if (v != "json" && v != "csv") result.ErrorMessage = "Invalid --format. Use json or csv.";
            });

            serverOpt.AddValidator(result =>
            {
                if (result.Tokens.Count == 0) return;
                var token = result.Tokens[0].Value;
                if (string.IsNullOrWhiteSpace(token)) return;
                if (!Uri.TryCreate(token, UriKind.Absolute, out var u) || (u.Scheme != "http" && u.Scheme != "https"))
                {
                    result.ErrorMessage = "--server must be a valid http(s) URL.";
                }
            });

            query.AddOption(symbolOpt);
            query.AddOption(startOpt);
            query.AddOption(freqOpt);
            query.AddOption(formatOpt);
            query.AddOption(outputOpt);
            query.AddOption(serverOpt);
            query.AddOption(verboseOpt);

            var fundamentals = new Command("fundamentals", "Query fundamentals payload with best/backup source fallbacks")
            {
                Description = "Query fundamentals data. Example:\n  yfinance fundamentals --symbol AAPL --server http://localhost:5005 --pretty"
            };

            var fundamentalsSymbolOpt = new Option<string>(new[] { "--symbol", "-s" }, "Stock symbol") { IsRequired = true };
            var fundamentalsServerOpt = new Option<string>("--server", () => string.Empty, "Server URL to proxy requests to (optional)");
            var fundamentalsOutputOpt = new Option<string>(new[] { "--output", "-o" }, () => string.Empty, "Output file path (defaults to stdout)");
            var fundamentalsPrettyOpt = new Option<bool>("--pretty", "Pretty-print JSON output");
            var fundamentalsVerboseOpt = new Option<bool>(new[] { "--verbose", "-v" }, "Verbose output");

            fundamentalsSymbolOpt.AddValidator(result =>
            {
                var token = result.Tokens.Count > 0 ? result.Tokens[0].Value : null;
                if (string.IsNullOrWhiteSpace(token))
                {
                    result.ErrorMessage = "--symbol is required.";
                    return;
                }
                if (token.Length > 12)
                {
                    result.ErrorMessage = "Symbol too long (max 12 characters).";
                    return;
                }
                if (!Regex.IsMatch(token, "^[A-Za-z0-9.-]+$"))
                {
                    result.ErrorMessage = "Symbol contains invalid characters. Use letters, numbers, dot, or hyphen.";
                }
            });

            fundamentalsServerOpt.AddValidator(result =>
            {
                if (result.Tokens.Count == 0) return;
                var token = result.Tokens[0].Value;
                if (string.IsNullOrWhiteSpace(token)) return;
                if (!Uri.TryCreate(token, UriKind.Absolute, out var u) || (u.Scheme != "http" && u.Scheme != "https"))
                {
                    result.ErrorMessage = "--server must be a valid http(s) URL.";
                }
            });

            fundamentals.AddOption(fundamentalsSymbolOpt);
            fundamentals.AddOption(fundamentalsServerOpt);
            fundamentals.AddOption(fundamentalsOutputOpt);
            fundamentals.AddOption(fundamentalsPrettyOpt);
            fundamentals.AddOption(fundamentalsVerboseOpt);

                        // Examples subcommand for nicer formatted usage examples
                        var examplesCmd = new Command("examples", "Show usage examples and common patterns");
                        examplesCmd.SetHandler(() =>
                        {
                                Console.WriteLine(@"Usage examples:
    yfinance query --symbol AAPL --start 2026-05-01 --format csv --output aapl.csv
    yfinance query --symbol AAPL --server http://localhost:5005
    yfinance query -s MSFT -S 2026-01-01 -f weekly -F json
    yfinance fundamentals --symbol AAPL --pretty

Notes:
    - Omit --output to write to stdout.
    - Frequency accepts shorthand: d,w,m or full words daily,weekly,monthly.
    - Use --server to proxy requests to a running YFinance server.");
                        });

                        root.AddCommand(examplesCmd);
            // Build a host to provide DI services (IHttpClientFactory, logging, adapters)
            using var host = Host.CreateDefaultBuilder()
                .ConfigureServices((context, services) =>
                {
                    services.AddHttpClient("proxy");
                    services.AddSingleton<IYFinanceSdk, YahooClientAdapter>();
                })
                .ConfigureLogging(logging => logging.AddConsole())
                .Build();

            query.SetHandler(async (string sym, string startStr, string freqStr, string fmt, string outPath, string serverUrl, bool verbose, CancellationToken ct) =>
            {
                if (verbose) Console.Error.WriteLine($"Query: {sym}, start={startStr}, freq={freqStr}, fmt={fmt}, server={serverUrl}");

                DateTime startDate = DateTime.Now.AddDays(-1);
                if (!string.IsNullOrWhiteSpace(startStr) && DateTime.TryParse(startStr, out var parsedStart))
                {
                    startDate = parsedStart;
                }

                var dataFrequency = MapFrequency(freqStr);

                var parameters = new StockQueryParameterData
                {
                    Symbol = sym,
                    StartDate = startDate,
                    DataFrequency = dataFrequency
                };

                IYFinanceSdk sdk;
                HttpClient? http = null;
                if (!string.IsNullOrWhiteSpace(serverUrl))
                {
                    var factory = host.Services.GetRequiredService<IHttpClientFactory>();
                    http = factory.CreateClient("proxy");
                    sdk = new HttpProxyClient(http, serverUrl);
                }
                else
                {
                    sdk = host.Services.GetRequiredService<IYFinanceSdk>();
                }

                try
                {
                    var data = await sdk.QueryAsync(parameters, ct);

                    Stream outStream;
                    FileStream? fs = null;
                    if (!string.IsNullOrWhiteSpace(outPath))
                    {
                        fs = new FileStream(outPath, FileMode.Create, FileAccess.Write, FileShare.None);
                        outStream = fs;
                    }
                    else
                    {
                        outStream = Console.OpenStandardOutput();
                    }

                    try
                    {
                        fmt = string.IsNullOrWhiteSpace(fmt) ? "json" : fmt.ToLowerInvariant();
                        if (fmt == "csv")
                        {
                            await CsvOutputFormatter.WriteCsvAsync(data, outStream, ct);
                        }
                        else
                        {
                            await JsonOutputFormatter.WriteJsonAsync(data, outStream, ct);
                        }

                        if (!string.IsNullOrWhiteSpace(outPath) && verbose)
                        {
                            Console.Error.WriteLine($"Wrote output to {outPath}");
                        }
                    }
                    finally
                    {
                        if (fs != null)
                        {
                            fs.Dispose();
                        }
                    }
                }
                catch (OperationCanceledException)
                {
                    Console.Error.WriteLine("Operation cancelled.");
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"Error: {ex.Message}");
                }
                finally
                {
                    http?.Dispose();
                }
            }, symbolOpt, startOpt, freqOpt, formatOpt, outputOpt, serverOpt, verboseOpt);

            root.AddCommand(query);

            fundamentals.SetHandler(async (string sym, string serverUrl, string outPath, bool pretty, bool verbose, CancellationToken ct) =>
            {
                if (verbose) Console.Error.WriteLine($"Fundamentals: {sym}, server={serverUrl}, pretty={pretty}");

                IYFinanceSdk sdk;
                HttpClient? http = null;
                if (!string.IsNullOrWhiteSpace(serverUrl))
                {
                    var factory = host.Services.GetRequiredService<IHttpClientFactory>();
                    http = factory.CreateClient("proxy");
                    sdk = new HttpProxyClient(http, serverUrl);
                }
                else
                {
                    sdk = host.Services.GetRequiredService<IYFinanceSdk>();
                }

                try
                {
                    var payload = await sdk.QueryFundamentalsAsync(sym, ct);
                    var json = JsonSerializer.Serialize(payload, new JsonSerializerOptions
                    {
                        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                        WriteIndented = pretty
                    });

                    if (!string.IsNullOrWhiteSpace(outPath))
                    {
                        await File.WriteAllTextAsync(outPath, json, ct);
                        if (verbose)
                        {
                            Console.Error.WriteLine($"Wrote output to {outPath}");
                        }
                    }
                    else
                    {
                        Console.WriteLine(json);
                    }
                }
                catch (OperationCanceledException)
                {
                    Console.Error.WriteLine("Operation cancelled.");
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"Error: {ex.Message}");
                }
                finally
                {
                    http?.Dispose();
                }
            }, fundamentalsSymbolOpt, fundamentalsServerOpt, fundamentalsOutputOpt, fundamentalsPrettyOpt, fundamentalsVerboseOpt);

            root.AddCommand(fundamentals);

            var exit = await root.InvokeAsync(args);

            await host.StopAsync();
            return exit;
        }

        static DataFrequency MapFrequency(string input)
        {
            if (string.IsNullOrWhiteSpace(input)) return DataFrequency.Daily;
            switch (input.Trim().ToLowerInvariant())
            {
                case "d":
                case "daily":
                    return DataFrequency.Daily;
                case "w":
                case "weekly":
                    return DataFrequency.Weekly;
                case "m":
                case "monthly":
                    return DataFrequency.Monthly;
                default:
                    return DataFrequency.Daily;
            }
        }
    }
}
