using FluentAssertions;
using Moq;
using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;
using SampleApp.Services;

namespace SampleApp.Services.Tests;

public class InventoryServiceTests
{
    private readonly Mock<IProductRepository> _repo = new();
    private InventoryService CreateSut() => new(_repo.Object);

    private static List<Product> MakeProducts() =>
    [
        new() { Id = 1, Name = "A", Category = "Widgets", StockQuantity = 100, IsActive = true },
        new() { Id = 2, Name = "B", Category = "Widgets", StockQuantity = 8,   IsActive = true },
        new() { Id = 3, Name = "C", Category = "Gadgets", StockQuantity = 2,   IsActive = true },
        new() { Id = 4, Name = "D", Category = "Gadgets", StockQuantity = 0,   IsActive = true },
        new() { Id = 5, Name = "E", Category = "Widgets", StockQuantity = 0,   IsActive = false },
    ];

    [Fact]
    public async Task GetLowStockProductsAsync_ReturnsActiveProductsAtOrBelowThreshold()
    {
        _repo.Setup(r => r.GetAllAsync()).ReturnsAsync(MakeProducts());

        var result = await CreateSut().GetLowStockProductsAsync();

        result.Should().HaveCount(3)
            .And.OnlyContain(p => p.IsActive && p.StockQuantity <= 10);
    }

    [Fact]
    public async Task GetCriticalStockProductsAsync_ReturnsAtOrBelowCriticalLevel()
    {
        _repo.Setup(r => r.GetAllAsync()).ReturnsAsync(MakeProducts());

        var result = await CreateSut().GetCriticalStockProductsAsync();

        result.Should().HaveCount(2)
            .And.OnlyContain(p => p.IsActive && p.StockQuantity <= 2);
    }

    [Fact]
    public async Task GetStockSummaryByCategory_GroupsCorrectly()
    {
        _repo.Setup(r => r.GetAllAsync()).ReturnsAsync(MakeProducts());

        var summary = await CreateSut().GetStockSummaryByCategory();

        summary["Widgets"].Should().Be(108); // 100 + 8 + 0 (inactive)
        summary["Gadgets"].Should().Be(2);   // 2 + 0
    }

    [Theory]
    [InlineData(0,   StockStatus.OutOfStock)]
    [InlineData(1,   StockStatus.Critical)]
    [InlineData(2,   StockStatus.Critical)]
    [InlineData(3,   StockStatus.Low)]
    [InlineData(10,  StockStatus.Low)]
    [InlineData(11,  StockStatus.Normal)]
    [InlineData(999, StockStatus.Normal)]
    public void GetStockStatus_ReturnsCorrectLevel(int quantity, StockStatus expected)
    {
        CreateSut().GetStockStatus(quantity).Should().Be(expected);
    }

    [Fact]
    public async Task ReserveStockAsync_SufficientStock_DeductsAndReturnsTrue()
    {
        var product = new Product { Id = 1, StockQuantity = 20, IsActive = true };
        _repo.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);
        _repo.Setup(r => r.UpdateAsync(It.IsAny<Product>())).ReturnsAsync(product);

        var result = await CreateSut().ReserveStockAsync(1, 5);

        result.Should().BeTrue();
        product.StockQuantity.Should().Be(15);
    }

    [Fact]
    public async Task ReserveStockAsync_InsufficientStock_ReturnsFalse()
    {
        var product = new Product { Id = 1, StockQuantity = 3, IsActive = true };
        _repo.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);

        var result = await CreateSut().ReserveStockAsync(1, 5);

        result.Should().BeFalse();
        product.StockQuantity.Should().Be(3); // unchanged
    }

    [Fact]
    public async Task ReserveStockAsync_ProductNotFound_ReturnsFalse()
    {
        _repo.Setup(r => r.GetByIdAsync(99)).ReturnsAsync((Product?)null);
        var result = await CreateSut().ReserveStockAsync(99, 1);
        result.Should().BeFalse();
    }

    [Fact]
    public async Task ReserveStockAsync_ZeroQuantity_Throws()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => CreateSut().ReserveStockAsync(1, 0));
    }
}
