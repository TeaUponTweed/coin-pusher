#!/usr/bin/env python

import gdax
from itertools import tee
import json

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)

class SimpleNodeVisitor():
   def __init__(self, path=None):
       self.path = path or []

   def __iter__(self):
       yield self.path
       for node in all_coins:
           if node not in self.path:
               if not self.path or is_valid_transition(self.path[-1], node, product_list):
                   yield from SimpleNodeVisitor(self.path + [node])

coin_increments = {
    'USD': 0.01,
    'BTC': 0.0001,
    'ETH': 0.001,
    'LTC': 0.01
}
all_coins = list(coin_increments)
product_list = ["BTC-USD","ETH-USD","LTC-USD","ETH-BTC","LTC-BTC"]

def is_valid_transition(a, b, product_list):
    return '{}-{}'.format(a, b) in product_list or '{}-{}'.format(b, a) in product_list

def trade_stats(base_currency, base_number, next_currency, order_book_map, volume_map): # TODO: add outstanding volume at bid/ask price for time calculation
    trade = '{}-{}'.format(base_currency, next_currency)
    trade_arbitrage = 1
    trade_time = 0
    if trade not in order_book_map:
        trade = '{}-{}'.format(next_currency, base_currency)
        order_book = order_book_map[trade]
        print("OB id: {}".format(order_book.product_id))
        price = float(order_book.get_bid())
        next_number = (base_number / price)//coin_increments[next_currency] * coin_increments[next_currency]
        trade_arbitrage /= price
        trade_time = next_number / volume_map[trade]
    else:
        order_book = order_book_map[trade]
        print("OB id: {}".format(order_book.product_id))
        price = float(order_book.get_bid())
        next_number = (base_number * price)//coin_increments[base_currency] * coin_increments[base_currency]
        trade_arbitrage *= price
        trade_time = base_number / volume_map[trade]

    return trade_arbitrage, trade_time, next_number

def loop_profit(loop, base_number, order_book_map, volume_map):
    loop.append(loop[0])
    loop_arbitrage = 1.0
    loop_time = 0.0
    intermediate_number = base_number
    print("Loop: {}, Volume: {}".format(loop, base_number))
    for base_currency, next_currency in pairwise(loop):
        trade_arbitrage, trade_time, trade_number = trade_stats(base_currency, intermediate_number, next_currency, order_book_map, volume_map)
        loop_arbitrage *= trade_arbitrage
        loop_time += trade_time
        intermediate_number = trade_number
    print("loop_arbitrage: {}, time: {}".format(loop_arbitrage, loop_time))
    return (loop_arbitrage - 1) / loop_time

def make_volume_map(order_book_map, public_client):
    volume_map = {}
    for product, order_book in order_book_map.items():
        volume = float(public_client.get_product_24hr_stats(product)['volume'])
        rate = volume / 24 / 3600
        volume_map[product] = rate
    return volume_map

def next_move(starting_with, number, order_book_map, volume_map, product_list):
    def f(path):
        return loop_profit(path, number, order_book_map, volume_map)
    all_paths = list(SimpleNodeVisitor([starting_with]))[1:] # Is there a better way to avoid the loop of lenth 1?
    print("All paths: {}".format(all_paths))
    profit, path = max(zip(map(f, all_paths), all_paths), key=lambda x: x[0])
    if profit > 0:
        return (path[1], profit)
    else:
        return None

def make_trade(product_id, price, size):
    # "FYI, you will never be charged a fee if you use the post_only option with limit orders" (I found this quote on gdax discussion)
    print("product: {}, price: {}, size: {}")

def get_api_credentials(api_credential_file = 'api_credentials.json', sandbox = False):
    with open(api_credential_file) as api_json:
        api_dict = json.load(api_json)

    credentials = {}

    if sandbox:
        credentials = api_dict["sandbox"]
    else:
        credentials = api_dict["official"]

    api_passphrase = credentials["passphrase"]
    api_key = credentials["key"]
    api_secret = credentials["b64secret"]

    return api_key, api_secret, api_passphrase

def run():

    auth_client = gdax.AuthenticatedClient(*get_api_credentials())
    public_client = gdax.PublicClient()
    # products = public_client.get_products()

    coin_increments = {
        'USD': 0.01,
        'BTC': 0.0001,
        'ETH': 0.001,
        'LTC': 0.01
    }

    # coin_increments = public_client.get_product_increments() # TODO: this call doesn't exist, but I'd like to do it programmatically

    order_book_map = {k:gdax.OrderBook(product_id=k) for k in product_list}
    for obm_entry in order_book_map.values():
        obm_entry.start()

    volume_map = make_volume_map(order_book_map, public_client)

    while True:
        # account_dict = {account['currency']:float(account['available']) for account in auth_client.get_accounts()}
        account_dict = {'ETH': 1.0, 'BTC': 1.0, 'USD': 2.4, 'LTC': 1.0, 'BCH': 1.0} # Test
        print("Account: {}".format(account_dict))

        next_trades = []

        for coin, number in account_dict.items():
            next_step = next_move(coin, number, order_book_map, volume_map, product_list)
            if next_step:
                next_trades.append((coin, number, next_step[0], next_step[1]))

        for entry in next_trades:
            make_trade(entry, _, number) # TODO: need to pipe price out of path evalutation so we can set trade price

        time.sleep(1)
        auth_client.cancel_all_trades() # TODO: this doesn't exist

if __name__ == "__main__":
    run()
