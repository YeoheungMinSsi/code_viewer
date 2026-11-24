namespace Shop;
public class Pricing {
    public int Price(int count) => count * 12000;
    public double Price(double count) => count * 12000;
    public string Label(int count, string suffix = "개") => count + suffix;
    public T Identity<T>(T value) => value;
    public int Sum(params int[] values) => values.Length;
}
