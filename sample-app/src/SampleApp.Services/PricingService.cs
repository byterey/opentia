using SampleApp.Core.Models;
using SampleApp.Core.Utilities;

namespace SampleApp.Services;

public class PricingService
{
    public decimal CalculateDiscountedPrice(decimal basePrice, decimal discountPercent)
    {
        if (basePrice < 0) throw new ArgumentOutOfRangeException(nameof(basePrice));
        var clamped = MathHelper.Clamp(discountPercent, 0m, 100m);
        return MathHelper.RoundTo(basePrice * (1 - clamped / 100m), 2);
    }

    public decimal CalculateTax(decimal amount, decimal taxRate)
    {
        if (amount < 0) throw new ArgumentOutOfRangeException(nameof(amount));
        if (taxRate < 0 || taxRate > 1) throw new ArgumentOutOfRangeException(nameof(taxRate));
        return MathHelper.RoundTo(amount * taxRate, 2);
    }

    public decimal CalculateOrderTotal(Order order, decimal customerDiscountRate, decimal taxRate)
    {
        var subtotal = order.TotalAmount;
        var discounted = CalculateDiscountedPrice(subtotal, customerDiscountRate * 100);
        var tax = CalculateTax(discounted, taxRate);
        return MathHelper.RoundTo(discounted + tax, 2);
    }

    public decimal GetBulkDiscount(int quantity) => quantity switch
    {
        >= 100 => 20m,
        >= 50  => 15m,
        >= 20  => 10m,
        >= 10  => 5m,
        _      => 0m,
    };

    public bool IsEligibleForFreeShipping(decimal orderTotal, decimal threshold = 50m) =>
        orderTotal >= threshold;
}
