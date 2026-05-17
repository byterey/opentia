using SampleApp.Core.Models;

namespace SampleApp.Core.Interfaces;

public interface IOrderRepository
{
    Task<Order?> GetByIdAsync(int id);
    Task<IEnumerable<Order>> GetByCustomerIdAsync(int customerId);
    Task<Order> AddAsync(Order order);
    Task<Order> UpdateAsync(Order order);
}
