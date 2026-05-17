using SampleApp.Services;

namespace SampleApp.Api.Validators;

public record ValidationResult(IReadOnlyList<string> Errors)
{
    public bool IsValid => Errors.Count == 0;
}

public class OrderValidator
{
    private readonly InventoryService _inventory;

    public OrderValidator(InventoryService inventory)
    {
        _inventory = inventory;
    }

    public async Task<ValidationResult> ValidateAsync(Dictionary<int, int> productQuantities)
    {
        var errors = new List<string>();

        foreach (var (productId, quantity) in productQuantities)
        {
            if (quantity <= 0)
                errors.Add($"Product {productId}: quantity must be positive.");

            var canReserve = await _inventory.ReserveStockAsync(productId, quantity <= 0 ? 1 : quantity);
            if (!canReserve)
                errors.Add($"Product {productId}: insufficient stock.");
        }

        return new ValidationResult(errors);
    }
}
