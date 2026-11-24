def format_total(value):
    return f"합계: {value}원"


class Order:
    def total(self):
        return 12000

    def receipt(self):
        return format_total(self.total())
