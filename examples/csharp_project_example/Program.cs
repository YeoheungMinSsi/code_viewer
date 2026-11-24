using PriceService = Shop.DiscountPricing;
class Program {
    static void Main() {
        var service = new PriceService();
        service.Price(2);
        service.Price(2.5);
        service.Label(suffix: "잔", count: 2);
        service.Identity<int>(2);
        service.Sum(1, 2, 3);
        service.Discount();
    }
}
