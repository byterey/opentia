namespace SampleApp.Core.Models;

public enum OrderStatus { Pending, Confirmed, Shipped, Delivered, Cancelled }

public class Order
{
    public int Id { get; set; }
    public int CustomerId { get; set; }
    public DateTime OrderDate { get; set; } = DateTime.UtcNow;
    public OrderStatus Status { get; set; } = OrderStatus.Pending;
    public List<OrderItem> Items { get; set; } = new();

    public decimal TotalAmount => Items.Sum(i => i.LineTotal);
    public int TotalItemCount => Items.Sum(i => i.Quantity);

    public bool CanBeCancelled() =>
        Status is OrderStatus.Pending or OrderStatus.Confirmed;

    public void AddItem(OrderItem item)
    {
        ArgumentNullException.ThrowIfNull(item);
        Items.Add(item);
    }

    public bool RemoveItem(int productId)
    {
        var item = Items.FirstOrDefault(i => i.ProductId == productId);
        if (item is null) return false;
        Items.Remove(item);
        return true;
    }
}
