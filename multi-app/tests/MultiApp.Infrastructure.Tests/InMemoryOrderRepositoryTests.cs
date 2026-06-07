using FluentAssertions;
using MultiApp.Domain.Entities;
using MultiApp.Domain.Enums;
using MultiApp.Infrastructure.Repositories;

namespace MultiApp.Infrastructure.Tests;

public class InMemoryOrderRepositoryTests
{
    private readonly InMemoryOrderRepository _sut = new();

    [Fact]
    public void GetById_ReturnsNullForMissingOrder()
    {
        _sut.GetById(Guid.NewGuid()).Should().BeNull();
    }

    [Fact]
    public void Save_And_GetById_RoundTrips()
    {
        var order = new Order("customer-1");
        _sut.Save(order);
        _sut.GetById(order.Id).Should().BeSameAs(order);
    }

    [Fact]
    public void GetAll_ReturnsAllSavedOrders()
    {
        _sut.Save(new Order("c1"));
        _sut.Save(new Order("c2"));
        _sut.GetAll().Should().HaveCount(2);
    }

    [Fact]
    public void GetByStatus_FiltersCorrectly()
    {
        var pending = new Order("c1");
        var confirmed = new Order("c2");
        confirmed.AddItem(new OrderItem("p1", "Widget", 1, 5.00m));
        confirmed.Confirm();

        _sut.Save(pending);
        _sut.Save(confirmed);

        _sut.GetByStatus(OrderStatus.Pending).Should().ContainSingle();
        _sut.GetByStatus(OrderStatus.Confirmed).Should().ContainSingle();
    }

    [Fact]
    public void Delete_RemovesOrder()
    {
        var order = new Order("customer-1");
        _sut.Save(order);
        _sut.Delete(order.Id);
        _sut.GetById(order.Id).Should().BeNull();
    }

    [Fact]
    public void Save_OverwritesExistingOrder()
    {
        var order = new Order("customer-1");
        _sut.Save(order);
        order.AddItem(new OrderItem("p1", "Widget", 1, 5.00m));
        _sut.Save(order);

        _sut.GetById(order.Id)!.Total.Should().Be(5.00m);
    }
}
