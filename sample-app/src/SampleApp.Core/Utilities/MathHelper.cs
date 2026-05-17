namespace SampleApp.Core.Utilities;

public static class MathHelper
{
    public static decimal RoundTo(decimal value, int decimalPlaces) =>
        Math.Round(value, decimalPlaces, MidpointRounding.AwayFromZero);

    public static decimal Clamp(decimal value, decimal min, decimal max)
    {
        if (min > max) throw new ArgumentException("min must be <= max");
        return Math.Max(min, Math.Min(max, value));
    }

    public static decimal Percentage(decimal value, decimal total)
    {
        if (total == 0) throw new DivideByZeroException("total cannot be zero");
        return RoundTo(value / total * 100, 2);
    }

    public static bool IsBetween(decimal value, decimal min, decimal max) =>
        value >= min && value <= max;

    public static int Factorial(int n)
    {
        if (n < 0) throw new ArgumentOutOfRangeException(nameof(n));
        return n <= 1 ? 1 : n * Factorial(n - 1);
    }

    public static decimal[] LinearInterpolate(decimal from, decimal to, int steps)
    {
        if (steps < 2) throw new ArgumentOutOfRangeException(nameof(steps));
        var result = new decimal[steps];
        for (var i = 0; i < steps; i++)
            result[i] = from + (to - from) * i / (steps - 1);
        return result;
    }
}
