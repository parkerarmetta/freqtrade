"""Starter strategy: EMA trend filter + RSI pullback entries (long-only spot).

This is a BASELINE to get the bot running today — a simple, widely-understood
shape (buy pullbacks in an uptrend), not a validated edge. Backtest it on your
own data and timerange before trusting it with real money, and expect to
iterate: the value of freqtrade is the workflow (backtest -> hyperopt ->
dry-run -> tiny live), not any single starter strategy.

Logic:
  Trend filter   EMA50 > EMA200 and price above EMA200  (only trade uptrends)
  Entry          RSI dips below `rsi_buy` (pullback within the uptrend)
  Exit           RSI above `rsi_sell` (strength to sell into), or trend break
  Safety         hard stoploss -5%; staged ROI targets

Indicators are pure pandas (no TA-Lib dependency), so this runs on any
freqtrade install, including minimal ones.
"""

from pandas import DataFrame, Series

from freqtrade.strategy import IntParameter, IStrategy


def ema(series: Series, span: int) -> Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: Series, period: int = 14) -> Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = gain / loss.replace(0.0, 1e-12)
    return 100.0 - 100.0 / (1.0 + rs)


class EmaTrendPullback(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "15m"
    can_short = False  # long-only; works on plain spot accounts

    # Staged profit-taking; positions that stall get closed by ROI decay.
    minimal_roi = {
        "0": 0.04,
        "60": 0.025,
        "180": 0.015,
        "360": 0.0,
    }
    stoploss = -0.05
    trailing_stop = False

    process_only_new_candles = True
    startup_candle_count = 210  # needs EMA200 warm-up

    rsi_buy = IntParameter(25, 45, default=38, space="buy")
    rsi_sell = IntParameter(60, 85, default=70, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ema(dataframe["close"], 50)
        dataframe["ema200"] = ema(dataframe["close"], 200)
        dataframe["rsi"] = rsi(dataframe["close"], 14)
        dataframe["uptrend"] = (
            (dataframe["ema50"] > dataframe["ema200"])
            & (dataframe["close"] > dataframe["ema200"])
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["uptrend"]
            & (dataframe["rsi"] < self.rsi_buy.value)
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "uptrend_pullback")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > self.rsi_sell.value)
            | (~dataframe["uptrend"]),
            "exit_long",
        ] = 1
        return dataframe
