using System.Diagnostics;
using System.Text.Json;
using System.Reflection;
using OoplesFinance.YahooFinanceAPI.Enums;
using OoplesFinance.YahooFinanceAPI.Models;
using Xunit;

namespace Cli.Native.Tests;

/// <summary>
/// Verifies the native CLI's JSON contracts and exit codes.
/// </summary>
/// <remarks>
/// Focuses on contract-shape regressions so CLI callers can rely on stable exit codes and payload envelopes.
/// </remarks>
public sealed class NativeCliContractTests
{
    #region Public Methods

    /// <summary>
    /// Verifies invoking <c>query</c> without a symbol returns validation JSON and exit code 2.
    /// </summary>
    [Fact]
    public async Task Query_MissingSymbol_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("query");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.False(string.IsNullOrWhiteSpace(error.GetProperty("message").GetString()));
    }

    /// <summary>
    /// Verifies an unknown command returns validation JSON and exit code 2.
    /// </summary>
    [Fact]
    public async Task UnknownCommand_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("unknown-command");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("Unknown command", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies <c>query-json</c> reports a runtime error when the requested input file is missing.
    /// </summary>
    [Fact]
    public async Task QueryJson_MissingInputFile_ReturnsRuntimeErrorJson_WithExitCode1()
    {
        var missingInput = Path.Combine(Path.GetTempPath(), $"missing-{Guid.NewGuid():N}.json");
        var result = await NativeCliProcess.RunAsync("query-json", "--input", missingInput);

        Assert.Equal(1, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("runtime_error", error.GetProperty("code").GetString());
        Assert.False(string.IsNullOrWhiteSpace(error.GetProperty("message").GetString()));
    }

    /// <summary>
    /// Verifies <c>fundamentals-json</c> requires a symbol and reports validation JSON when omitted.
    /// </summary>
    [Fact]
    public async Task FundamentalsJson_MissingSymbol_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("fundamentals-json");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("--symbol", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies <c>top-trending-stocks</c> requires a positive count and reports validation JSON when omitted.
    /// </summary>
    [Fact]
    public async Task TopTrendingStocks_MissingCount_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("top-trending-stocks");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("--count", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies <c>top-gainers</c> requires a positive count and reports validation JSON when omitted.
    /// </summary>
    [Fact]
    public async Task TopGainers_MissingCount_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("top-gainers");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("--count", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies <c>analyst-strong-buy-stocks</c> rejects a non-positive count with validation JSON.
    /// </summary>
    [Fact]
    public async Task AnalystStrongBuyStocks_InvalidCount_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("analyst-strong-buy-stocks", "--count", "0");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("--count", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies <c>chart-info</c> rejects an unsupported range alias with validation JSON.
    /// </summary>
    [Fact]
    public async Task ChartInfo_InvalidRangeAlias_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("chart-info", "--symbol", "AAPL", "--range", "not-a-range");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("--range", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies <c>top-trending-stocks</c> rejects an unsupported country alias with validation JSON.
    /// </summary>
    [Fact]
    public async Task TopTrendingStocks_InvalidCountryAlias_ReturnsValidationErrorJson_WithExitCode2()
    {
        var result = await NativeCliProcess.RunAsync("top-trending-stocks", "--country", "not-a-country", "--count", "5");

        Assert.Equal(2, result.ExitCode);
        using var json = ParseJson(result.StdOut);

        var root = json.RootElement;
        Assert.False(root.GetProperty("ok").GetBoolean());

        var error = root.GetProperty("error");
        Assert.Equal("validation_error", error.GetProperty("code").GetString());
        Assert.Contains("--country", error.GetProperty("message").GetString() ?? string.Empty);
    }

    /// <summary>
    /// Verifies normalized chart-info data emits UTC timestamp strings and completion metadata using a deterministic UTC clock.
    /// </summary>
    [Fact]
    public void BuildNormalizedChartInfoData_UsesUtcArraysAndComputesRequiredCompletionList()
    {
        var method = LoadCliAssembly()
            .GetType("QuoteCommands", throwOnError: true)!
            .GetMethod("BuildNormalizedChartInfoData", BindingFlags.NonPublic | BindingFlags.Static)!;
        var now = new DateTimeOffset(2026, 9, 25, 14, 10, 0, TimeSpan.Zero);
        var chartInfo = new ChartInfo
        {
            DateList =
            [
                now.AddMinutes(-15).UtcDateTime,
                now.AddMinutes(-2).UtcDateTime
            ],
            OpenList = [100d, 101d],
            HighList = [101d, 102d],
            LowList = [99d, 100d],
            CloseList = [100d, 101d],
            VolumeList = [100L, 101L]
        };

        var normalized = method.Invoke(null, [chartInfo, "5m", new Func<DateTimeOffset>(() => now)]);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(normalized));
        var root = json.RootElement;

        Assert.Equal("5m", root.GetProperty("interval").GetString());
        Assert.EndsWith("Z", root.GetProperty("dateList")[0].GetString());
        Assert.Equal(100d, root.GetProperty("openList")[0].GetDouble());
        Assert.Equal(102d, root.GetProperty("highList")[1].GetDouble());
        Assert.Equal(100d, root.GetProperty("lowList")[1].GetDouble());
        Assert.Equal(101d, root.GetProperty("closeList")[1].GetDouble());
        Assert.Equal(101d, root.GetProperty("volumeList")[1].GetDouble());
        var completedList = root.GetProperty("completedList");
        Assert.Equal(JsonValueKind.Array, completedList.ValueKind);
        Assert.True(completedList[0].GetBoolean());
        Assert.False(completedList[1].GetBoolean());
    }

    /// <summary>
    /// Verifies the completion calculation flips exactly at the UTC interval boundary.
    /// </summary>
    [Fact]
    public void BuildNormalizedChartInfoData_UsesExactUtcBoundaryForCompletion()
    {
        var method = LoadCliAssembly()
            .GetType("QuoteCommands", throwOnError: true)!
            .GetMethod("BuildNormalizedChartInfoData", BindingFlags.NonPublic | BindingFlags.Static)!;
        var now = new DateTimeOffset(2026, 9, 25, 14, 5, 0, TimeSpan.Zero);
        var chartInfo = new ChartInfo
        {
            DateList =
            [
                new DateTime(2026, 9, 25, 14, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 9, 25, 14, 1, 0, DateTimeKind.Utc)
            ],
            OpenList = [100d, 101d],
            HighList = [101d, 102d],
            LowList = [99d, 100d],
            CloseList = [100d, 101d],
            VolumeList = [100L, 101L]
        };

        var normalized = method.Invoke(null, [chartInfo, "5m", new Func<DateTimeOffset>(() => now)]);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(normalized));
        var completedList = json.RootElement.GetProperty("completedList");

        Assert.True(completedList[0].GetBoolean());
        Assert.False(completedList[1].GetBoolean());
    }

    /// <summary>
    /// Verifies normalized chart-info data rejects non-UTC timestamps so the explicit UTC contract stays intact.
    /// </summary>
    [Fact]
    public void BuildNormalizedChartInfoData_RejectsNonUtcDateKindsForExplicitUtcContract()
    {
        var method = LoadCliAssembly()
            .GetType("QuoteCommands", throwOnError: true)!
            .GetMethod("BuildNormalizedChartInfoData", BindingFlags.NonPublic | BindingFlags.Static)!;

        var localChartInfo = new ChartInfo
        {
            DateList = [new DateTime(2026, 9, 24, 14, 0, 0, DateTimeKind.Local)],
            OpenList = [100d],
            HighList = [101d],
            LowList = [99d],
            CloseList = [100d],
            VolumeList = [100L]
        };

        var unspecifiedChartInfo = new ChartInfo
        {
            DateList = [new DateTime(2026, 9, 24, 14, 0, 0, DateTimeKind.Unspecified)],
            OpenList = [100d],
            HighList = [101d],
            LowList = [99d],
            CloseList = [100d],
            VolumeList = [100L]
        };

        var localException = Assert.Throws<TargetInvocationException>(() => method.Invoke(null, [localChartInfo, "5m", new Func<DateTimeOffset>(() => DateTimeOffset.UtcNow)]));
        var localInner = Assert.IsType<InvalidOperationException>(localException.InnerException);
        Assert.Contains("explicit UTC contract", localInner.Message, StringComparison.OrdinalIgnoreCase);

        var unspecifiedException = Assert.Throws<TargetInvocationException>(() => method.Invoke(null, [unspecifiedChartInfo, "5m", new Func<DateTimeOffset>(() => DateTimeOffset.UtcNow)]));
        Assert.IsType<InvalidOperationException>(unspecifiedException.InnerException);
    }

    /// <summary>
    /// Verifies the emitted chart-info envelope remains compatible with the RSI normalized-data parser without replacing <see cref="Console.Out"/> globally.
    /// </summary>
    [Fact]
    public async Task ChartInfo_EmitsRsiCompatibleNormalizedDataEnvelope()
    {
        var method = LoadCliAssembly()
            .GetType("QuoteCommands", throwOnError: true)!
            .GetMethods(BindingFlags.NonPublic | BindingFlags.Static)
            .Single(candidate => candidate.Name == "HandleChartInfoAsync"
                && candidate.GetParameters()[0].ParameterType == typeof(Func<string, TimeRange, TimeInterval, Task<ChartInfo>>)
                && candidate.GetParameters().Length == 5);
        var now = new DateTimeOffset(2026, 9, 25, 14, 10, 0, TimeSpan.Zero);
        var provider = new Func<string, TimeRange, TimeInterval, Task<ChartInfo>>((symbol, range, interval) =>
            Task.FromResult(new ChartInfo
            {
                DateList =
                [
                    now.AddMinutes(-10).UtcDateTime,
                    now.AddMinutes(-1).UtcDateTime
                ],
                OpenList = [100d, 101d],
                HighList = [101d, 102d],
                LowList = [99d, 100d],
                CloseList = [100.5d, 101.5d],
                VolumeList = [123L, 124L]
            }));
        var serializerOptions = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        var output = new StringWriter();
        var task = (Task<int>)method.Invoke(null, [provider, new[] { "--symbol", "AAPL", "--interval", "5m" }, serializerOptions, new Func<DateTimeOffset>(() => now), output])!;
        Assert.Equal(0, await task);

        using var json = JsonDocument.Parse(output.ToString());
        var root = json.RootElement;
        var normalized = root.GetProperty("normalizedData");

        Assert.True(root.GetProperty("ok").GetBoolean());
        Assert.Equal("chart-info", root.GetProperty("command").GetString());
        Assert.Equal("AAPL", root.GetProperty("request").GetProperty("symbol").GetString());
        Assert.Equal("5m", normalized.GetProperty("interval").GetString());
        Assert.EndsWith("Z", normalized.GetProperty("dateList")[0].GetString());
        Assert.Equal(100d, normalized.GetProperty("openList")[0].GetDouble());
        Assert.Equal(101d, normalized.GetProperty("highList")[0].GetDouble());
        Assert.Equal(99d, normalized.GetProperty("lowList")[0].GetDouble());
        Assert.Equal(100.5d, normalized.GetProperty("closeList")[0].GetDouble());
        Assert.Equal(123d, normalized.GetProperty("volumeList")[0].GetDouble());
        var completedList = normalized.GetProperty("completedList");
        Assert.Equal(2, completedList.GetArrayLength());
        Assert.True(completedList[0].GetBoolean());
        Assert.False(completedList[1].GetBoolean());
    }

    #endregion Public Methods

    #region Private Methods

    /// <summary>
    /// Parses CLI stdout into a JSON document after asserting the payload is non-empty.
    /// </summary>
    /// <param name="text">The stdout payload to parse.</param>
    /// <returns>The parsed JSON document.</returns>
    private static JsonDocument ParseJson(string text)
    {
        Assert.False(string.IsNullOrWhiteSpace(text));
        return JsonDocument.Parse(text);
    }

    /// <summary>
    /// Loads the native CLI assembly from the verified build artifact path.
    /// </summary>
    /// <returns>The loaded CLI assembly.</returns>
    private static Assembly LoadCliAssembly()
    {
        var cliArtifact = Task.Run(() => NativeCliProcess.GetCliArtifactAsync())
            .GetAwaiter()
            .GetResult();
        var assemblyPath = Path.GetFullPath(cliArtifact.AssemblyPath);

        return AppDomain.CurrentDomain.GetAssemblies()
            .FirstOrDefault(assembly => !string.IsNullOrEmpty(assembly.Location)
                && string.Equals(Path.GetFullPath(assembly.Location), assemblyPath, StringComparison.OrdinalIgnoreCase))
            ?? Assembly.LoadFrom(assemblyPath);
    }

    #endregion Private Methods

    #region Nested Types

    /// <summary>
    /// Launches the native CLI as a child process and captures its exit code plus output streams.
    /// </summary>
    private static class NativeCliProcess
    {
        private static readonly object SyncRoot = new();
        private static Task<CliArtifactInfo>? _cliArtifactTask;

        /// <summary>
        /// Runs the native CLI with the supplied arguments and captures the completed process result.
        /// </summary>
        /// <param name="cliArgs">The CLI arguments to forward after the command separator.</param>
        /// <returns>The completed process result.</returns>
        public static async Task<CliRunResult> RunAsync(params string[] cliArgs)
        {
            var cliArtifact = await GetCliArtifactAsync();
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                WorkingDirectory = cliArtifact.RepositoryRoot,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            startInfo.ArgumentList.Add(cliArtifact.AssemblyPath);
            foreach (var cliArg in cliArgs)
            {
                startInfo.ArgumentList.Add(cliArg);
            }

            return await RunProcessAsync(startInfo, TimeSpan.FromSeconds(45), "native CLI");
        }

        /// <summary>
        /// Builds the CLI project once per test process and returns the deterministic artifact path.
        /// </summary>
        /// <returns>The repository root and runnable CLI assembly path.</returns>
        internal static Task<CliArtifactInfo> GetCliArtifactAsync()
        {
            lock (SyncRoot)
            {
                _cliArtifactTask ??= BuildCliArtifactAsync();
                return _cliArtifactTask;
            }
        }

        /// <summary>
        /// Builds the CLI project and verifies the current runnable artifact exists before any contract test launches it.
        /// </summary>
        /// <returns>The verified CLI artifact info.</returns>
        private static async Task<CliArtifactInfo> BuildCliArtifactAsync()
        {
            var repositoryRoot = FindRepositoryRoot();
            var cliProjectPath = Path.Combine(repositoryRoot, "Cli", "YFinance.Native.Cli.csproj");
            var configuration = GetBuildConfiguration();
            const string targetFramework = "net10.0";
            var outputDirectory = Path.Combine(repositoryRoot, "Cli", "bin", configuration, targetFramework);
            var assemblyPath = Path.Combine(outputDirectory, "yfinance-native-cli.dll");
            var runtimeConfigPath = Path.Combine(outputDirectory, "yfinance-native-cli.runtimeconfig.json");

            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                WorkingDirectory = repositoryRoot,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            startInfo.ArgumentList.Add("build");
            startInfo.ArgumentList.Add(cliProjectPath);
            startInfo.ArgumentList.Add("--configuration");
            startInfo.ArgumentList.Add(configuration);
            startInfo.ArgumentList.Add("--framework");
            startInfo.ArgumentList.Add(targetFramework);
            startInfo.ArgumentList.Add("--nologo");

            var buildResult = await RunProcessAsync(startInfo, TimeSpan.FromMinutes(2), "native CLI build");
            if (buildResult.ExitCode != 0)
            {
                throw new InvalidOperationException(
                    $"Building the native CLI failed with exit code {buildResult.ExitCode}.{Environment.NewLine}stdout:{Environment.NewLine}{buildResult.StdOut}{Environment.NewLine}stderr:{Environment.NewLine}{buildResult.StdErr}");
            }

            if (!File.Exists(assemblyPath))
            {
                throw new FileNotFoundException($"The built native CLI assembly was not found at '{assemblyPath}'.", assemblyPath);
            }

            if (!File.Exists(runtimeConfigPath))
            {
                throw new FileNotFoundException($"The built native CLI runtime config was not found at '{runtimeConfigPath}'.", runtimeConfigPath);
            }

            return new CliArtifactInfo(repositoryRoot, assemblyPath);
        }

        /// <summary>
        /// Runs a child process, enforces a timeout, and captures the completed output streams.
        /// </summary>
        /// <param name="startInfo">The prepared process start info.</param>
        /// <param name="timeout">The maximum allowed runtime.</param>
        /// <param name="operationName">The human-readable operation name used in failure messages.</param>
        /// <returns>The completed process result.</returns>
        private static async Task<CliRunResult> RunProcessAsync(
            ProcessStartInfo startInfo,
            TimeSpan timeout,
            string operationName)
        {

            using var process = new Process { StartInfo = startInfo };
            process.Start();

            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();

            var waitTask = process.WaitForExitAsync();
            var timeoutTask = Task.Delay(timeout);
            var completed = await Task.WhenAny(waitTask, timeoutTask);
            if (completed == timeoutTask)
            {
                try
                {
                    process.Kill(entireProcessTree: true);
                }
                catch
                {
                    // Ignore cleanup failures in timeout path.
                }

                throw new TimeoutException($"Timed out waiting for the {operationName} process to exit.");
            }

            await waitTask;

            var stdout = (await stdoutTask).Trim();
            var stderr = (await stderrTask).Trim();

            return new CliRunResult(process.ExitCode, stdout, stderr);
        }

        /// <summary>
        /// Reads the active test build configuration so the CLI build lands under the expected output folder.
        /// </summary>
        /// <returns>The active build configuration, or <c>Debug</c> when the attribute is unavailable.</returns>
        private static string GetBuildConfiguration()
        {
            return typeof(NativeCliContractTests).Assembly
                .GetCustomAttribute<AssemblyConfigurationAttribute>()?
                .Configuration
                ?? "Debug";
        }

        /// <summary>
        /// Walks upward from the test output directory until the YFinance solution root is found.
        /// </summary>
        /// <returns>The repository root containing <c>YFinance.sln</c>.</returns>
        private static string FindRepositoryRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory is not null)
            {
                var candidate = Path.Combine(directory.FullName, "YFinance.sln");
                if (File.Exists(candidate))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new DirectoryNotFoundException("Could not locate repository root containing YFinance.sln.");
        }
    }

    /// <summary>
    /// Captures the native CLI exit code plus trimmed stdout and stderr.
    /// </summary>
    /// <remarks>
    /// Uses a sealed record so each assertion consumes one immutable process result snapshot.
    /// </remarks>
    private sealed record CliRunResult(int ExitCode, string StdOut, string StdErr);

    /// <summary>
    /// Stores the verified native CLI repository root and runnable assembly path.
    /// </summary>
    /// <param name="RepositoryRoot">The native CLI repository root.</param>
    /// <param name="AssemblyPath">The built native CLI assembly path.</param>
    private sealed record CliArtifactInfo(string RepositoryRoot, string AssemblyPath);

    #endregion Nested Types
}
