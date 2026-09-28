using System.Text.Json;
using System.IO;

/// <summary>
/// Writes CLI JSON envelopes and standardized validation failures to a text output stream.
/// </summary>
internal static class JsonEnvelope
{
    #region Constants

    /// <summary>
    /// Indicates successful CLI completion.
    /// </summary>
    public const int ExitSuccess = 0;

    /// <summary>
    /// Indicates an unexpected runtime failure.
    /// </summary>
    public const int ExitRuntimeError = 1;

    /// <summary>
    /// Indicates invalid user input or request arguments.
    /// </summary>
    public const int ExitValidationError = 2;

    #endregion Constants

    #region Public Methods

    /// <summary>
    /// Serializes a payload and writes it as a single JSON line.
    /// </summary>
    /// <param name="payload">The payload to serialize.</param>
    /// <param name="serializerOptions">The serializer options controlling JSON output.</param>
    /// <param name="writer">The optional destination writer; defaults to standard output.</param>
    public static void WriteJson(object payload, JsonSerializerOptions serializerOptions, TextWriter? writer = null)
    {
        (writer ?? Console.Out).WriteLine(JsonSerializer.Serialize(payload, serializerOptions));
    }

    /// <summary>
    /// Writes a standardized validation-error envelope and returns the matching process exit code.
    /// </summary>
    /// <param name="message">The validation failure message to emit.</param>
    /// <param name="serializerOptions">The serializer options controlling JSON output.</param>
    /// <param name="writer">The optional destination writer; defaults to standard output.</param>
    /// <returns><see cref="ExitValidationError" />.</returns>
    public static int WriteValidationErrorAndReturn(string message, JsonSerializerOptions serializerOptions, TextWriter? writer = null)
    {
        WriteJson(new
        {
            ok = false,
            error = new
            {
                code = "validation_error",
                message
            }
        }, serializerOptions, writer);

        return ExitValidationError;
    }

    #endregion Public Methods
}
