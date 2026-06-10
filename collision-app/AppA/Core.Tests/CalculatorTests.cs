using AppA.Core;

namespace AppA.Core.Tests;

public class CalculatorTests
{
    public void Add_ReturnsSum()
    {
        var calc = new Calculator();
        if (calc.Add(2, 3) != 5) throw new Exception("Add failed");
    }

    public void Subtract_ReturnsDifference()
    {
        var calc = new Calculator();
        if (calc.Subtract(5, 3) != 2) throw new Exception("Subtract failed");
    }
}
