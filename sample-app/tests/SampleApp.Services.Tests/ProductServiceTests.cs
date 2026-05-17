using FluentAssertions;
using Moq;
using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;
using SampleApp.Services;

namespace SampleApp.Services.Tests;

public class ProductServiceTests
{
    private readonly Mock<IProductRepository> _repo = new();
    private readonly Mock<INotificationService> _notifications = new();

    private ProductService CreateSut() => new(_repo.Object, _notifications.Object);

    [Fact]
    public async Task GetProductAsync_ValidId_ReturnsProduct()
    {
        var product = new Product { Id = 1, Name = "Widget" };
        _repo.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);

        var result = await CreateSut().GetProductAsync(1);

        result.Should().Be(product);
    }

    [Fact]
    public async Task GetProductAsync_InvalidId_Throws()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => CreateSut().GetProductAsync(0));
    }

    [Fact]
    public async Task GetProductAsync_NotFound_ReturnsNull()
    {
        _repo.Setup(r => r.GetByIdAsync(99)).ReturnsAsync((Product?)null);
        var result = await CreateSut().GetProductAsync(99);
        result.Should().BeNull();
    }

    [Fact]
    public async Task GetAvailableProductsAsync_FiltersInactiveAndOutOfStock()
    {
        _repo.Setup(r => r.GetAllAsync()).ReturnsAsync(new List<Product>
        {
            new() { Id = 1, IsActive = true,  StockQuantity = 5 },
            new() { Id = 2, IsActive = false, StockQuantity = 5 },
            new() { Id = 3, IsActive = true,  StockQuantity = 0 },
        });

        var result = await CreateSut().GetAvailableProductsAsync();

        result.Should().ContainSingle(p => p.Id == 1);
    }

    [Fact]
    public async Task CreateProductAsync_ValidArgs_CreatesAndReturns()
    {
        var created = new Product { Id = 10, Name = "Gizmo", Price = 9.99m };
        _repo.Setup(r => r.AddAsync(It.IsAny<Product>())).ReturnsAsync(created);

        var result = await CreateSut().CreateProductAsync("Gizmo", 9.99m, "Electronics", 100);

        result.Should().Be(created);
        _repo.Verify(r => r.AddAsync(It.Is<Product>(p =>
            p.Name == "Gizmo" && p.Price == 9.99m && p.IsActive)), Times.Once);
    }

    [Theory]
    [InlineData("",    10, "Electronics", 5)]
    [InlineData("   ", 10, "Electronics", 5)]
    public async Task CreateProductAsync_EmptyName_Throws(string name, decimal price, string cat, int stock)
    {
        await Assert.ThrowsAsync<ArgumentException>(
            () => CreateSut().CreateProductAsync(name, price, cat, stock));
    }

    [Fact]
    public async Task CreateProductAsync_NegativePrice_Throws()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(
            () => CreateSut().CreateProductAsync("Widget", -1, "Cat", 0));
    }

    [Fact]
    public async Task DeactivateProductAsync_ExistingProduct_DeactivatesAndReturnsTrue()
    {
        var product = new Product { Id = 1, IsActive = true };
        _repo.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);
        _repo.Setup(r => r.UpdateAsync(It.IsAny<Product>())).ReturnsAsync(product);

        var result = await CreateSut().DeactivateProductAsync(1);

        result.Should().BeTrue();
        product.IsActive.Should().BeFalse();
    }

    [Fact]
    public async Task DeactivateProductAsync_NotFound_ReturnsFalse()
    {
        _repo.Setup(r => r.GetByIdAsync(99)).ReturnsAsync((Product?)null);
        var result = await CreateSut().DeactivateProductAsync(99);
        result.Should().BeFalse();
    }

    [Fact]
    public async Task AdjustStockAsync_BelowThreshold_SendsLowStockAlert()
    {
        var product = new Product { Id = 1, Name = "Widget", StockQuantity = 10 };
        _repo.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);
        _repo.Setup(r => r.UpdateAsync(It.IsAny<Product>())).ReturnsAsync(product);

        await CreateSut().AdjustStockAsync(1, -8); // leaves 2 (below threshold of 5)

        _notifications.Verify(n => n.SendLowStockAlertAsync(1, "Widget", 2), Times.Once);
    }

    [Fact]
    public async Task AdjustStockAsync_StockNeverGoesNegative()
    {
        var product = new Product { Id = 1, Name = "Widget", StockQuantity = 3 };
        _repo.Setup(r => r.GetByIdAsync(1)).ReturnsAsync(product);
        _repo.Setup(r => r.UpdateAsync(It.IsAny<Product>())).ReturnsAsync(product);

        await CreateSut().AdjustStockAsync(1, -100);

        product.StockQuantity.Should().Be(0);
    }

    [Fact]
    public async Task AdjustStockAsync_ProductNotFound_Throws()
    {
        _repo.Setup(r => r.GetByIdAsync(99)).ReturnsAsync((Product?)null);
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => CreateSut().AdjustStockAsync(99, -1));
    }

    [Fact]
    public async Task SearchByNameAsync_EmptyQuery_ReturnsEmpty()
    {
        var result = await CreateSut().SearchByNameAsync("");
        result.Should().BeEmpty();
    }

    [Fact]
    public async Task SearchByNameAsync_MatchingQuery_ReturnsMatches()
    {
        _repo.Setup(r => r.GetAllAsync()).ReturnsAsync(new List<Product>
        {
            new() { Id = 1, Name = "Blue Widget" },
            new() { Id = 2, Name = "Red Gadget" },
            new() { Id = 3, Name = "Blue Gadget" },
        });

        var result = await CreateSut().SearchByNameAsync("blue");

        result.Should().HaveCount(2).And.OnlyContain(p => p.Name.Contains("Blue"));
    }
}
