import { discount, BaseItem } from "./pricing";
import * as prices from "./pricing";

class Book extends BaseItem {
  label(): string {
    return `책 ${this.price()}원`;
  }
}

export function checkout(): number {
  const book = new Book(10000);
  book.label();
  return discount(book.price()) + prices.discount(500);
}
