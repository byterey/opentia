namespace SampleApp.Core.Interfaces;

public interface INotificationService
{
    Task SendOrderConfirmationAsync(int orderId, string email);
    Task SendShipmentNotificationAsync(int orderId, string email, string trackingNumber);
    Task SendLowStockAlertAsync(int productId, string productName, int currentStock);
}
