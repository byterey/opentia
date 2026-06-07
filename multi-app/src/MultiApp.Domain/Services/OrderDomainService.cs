using MultiApp.Domain.Entities;
using MultiApp.Domain.Enums;

namespace MultiApp.Domain.Services;

public class OrderDomainService
{ //chang
    public decimal CalculateTotal(Order order) => order.Total;

    public bool CanTransitionTo(Order order, OrderStatus target) => (order.Status, target) switch
    {
        (OrderStatus.Pending, OrderStatus.Confirmed) => order.Items.Count > 0,
        (OrderStatus.Pending, OrderStatus.Cancelled) => true,
        (OrderStatus.Pending, OrderStatus.Expired) => true,
        (OrderStatus.Confirmed, OrderStatus.Processing) => true,
        (OrderStatus.Confirmed, OrderStatus.Cancelled) => true,
        (OrderStatus.Processing, OrderStatus.Completed) => true,
        (OrderStatus.Processing, OrderStatus.Cancelled) => true,
        _ => false,
    };

    public IReadOnlyList<Order> FindExpired(IEnumerable<Order> orders, TimeSpan expiryWindow) =>
        orders.Where(o => o.IsExpired(expiryWindow)).ToList();
}
