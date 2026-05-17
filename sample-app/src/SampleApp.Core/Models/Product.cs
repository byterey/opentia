namespace SampleApp.Core.Models;

public class Product
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public decimal Price { get; set; }
    public string Category { get; set; } = string.Empty;
    public int StockQuantity { get; set; }
    public bool IsActive { get; set; } = true;

    public bool IsInStock() => StockQuantity > 0;

    public bool IsAvailable() => IsActive && IsInStock();

    public decimal GetDiscountedPrice(decimal discountPercent)
    {
        if (discountPercent < 0 || discountPercent > 100)
            throw new ArgumentOutOfRangeException(nameof(discountPercent), "Discount must be 0–100.");
        return Price * (1 - discountPercent / 100m);
    }
}
