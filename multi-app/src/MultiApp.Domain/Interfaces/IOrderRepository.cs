using MultiApp.Domain.Entities;
using MultiApp.Domain.Enums;

namespace MultiApp.Domain.Interfaces;

public interface IOrderRepository
{
    Order? GetById(Guid id);
    IReadOnlyList<Order> GetAll();
    IReadOnlyList<Order> GetByStatus(OrderStatus status);
    void Save(Order order);
    void Delete(Guid id);
}
