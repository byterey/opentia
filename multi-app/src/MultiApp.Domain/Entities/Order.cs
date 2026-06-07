using MultiApp.Domain.Enums;

namespace MultiApp.Domain.Entities;

public class Order
{
    private readonly List<OrderItem> _items = new();

    public Guid Id { get; private set; }
    public string CustomerId { get; private set; }
    public OrderStatus Status { get; private set; }
    public DateTime CreatedAt { get; private set; }
    public DateTime? UpdatedAt { get; private set; }
    public IReadOnlyList<OrderItem> Items => _items.AsReadOnly();
    public decimal Total => _items.Sum(i => i.TotalPrice);

    public Order(string customerId)
    {
        if (string.IsNullOrWhiteSpace(customerId))
            throw new ArgumentException("CustomerId is required.", nameof(customerId));

        Id = Guid.NewGuid();
        CustomerId = customerId;
        Status = OrderStatus.Pending;
        CreatedAt = DateTime.UtcNow;
    }

    public void AddItem(OrderItem item)
    {
        if (Status != OrderStatus.Pending)
            throw new InvalidOperationException("Items can only be added to pending orders.");

        _items.Add(item);
        UpdatedAt = DateTime.UtcNow;
    }

    public void Confirm()
    {
        if (Status != OrderStatus.Pending)
            throw new InvalidOperationException($"Cannot confirm an order in '{Status}' status.");
        if (_items.Count == 0)
            throw new InvalidOperationException("Cannot confirm an empty order.");

        Status = OrderStatus.Confirmed;
        UpdatedAt = DateTime.UtcNow;
    }

    public void Cancel()
    {
        if (Status == OrderStatus.Completed || Status == OrderStatus.Cancelled)
            throw new InvalidOperationException($"Cannot cancel an order in '{Status}' status.");

        Status = OrderStatus.Cancelled;
        UpdatedAt = DateTime.UtcNow;
    }

    public void Complete()
    {
        if (Status != OrderStatus.Confirmed && Status != OrderStatus.Processing)
            throw new InvalidOperationException($"Cannot complete an order in '{Status}' status.");

        Status = OrderStatus.Completed;
        UpdatedAt = DateTime.UtcNow;
    }

    public void Expire()
    {
        if (Status != OrderStatus.Pending)
            throw new InvalidOperationException($"Only pending orders can expire.");

        Status = OrderStatus.Expired;
        UpdatedAt = DateTime.UtcNow;
    }

    public bool IsExpired(TimeSpan expiryWindow) =>
        Status == OrderStatus.Pending && DateTime.UtcNow - CreatedAt > expiryWindow;
}
