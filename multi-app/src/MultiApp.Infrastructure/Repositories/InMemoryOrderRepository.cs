using MultiApp.Domain.Entities;
using MultiApp.Domain.Enums;
using MultiApp.Domain.Interfaces;

namespace MultiApp.Infrastructure.Repositories;

public class InMemoryOrderRepository : IOrderRepository
{
    private readonly Dictionary<Guid, Order> _store = new();

    public Order? GetById(Guid id) =>
        _store.TryGetValue(id, out var order) ? order : null;

    public IReadOnlyList<Order> GetAll() =>
        _store.Values.ToList();

    public IReadOnlyList<Order> GetByStatus(OrderStatus status) =>
        _store.Values.Where(o => o.Status == status).ToList();

    public void Save(Order order) =>
        _store[order.Id] = order;

    public void Delete(Guid id) =>
        _store.Remove(id);
}
