using FluentAssertions;
using MultiApp.Domain.Entities;
using MultiApp.Domain.Enums;

namespace MultiApp.Domain.Tests;

public class OrderTests
{
    [Fact]
    public void NewOrder_HasPendingStatus()
    {
        var order = new Order("customer-1");
        order.Status.Should().Be(OrderStatus.Pending);
    }

    [Fact]
    public void NewOrder_RequiresCustomerId()
    {
        var act = () => new Order("");
        act.Should().Throw<ArgumentException>();
    }

    [Fact]
    public void AddItem_IncreasesTotal()
    {
        var order = new Order("customer-1");
        order.AddItem(new OrderItem("p1", "Widget", 2, 10.00m));
        order.Total.Should().Be(20.00m);
    }

    [Fact]
    public void AddItem_ThrowsWhenNotPending()
    {
        var order = new Order("customer-1");
        order.AddItem(new OrderItem("p1", "Widget", 1, 5.00m));
        order.Confirm();

        var act = () => order.AddItem(new OrderItem("p2", "Gadget", 1, 3.00m));
        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Confirm_TransitionsToPendingToConfirmed()
    {
        var order = new Order("customer-1");
        order.AddItem(new OrderItem("p1", "Widget", 1, 5.00m));
        order.Confirm();
        order.Status.Should().Be(OrderStatus.Confirmed);
    }

    [Fact]
    public void Confirm_ThrowsWhenEmpty()
    {
        var order = new Order("customer-1");
        var act = () => order.Confirm();
        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Cancel_WorksFromPending()
    {
        var order = new Order("customer-1");
        order.Cancel();
        order.Status.Should().Be(OrderStatus.Cancelled);
    }

    [Fact]
    public void Cancel_ThrowsWhenCompleted()
    {
        var order = BuildConfirmedOrder();
        order.Complete();

        var act = () => order.Cancel();
        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Complete_WorksFromConfirmed()
    {
        var order = BuildConfirmedOrder();
        order.Complete();
        order.Status.Should().Be(OrderStatus.Completed);
    }

    [Fact]
    public void Expire_WorksFromPending()
    {
        var order = new Order("customer-1");
        order.Expire();
        order.Status.Should().Be(OrderStatus.Expired);
    }

    [Fact]
    public void Expire_ThrowsWhenConfirmed()
    {
        var order = BuildConfirmedOrder();
        var act = () => order.Expire();
        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Total_SumsAllItems()
    {
        var order = new Order("customer-1");
        order.AddItem(new OrderItem("p1", "A", 2, 10.00m));
        order.AddItem(new OrderItem("p2", "B", 3, 5.00m));
        order.Total.Should().Be(35.00m);
    }

    private static Order BuildConfirmedOrder()
    {
        var order = new Order("customer-1");
        order.AddItem(new OrderItem("p1", "Widget", 1, 10.00m));
        order.Confirm();
        return order;
    }
}
