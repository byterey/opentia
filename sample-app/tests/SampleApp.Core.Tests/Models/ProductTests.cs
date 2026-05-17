using FluentAssertions;
using SampleApp.Core.Models;

namespace SampleApp.Core.Tests.Models;

public class ProductTests
{
    [Fact]
    public void IsInStock_QuantityGreaterThanZero_ReturnsTrue()
    {
        var p = new Product { StockQuantity = 5 };
        p.IsInStock().Should().BeTrue();
    }

    [Fact]
    public void IsInStock_QuantityIsZero_ReturnsFalse()
    {
        var p = new Product { StockQuantity = 0 };
        p.IsInStock().Should().BeFalse();
    }

    [Fact]
    public void IsAvailable_ActiveAndInStock_ReturnsTrue()
    {
        var p = new Product { IsActive = true, StockQuantity = 1 };
        p.IsAvailable().Should().BeTrue();
    }

    [Fact]
    public void IsAvailable_Inactive_ReturnsFalse()
    {
        var p = new Product { IsActive = false, StockQuantity = 99 };
        p.IsAvailable().Should().BeFalse();
    }

    [Fact]
    public void IsAvailable_OutOfStock_ReturnsFalse()
    {
        var p = new Product { IsActive = true, StockQuantity = 0 };
        p.IsAvailable().Should().BeFalse();
    }

    [Theory]
    [InlineData(100, 10, 90)]
    [InlineData(200, 50, 100)]
    [InlineData(50,  0,  50)]
    [InlineData(100, 100, 0)]
    public void GetDiscountedPrice_ReturnsCorrectValue(decimal price, decimal pct, decimal expected)
    {
        var p = new Product { Price = price };
        p.GetDiscountedPrice(pct).Should().Be(expected);
    }

    [Fact]
    public void GetDiscountedPrice_NegativeDiscount_Throws()
    {
        var p = new Product { Price = 100 };
        Assert.Throws<ArgumentOutOfRangeException>(() => p.GetDiscountedPrice(-1));
    }

    [Fact]
    public void GetDiscountedPrice_DiscountAbove100_Throws()
    {
        var p = new Product { Price = 100 };
        Assert.Throws<ArgumentOutOfRangeException>(() => p.GetDiscountedPrice(101));
    }

    [Fact]
    public void NewProduct_IsActiveByDefault()
    {
        new Product().IsActive.Should().BeTrue();
    }

    [Fact]
    public void NewProduct_DefaultNameIsEmpty()
    {
        new Product().Name.Should().BeEmpty();
    }
}
