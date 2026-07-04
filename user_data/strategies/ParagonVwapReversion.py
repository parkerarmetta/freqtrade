"""Paragon VWAP Reversion (S1) — mechanized Tier-1 slice of the Doc strategy.

This encodes the COMPUTABLE part of "BTC Trading Strategy Doc v1.1": the S1
Reversion Fade at a 2SD VWAP extremity, with a candle-based absorption proxy,
HTF regime context, 0.5%-fixed-risk sizing, and mean-reversion exits.

What is faithful to the Doc:
  * Location gate — trade only at extremities (2SD VWAP band), never in
    no-man's-land (Doc §8).
  * Outside-in reversion as the core mode (Doc §2, ~90% of trades).
  * 0.5% fixed risk per trade, exchange-independent (Doc §7) via
    custom_stake_amount + a defined invalidation distance.
  * Target = the mean/VWAP (Doc §9 "scale out into high-EV levels").

What is a PROXY, not the real thing (be honest about this):
  * "Absorption" here = a candle that poked THROUGH the 2SD band and closed back
    inside with a rejection wick on above-average volume. That approximates
    "failed effort through the extremity" from PRICE ALONE. The Doc's real
    trigger is an order-flow read (delta / OI / book skew) this bot cannot see.
    By the Doc's own grading, location-without-flow is at best a B-grade, which
    is normally a SKIP — so treat this as a measurement tool ("does the location
    edge exist?"), not a reproduction of the discretionary edge.
  * The HTF-trend guard slightly deviates from "EMAs are context only, never
    entry signals" (Doc §2). It exists to avoid fading a runaway trend — the
    risk the missing flow reads would otherwise manage. Toggle it off to be
    strictly faithful.

Not included yet (Tier 3): real OI / order-flow / book-skew reads (need a custom
data pipeline), and the discretionary A+/A/B grading.
"""

from datetime import datetime

import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import BooleanParameter, DecimalParameter, IStrategy, informative


class ParagonVwapReversion(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1m"           # Doc §1: 1-minute execution
    can_short = True           # BTC perps, both directions (Doc is ~90% reversion)

    # Exits are handled by signals (reach VWAP) + the hard invalidation stop.
    # minimal_roi is left effectively off so the mean-reversion logic governs.
    minimal_roi = {"0": 10}
    # Hard invalidation distance beyond the 2SD entry. Also the risk unit the
    # 0.5% sizing is computed against. Hyperopt-tunable.
    stoploss = -0.008
    use_custom_stoploss = False
    trailing_stop = False

    process_only_new_candles = True
    startup_candle_count = 200
    use_exit_signal = True
    exit_profit_only = False

    # --- risk / sizing (Doc §7) ---
    # Base risk fraction. Compounding is automatic: risk is computed off CURRENT
    # equity every trade, so dollar size grows as the account grows at a fixed %.
    risk_per_trade = 0.005     # 0.5% of equity, non-discretionary

    # OPTIONAL equity-milestone risk ladder — steps the risk % up in increments
    # as the account scales. Each tier is (equity_at_or_above, risk_fraction);
    # the highest tier whose threshold is met wins.
    #
    # DEFAULT is a single 0.5% tier == Doc §7's "0.5% fixed until $25K" rule, so
    # nothing escalates unless you deliberately opt in. This is intentional:
    # Doc Tripwire #1 is "oversizing after a slow week", and a ladder is exactly
    # what that guards against. If you do scale, gate it on equity milestones
    # (as here), never on streaks or conviction.
    #
    # Example opt-in ladder (uncomment / edit to use):
    #   risk_ladder = [(0, 0.005), (5_000, 0.010), (10_000, 0.015), (25_000, 0.020)]
    risk_ladder = [(0, 0.005)]

    max_leverage = 5.0

    # --- tunable signal params ---
    band_mult = DecimalParameter(1.8, 2.6, default=2.0, decimals=1, space="buy")
    vol_mult = DecimalParameter(1.0, 2.5, default=1.3, decimals=1, space="buy")
    use_regime_guard = BooleanParameter(default=True, space="buy")
    trend_buffer = DecimalParameter(0.000, 0.010, default=0.004, decimals=3, space="buy")

    # ------------------------------------------------------------------ #
    # HTF context (Doc §2: higher-timeframe context, EMAs as context only)
    # ------------------------------------------------------------------ #
    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    # ------------------------------------------------------------------ #
    # Indicators
    # ------------------------------------------------------------------ #
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe
        tp = (df["high"] + df["low"] + df["close"]) / 3.0

        # Anchored (daily-reset) VWAP with volume-weighted std bands.
        day = df["date"].dt.normalize()
        vol = df["volume"].clip(lower=0.0)
        cum_v = vol.groupby(day).cumsum().replace(0.0, np.nan)
        vwap = (tp * vol).groupby(day).cumsum() / cum_v
        # running volume-weighted variance: E[tp^2] - E[tp]^2
        mean_sq = (tp * tp * vol).groupby(day).cumsum() / cum_v
        var = (mean_sq - vwap * vwap).clip(lower=0.0)
        std = np.sqrt(var)

        df["vwap"] = vwap.ffill()
        df["vwap_std"] = std.ffill().fillna(0.0)
        df["atr"] = ta.ATR(df, timeperiod=14)
        df["vol_sma"] = df["volume"].rolling(20, min_periods=5).mean()
        return df

    # ------------------------------------------------------------------ #
    # Entries — S1 reversion fade at the 2SD extremity
    # ------------------------------------------------------------------ #
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe
        k = self.band_mult.value
        lower = df["vwap"] - k * df["vwap_std"]
        upper = df["vwap"] + k * df["vwap_std"]

        # Absorption proxy: poked THROUGH the band, closed back INSIDE, with a
        # rejection wick, on above-average volume (effort that got absorbed).
        vol_ok = (df["vwap_std"] > 0) & (df["volume"] > self.vol_mult.value * df["vol_sma"])

        lower_wick = df[["close", "open"]].min(axis=1) - df["low"]
        upper_wick = df["high"] - df[["close", "open"]].max(axis=1)

        long_abs = (df["low"] < lower) & (df["close"] > lower) & (lower_wick > upper_wick)
        short_abs = (df["high"] > upper) & (df["close"] < upper) & (upper_wick > lower_wick)

        long_cond = long_abs & vol_ok
        short_cond = short_abs & vol_ok

        if self.use_regime_guard.value:
            buf = self.trend_buffer.value
            ema_htf = df.get("ema50_1h")
            if ema_htf is not None:
                # Don't fade a runaway trend: skip longs in a strong downtrend,
                # skip shorts in a strong uptrend.
                long_cond &= ~(df["close"] < ema_htf * (1 - buf))
                short_cond &= ~(df["close"] > ema_htf * (1 + buf))

        df.loc[long_cond, ["enter_long", "enter_tag"]] = (1, "S1_fade_2sd")
        df.loc[short_cond, ["enter_short", "enter_tag"]] = (1, "S1_fade_2sd")
        return df

    # ------------------------------------------------------------------ #
    # Exits — revert to the mean (VWAP)
    # ------------------------------------------------------------------ #
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe
        df.loc[df["high"] >= df["vwap"], "exit_long"] = 1     # long fade reached the mean
        df.loc[df["low"] <= df["vwap"], "exit_short"] = 1     # short fade reached the mean
        return df

    # ------------------------------------------------------------------ #
    # Risk sizing (Doc §7): risk = equity * 0.5% per trade
    # ------------------------------------------------------------------ #
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                 side: str, **kwargs) -> float:
        return min(self.max_leverage, max_leverage)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: float | None, max_stake: float,
                            leverage: float, entry_tag: str | None, side: str, **kwargs) -> float:
        return self._risk_stake(self.wallets.get_total_stake_amount() if self.wallets else proposed_stake,
                                leverage, min_stake, max_stake, proposed_stake)

    def _risk_for_equity(self, capital: float) -> float:
        """Risk fraction for the current equity, from the milestone ladder.
        Defaults to a flat 0.5% (single tier) = Doc §7."""
        risk = self.risk_per_trade
        for threshold, frac in sorted(self.risk_ladder):
            if capital >= threshold:
                risk = frac
        return risk

    def _risk_stake(self, capital: float, leverage: float, min_stake, max_stake,
                    fallback: float) -> float:
        """Collateral so that hitting the stop loses exactly `risk` of capital.
        loss_at_stop = notional * |stoploss| = stake * leverage * |stoploss|;
        set == capital*risk -> stake = capital*risk/(lev*|stop|)."""
        stop_frac = abs(self.stoploss)
        if capital <= 0 or leverage <= 0 or stop_frac <= 0:
            return fallback
        risk = self._risk_for_equity(capital)
        stake = (capital * risk) / (leverage * stop_frac)
        if max_stake:
            stake = min(stake, max_stake)
        if min_stake:
            stake = max(stake, min_stake)
        return stake


class ParagonVwapReversionSpot(ParagonVwapReversion):
    """Long-only spot variant — for US-legal spot venues (e.g. Kraken) that
    cannot short. Only the LOWER-band fade fires; the short (upper-band) half of
    S1 is dropped. Everything else (location gate, sizing, exits) is inherited.
    Use this on a `trading_mode: spot` config; it fixes freqtrade's rule that a
    can_short strategy cannot run on spot."""

    can_short = False
