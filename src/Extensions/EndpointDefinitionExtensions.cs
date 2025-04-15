namespace YFinance;

/// <summary>
/// The endpoint definition extensions.
/// </summary>
public static class EndpointDefinitionExtensions
{
    /// <summary>
    /// Add endpoint definitions.
    /// </summary>
    /// <param name="services">The services.</param>
    /// <param name="scanMarkers">The scan markers.</param>
    public static void AddEndpointDefinitions(this IServiceCollection services, params Type[] scanMarkers)
    {
        var endpointDefinitions = new List<IEndpointDefinition>();

        foreach (var marker in scanMarkers)
        {
            endpointDefinitions.AddRange(
                marker.Assembly.ExportedTypes
                    .Where(x => typeof(IEndpointDefinition).IsAssignableFrom(x) && !x.IsInterface && !x.IsAbstract)
                    .Select(Activator.CreateInstance).Cast<IEndpointDefinition>()
            );
        }

        foreach (var endpointDefinition in endpointDefinitions)
        {
            endpointDefinition.DefineServices(services);
        }

        services.AddSingleton(endpointDefinitions as IReadOnlyCollection<IEndpointDefinition>);
    }

    /// <summary>
    /// Use endpoint definitions.
    /// </summary>
    /// <param name="app">The app.</param>
    /// <param name="env">The environment.</param>
    public static void UseEndpointDefinitions(this WebApplication app, IWebHostEnvironment env)
    {
        var definitions = app.Services.GetRequiredService<IReadOnlyCollection<IEndpointDefinition>>();

        foreach (var endpointDefinition in definitions)
        {
            endpointDefinition.DefineEndpoints(app, env);
        }
    }
}