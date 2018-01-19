#!/usr/bin/env python

import json
# import collections
from typing import List, Dict, NamedTuple
from pathlib import Path

import gdax

TradeID = str
Ticker = str
Currency = str
Side = str
Amount = float
Price = float
Time = str
Credential = str
File = str


class Trade(NamedTuple):
    trade_id: TradeID
    ticker: Ticker
    held_currency: Currency
    amount: Amount
    price: Price
    time: Time


class TradeCurrencies(NamedTuple):
    base_currency: Currency
    quote_currency: Currency


class APICredentials(NamedTuple):
    key: Credential
    b64secret: Credential
    passphrase: Credential


Trades = List[Trade]
Wallet = Dict[Currency, Amount]


def get_currencies_from_ticker(ticker: Ticker) -> TradeCurrencies:
    base_currency = ticker[0:3]
    quote_currency = ticker[4:7]
    return TradeCurrencies(base_currency, quote_currency)


def get_held_currency_from_side(ticker: Ticker, side: Side) -> Currency:
    return ticker[0:3] if side == 'sell' else ticker[4:7]


def get_trade_side(trade: Trade) -> Side:
    return 'sell' if trade.held_currency == trade.ticker[0:3] else 'buy' 


def make_ticker(quote_currency: Currency, base_currency: Currency):
    return quote_currency + '-' + base_currency


def get_api_credentials(api_credential_file: File = str(Path.home())+'/gdax_api_credentials.json',
                        sandbox: bool = False) -> APICredentials:
    with open(api_credential_file) as api_json:
        api_dict = json.load(api_json)

    exchange = api_dict['sandbox'] if sandbox else api_dict['official']

    return APICredentials(exchange['key'], exchange['b64secret'], exchange['passphrase'])


class GdaxAccount:

    def __init__(self, credentials: APICredentials) -> None:
        self.auth_client = gdax.AuthenticatedClient(*credentials) if credentials else None
        self.wallet = self._initialize_wallet()
        self.trades = self._initialize_trades()

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
                wallet[currency] = account['available']
        return wallet  # could add a default 'test' wallet when no auth_client in available

    def _initialize_trades(self) -> Trades:
        """
        Return outstanding trades on account
        """
        outstanding_trades = list()
        if self.auth_client:
            order_list = self.auth_client.get_orders()
            # Add handler for api call failure
            for order in order_list:
                trade_id = order['id']
                ticker = order['product_id']
                side = order['side']
                held_currency = get_held_currency_from_side(ticker, side)
                amount = order['size']
                price = order['price']
                time = order['created_at']
                outstanding_trades.append(Trade(trade_id, ticker, held_currency, amount, price, time))
        return outstanding_trades

    def make_trade(self, trade: Trade) -> None:
        if get_trade_side(trade) == 'sell':
            post_response = self.auth_client.sell(price=trade.price, size=trade.amount, product_id=trade.ticker,
                                                  post_only=True, time_in_force='GTC')
        else:
            post_response = self.auth_client.buy(price=trade.price, size=trade.amount, product_id=trade.ticker,
                                                 post_only=True, time_in_force='GTC')

    def _get_currency_value_in_usd(self, currency: Currency, amount: float) -> float:
        if currency == 'USD':
            return amount
        else:
            ticker = make_ticker(currency, 'USD')
            price, _ = self.wsClient.get_ask(ticker)
            return price * amount

    def _get_trade_value_in_usd(self, trade: Trade) -> float:
        ticker = trade.ticker
        amount = trade.amount
        price = trade.price
        if 'USD' in get_currencies_from_ticker(ticker):
            return amount*price
        else:
            _, value_currency = get_currencies_from_ticker(ticker)
            value_ticker = make_ticker(value_currency, 'USD')
            value_price, _ = self.wsClient.get_ask(value_ticker)
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
        trader.log_account_value()
        next_trade = trader.get_next_trade()
        trader.execute_trade(next_trade)

    trader.shutdown_trader()
    trader.log_account_value()


if __name__ == '__main__':
    run()
