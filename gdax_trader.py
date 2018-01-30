#!/usr/bin/env python

import json
import os
import time
# import collections
from typing import List, Dict, NamedTuple, Callable, Optional, Tuple, Iterable
from pathlib import Path
from order_book import OfflineOrderBook

import gdax
from gdax.public_client import PublicClient

TradeID = str
Ticker = str
Currency = str
Side = str
Amount = float
Price = float
Time = str
Credential = str
File = str
Sequence = int


class Trade(NamedTuple):
    trade_id: TradeID
    ticker: Ticker
    held_currency: Currency
    amount: Amount
    price: Price
    time: Time
    sequence: Sequence


class TradeCurrencies(NamedTuple):
    base_currency: Currency
    quote_currency: Currency


class APICredentials(NamedTuple):
    key: Credential
    b64secret: Credential
    passphrase: Credential


class CurrencyDelta(NamedTuple):
    currency: Currency
    amount: Amount


def get_next_currency(trade: Trade) -> Currency:
    return trade.ticker.replace(trade.held_currency, '').replace('-', '')


def get_trade_result(trade: Trade, amount_remaining: float) -> Tuple[CurrencyDelta, CurrencyDelta]:
    trade_side = get_trade_side(trade)
    held_delta = trade.amount - amount_remaining
    next_delta = held_delta * trade.price
    if trade_side == 'buy':
        held_delta, next_delta = next_delta, held_delta

    return (CurrencyDelta(trade.held_currency, held_delta),
            CurrencyDelta(get_next_currency(trade), next_delta))


class Trades(object):
    def __init__(self, trades: Optional[Dict[TradeID, Trade]]=None):
        self.trades = trades or {}

    def add(self, trade: Trade):
        assert trade.trade_id not in self.trades
        self.trades[trade.trade_id] = trade

    def replace(self, trade: Trade):
        old_trade = self.trades[trade.trade_id]
        assert old_trade.sequence < trade.sequence
        self.trades[trade.trade_id] = trade

    def get(self, trade_id: TradeID) -> Trade:
        return self.trades[trade_id]

    def remove(self, trade_id: TradeID):
        return self.trades.pop(trade_id)

    def __iter__(self) -> Iterable[Trade]:
        yield from self.trades.values()


Wallet = Dict[Currency, Amount]


def get_currencies_from_ticker(ticker: Ticker) -> TradeCurrencies:
    base_currency = ticker[0:3]
    quote_currency = ticker[4:7]
    return TradeCurrencies(base_currency, quote_currency)


def get_held_currency_from_side(ticker: Ticker, side: Side) -> Currency:
    return ticker[0:3] if side == 'sell' else ticker[4:7]


def get_trade_side(trade: Trade) -> Side:
    return 'sell' if trade.held_currency == trade.ticker[0:3] else 'buy' 


def make_ticker(quote_currency: Currency, base_currency: Currency) -> Ticker:
    return quote_currency + '-' + base_currency


def get_api_credentials(api_credential_file: File = os.path.join(str(Path.home()), 'gdax_api_credentials.json'),
                        sandbox: bool = False) -> APICredentials:
    with open(api_credential_file) as api_json:
        api_dict = json.load(api_json)

    exchange = api_dict['sandbox'] if sandbox else api_dict['official']

    return APICredentials(exchange['key'], exchange['b64secret'], exchange['passphrase'])


class GdaxAccount:

    def __init__(self, credentials: APICredentials) -> None:
        self.auth_client = gdax.AuthenticatedClient(*credentials) if credentials else None
        self.websocket_manager = WebsocketManager(products=["BTC-USD", "ETH-USD", "LTC-USD", "ETH-BTC", "LTC-BTC"])
        self.websocket_manager.start()
        self.wallet = self._initialize_wallet()

        self._initialize_trades()

    def _initialize_wallet(self) -> Wallet:
        """
        Return amount available of each currency in wallet
        """
        wallet = {}
        if self.auth_client:
            account_list = self.auth_client.get_accounts()
            # Add handler for api call failure
            for account in account_list:
                currency = account['currency']
                wallet[currency] = float(account['available'])
        return wallet  # could add a default 'test' wallet when no auth_client in available

    def _add_trade(self, order: Dict) -> None:
        """
        Constructs a Trade object from order and adds it to self.trades
        """
        trade_id = order['id']
        ticker = Ticker(order['product_id'])
        side = order['side']
        held_currency = get_held_currency_from_side(ticker, side)
        amount = Amount(order['size'])
        price = Price(order['price'])
        order_time = Time(order['created_at'])
        self.trades.add(Trade(trade_id, ticker, held_currency, amount, price, order_time, -1))

    def _process_trade_msg(self, msg: Dict) -> None:
        """
        processes GDAX msg and alters the internal trade object and wallet to match
        """
        trade_id = TradeID(msg['trade_id'])
        try:
            trade = self.trades.get(trade_id)
        except KeyError:
            pass
        else:
            if msg['type'] == 'done':
                self.trades.remove(trade_id)
                (held_currency, held_delta), (next_currency, next_delta) = get_trade_result(trade, 0.0)
                # treat cancelled orders like a successful trade back to held currency
                if msg['reason'] == 'cancelled':
                    next_currency, next_delta = held_currency, held_delta

            elif msg['type'] == 'match':
                (held_currency, held_delta), (next_currency, next_delta) = get_trade_result(trade, 0.0)
                self.trades.trades[trade_id].amount -= held_currency

            elif msg['type'] == 'open':
                remaining_size = float(msg['remaining_size'])
                _, (next_currency, next_delta) = get_trade_result(
                    trade, remaining_size)
                # update internal trade with new size
                self.trades.trades[trade_id].amount = remaining_size
            else:
                return
            # add currency to wallet
            self.wallet[next_currency] += next_delta

    def _initialize_trades(self) -> None:
        """
        Initialize trades list with outstanding GDAX trades
        """
        self.trades = Trades()
        if self.auth_client:
            order_list = self.auth_client.get_orders()
            # Add handler for api call failure
            for order in order_list:
                if order:
                    self._add_trade(order)

    def make_trade(self, trade: Trade) -> None:
        """
        Attempts to post trade to GDAX
        """
        if get_trade_side(trade) == 'sell':
            post_response = self.auth_client.sell(price=trade.price, size=trade.amount, product_id=trade.ticker,
                                                  post_only=True, time_in_force='GTC')
        else:
            post_response = self.auth_client.buy(price=trade.price, size=trade.amount, product_id=trade.ticker,
                                                 post_only=True, time_in_force='GTC')
        self._handle_trade_response(post_response)

    def _handle_trade_response(self, response_msg: Dict) -> None:
        """
        Handles GDAX response to posted trade
        If trade was accepted on GDAX, add to current outstanding trades
        """
        if 'received' in response_msg:
            self._add_trade(response_msg)
        else:
            print('Unable to make trade')
            if 'message' in response_msg:
                print(response_msg['message'])
            else:
                print("unexpected response: {}".format(response_msg))

    def _get_currency_value_in_usd(self, currency: Currency, amount: float) -> float:
        if currency == 'USD':
            return amount
        else:
            ticker = make_ticker(currency, 'USD')
            if ticker in self.websocket_manager.products:
                price, _ = self.websocket_manager.get_ask(ticker)
                return price * amount
            return 0

    def _get_trade_value_in_usd(self, trade: Trade) -> float:
        ticker = trade.ticker
        amount = trade.amount
        price = trade.price
        if 'USD' in get_currencies_from_ticker(ticker):
            return amount*price
        else:
            _, value_currency = get_currencies_from_ticker(ticker)
            value_ticker = make_ticker(value_currency, 'USD')
            value_price, _ = self.websocket_manager.get_ask(value_ticker)
            value_amount = amount*price
            return value_price * value_amount

    def get_account_value(self) -> float:
        total = 0.0
        for currency, amount in self.wallet.items():
            total += self._get_currency_value_in_usd(currency, amount)
        for trade in self.trades:
            total += self._get_trade_value_in_usd(trade)
        return total

    def cancel_all_trades(self) -> None:
        self.auth_client.cancel_all()


class WebsocketManager(gdax.WebsocketClient):
    """
    Maintains order books for a list of tickers
    can pass msgs up through msg_handler
    """
    def __init__(self, products: List[Ticker],
                 msg_handler: Optional[Callable[[Dict], None]] = None) -> None:
        gdax.WebsocketClient.__init__(self, products=products)
        self.msg_handler = msg_handler
        self.order_book_map = {}

    def on_open(self) -> None:
        """
        Initializes map of order books
        """
        # TODO test offline order book
        for product in self.products:
            client = PublicClient()
            ob = OfflineOrderBook(client=client, product_id=product)
            ob.reset_book()
            self.order_book_map[product] = ob

    def on_message(self, msg: Dict) -> None:
        """
        Does two things:
        1. Updates internal order book for product ID
        2. Passes msg to msg_handler
        """
        product_id = msg.get('product_id')
        if product_id in self.products:
            self.order_book_map[product_id].process_message(msg)
        else:
            print("Unexpected product in message: {}".format(product_id))

        if self.msg_handler is not None:
            self.msg_handler(msg)

    def _get_spread(self, product_id: Ticker, do_get_bid: bool) -> Tuple[float, float]:
        """
        Get current bid/ask price, and quantity of currency on the books at that price
            from order book associated with product ID
        """
        try:
            order_book = self.order_book_map[product_id]
        except KeyError:
            raise ValueError('Unknown product {}'.format(product_id))
        else:
            if do_get_bid:
                price = order_book.get_bid()
                bids = order_book.get_bids(price)
                amount = sum(float(entry['size']) for entry in bids)
            else:
                price = order_book.get_ask()
                asks = order_book.get_asks(price)
                amount = sum(float(entry['size']) for entry in asks)
            return float(price), amount

    def get_bid(self, product_id: Ticker) -> Tuple[float, float]:
        return self._get_spread(product_id, True)

    def get_ask(self, product_id: Ticker) -> Tuple[float, float]:
        return self._get_spread(product_id, False)


class Trader:

    def __init__(self) -> None:
        self.gdax_account = GdaxAccount(get_api_credentials())

    def get_next_trade(self) -> Trade:
        pass

    def execute_trade(self, trade: Trade) -> None:
        self.gdax_account.make_trade(trade)

    def shutdown_trader(self) -> None:
        self.gdax_account.cancel_all_trades()

    def log_account_value(self) -> None:
        print('Account value: {}'.format(self.gdax_account.get_account_value())) 


def run():
    trader = Trader()
    for _ in range(100):
        print('STEP')
        trader.log_account_value()
        next_trade = trader.get_next_trade()
        if next_trade is not None:
            trader.execute_trade(next_trade)
        else:
            print('No next trade')
            time.sleep(1)

    trader.shutdown_trader()
    trader.log_account_value()


if __name__ == '__main__':
    run()
