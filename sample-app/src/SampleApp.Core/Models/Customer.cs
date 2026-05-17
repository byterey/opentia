namespace SampleApp.Core.Models;

public enum CustomerTier { Standard, Silver, Gold, Platinum }

public class Customer
{
    public int Id { get; set; }
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string Email { get; set; } = string.Empty;
    public CustomerTier Tier { get; set; } = CustomerTier.Standard;
    public DateTime RegisteredAt { get; set; } = DateTime.UtcNow;

    public string FullName => $"{FirstName} {LastName}".Trim();

    public decimal GetDiscountRate() => Tier switch
    {
        CustomerTier.Silver   => 0.05m,
        CustomerTier.Gold     => 0.10m,
        CustomerTier.Platinum => 0.15m,
        _                     => 0m,
    };

    public bool IsEmailValid() =>
        !string.IsNullOrWhiteSpace(Email)
        && Email.Contains('@')
        && Email.Contains('.');
}
