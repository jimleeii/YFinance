namespace YFinance.EndpointDefinitions;

/// <summary>
/// The open api endpoint definition.
/// </summary>
public class OpenApiEndpointDefinition : IEndpointDefinition
{
    /// <summary>
    /// Defines the endpoints.
    /// </summary>
    /// <param name="app">The app.</param>
    /// <param name="env">The environment.</param>
    public void DefineEndpoints(WebApplication app, IWebHostEnvironment env)
    {
        if (env.IsDevelopment())
        {
            // URL ./openapi/v1.json
            app.MapOpenApi().CacheOutput();
        }
    }

    /// <summary>
    /// Defines the services.
    /// </summary>
    /// <param name="services">The services.</param>
    public void DefineServices(IServiceCollection services)
    {
        services.AddOutputCache(options => options.AddBasePolicy(policy => policy.Expire(TimeSpan.FromMinutes(10))));

        // Document name is v1
        services.AddOpenApi();
    }
}