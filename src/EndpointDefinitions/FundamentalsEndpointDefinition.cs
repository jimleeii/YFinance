namespace YFinance.EndpointDefinitions;

/// <summary>
/// The fundamentals endpoint definition.
/// </summary>
public class FundamentalsEndpointDefinition : IEndpointDefinition
{
    /// <summary>
    /// Defines the endpoints.
    /// </summary>
    /// <param name="app">The app.</param>
    /// <param name="env">The environment.</param>
    public void DefineEndpoints(WebApplication app, IWebHostEnvironment env)
    {
        app.MapPut("api/Fundamentals", ProcessMessageAsync);
    }

    /// <summary>
    /// Defines the services.
    /// </summary>
    /// <param name="services">The services.</param>
    public void DefineServices(IServiceCollection services)
    {
        services.AddSingleton<IFundamentalsService, FundamentalsService>();
    }

    /// <summary>
    /// Processes fundamentals request message asynchronously.
    /// </summary>
    /// <param name="fundamentalsService">The fundamentals service.</param>
    /// <param name="message">The request message.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    internal static async Task<IResult> ProcessMessageAsync(IFundamentalsService fundamentalsService, FundamentalsRequestData message)
    {
        if (string.IsNullOrWhiteSpace(message.Symbol))
        {
            return Results.BadRequest(new { error = "symbol is required." });
        }

        var payload = await fundamentalsService.GetFundamentalsAsync(message.Symbol);
        return Results.Ok(payload);
    }
}
