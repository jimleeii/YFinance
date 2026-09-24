using System.Text.Json;

internal static class JsonEnvelope
{
    public const int ExitSuccess = 0;
    public const int ExitRuntimeError = 1;
    public const int ExitValidationError = 2;

    public static void WriteJson(object payload, JsonSerializerOptions serializerOptions)
    {
        Console.WriteLine(JsonSerializer.Serialize(payload, serializerOptions));
    }

    public static int WriteValidationErrorAndReturn(string message, JsonSerializerOptions serializerOptions)
    {
        WriteJson(new
        {
            ok = false,
            error = new
            {
                code = "validation_error",
                message
            }
        }, serializerOptions);

        return ExitValidationError;
    }
}
