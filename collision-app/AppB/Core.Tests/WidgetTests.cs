using AppB.Core;

namespace AppB.Core.Tests;

public class WidgetTests
{
    public void Spin_SetsSpinning()
    {
        var widget = new Widget();
        widget.Spin();
        if (!widget.Spinning) throw new Exception("Spin failed");
    }
}
