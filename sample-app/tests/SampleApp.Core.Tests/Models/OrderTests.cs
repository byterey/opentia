using FluentAssertions;
using SampleApp.Core.Models;

namespace SampleApp.Core.Tests.Models;

public class OrderTests
{
    private static OrderItem MakeItem(int productId, int qty, decimal price) =>
        new() { ProductId = productId, Quantity = qty, UnitPrice = price, ProductName = $"P{productId}" };

    [Fact]
    public void TotalAmount_SumsAllLineTotals()
    {
        var order = new Order();
        order.AddItem(MakeItem(1, 2, 10));
        order.AddItem(MakeItem(2, 3, 5));
        order.TotalAmount.Should().Be(35m);
    }

    [Fact]
    public void TotalAmount_EmptyOrder_IsZero()
    {
        new Order().TotalAmount.Should().Be(0);
    }

    [Fact]
    public void TotalItemCount_SumsQuantities()
    {
        var order = new Order();
        order.AddItem(MakeItem(1, 2, 10));
        order.AddItem(MakeItem(2, 5, 5));
        order.TotalItemCount.Should().Be(7);
    }

    [Theory]
    [InlineData(OrderStatus.Pending,   true)]
    [InlineData(OrderStatus.Confirmed, true)]
    [InlineData(OrderStatus.Shipped,   false)]
    [InlineData(OrderStatus.Delivered, false)]
    [InlineData(OrderStatus.Cancelled, false)]
    public void CanBeCancelled_CorrectPerStatus(OrderStatus status, bool expected)
    {
        var order = new Order { Status = status };
        order.CanBeCancelled().Should().Be(expected);
    }

    [Fact]
    public void AddItem_NullItem_Throws()
    {
        var order = new Order();
        Assert.Throws<ArgumentNullException>(() => order.AddItem(null!));
    }

    [Fact]
    public void RemoveItem_ExistingProduct_ReturnsTrueAndRemoves()
    {
        var order = new Order();
        order.AddItem(MakeItem(42, 1, 9.99m));
        order.RemoveItem(42).Should().BeTrue();
        order.Items.Should().BeEmpty();
    }

    [Fact]
    public void RemoveItem_NonexistentProduct_ReturnsFalse()
    {
        var order = new Order();
        order.RemoveItem(999).Should().BeFalse();
    }

    [Fact]
    public void NewOrder_DefaultStatusIsPending()
    {
        new Order().Status.Should().Be(OrderStatus.Pending);
    }
}
