namespace MultiApp.Domain.Entities;

public class OrderItem
{
    public Guid Id { get; private set; }
    public string ProductId { get; private set; }
    public string ProductName { get; private set; }
    public int Quantity { get; private set; }
    public decimal UnitPrice { get; private set; }
    public decimal TotalPrice => Quantity * UnitPrice;

    public OrderItem(string productId, string productName, int quantity, decimal unitPrice)
    {
        if (quantity <= 0) throw new ArgumentException("Quantity must be positive.", nameof(quantity));
        if (unitPrice < 0) throw new ArgumentException("Unit price cannot be negative.", nameof(unitPrice));

        Id = Guid.NewGuid();
        ProductId = productId;
        ProductName = productName;
        Quantity = quantity;
        UnitPrice = unitPrice;
    }
}
