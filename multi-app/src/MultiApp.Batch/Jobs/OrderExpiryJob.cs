using MultiApp.Domain.Enums;
using MultiApp.Domain.Interfaces;
using MultiApp.Domain.Services;

namespace MultiApp.Batch.Jobs;

public class OrderExpiryJob
{
    private readonly IOrderRepository _repository;
    private readonly OrderDomainService _domainService;
    private readonly TimeSpan _expiryWindow;

    public OrderExpiryJob(IOrderRepository repository, OrderDomainService domainService, TimeSpan expiryWindow)
    {
        _repository = repository;
        _domainService = domainService;
        _expiryWindow = expiryWindow;
    }

    public int Run()
    {
        var pending = _repository.GetByStatus(OrderStatus.Pending);
        var expired = _domainService.FindExpired(pending, _expiryWindow);

        foreach (var order in expired)
        {
            order.Expire();
            _repository.Save(order);
        }

        return expired.Count;
    }
}
