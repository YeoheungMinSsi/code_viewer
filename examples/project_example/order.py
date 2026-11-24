from pricing import discount as sale
import pricing as prices

def checkout():
    return sale(10000) + prices.discount(20000)
