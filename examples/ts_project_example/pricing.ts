export interface Priced {
  price(): number;
}

export function discount(price: number): number {
  return price * 0.9;
}

export class BaseItem implements Priced {
  constructor(protected amount: number) {}

  price(): number {
    return this.amount;
  }
}
