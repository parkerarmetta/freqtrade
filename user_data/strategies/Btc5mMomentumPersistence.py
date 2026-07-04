"""BTC 5-minute momentum-persistence test strategy.

Purpose: answer ONE empirical question — do BTC moves inside a 5-minute window
tend to EXTEND to the window's close? This is the load-bearing hypothesis of a
Polymarket "BTC 5m Up/Down" momentum strategy (buy the side BTC already moved
toward, ~2 minutes before the window closes). If the hypothesis fails on years
of spot data, that strategy has no edge to harvest.

Mapping of the Polymarket bet onto spot candles (1m timeframe; a "window" is a
5-minute bucket aligned to :00/:05/...):

  minute 1-3   measure the move: close(3rd candle) vs open(1st candle)
  minute 4     if |move| >= move_min_pct, enter in the move's direction
               (signal fires on the 3rd candle; freqtrade enters at the open of
               the next candle — exactly "2 minutes left")
  bucket end   exit (signal on the 5th candle -> exit at the next candle open,
               which is the bucket close)

So each trade holds ~120 seconds and wins iff the move persisted — the same
payoff shape as the Polymarket bet, minus the binary-market pricing.

Usage notes:
  * Symmetric test (up AND down moves) needs shorts -> run with
    `trading_mode: futures`, pair BTC/USDT:USDT (see
    user_data/config_btc5m_momentum.example.json). On spot, set can_short=False
    for a long-only (up-moves) test.
  * The threshold is a PERCENTAGE (default 0.11% ~= $70 on $65k BTC) so results
    are comparable across years of very different BTC price levels.
  * Read the results as a hypothesis test, not a production strategy: what
    matters is whether avg profit per trade is positive BEFORE fees and by how
    much, vs the fee/spread hurdle of wherever you would actually trade it.
"""

from datetime import datetime, timezone
from typing import Optional

from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import DecimalParameter, IStrategy


BUCKET_SEC = 300  # 5-minute windows, aligned like Polymarket's btc-updown-5m


class Btc5mMomentumPersistence(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1m"
    can_short = True  # requires trading_mode: futures; set False for spot

    # The bet is "window closes in the move's direction" — no profit target or
    # stop inside the window; the time-based exit is the resolution.
    minimal_roi = {"0": 100}
    stoploss = -0.99
    trailing_stop = False

    # Enter/exit with momentum near the close -> market orders.
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    process_only_new_candles = True
    startup_candle_count = 10

    # Minimum move over the first 3 minutes to call it an impulse.
    # 0.0011 ~= the $70-on-$65k rule of the original strategy. Hyperopt space
    # spans "almost any move" to "rare large impulse".
    move_min_pct = DecimalParameter(0.0003, 0.0050, default=0.0011, decimals=4, space="buy")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Seconds into the wall-clock-aligned 5m bucket (:00/:05/...). Computed
        # from minute/second fields, NOT epoch-int casts — datetime .astype
        # ("int64") is resolution-dependent (ns in pandas 2.x, us in 3.x).
        sec_into = (dataframe["date"].dt.minute % 5) * 60 + dataframe["date"].dt.second
        dataframe["sec_into_bucket"] = sec_into
        # Open of the current 5m bucket = open of its first 1m candle.
        dataframe["bucket_open"] = (
            dataframe["open"].where(sec_into == 0).ffill()
        )
        dataframe["move_pct"] = (dataframe["close"] - dataframe["bucket_open"]) / dataframe[
            "bucket_open"
        ]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Signal on the 3rd candle of the bucket (open +120s, closes +180s);
        # the fill lands on the next candle open — 2 minutes before bucket end.
        at_signal_minute = dataframe["sec_into_bucket"] == 120
        threshold = self.move_min_pct.value

        dataframe.loc[
            at_signal_minute & (dataframe["move_pct"] >= threshold),
            ["enter_long", "enter_tag"],
        ] = (1, "impulse_up")
        dataframe.loc[
            at_signal_minute & (dataframe["move_pct"] <= -threshold),
            ["enter_short", "enter_tag"],
        ] = (1, "impulse_down")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Signal on the bucket's last candle (open +240s) -> exit fills at the
        # next candle open, i.e. exactly the bucket close.
        at_last_minute = dataframe["sec_into_bucket"] == 240
        dataframe.loc[at_last_minute, "exit_long"] = 1
        dataframe.loc[at_last_minute, "exit_short"] = 1
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        # Safety net: if the bucket-end exit signal was missed (data gap), do
        # not let a 2-minute bet ride into the next window.
        open_utc = trade.open_date_utc.replace(tzinfo=timezone.utc)
        held_sec = (current_time - open_utc).total_seconds()
        if held_sec > 180:
            return "bucket_end_failsafe"
        return None
