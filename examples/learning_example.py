def format_total(value):
    return f"합계: {value}원"


class Order:
    def __init__(self):
        self.price = 12000

    def total(self):
        return self.price

    def receipt(self):
        return format_total(self.total())


if __name__ == "__main__":
    order = Order()
    print(order.receipt())
