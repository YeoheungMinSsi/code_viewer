using System;
namespace Learning;
interface IReceipt { string Receipt(); }
class Order : IReceipt {
    public int Price { get; set; } = 12000;
    public int Total() => Price;
    public string Receipt() => $"합계: {Total()}원";
}
class Program {
    static int Amount() => 12000;
    static void Main(string[] args) {
        var order = new Order();
        Console.WriteLine(Amount());
        Console.WriteLine(order.Receipt());
    }
}
