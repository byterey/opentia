using MultiApp.Domain.Enums;
using MultiApp.Domain.Interfaces;

namespace MultiApp.Batch.Jobs;

public record OrderStatusReport(
    int Total,
    int Pending,
    int Confirmed,
    int Processing,
    int Completed,
    int Cancelled,
    int Expired,
    decimal TotalRevenue
);

public class ReportGenerationJob
{
    private readonly IOrderRepository _repository;

    public ReportGenerationJob(IOrderRepository repository)
    {
        _repository = repository;
    }

    public OrderStatusReport Generate()
    {
        var orders = _repository.GetAll();
        return new OrderStatusReport(
            Total: orders.Count,
            Pending: orders.Count(o => o.Status == OrderStatus.Pending),
            Confirmed: orders.Count(o => o.Status == OrderStatus.Confirmed),
            Processing: orders.Count(o => o.Status == OrderStatus.Processing),
            Completed: orders.Count(o => o.Status == OrderStatus.Completed),
            Cancelled: orders.Count(o => o.Status == OrderStatus.Cancelled),
            Expired: orders.Count(o => o.Status == OrderStatus.Expired),
            TotalRevenue: orders.Where(o => o.Status == OrderStatus.Completed).Sum(o => o.Total)
        );
    }
}
