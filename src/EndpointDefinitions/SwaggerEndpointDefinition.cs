using Microsoft.OpenApi.Models;

namespace YFinance.EndpointDefinitions;

/// <summary>
/// The swagger endpoint definition.
/// </summary>
public class SwaggerEndpointDefinition : IEndpointDefinition
{
    /// <summary>
    /// The title.
    /// </summary>
    private const string Title = "Stock.Chart";

    /// <summary>
    /// The version.
    /// </summary>
    private const string Version = "v1";

    /// <summary>
    /// Defines the endpoints.
    /// </summary>
    /// <param name="app">The app.</param>
    /// <param name="env">The environment.</param>
    public void DefineEndpoints(WebApplication app, IWebHostEnvironment env)
    {
        if (env.IsDevelopment())
        {
            app.UseSwagger();
            app.UseSwaggerUI(c => c.SwaggerEndpoint("/swagger/v1/swagger.json", $"{Title} {Version}"));
        }
    }

    /// <summary>
    /// Defines the services.
    /// </summary>
    /// <param name="services">The services.</param>
    public void DefineServices(IServiceCollection services)
    {
        services.AddEndpointsApiExplorer();
        services.AddSwaggerGen(c =>
        {
            c.SwaggerDoc(Version, new OpenApiInfo { Title = Title, Version = Version });
        });
    }
}