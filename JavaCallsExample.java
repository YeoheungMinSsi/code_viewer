class BaseOrder {
    public int price(int count) { return count * 12000; }
    public String label(String text) { return "주문: " + text; }
    public String label(int count) { return "수량: " + count; }
}

class SpecialOrder extends BaseOrder {
    public SpecialOrder() {}

    @Override
    public int price(int count) { return super.price(count) - 1000; }

    public void receipt() {
        int count = 2;
        label(count);
        label("커피");
        price(count);
    }
}

public class JavaCallsExample {
    public static void main(String[] args) {
        SpecialOrder order = new SpecialOrder();
        order.receipt();
    }
}
