namespace YFinance.EndpointDefinitions;

/// <summary>
/// The Mcp endpoint definition.
/// </summary>
public class McpEndpointDefinition : IEndpointDefinition
{
    /// <summary>
    /// Defines the endpoints.
    /// </summary>
    /// <param name="app">The app.</param>
    /// <param name="env">The environment.</param>
    public void DefineEndpoints(WebApplication app, IWebHostEnvironment env)
    {
        app.MapMcp();
    }

    /// <summary>
    /// Configures MCP server services with standard input/output transport,
    /// tools, and prompts from the assembly.
    /// </summary>
    /// <param name="services">The services collection to add the MCP server to.</param>
    public void DefineServices(IServiceCollection services)
    {
        services.AddMcpServer().WithStdioServerTransport().WithToolsFromAssembly().WithPromptsFromAssembly();
    }
}