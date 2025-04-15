using System.Text.Json.Serialization;
using YFinance;

var builder = WebApplication.CreateBuilder(args);
builder.Logging.AddConsole(consoleLogOptions =>
{
    // Configure all logs to go to stderr
    consoleLogOptions.LogToStandardErrorThreshold = LogLevel.Trace;
});
builder.Services.AddEndpointDefinitions(typeof(IEndpointDefinition));
builder.Services.ConfigureHttpJsonOptions(static options => options.SerializerOptions.NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals);

var app = builder.Build();
app.UseEndpointDefinitions(builder.Environment);

app.MapGet("/", () => "Hello YFinance!");

await app.RunAsync();