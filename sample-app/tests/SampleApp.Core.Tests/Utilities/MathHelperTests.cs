using FluentAssertions;
using SampleApp.Core.Utilities;

namespace SampleApp.Core.Tests.Utilities;

public class MathHelperTests
{
    [Theory]
    [InlineData(2.345, 2, 2.35)]
    [InlineData(2.344, 2, 2.34)]
    [InlineData(2.5,   0, 3)]
    public void RoundTo_HalfUp(decimal value, int places, decimal expected)
    {
        MathHelper.RoundTo(value, places).Should().Be(expected);
    }

    [Theory]
    [InlineData(5,  0, 10, 5)]
    [InlineData(-1, 0, 10, 0)]
    [InlineData(15, 0, 10, 10)]
    public void Clamp_ReturnsWithinBounds(decimal value, decimal min, decimal max, decimal expected)
    {
        MathHelper.Clamp(value, min, max).Should().Be(expected);
    }

    [Fact]
    public void Clamp_MinGreaterThanMax_Throws()
    {
        Assert.Throws<ArgumentException>(() => MathHelper.Clamp(5, 10, 0));
    }

    [Theory]
    [InlineData(25, 100, 25)]
    [InlineData(1,  4,   25)]
    [InlineData(0,  100, 0)]
    public void Percentage_CalculatesCorrectly(decimal value, decimal total, decimal expected)
    {
        MathHelper.Percentage(value, total).Should().Be(expected);
    }

    [Fact]
    public void Percentage_ZeroTotal_Throws()
    {
        Assert.Throws<DivideByZeroException>(() => MathHelper.Percentage(5, 0));
    }

    [Theory]
    [InlineData(0, 1)]
    [InlineData(1, 1)]
    [InlineData(5, 120)]
    public void Factorial_CorrectValues(int n, int expected)
    {
        MathHelper.Factorial(n).Should().Be(expected);
    }

    [Fact]
    public void Factorial_Negative_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => MathHelper.Factorial(-1));
    }

    [Fact]
    public void IsBetween_ValueInRange_ReturnsTrue()
    {
        MathHelper.IsBetween(5, 1, 10).Should().BeTrue();
    }

    [Fact]
    public void IsBetween_ValueOutOfRange_ReturnsFalse()
    {
        MathHelper.IsBetween(11, 1, 10).Should().BeFalse();
    }

    [Fact]
    public void LinearInterpolate_ReturnsCorrectEndpoints()
    {
        var result = MathHelper.LinearInterpolate(0, 10, 3);
        result.Should().HaveCount(3);
        result[0].Should().Be(0);
        result[^1].Should().Be(10);
    }

    [Fact]
    public void LinearInterpolate_StepsLessThanTwo_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => MathHelper.LinearInterpolate(0, 10, 1));
    }
}
