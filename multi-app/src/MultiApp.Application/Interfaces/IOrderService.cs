using MultiApp.Application.DTOs;

namespace MultiApp.Application.Interfaces;

public interface IOrderService
{
    OrderDto CreateOrder(CreateOrderRequest request);
    OrderDto? GetOrder(Guid id);
    IReadOnlyList<OrderDto> GetAllOrders();
    OrderDto ConfirmOrder(Guid id);
    OrderDto CancelOrder(Guid id);
}
