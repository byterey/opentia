using MultiApp.Domain.Enums;

namespace MultiApp.Application.DTOs;

public class OrderDto
{
    public Guid Id { get; set; }
    public string CustomerId { get; set; } = string.Empty;
    public OrderStatus Status { get; set; }
    public decimal Total { get; set; }
    public DateTime CreatedAt { get; set; }
    public List<OrderItemDto> Items { get; set; } = new();
}

public class OrderItemDto
{
    public string ProductId { get; set; } = string.Empty;
    public string ProductName { get; set; } = string.Empty;
    public int Quantity { get; set; }
    public decimal UnitPrice { get; set; }
    public decimal TotalPrice { get; set; }
}
