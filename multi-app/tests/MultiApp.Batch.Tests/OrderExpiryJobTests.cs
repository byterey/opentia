using FluentAssertions;
using MultiApp.Batch.Jobs;
using MultiApp.Domain.Entities;
using MultiApp.Domain.Enums;
using MultiApp.Domain.Services;
using MultiApp.Infrastructure.Repositories;

namespace MultiApp.Batch.Tests;

public class OrderExpiryJobTests
{
    private readonly InMemoryOrderRepository _repository = new();
    private readonly OrderDomainService _domainService = new();

    [Fact]
    public void Run_DoesNotExpireRecentOrders()
    {
        var order = new Order("c1");
        _repository.Save(order);

        var job = new OrderExpiryJob(_repository, _domainService, TimeSpan.FromHours(24));
        var expired = job.Run();

        expired.Should().Be(0);
        order.Status.Should().Be(OrderStatus.Pending);
    }

    [Fact]
    public void Run_ReturnsZeroWhenNoOrders()
    {
        var job = new OrderExpiryJob(_repository, _domainService, TimeSpan.FromHours(1));
        job.Run().Should().Be(0);
    }

    [Fact]
    public void Run_SkipsAlreadyCancelledOrders()
    {
        var order = new Order("c1");
        order.Cancel();
        _repository.Save(order);

        var job = new OrderExpiryJob(_repository, _domainService, TimeSpan.Zero);
        var expired = job.Run();

        expired.Should().Be(0);
        order.Status.Should().Be(OrderStatus.Cancelled);
    }

    [Fact]
    public void Run_SkipsConfirmedOrders()
    {
        var order = new Order("c1");
        order.AddItem(new OrderItem("p1", "Widget", 1, 5.00m));
        order.Confirm();
        _repository.Save(order);

        var job = new OrderExpiryJob(_repository, _domainService, TimeSpan.Zero);
        var expired = job.Run();

        expired.Should().Be(0);
        order.Status.Should().Be(OrderStatus.Confirmed);
    }
}

public class ReportGenerationJobTests
{
    private readonly InMemoryOrderRepository _repository = new();

    [Fact]
    public void Generate_ReturnsZeroTotalsForEmptyRepository()
    {
        var job = new ReportGenerationJob(_repository);
        var report = job.Generate();

        report.Total.Should().Be(0);
        report.TotalRevenue.Should().Be(0);
    }

    [Fact]
    public void Generate_CountsOrdersByStatus()
    {
        var pending = new Order("c1");
        var confirmed = new Order("c2");
        confirmed.AddItem(new OrderItem("p1", "Widget", 1, 10.00m));
        confirmed.Confirm();
        var completed = new Order("c3");
        completed.AddItem(new OrderItem("p1", "Widget", 2, 20.00m));
        completed.Confirm();
        completed.Complete();

        _repository.Save(pending);
        _repository.Save(confirmed);
        _repository.Save(completed);

        var job = new ReportGenerationJob(_repository);
        var report = job.Generate();

        report.Total.Should().Be(3);
        report.Pending.Should().Be(1);
        report.Confirmed.Should().Be(1);
        report.Completed.Should().Be(1);
        report.TotalRevenue.Should().Be(40.00m);
    }
}
