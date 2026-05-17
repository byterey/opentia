namespace SampleApp.Core.Utilities;

public static class StringHelper
{
    public static string Truncate(string value, int maxLength)
    {
        if (string.IsNullOrEmpty(value)) return value;
        if (maxLength <= 0) throw new ArgumentOutOfRangeException(nameof(maxLength));
        return value.Length <= maxLength ? value : value[..maxLength];
    }

    public static string ToTitleCase(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return value;
        return string.Join(" ", value.Split(' ')
            .Select(w => w.Length > 0 ? char.ToUpper(w[0]) + w[1..].ToLower() : w));
    }

    public static bool IsValidEmail(string email)
    {
        if (string.IsNullOrWhiteSpace(email)) return false;
        var parts = email.Split('@');
        return parts.Length == 2 && parts[0].Length > 0 && parts[1].Contains('.');
    }

    public static string MaskEmail(string email)
    {
        if (!IsValidEmail(email)) return email;
        var at = email.IndexOf('@');
        var name = email[..at];
        var domain = email[(at + 1)..];
        var visible = name.Length <= 2 ? name[..1] : name[..2];
        return $"{visible}***@{domain}";
    }

    public static string RemoveWhitespace(string value) =>
        string.IsNullOrEmpty(value)
            ? value
            : new string(value.Where(c => !char.IsWhiteSpace(c)).ToArray());

    public static string Slugify(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return string.Empty;
        return value.ToLower()
            .Replace(' ', '-')
            .Where(c => char.IsLetterOrDigit(c) || c == '-')
            .Aggregate(string.Empty, (acc, c) => acc + c);
    }
}
