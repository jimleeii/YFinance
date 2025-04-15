namespace YFinance;

/// <summary>
/// The string extensions.
/// </summary>
public static class StringExtensions
{
    /// <summary>
    /// Equals ignore case.
    /// </summary>
    /// <param name="str1">The str1.</param>
    /// <param name="str2">The str2.</param>
    /// <returns>A bool</returns>
    public static bool EqualsIgnoreCase(this string? str1, object str2)
    {
        return string.Equals(str1, str2.ToString(), StringComparison.OrdinalIgnoreCase);
    }
}