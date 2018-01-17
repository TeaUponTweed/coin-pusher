## TODO
<!-- * M/E - Not attempting orders that are not possbile  -->
* Dont evaluate loops that are invalid due to volume
* M/M - Take into account outstanding trades when calculating account value
    * re-evaluate loops with outstanding trades
* L/E - implement logging system
* M/E - don't attempt to post duplicate trades
* M/M - don't cancel other trades at same price
* M/H - monitor when trades are completed
    * get a user specific websocket
* L/E - clean up user output
* L/H - Make nice UI
* M/M - float vs decimal formatting (round vs truncation)
* L/H - better velocity calculator
* L/M - create arbitrage object
* L/E - start using params file
* L/E - calculate loops programatically
