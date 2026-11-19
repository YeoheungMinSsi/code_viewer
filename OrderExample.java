import java.util.Locale;

class Order {
    private int price;

    public Order(int price) {
        this.price = price;
    }

    public int total() {
        return price;
    }

    public String receipt() {
        return String.format(Locale.KOREA, "합계: %d원", total());
    }
}

public class OrderExample {
    public static void main(String[] args) {
        Order order = new Order(12000);
        System.out.println(order.receipt());
    }
}
