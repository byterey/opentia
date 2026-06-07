namespace MultiApp.Application.DTOs;

public class CreateOrderRequest
{
    public string CustomerId { get; set; } = string.Empty;
    public List<OrderItemRequest> Items { get; set; } = new();
}

public class OrderItemRequest
{
    public string ProductId { get; set; } = string.Empty;
    public string ProductName { get; set; } = string.Empty;
    public int Quantity { get; set; }
    public decimal UnitPrice { get; set; }
}
