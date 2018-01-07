#!/usr/bin/env python

import gdax
from itertools import tee
import json
import time

loops = {
        "USD" : [
            ['USD','BTC','USD'],
            ['USD','LTC','USD'],
            ['USD','ETH','USD'],
            ['USD','BTC','ETH','USD'],
            ['USD','BTC','LTC','USD'],
            ['USD','ETH','BTC','USD'],
            ['USD','LTC','BTC','USD'],
            ['USD','LTC','BTC','ETH','USD'],
            ['USD','ETH','BTC','LTC','USD'],
            ],
        "BTC" : [
            ['BTC','USD','BTC'],
            ['BTC','LTC','BTC'],
            ['BTC','ETH','BTC'],
            ['BTC','ETH','USD','BTC'],
            ['BTC','LTC','USD','BTC'],
            ['BTC','USD','ETH','BTC'],
            ['BTC','USD','LTC','BTC'],
            ['BTC','LTC','USD','ETH','BTC'],
            ['BTC','ETH','USD','LTC','BTC'],
            ],
        "ETH" : [
            ['ETH','USD','ETH'],
            ['ETH','BTC','ETH'],
            ['ETH','USD','BTC','ETH'],
            ['ETH','BTC','USD','ETH'],
            ['ETH','USD','LTC','BTC','ETH'],
            ['ETH','BTC','LTC','USD','ETH'],
            ],
        "LTC" : [
            ['LTC','USD','LTC'],
            ['LTC','BTC','LTC'],
            ['LTC','USD','BTC','LTC'],
            ['LTC','BTC','USD','LTC'],
            ['LTC','USD','ETH','BTC','LTC'],
            ['LTC','BTC','ETH','USD','LTC'],
            ]
        }


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

def trade_stats(base_currency, base_number, next_currency, wsClient, volume_map): # TODO: add outstanding volume at bid/ask price for time calculation
    trade = '{}-{}'.format(base_currency, next_currency)
    trade_arbitrage = 1
    trade_time = 0
    if trade not in wsClient.products:
        trade = '{}-{}'.format(next_currency, base_currency)
        price, existing_number = wsClient.get_bid(trade)
        # print("Buy: {}, price: {}, existing_amount: {}".format(trade, price, existing_number))
        next_number = (base_number / price)//coin_increments[next_currency] * coin_increments[next_currency]
        trade_arbitrage /= price
        trade_time = (next_number + existing_number) / volume_map[trade]
        if trade_time == 0:
            print("Case 1")
            print("Trade: {}, price: {}, base_number: {}, next_number: {}, time: {}".format(trade, price, base_number, next_number, trade_time))
    else:
        price, existing_number = wsClient.get_ask(trade)
        # print("Sell: {}, price: {}, existing_amount: {}".format(trade, price, existing_number))
        next_number = (base_number * price)//coin_increments[base_currency] * coin_increments[base_currency]
        trade_arbitrage *= price
        trade_time = (base_number + existing_number) / volume_map[trade]
        if trade_time == 0:
            print("Case 2")
            print("Trade: {}, price: {}, base_number: {}, next_number: {}, time: {}".format(trade, price, base_number, next_number, trade_time))

    return trade_arbitrage, trade_time, next_number, price

def loop_profit(loop, base_number, wsClient, volume_map):
    # loop.append(loop[0])
    loop_arbitrage = 1.0
    loop_time = 0.0
    intermediate_number = base_number
    # print("Loop: {}, Volume: {}".format(loop, base_number))
    price = None
    for base_currency, next_currency in pairwise(loop):
        trade_arbitrage, trade_time, trade_number, trade_price = trade_stats(base_currency, intermediate_number, next_currency, wsClient, volume_map)
        if not price:
            price = trade_price
        loop_arbitrage *= trade_arbitrage
        loop_time += trade_time
        intermediate_number = trade_number
    trade_value = (loop_arbitrage - 1) / loop_time
    print("loop: {}, loop_arbitrage: {}, time: {} -> value: {}".format(loop, loop_arbitrage, loop_time, trade_value * 1e6))
    return trade_value, price

def make_volume_map(products, public_client):
    volume_map = {}
    for product in products:
        volume = float(public_client.get_product_24hr_stats(product)['volume'])
        rate = volume / 24 / 3600
        volume_map[product] = rate
    return volume_map

def next_move(starting_with, number, wsClient, volume_map, product_list):
    def f(path):
        return loop_profit(path, number, wsClient, volume_map)
    # all_paths = list(SimpleNodeVisitor([starting_with]))[1:] # Is there a better way to avoid the loop of lenth 1?
    all_paths = loops[starting_with]
    # print("All paths: {}".format(all_paths))
    profit, path = max(zip(map(f, all_paths), all_paths), key=lambda x: x[0][0])
    if profit[0] > 0:
        return path[1], profit[0], profit[1]
    else:
        return None, None, None

def make_trade(base_coin, number, next_coin, price, wsClient, auth_client = None):
    # "FYI, you will never be charged a fee if you use the post_only option with limit orders" (I found this quote on gdax discussion)
    trade = '{}-{}'.format(base_coin, next_coin)
    if trade in wsClient.products:
        corrected_number = (number // coin_increments[base_coin]) * coin_increments[base_coin]
        print("Sell {} {} at {}".format(corrected_number, trade, price))
        if auth_client:
            print(auth_client.sell(price=price, size=corrected_number, product_id=trade, post_only=True, time_in_force="GTC")) # Candel order after 1 minute
    else:
        next_number = number / price
        corrected_next_number = (next_number // coin_increments[next_coin]) * coin_increments[next_coin]
        trade = '{}-{}'.format(next_coin, base_coin)
        print("Buy {} {} at {}".format(corrected_next_number, trade, price))
        if auth_client:
            print(auth_client.buy(price=price, size=corrected_next_number, product_id=trade, post_only=True, time_in_force="GTC")) # Cancel order after 1 minute

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

def get_account_value_usd(account_dict, wsClient):
    # account_dict = {'ETH': 1.5, 'BTC': 0.05, 'USD': 1000.0, 'LTC': 3.0, 'BCH': 0.5}
    total = 0.0
    for currency, amount in account_dict.items():
        if currency == "USD":
            total += amount
        elif currency in all_coins:
            currency_pair = '{}-USD'.format(currency)
            price, _ = wsClient.get_ask(currency_pair)
            total += price * amount
    return total

class newWebsocket(gdax.WebsocketClient):
    def on_open(self):
        self.order_book_map = {k:gdax.OrderBook(product_id=k) for k in self.products}
        # self.order_book_btc = gdax.OrderBook(product_id='BTC-USD')
        # self.order_book_eth = gdax.OrderBook(product_id='ETH-USD')

    def on_message(self, msg):
        product_id = msg.get('product_id')
        if product_id in self.products:
            self.order_book_map[product_id].process_message(msg)
            # print("{} message received!".format(product_id))
        else:
            print("Unexpected product in message: {}".format(product_id))
        # self.order_book_btc.process_message(msg)
        # self.order_book_eth.process_message(msg)

    def get_bid(self, product_id):
        if product_id in self.products:
            try:
                order_book = self.order_book_map[product_id]
                price = order_book.get_bid()
                bids = order_book.get_bids(price)
                amount = sum(float(entry['size']) for entry in bids)
                # print("bid price: {}, amount: {}".format(price, amount))
                return float(price), amount
            except:
                print("Couldn't get bid")
                return None
        else:
            print("Unexpected product in message: {}".format(product_id))

    def get_ask(self, product_id):
        if product_id in self.products:
            try:
                order_book = self.order_book_map[product_id]
                price = order_book.get_ask()
                asks = order_book.get_asks(price)
                amount = sum(float(entry['size']) for entry in asks)
                # print("ask price: {}, amount: {}".format(price, amount))
                return float(price), amount
            except:
                print("Couldn't get ask")
                return None
        else:
            print("Unexpected product in message: {}".format(product_id))

def run():

    # auth_client = gdax.AuthenticatedClient(*get_api_credentials())
    public_client = gdax.PublicClient()
    wsClient = newWebsocket(products = ["BTC-USD","ETH-USD","LTC-USD","ETH-BTC","LTC-BTC"])
    wsClient.start()
    # products = public_client.get_products()

    # coin_increments = public_client.get_product_increments() # TODO: this call doesn't exist, but I'd like to do it programmatically

    volume_map = make_volume_map(wsClient.products, public_client)

    time.sleep(10)

    for _ in range(5):
        # account_dict = {account['currency']:float(account['available']) for account in auth_client.get_accounts()}
        account_dict = {'ETH': 1.5, 'BTC': 0.05, 'USD': 1000.0, 'LTC': 3.0, 'BCH': 0.5} # Test
        # account_dict = {'ETH': 0.0, 'BTC': 0.0024, 'USD': 0.0, 'LTC': 0.0, 'BCH': 0.0} # Test
        print("Account: {}".format(account_dict))
        current_account_value = get_account_value_usd(account_dict, wsClient)
        print("Current value: {}".format(current_account_value))

        next_trades = []

        for coin, number in account_dict.items():
            if coin in all_coins and number >= coin_increments[coin]:
                next_step, profit, price = next_move(coin, number, wsClient, volume_map, product_list)
                if next_step:
                    next_trades.append((coin, number, next_step, price))

        for base_coin, number, next_coin, price in next_trades:
            # make_trade(base_coin, number, next_coin, price, wsClient, auth_client)
            make_trade(base_coin, number, next_coin, price, wsClient)

        time.sleep(10)
        # auth_client.cancel_all()
    wsClient.close()

if __name__ == "__main__":
    run()
