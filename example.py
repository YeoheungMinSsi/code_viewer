class Order:
    def total(self):
        return sum(self.items)

    def receipt(self):
        return self.total()


def show(order):
    return order.receipt()


class Cart:
    async def refresh(self):
        pass
