function formatTotal(value: number): string {
  return `합계: ${value}원`;
}

class Order {
  price: number;

  constructor() {
    this.price = 12000;
  }

  total(): number {
    return this.price;
  }

  receipt(): string {
    return formatTotal(this.total());
  }
}

const order = new Order();
console.log(order.receipt());
