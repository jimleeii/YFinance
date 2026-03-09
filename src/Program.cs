using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);
builder.Logging.AddConsole(consoleLogOptions =>
{
    // Configure all logs to go to stderr
    consoleLogOptions.LogToStandardErrorThreshold = LogLevel.Trace;
});
builder.Services.AddEndpointDefinitions(typeof(IEndpointDefinition));
builder.Services.ConfigureHttpJsonOptions(static options => options.SerializerOptions.NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals);
builder.Services.AddHealthChecks();

var app = builder.Build();
app.UseEndpointDefinitions(builder.Environment);

app.MapHealthChecks("/health");
app.MapGet("/info", () => "Hello YFinance!");

await app.RunAsync();