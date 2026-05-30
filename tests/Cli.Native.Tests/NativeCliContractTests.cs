using System.Diagnostics;
using System.Text.Json;
using Xunit;

namespace Cli.Native.Tests;

public sealed class NativeCliContractTests
{
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

    private static JsonDocument ParseJson(string text)
    {
        Assert.False(string.IsNullOrWhiteSpace(text));
        return JsonDocument.Parse(text);
    }

    private static class NativeCliProcess
    {
        public static async Task<CliRunResult> RunAsync(params string[] cliArgs)
        {
            var repoRoot = FindRepositoryRoot();
            var cliProjectPath = Path.Combine(repoRoot, "Cli", "YFinance.Native.Cli.csproj");

            var arguments = string.Join(" ", cliArgs.Select(Escape));
            var startInfo = new ProcessStartInfo
            {
                FileName = "dotnet",
                Arguments = $"run --no-build --project \"{cliProjectPath}\" -- {arguments}",
                WorkingDirectory = repoRoot,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            using var process = new Process { StartInfo = startInfo };
            process.Start();

            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();

            var waitTask = process.WaitForExitAsync();
            var timeoutTask = Task.Delay(TimeSpan.FromSeconds(45));
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

                throw new TimeoutException("Timed out waiting for native CLI process to exit.");
            }

            await waitTask;

            var stdout = (await stdoutTask).Trim();
            var stderr = (await stderrTask).Trim();

            return new CliRunResult(process.ExitCode, stdout, stderr);
        }

        private static string Escape(string arg)
        {
            if (string.IsNullOrEmpty(arg))
            {
                return "\"\"";
            }

            return arg.Contains(' ') ? $"\"{arg}\"" : arg;
        }

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

    private sealed record CliRunResult(int ExitCode, string StdOut, string StdErr);
}
