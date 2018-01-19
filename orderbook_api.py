#!/usr/bin/env python

import gdax
from itertools import tee
import json
import time
import math
from pathlib import Path

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
    # print("loop: {}, loop_arbitrage: {}, time: {} -> value: {}".format(loop, loop_arbitrage, loop_time, trade_value * 1e6))
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


def get_api_credentials(api_credential_file = str(Path.home())+'/gdax_api_credentials.json', sandbox = False):
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

class newWebsocket(gdax.WebsocketClient):

    myTrades = None

    def on_open(self):
        self.order_book_map = {k:gdax.OrderBook(product_id=k) for k in self.products}

    def on_message(self, msg):
        # {'type': 'done', 'side': 'sell', 'order_id': '7ebcaf46-c0d7-47ea-8c06-cd5221e205c3', 'reason': 'filled', 'product_id': 'BTC-USD', 'price': '14292.49000000', 'remaining_size': '0.00000000', 'sequence': 4823523105, 'time': '2018-01-10T03:39:24.776000Z'}
        product_id = msg.get('product_id')
        if msg.get('type') == 'done' and msg.get('reason') == 'filled':
            newWebsocket.myTrades.pop(msg['order_id'], None)

        if product_id in self.products:
            self.order_book_map[product_id].process_message(msg)
            # print("{} message received!".format(product_id))
        else:
            print("Unexpected product in message: {}".format(product_id))

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

class OrderManager:
    """
    Object that manages past orders so new orders can be compared against existing orders and specific orders can be cancelled

    Notes:
    -----
    "A successful order will be assigned an order id" (from gdax api docs)

    Example Order Responses:
    ------------------------
    {'id': '3cbea448-fdba-40c7-9161-ab97d032d859', 'price': '285.05000000', 'size': '0.14000000', 'product_id': 'LTC-USD', 'side': 'buy', 'stp': 'dc', 'type': 'limit', 'time_in_force': 'GTC', 'post_only': True, 'created_at': '2018-01-07T05:03:19.867218Z', 'fill_fees': '0.0000000000000000', 'filled_size': '0.00000000', 'executed_value': '0.0000000000000000', 'status': 'pending', 'settled': False}
    {'message': 'size required'}
    {'message': 'size too precise (0.038450615867888595)'}
    {'message': 'Insufficient funds'}
    {'message': 'Order size is too small. Minimum size is 0.01'}
    {'message': 'invalid cancel_after (1,0,0)'}
    """

    def __init__(self, wsClient, auth_client = None):
        self.wsClient = wsClient
        self.auth_client = auth_client
        self.outstanding_trades = {}
        newWebsocket.myTrades = self.outstanding_trades
    def get_account_dict(self):
        account_dict = {}
        if self.auth_client:
            account_dict = {account['currency']:float(account['available']) for account in self.auth_client.get_accounts()}
        else:
            account_dict = {'ETH': 1.5, 'BTC': 0.05, 'USD': 1000.0, 'LTC': 3.0, 'BCH': 0.5} # TODO: Make this "test account" param configurable?
        # print("Account: {}".format(account_dict))
        return account_dict

    def get_account_value_usd(self):
        total = 0.0
        # for currency, amount in [*self.get_account_dict().items(), *[(trade['currency'], float(trade['size'])) for trade in self.outstanding_trades.values()]] :
        for currency, amount in self.get_account_dict().items():
            if currency == "USD":
                total += amount
            elif currency in all_coins:
                currency_pair = '{}-USD'.format(currency)
                price, _ = self.wsClient.get_ask(currency_pair)
                total += price * amount
        for outstanding_trade in self.outstanding_trades.values():
            trade = outstanding_trade["trade"]
            size = float(outstanding_trade["size"])
            price = float(outstanding_trade["price"])
            currency = outstanding_trade["currency"]
            if currency == "USD" or trade[4:7] == "USD":
                total += size*price
            else:
                next_currency = trade[4:7]
                currency_pair = '{}-USD'.format(next_currency)
                next_price, _ = self.wsClient.get_ask(currency_pair)
                amount = size*price
                total += next_price * amount
        return total

    def _handle_response(self, response):
        if {'id', 'price', 'size', 'product_id', 'side'} <= set(response):
            trade = response['product_id']
            price = response['price']
            size = response['size']
            side = response['side']
            trade_id = response['id']

            currency = trade[0:3] if side == "sell" else trade[4:7]

            self.outstanding_trades[trade_id] = {'trade': trade, 'size': size, 'price': price, 'currency': currency}
            print(self.outstanding_trades)
        else:
            if 'message' in response:
                print(response['message'])
            else:
                print("unexpected response: {}".format(response))

    def _trade_on_book(self, base_currency, trade, size, price):
        last_trades = [trade for trade in self.outstanding_trades.values() if base_currency == trade['currency']]
        print("trade: {}, size {}, price{}".format(trade,size,price))
        print(last_trades)
        same_trades, same_price, other = [], [], []
        for last_trade in last_trades:
            if last_trade['trade'] == trade and math.isclose(float(last_trade['size']),size) and math.isclose(float(last_trade['price']),price):
                same_trades.append(last_trade)
            elif last_trade['trade'] == trade and math.isclose(float(last_trade['price']),price):
                same_price.append(last_trade)
            else:
                other.append(last_trade)
        return same_trades, same_price, other

    def post_trade(self, base_coin, base_number, next_coin, price):
        # "FYI, you will never be charged a fee if you use the post_only option with limit orders" (I found this quote on gdax discussion)
        trade = '{}-{}'.format(base_coin, next_coin)
        if trade in self.wsClient.products:
            corrected_number = (base_number // coin_increments[base_coin]) * coin_increments[base_coin]
            if corrected_number == 0.0:
                return
            print("Sell {0:.6f} {1} at {2}".format(corrected_number, trade, price))

            if self.auth_client:
                same_trades, same_price, other = self._trade_on_book(base_coin, trade, corrected_number, price)
                if not any((same_trades, same_price, other)):
                    print("No trade already on books")
                if other:
                    for outstanding_trade in other:
                        print("### outstanding trade: {}".format(outstanding_trade))
                        for trade_id, trade_vals in self.outstanding_trades.items():
                            if trade_vals == outstanding_trade:
                                self.cancel_trade(trade_id)
                        print("Canceling previous order {}".format(trade_id))
                if same_trades:
                    print("Trade already on books")
                    return
                if same_price:
                    print("Add another order at this price")
                post_response = self.auth_client.sell(price=price, size="{0:.6f}".format(corrected_number), product_id=trade, post_only=True, time_in_force="GTC") # TODO: Make cancel behavior param configurable
                # print(post_response)
                self._handle_response(post_response)
        else:
            next_number = base_number / price
            corrected_next_number = (next_number // coin_increments[next_coin]) * coin_increments[next_coin]
            if corrected_next_number == 0.0:
                return
            trade = '{}-{}'.format(next_coin, base_coin)
            print("Buy {0:0.6f} {1} at {2}".format(corrected_next_number, trade, price))

            if self.auth_client:
                prev_trade = self._trade_on_book(base_coin, trade, corrected_next_number, price)
                if  prev_trade == "No trade":
                    print("No trade already on books")
                if  prev_trade == "Same trade":
                    print("Trade already on books")
                if prev_trade == "Different trade":
                    currency = trade[4:7]
                    trade_id = self.outstanding_trades[currency]['trade_id']
                    self.cancel_trade(trade_id)
                    print("Canceling previous order")
                post_response = self.auth_client.buy(price=price, size="{0:.6f}".format(corrected_next_number), product_id=trade, post_only=True, time_in_force="GTC") # TODO: Make cancel behavior param configurable
                print(post_response)
                self._handle_response(post_response)

    def cancel_trade(self, trade_id):
        resp = self.auth_client.cancel_order(trade_id)
        print(resp)

    def cancel_all_trades(self):
        print("Cancelling all trades!")
        if self.auth_client:
            self.auth_client.cancel_all()

def run():

    try:
        # auth_client = gdax.AuthenticatedClient(*get_api_credentials())
        auth_client = None
        public_client = gdax.PublicClient()
        wsClient = newWebsocket(products = ["BTC-USD","ETH-USD","LTC-USD","ETH-BTC","LTC-BTC"])
        wsClient.start()
        order_manager = OrderManager(wsClient, auth_client)

        # coin_increments = public_client.get_product_increments() # TODO: this call doesn't exist, but I'd like to do it programmatically

        volume_map = make_volume_map(wsClient.products, public_client)

        time.sleep(10)

        for _ in range(10000):
            current_account_value = order_manager.get_account_value_usd()
            print("Current value: {}".format(current_account_value))

            next_trades = []

            # Find trades for current available currency
            for coin, number in order_manager.get_account_dict().items():
                if coin in all_coins and number >= coin_increments[coin]:
                    next_step, profit, price = next_move(coin, number, wsClient, volume_map, product_list)
                    if next_step:
                        next_trades.append((coin, number, next_step, price))

            # Evaluate existing trades for better options
            for trade_id, trade_vals in order_manager.outstanding_trades.items():
                # {'trade': trade, 'size': size, 'price': price, 'currency': currency}
                currency = trade_vals['currency']
                volume = trade_vals['size'] if trade_vals['trade'][0:4] == currency else float(trade_vals['size'])*float(trade_vals['price'])
                next_step, profit, price = next_move(currency, volume, wsClient, volume_map, product_list)
                if next_step:
                    next_trades.append((currency, volume, next_step, price))

            for base_coin, number, next_coin, price in next_trades:
                order_manager.post_trade(base_coin, number, next_coin, price)

            time.sleep(0.1)
            print("")
    finally:
        order_manager.cancel_all_trades()
        wsClient.close()

if __name__ == "__main__":
    run()
