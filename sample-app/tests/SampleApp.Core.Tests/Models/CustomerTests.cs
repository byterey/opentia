using FluentAssertions;
using SampleApp.Core.Models;

namespace SampleApp.Core.Tests.Models;

public class CustomerTests
{
    [Theory]
    [InlineData("Alice", "Smith", "Alice Smith")]
    [InlineData("Alice", "",     "Alice")]
    [InlineData("",      "Smith","Smith")]
    public void FullName_CombinesFirstAndLast(string first, string last, string expected)
    {
        var c = new Customer { FirstName = first, LastName = last };
        c.FullName.Should().Be(expected);
    }

    [Theory]
    [InlineData(CustomerTier.Standard, 0.00)]
    [InlineData(CustomerTier.Silver,   0.05)]
    [InlineData(CustomerTier.Gold,     0.10)]
    [InlineData(CustomerTier.Platinum, 0.15)]
    public void GetDiscountRate_CorrectPerTier(CustomerTier tier, decimal expected)
    {
        var c = new Customer { Tier = tier };
        c.GetDiscountRate().Should().Be(expected);
    }

    [Theory]
    [InlineData("alice@example.com", true)]
    [InlineData("alice@example",     false)]
    [InlineData("aliceexample.com",  false)]
    [InlineData("",                  false)]
    [InlineData("   ",               false)]
    public void IsEmailValid_ValidatesCorrectly(string email, bool expected)
    {
        var c = new Customer { Email = email };
        c.IsEmailValid().Should().Be(expected);
    }

    [Fact]
    public void NewCustomer_DefaultTierIsStandard()
    {
        new Customer().Tier.Should().Be(CustomerTier.Standard);
    }

    [Fact]
    public void NewCustomer_DefaultDiscountIsZero()
    {
        new Customer().GetDiscountRate().Should().Be(0m);
    }
}
