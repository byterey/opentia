using MultiApp.Application.DTOs;
using MultiApp.Application.Interfaces;
using MultiApp.Domain.Entities;
using MultiApp.Domain.Interfaces;

namespace MultiApp.Application.Services;

public class OrderService : IOrderService
{
    private readonly IOrderRepository _repository;

    public OrderService(IOrderRepository repository)
    {
        _repository = repository;
    }

    public OrderDto CreateOrder(CreateOrderRequest request)
    {
        var order = new Order(request.CustomerId);
        foreach (var item in request.Items)
            order.AddItem(new OrderItem(item.ProductId, item.ProductName, item.Quantity, item.UnitPrice));

        _repository.Save(order);
        return ToDto(order);
    }

    public OrderDto? GetOrder(Guid id) =>
        _repository.GetById(id) is { } order ? ToDto(order) : null;

    public IReadOnlyList<OrderDto> GetAllOrders() =>
        _repository.GetAll().Select(ToDto).ToList();

    public OrderDto ConfirmOrder(Guid id)
    {
        var order = _repository.GetById(id)
            ?? throw new KeyNotFoundException($"Order {id} not found.");

        order.Confirm();
        _repository.Save(order);
        return ToDto(order);
    }

    public OrderDto CancelOrder(Guid id)
    {
        var order = _repository.GetById(id)
            ?? throw new KeyNotFoundException($"Order {id} not found.");

        order.Cancel();
        _repository.Save(order);
        return ToDto(order);
    }

    private static OrderDto ToDto(Order order) => new()
    {
        Id = order.Id,
        CustomerId = order.CustomerId,
        Status = order.Status,
        Total = order.Total,
        CreatedAt = order.CreatedAt,
        Items = order.Items.Select(i => new OrderItemDto
        {
            ProductId = i.ProductId,
            ProductName = i.ProductName,
            Quantity = i.Quantity,
            UnitPrice = i.UnitPrice,
            TotalPrice = i.TotalPrice,
        }).ToList(),
    };
}
