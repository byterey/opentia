using FluentAssertions;
using MultiApp.Application.DTOs;
using MultiApp.Application.Services;
using MultiApp.Domain.Enums;
using MultiApp.Infrastructure.Repositories;

namespace MultiApp.Application.Tests;

public class OrderServiceTests
{
    private readonly OrderService _sut;

    public OrderServiceTests()
    {
        _sut = new OrderService(new InMemoryOrderRepository());
    }

    [Fact]
    public void CreateOrder_ReturnsDtoWithPendingStatus()
    {
        var dto = _sut.CreateOrder(BuildRequest("customer-1"));
        dto.Status.Should().Be(OrderStatus.Pending);
        dto.CustomerId.Should().Be("customer-1");
    }

    [Fact]
    public void CreateOrder_PersistsOrder()
    {
        var dto = _sut.CreateOrder(BuildRequest("customer-1"));
        _sut.GetOrder(dto.Id).Should().NotBeNull();
    }

    [Fact]
    public void GetOrder_ReturnsNullForUnknownId()
    {
        _sut.GetOrder(Guid.NewGuid()).Should().BeNull();
    }

    [Fact]
    public void GetAllOrders_ReturnsAllCreated()
    {
        _sut.CreateOrder(BuildRequest("c1"));
        _sut.CreateOrder(BuildRequest("c2"));
        _sut.GetAllOrders().Should().HaveCount(2);
    }

    [Fact]
    public void ConfirmOrder_ChangesStatusToConfirmed()
    {
        var created = _sut.CreateOrder(BuildRequest("customer-1"));
        var confirmed = _sut.ConfirmOrder(created.Id);
        confirmed.Status.Should().Be(OrderStatus.Confirmed);
    }

    [Fact]
    public void ConfirmOrder_ThrowsForUnknownId()
    {
        var act = () => _sut.ConfirmOrder(Guid.NewGuid());
        act.Should().Throw<KeyNotFoundException>();
    }

    [Fact]
    public void CancelOrder_ChangesStatusToCancelled()
    {
        var created = _sut.CreateOrder(BuildRequest("customer-1"));
        var cancelled = _sut.CancelOrder(created.Id);
        cancelled.Status.Should().Be(OrderStatus.Cancelled);
    }

    [Fact]
    public void CreateOrder_CalculatesTotalCorrectly()
    {
        var request = new CreateOrderRequest
        {
            CustomerId = "customer-1",
            Items =
            [
                new() { ProductId = "p1", ProductName = "A", Quantity = 2, UnitPrice = 15.00m },
                new() { ProductId = "p2", ProductName = "B", Quantity = 1, UnitPrice = 10.00m },
            ],
        };
        var dto = _sut.CreateOrder(request);
        dto.Total.Should().Be(40.00m);
    }

    private static CreateOrderRequest BuildRequest(string customerId) => new()
    {
        CustomerId = customerId,
        Items = [new() { ProductId = "p1", ProductName = "Widget", Quantity = 1, UnitPrice = 9.99m }],
    };
}
