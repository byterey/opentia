namespace AppB.Core;

public class Widget
{
    public bool Spinning { get; private set; }

    public void Spin() => Spinning = true;
}
