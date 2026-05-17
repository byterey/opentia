using FluentAssertions;
using SampleApp.Core.Models;
using SampleApp.Services;

namespace SampleApp.Services.Tests;

public class PricingServiceTests
{
    private readonly PricingService _sut = new();

    [Theory]
    [InlineData(100, 10,  90)]
    [InlineData(200, 25, 150)]
    [InlineData(50,  0,   50)]
    [InlineData(100, 100,  0)]
    public void CalculateDiscountedPrice_ReturnsCorrectValue(decimal price, decimal pct, decimal expected)
    {
        _sut.CalculateDiscountedPrice(price, pct).Should().Be(expected);
    }

    [Fact]
    public void CalculateDiscountedPrice_NegativePrice_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => _sut.CalculateDiscountedPrice(-1, 10));
    }

    [Fact]
    public void CalculateDiscountedPrice_DiscountOver100_ClampedTo100()
    {
        // discount is clamped, no exception
        _sut.CalculateDiscountedPrice(100, 150).Should().Be(0);
    }

    [Theory]
    [InlineData(100, 0.2,  20)]
    [InlineData(50,  0.1,   5)]
    [InlineData(0,   0.2,   0)]
    public void CalculateTax_ReturnsCorrectAmount(decimal amount, decimal rate, decimal expected)
    {
        _sut.CalculateTax(amount, rate).Should().Be(expected);
    }

    [Fact]
    public void CalculateTax_NegativeAmount_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => _sut.CalculateTax(-1, 0.1m));
    }

    [Fact]
    public void CalculateTax_RateAboveOne_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => _sut.CalculateTax(100, 1.1m));
    }

    [Theory]
    [InlineData(1,   0)]
    [InlineData(10,  5)]
    [InlineData(20,  10)]
    [InlineData(50,  15)]
    [InlineData(100, 20)]
    public void GetBulkDiscount_CorrectTiers(int quantity, decimal expected)
    {
        _sut.GetBulkDiscount(quantity).Should().Be(expected);
    }

    [Theory]
    [InlineData(50,   50, true)]
    [InlineData(49.99,50, false)]
    [InlineData(100,  50, true)]
    public void IsEligibleForFreeShipping_CorrectThreshold(decimal total, decimal threshold, bool expected)
    {
        _sut.IsEligibleForFreeShipping(total, threshold).Should().Be(expected);
    }

    [Fact]
    public void CalculateOrderTotal_AppliesDiscountThenTax()
    {
        var order = new Order();
        order.AddItem(new SampleApp.Core.Models.OrderItem
        {
            Quantity = 2, UnitPrice = 50m, ProductName = "Widget", ProductId = 1
        }); // subtotal = 100

        // 10% customer discount → 90; 20% tax → 18; total = 108
        var total = _sut.CalculateOrderTotal(order, customerDiscountRate: 0.10m, taxRate: 0.20m);

        total.Should().Be(108m);
    }
}
