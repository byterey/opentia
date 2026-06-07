using SampleApp.Services;
using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;

namespace SampleApp.Api.Tests.Validators;

public class OrderValidatorTests
{
    private static OrderValidator BuildValidator(params (int id, int stock)[] products)
    {
        var repo = new StubProductRepository(products);
        var inventory = new InventoryService(repo);
        return new OrderValidator(inventory);
    }

    [Fact]
    public async Task ValidateAsync_AllInStock_ReturnsValid()
    {
        var validator = BuildValidator((1, 10), (2, 5));

        var result = await validator.ValidateAsync(new() { [1] = 2, [2] = 1 });

        Assert.True(result.IsValid);
        Assert.Empty(result.Errors);
    }

    [Fact]
    public async Task ValidateAsync_InsufficientStock_ReturnsError()
    {
        var validator = BuildValidator((1, 1));

        var result = await validator.ValidateAsync(new() { [1] = 5 });

        Assert.False(result.IsValid);
        Assert.Contains(result.Errors, e => e.Contains("insufficient stock"));
    }

    [Fact]
    public async Task ValidateAsync_ZeroQuantity_ReturnsError()
    {
        var validator = BuildValidator((1, 10));

        var result = await validator.ValidateAsync(new() { [1] = 0 });

        Assert.False(result.IsValid);
        Assert.Contains(result.Errors, e => e.Contains("quantity must be positive"));
    }

    [Fact]
    public async Task ValidateAsync_NegativeQuantity_ReturnsError()
    {
        var validator = BuildValidator((1, 10));

        var result = await validator.ValidateAsync(new() { [1] = -3 });

        Assert.False(result.IsValid);
        Assert.Contains(result.Errors, e => e.Contains("quantity must be positive"));
    }

    [Fact]
    public async Task ValidateAsync_EmptyOrder_ReturnsValid()
    {
        var validator = BuildValidator();

        var result = await validator.ValidateAsync(new());

        Assert.True(result.IsValid);
        Assert.Empty(result.Errors);
    }

    private sealed class StubProductRepository : IProductRepository
    {
        private readonly Dictionary<int, Product> _products;

        public StubProductRepository(IEnumerable<(int id, int stock)> items)
        {
            _products = items.ToDictionary(
                x => x.id,
                x => new Product { Id = x.id, StockQuantity = x.stock, IsActive = true });
        }

        public Task<Product?> GetByIdAsync(int id) =>
            Task.FromResult(_products.GetValueOrDefault(id));

        public Task<Product> UpdateAsync(Product product)
        {
            _products[product.Id] = product;
            return Task.FromResult(product);
        }

        public Task<IEnumerable<Product>> GetAllAsync() =>
            Task.FromResult<IEnumerable<Product>>(_products.Values);

        public Task<IEnumerable<Product>> GetByCategoryAsync(string category) =>
            Task.FromResult(_products.Values.Where(p => p.Category == category));

        public Task<Product> AddAsync(Product product)
        {
            _products[product.Id] = product;
            return Task.FromResult(product);
        }

        public Task<bool> DeleteAsync(int id) =>
            Task.FromResult(_products.Remove(id));
    }
}
