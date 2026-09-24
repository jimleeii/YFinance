using System.Text.Json;
using OoplesFinance.YahooFinanceAPI;

var serializerOptions = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    WriteIndented = CliArgHelpers.IsSwitchOn(args, "--pretty")
};

try
{
    if (args.Length == 0 || CliArgHelpers.IsSwitchOn(args, "--help") || CliArgHelpers.IsSwitchOn(args, "-h"))
    {
        WriteHelp();
        return JsonEnvelope.ExitSuccess;
    }

    var command = args[0].Trim().ToLowerInvariant();
    var commandArgs = args.Skip(1).ToArray();

    var yahoo = new YahooClient();

    if (!CommandRegistry.Commands.TryGetValue(command, out var handler))
    {
        return JsonEnvelope.WriteValidationErrorAndReturn($"Unknown command '{command}'.", serializerOptions);
    }

    return await handler(yahoo, commandArgs, serializerOptions);
}
catch (Exception ex)
{
    JsonEnvelope.WriteJson(new
    {
        ok = false,
        error = new
        {
            code = "runtime_error",
            message = ex.Message
        }
    }, serializerOptions);

    return JsonEnvelope.ExitRuntimeError;
}

static void WriteHelp() => Console.WriteLine(CommandRegistry.HelpText);
