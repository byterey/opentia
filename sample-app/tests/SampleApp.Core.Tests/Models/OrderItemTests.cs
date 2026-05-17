using FluentAssertions;
using SampleApp.Core.Models;

namespace SampleApp.Core.Tests.Models;

public class OrderItemTests
{
    [Theory]
    [InlineData(2, 10.00, 20.00)]
    [InlineData(5, 3.50,  17.50)]
    [InlineData(1, 99.99, 99.99)]
    [InlineData(0, 10.00, 0)]
    public void LineTotal_CalculatesCorrectly(int qty, decimal price, decimal expected)
    {
        var item = new OrderItem { Quantity = qty, UnitPrice = price };
        item.LineTotal.Should().Be(expected);
    }

    [Fact]
    public void IsValid_PositiveQtyAndNonNegativePrice_ReturnsTrue()
    {
        var item = new OrderItem { Quantity = 1, UnitPrice = 0 };
        item.IsValid().Should().BeTrue();
    }

    [Fact]
    public void IsValid_ZeroQuantity_ReturnsFalse()
    {
        var item = new OrderItem { Quantity = 0, UnitPrice = 10 };
        item.IsValid().Should().BeFalse();
    }

    [Fact]
    public void IsValid_NegativeUnitPrice_ReturnsFalse()
    {
        var item = new OrderItem { Quantity = 1, UnitPrice = -1 };
        item.IsValid().Should().BeFalse();
    }
}
