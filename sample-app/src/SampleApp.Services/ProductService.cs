using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;

namespace SampleApp.Services;

public class ProductService
{
    private readonly IProductRepository _repository;
    private readonly INotificationService _notifications;
    private const int LowStockThreshold = 5;

    public ProductService(IProductRepository repository, INotificationService notifications)
    {
        _repository = repository;
        _notifications = notifications;
    }

    public async Task<Product?> GetProductAsync(int id)
    {
        if (id <= 0) throw new ArgumentOutOfRangeException(nameof(id));
        return await _repository.GetByIdAsync(id);
    }

    public async Task<IEnumerable<Product>> GetAvailableProductsAsync()
    {
        var all = await _repository.GetAllAsync();
        return all.Where(p => p.IsAvailable());
    }

    public async Task<Product> CreateProductAsync(string name, decimal price, string category, int stock)
    {
        if (string.IsNullOrWhiteSpace(name)) throw new ArgumentException("Name is required", nameof(name));
        if (price < 0) throw new ArgumentOutOfRangeException(nameof(price));
        if (stock < 0) throw new ArgumentOutOfRangeException(nameof(stock));

        var product = new Product
        {
            Name = name,
            Price = price,
            Category = category,
            StockQuantity = stock,
            IsActive = true,
        };
        return await _repository.AddAsync(product);
    }

    public async Task<bool> DeactivateProductAsync(int id)
    {
        var product = await _repository.GetByIdAsync(id);
        if (product is null) return false;
        product.IsActive = false;
        await _repository.UpdateAsync(product);
        return true;
    }

    public async Task AdjustStockAsync(int id, int adjustment)
    {
        var product = await _repository.GetByIdAsync(id);
        if (product is null) throw new InvalidOperationException($"Product {id} not found.");

        product.StockQuantity = Math.Max(0, product.StockQuantity + adjustment);
        await _repository.UpdateAsync(product);

        if (product.StockQuantity <= LowStockThreshold)
            await _notifications.SendLowStockAlertAsync(id, product.Name, product.StockQuantity);
    }

    public async Task<IEnumerable<Product>> SearchByNameAsync(string query)
    {
        if (string.IsNullOrWhiteSpace(query)) return Enumerable.Empty<Product>();
        var all = await _repository.GetAllAsync();
        return all.Where(p => p.Name.Contains(query, StringComparison.OrdinalIgnoreCase));
    }
}
