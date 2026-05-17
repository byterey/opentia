using FluentAssertions;
using Moq;
using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;
using SampleApp.Services;

namespace SampleApp.Services.Tests;

public class OrderServiceTests
{
    private readonly Mock<IOrderRepository> _orders = new();
    private readonly Mock<IProductRepository> _products = new();
    private readonly Mock<INotificationService> _notifications = new();

    private OrderService CreateSut() => new(_orders.Object, _products.Object, _notifications.Object);

    private static Product AvailableProduct(int id, string name, decimal price, int stock) =>
        new() { Id = id, Name = name, Price = price, StockQuantity = stock, IsActive = true };

    [Fact]
    public async Task PlaceOrderAsync_ValidOrder_ReturnsConfirmedOrder()
    {
        var product = AvailableProduct(1, "Widget", 9.99m, 50);
        _products.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);

        var saved = new Order { Id = 100, Status = OrderStatus.Confirmed };
        _orders.Setup(r => r.AddAsync(It.IsAny<Order>())).ReturnsAsync(saved);

        var result = await CreateSut().PlaceOrderAsync(
            customerId: 42,
            productQuantities: new Dictionary<int, int> { { 1, 3 } },
            email: "user@test.com");

        result.Id.Should().Be(100);
        _notifications.Verify(n => n.SendOrderConfirmationAsync(100, "user@test.com"), Times.Once);
    }

    [Fact]
    public async Task PlaceOrderAsync_EmptyItems_Throws()
    {
        await Assert.ThrowsAsync<ArgumentException>(
            () => CreateSut().PlaceOrderAsync(1, new Dictionary<int, int>(), "x@x.com"));
    }

    [Fact]
    public async Task PlaceOrderAsync_InvalidCustomerId_Throws()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => CreateSut().PlaceOrderAsync(0, new Dictionary<int, int> { { 1, 1 } }, "x@x.com"));
    }

    [Fact]
    public async Task PlaceOrderAsync_ProductNotFound_Throws()
    {
        _products.Setup(r => r.GetByIdAsync(99)).ReturnsAsync((Product?)null);
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => CreateSut().PlaceOrderAsync(1, new Dictionary<int, int> { { 99, 1 } }, "x@x.com"));
    }

    [Fact]
    public async Task PlaceOrderAsync_InactiveProduct_Throws()
    {
        var product = new Product { Id = 1, IsActive = false, StockQuantity = 10 };
        _products.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => CreateSut().PlaceOrderAsync(1, new Dictionary<int, int> { { 1, 1 } }, "x@x.com"));
    }

    [Fact]
    public async Task PlaceOrderAsync_InsufficientStock_Throws()
    {
        var product = AvailableProduct(1, "Widget", 9.99m, 2);
        _products.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => CreateSut().PlaceOrderAsync(1, new Dictionary<int, int> { { 1, 5 } }, "x@x.com"));
    }

    [Fact]
    public async Task CancelOrderAsync_PendingOrder_ReturnsTrueAndCancels()
    {
        var order = new Order { Id = 1, Status = OrderStatus.Pending };
        _orders.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(order);
        _orders.Setup(r => r.UpdateAsync(It.IsAny<Order>())).ReturnsAsync(order);

        var result = await CreateSut().CancelOrderAsync(1);

        result.Should().BeTrue();
        order.Status.Should().Be(OrderStatus.Cancelled);
    }

    [Fact]
    public async Task CancelOrderAsync_ShippedOrder_Throws()
    {
        var order = new Order { Id = 1, Status = OrderStatus.Shipped };
        _orders.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(order);

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => CreateSut().CancelOrderAsync(1));
    }

    [Fact]
    public async Task CancelOrderAsync_NotFound_ReturnsFalse()
    {
        _orders.Setup(r => r.GetByIdAsync(99)).ReturnsAsync((Order?)null);
        var result = await CreateSut().CancelOrderAsync(99);
        result.Should().BeFalse();
    }

    [Fact]
    public async Task GetOrderAsync_InvalidId_Throws()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => CreateSut().GetOrderAsync(0));
    }

    [Fact]
    public async Task GetCustomerOrdersAsync_ReturnsRepositoryResult()
    {
        var orders = new List<Order> { new() { Id = 1 }, new() { Id = 2 } };
        _orders.Setup(r => r.GetByCustomerIdAsync(5)).ReturnsAsync(orders);

        var result = await CreateSut().GetCustomerOrdersAsync(5);

        result.Should().HaveCount(2);
    }
}
