public class Order
{
    private int price = 12000;

    public Order() {}

    public int Total()
    {
        return price;
    }

    public string FormatTotal(int value)
    {
        return $"합계: {value}원";
    }

    public string Receipt()
    {
        return FormatTotal(Total());
    }
}

public class LearningExample
{
    public static void Main(string[] args)
    {
        Order order = new Order();
        System.Console.WriteLine(order.Receipt());
    }
}
