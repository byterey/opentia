using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;

namespace SampleApp.Services;

public class OrderService
{
    private readonly IOrderRepository _orders;
    private readonly IProductRepository _products;
    private readonly INotificationService _notifications;

    public OrderService(
        IOrderRepository orders,
        IProductRepository products,
        INotificationService notifications)
    {
        _orders = orders;
        _products = products;
        _notifications = notifications;
    }

    public async Task<Order> PlaceOrderAsync(
        int customerId,
        Dictionary<int, int> productQuantities,
        string email)
    {
        if (customerId <= 0) throw new ArgumentOutOfRangeException(nameof(customerId));
        if (productQuantities is null || productQuantities.Count == 0)
            throw new ArgumentException("Order must contain at least one item.");

        var order = new Order { CustomerId = customerId };

        foreach (var (productId, quantity) in productQuantities)
        {
            var product = await _products.GetByIdAsync(productId)
                ?? throw new InvalidOperationException($"Product {productId} not found.");

            if (!product.IsAvailable())
                throw new InvalidOperationException($"Product '{product.Name}' is not available.");

            if (product.StockQuantity < quantity)
                throw new InvalidOperationException($"Insufficient stock for '{product.Name}'.");

            order.AddItem(new OrderItem
            {
                ProductId = productId,
                ProductName = product.Name,
                Quantity = quantity,
                UnitPrice = product.Price,
            });
        }

        order.Status = OrderStatus.Confirmed;
        var saved = await _orders.AddAsync(order);
        await _notifications.SendOrderConfirmationAsync(saved.Id, email);
        return saved;
    }

    public async Task<bool> CancelOrderAsync(int orderId)
    {
        var order = await _orders.GetByIdAsync(orderId);
        if (order is null) return false;
        if (!order.CanBeCancelled())
            throw new InvalidOperationException($"Order {orderId} cannot be cancelled (status: {order.Status}).");

        order.Status = OrderStatus.Cancelled;
        await _orders.UpdateAsync(order);
        return true;
    }

    public async Task<Order?> GetOrderAsync(int orderId)
    {
        if (orderId <= 0) throw new ArgumentOutOfRangeException(nameof(orderId));
        return await _orders.GetByIdAsync(orderId);
    }

    public async Task<IEnumerable<Order>> GetCustomerOrdersAsync(int customerId) =>
        await _orders.GetByCustomerIdAsync(customerId);
}
