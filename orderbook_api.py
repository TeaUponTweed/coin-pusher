#!/usr/bin/env python

import gdax
from itertools import tee
import json

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable) next(b, None)
    return zip(a, b)

class SimpleNodeVisitor():
   def __init__(self, product_list, path=None):
       self.path = path or []
       self.product_list = product_list

   def __iter__(self):
       yield self.path
       for node in self.all_coins:
           if node not in self.path:
               if not self.path or is_valid_transition(self.path[-1], node, self.product_list):
                   yield from SimpleNodeVisitor(self.path + [node])

all_coins = list(coin_increments)

def is_valid_transition(a, b, product_list):
    return '{}-{}'.format(a, b) in product_list or '{}-{}'.format(b, a) in product_list

def trade_stats(base_currency, base_number, next_currency, coin_increments): # TODO: add outstanding volume at bid/ask price for time calculation
    trade = '{}-{}'.format(base_currency, next_currency)
    if trade not in order_book_map:
        trade = '{}-{}'.format(next_currency, base_currency)
        order_book = order_book_map[trade]
        price = order_book.get_bid()
        next_number = (base_number / price)//coin_increments[next_currency] * coin_incremenets[next_currency]
        trade_arbitrage /= price
        trade_time = next_number / volume_map[trade]
    else:
        order_book = order_book_map[trade]
        price = order_book.get_bid()
        next_number = (base_number * price)//coin_increments[base_currency] * coin_increments[base_currency]
        trade_arbitrage *= price
        trade_time = number / volume_map[trade]

    return trade_arbitrage, trade_time, next_number

def loop_profit(loop, base_number, order_book_map, volume_map):
    loop = loop.append(loop[0])
    loop_arbitrage = 1.0
    loop_time = 0.0
    intermediate_number = base_number
    for base_currency, next_currency in pairwise(loop):
        trade_arbitrage, trade_time, trade_number = trade_stats(base_currency, intermediate_number, next_currency)
        loop_arbitrage *= trade_arbitrage
        loop_time += trade_time
        intermediate_number = trade_number
    return (loop_arbitrage - ) / loop_time

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
    all_paths = list(SimpleNodeVisitor([starting_with], product_list))
    profit, path = max(zip(map(f, all_paths), paths), key=lambda x: x[0])
    if profit > 0:
        return (path[1], profit)
    else:
        return None

def make_trade(product_id, price, size):
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

    return api_passphrase, api_key, api_secret

def run():

    auth_client = gdax.AuthenticatedClient(*get_api_credentials())
    public_client = gdax.PublicClient()
    // product_list = ["BTC-USD","ETH-USD","LTC-USD","ETH-BTC","LTC-BTC"]
    product_list = public_client.get_products()

    '''
    coin_increments = {
        'USD': 0.01,
        'BTC': 0.0001,
        'ETH': 0.001,
        'LTC': 0.01
    }
    '''
    coin_increments = public_client.get_product_increments() # TODO: this call doesn't exist, but I'd like to do it programmatically

    order_book_map = {k:gdax.OrderBook(product_id=k) for k in product_list}
    volume_map = make_volume_map(order_book_map, public_client)

    while True:
        current_coins = auth_client.get_accounts()

        next_trades = []

        for coin, number in current_coins:
            next_step = next_move(coin, number, order_book_map, volume_map, product_list)
            if next_step:
                next_trades.append((coin, number, next_step[0], next_step[1])

        sorted(next_trades, key=lambda x: x[3], reverse = True)

        for entry in next_trades:
            make_trade(entry, _, number) # TODO: need to pipe price out of path evalutation so we can set trade price

        time.sleep(1)
        auth_client.cancel_all_trades() # TODO: this doesn't exist

if __name__ == "__main__":
    run()
