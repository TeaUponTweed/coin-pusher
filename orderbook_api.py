#!/usr/bin/env python

import gdax
from itertools import tee

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..." 
    a, b = tee(iterable) next(b, None) 
    return zip(a, b)

class SimpleNodeVisitor():
   def __init__(self, path=None):
       self.path = path or []

   def __iter__(self):
       yield self.path
       for node in all_coins:
           if node not in self.path:
               if not self.path or is_valid_transition(self.path[-1], node):
                   yield from SimpleNodeVisitor(self.path + [node])

product_list = ["BTC-USD","ETH-USD","LTC-USD","ETH-BTC","LTC-BTC"]

public_client = gdax.PublicClient()

coin_increments = {
    'USD': 0.01,
    'BTC': 0.0001,
    'ETH': 0.001,
    'LTC': 0.01
}

all_coins = list(coin_increments)

def is_valid_transition(a, b):
    return '{}-{}'.format(a, b) in product_list or '{}-{}'.format(b, a) in product_list

def loop_profit(loop, number, order_book_map, volume_map):
    loop = loop.append(loop[0])
    arbitrage = 1.0
    trade_time = 0.0
    for current_currency, next_currency in pairwise(loop):
        order_book = order_book_map[trade]
        trade = '{}-{}'.format(current_currency, next_currency)
        if trade not in order_book_map:
            trade = '{}-{}'.format(next_currency, current_currency)
            arbitrage /= order_book.get_bid()
            convertable_coins = movable_coins * price//coin_increments[next_currency] * coin_incremenets[next_currency]
        else:
            movable_coins = number//coin_increments[current_currency] * coin_increments[current_currency]
            arbitrage *= order_book.get_ask()
        trade_time += volume_map[trade]

    arbitrage_opporunity = 1 / btc_usd_max_bid * btc_usd_min_sell
    trade_time_btc = timing_dollar_reference / usd_btc_sec + timing_dollar_reference / usd_btc_sec
    gain_btc = (arbitrage_opporunity_btc - 1) / trade_time_btc

def make_volume_map(order_book_map):
    volume_map = {}
    for product, order_book in order_book_map.items():
        volume = float(public_client.get_product_24hr_stats(product)['volume'])
        # price = float(order_book.get_current_ticker()['price'])
        rate = volume * 24 / 3600
        volume_map[product] = rate
    return volume_map

def next_move(starting_with, number):
    def f(path):
        return loop_profit(path, number)
    all_paths = list(SimpleNodeVisitor([starting_with]))
    profit, path = max(zip(map(f, all_paths), paths), key=lambda x: x[0])
    if profit > 0:
        return path[1]
    else:
        return None

def make_trade(product_id, price, size):
    print("product: {}, price: {}, size: {}")

def run():

    order_book_map = {k:gdax.OrderBook(product_id=k) for k in product_list}

if __name__ == "__main__":
    run()
