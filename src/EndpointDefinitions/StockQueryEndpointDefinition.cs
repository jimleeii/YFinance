using OoplesFinance.YahooFinanceAPI.Models;

namespace YFinance.EndpointDefinitions;

/// <summary>
/// The stock query endpoint definition.
/// </summary>
public class StockQueryEndpointDefinition : IEndpointDefinition
{
    /// <summary>
    /// Defines the endpoints.
    /// </summary>
    /// <param name="app">The app.</param>
    /// <param name="env">The environment.</param>
    public void DefineEndpoints(WebApplication app, IWebHostEnvironment env)
    {
        app.MapPut("api/StockQuery", ProcessMessageAsync);
    }

    /// <summary>
    /// Defines the services.
    /// </summary>
    /// <param name="services">The services.</param>
    public void DefineServices(IServiceCollection services)
    {
        services.AddSingleton<IStockQueryService, StockQueryService>();
    }

    /// <summary>
    /// Processes the message asynchronously.
    /// </summary>
    /// <param name="message">The message.</param>
    /// <returns>A Task of type IResult</returns>
    internal static async Task<IResult> ProcessMessageAsync(IStockQueryService stockQueryService, StockQueryParameterData message)
    {
        IEnumerable<HistoricalChartInfo> data = await stockQueryService.QueryHistoricalDataAsync(message);
        return Results.Ok(data);
    }
}