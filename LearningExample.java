class Order {
    private int price = 12000;
    public Order() {}
    public int total() { return price; }
    public String format_total(int value) { return "합계: " + value + "원"; }
    public String receipt() { return format_total(total()); }
}
public class LearningExample {
    public static void main(String[] args) {
        Order order = new Order();
        System.out.println(order.receipt());
    }
}
