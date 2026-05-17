using SampleApp.Core.Interfaces;
using SampleApp.Core.Models;

namespace SampleApp.Services;

public enum StockStatus { Normal, Low, Critical, OutOfStock }

public class InventoryService
{
    private readonly IProductRepository _repository;
    private const int CriticalLevel = 2;
    private const int LowLevel = 10;

    public InventoryService(IProductRepository repository)
    {
        _repository = repository;
    }

    public async Task<IEnumerable<Product>> GetLowStockProductsAsync()
    {
        var all = await _repository.GetAllAsync();
        return all.Where(p => p.IsActive && p.StockQuantity <= LowLevel);
    }

    public async Task<IEnumerable<Product>> GetCriticalStockProductsAsync()
    {
        var all = await _repository.GetAllAsync();
        return all.Where(p => p.IsActive && p.StockQuantity <= CriticalLevel);
    }

    public async Task<Dictionary<string, int>> GetStockSummaryByCategory()
    {
        var all = await _repository.GetAllAsync();
        return all
            .GroupBy(p => p.Category)
            .ToDictionary(g => g.Key, g => g.Sum(p => p.StockQuantity));
    }

    public StockStatus GetStockStatus(int quantity) => quantity switch
    {
        0                => StockStatus.OutOfStock,
        <= CriticalLevel => StockStatus.Critical,
        <= LowLevel      => StockStatus.Low,
        _                => StockStatus.Normal,
    };

    public async Task<bool> ReserveStockAsync(int productId, int quantity)
    {
        if (quantity <= 0) throw new ArgumentOutOfRangeException(nameof(quantity));
        var product = await _repository.GetByIdAsync(productId);
        if (product is null || product.StockQuantity < quantity) return false;
        product.StockQuantity -= quantity;
        await _repository.UpdateAsync(product);
        return true;
    }
}
