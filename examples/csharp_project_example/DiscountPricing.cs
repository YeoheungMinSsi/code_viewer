namespace Shop;
public class DiscountPricing : Pricing {
    public int Discount() => base.Price(2) - 1000;
}
