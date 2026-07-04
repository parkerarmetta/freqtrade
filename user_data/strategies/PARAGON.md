# ParagonVwapReversion — mechanized S1 (Tier 1 of the Doc strategy)

Encodes the **computable** part of *BTC Trading Strategy Doc v1.1*: the S1
Reversion Fade at a 2SD VWAP extremity, with 0.5%-fixed-risk sizing. It runs on
freqtrade's existing engine — the only custom code is the strategy's decision
logic; VWAP/EMA/ATR come from the bundled indicator libraries.

## What it does

- **Location gate** (Doc §8): only trades at the 2SD VWAP band, never mid-range.
- **Absorption proxy** (Doc §5, S1): enters when a candle pokes *through* the 2SD
  band and closes back *inside* with a rejection wick on above-average volume,
  then fades back toward VWAP (the mean).
- **HTF regime guard**: won't fade a runaway 1h trend (toggle: `use_regime_guard`).
- **Exit**: back to VWAP (Doc §9, "scale out into high-EV levels").

## Honest scope (read this)

This is the **skeleton** of your setup, not your edge. The Doc's real S1 trigger
is an **order-flow read** (delta / OI / book skew) — by its own grading, location
*without* a clear flow read is at best a **B-grade, which is a SKIP**. This bot
has no flow data, so the absorption "trigger" is a price-only proxy. Treat the
backtest as answering *"does the bare location edge even exist?"* — not as a
reproduction of your discretionary results. Real OI/flow reads are Tier 3 (a
separate data pipeline) and bolt on later.

## Sizing & account scaling (Doc §7)

Two separate things:

1. **Compounding (always on):** risk = *current equity* × the risk %, recomputed
   every trade. So dollar size grows automatically as the account grows — $5 risk
   at $1K becomes $125 at $25K, all at a flat 0.5%. This is Doc §7's "same math,
   bigger dollars." No configuration needed.

2. **Risk-% ladder (opt-in, default OFF):** `risk_ladder` steps the risk *percent*
   up at equity milestones. It defaults to a single 0.5% tier — i.e. Doc §7's
   "0.5% fixed until $25K". To scale the percentage, edit `risk_ladder`, e.g.:

   ```python
   risk_ladder = [(0, 0.005), (5_000, 0.010), (10_000, 0.015), (25_000, 0.020)]
   ```

   **Caution — this deviates from your own rulebook.** Doc §7 mandates 0.5% fixed
   until $25K, and Tripwire #1 is "oversizing after a slow week." The ladder is
   deliberately milestone-gated (never streak- or feeling-driven) and off by
   default so nothing escalates by accident. Turn it on only as a deliberate,
   documented decision.

Sizing math (verified): stake = equity × risk% ÷ (leverage × |stoploss|), so a
stop-out loses exactly the risk % of equity regardless of leverage.

## Run it

```bash
cp user_data/config_paragon.example.json user_data/config_paragon.json
# set exchange (a freqtrade-supported perp venue: bybit / okx), api_server secrets

freqtrade download-data -c user_data/config_paragon.json \
    --timeframe 1m 1h --timerange 20240101-      # 1h needed for the HTF guard
freqtrade backtesting -c user_data/config_paragon.json \
    --strategy ParagonVwapReversion --timerange 20240101-
freqtrade hyperopt -c user_data/config_paragon.json \
    --strategy ParagonVwapReversion --hyperopt-loss SharpeHyperOptLoss \
    --spaces buy -e 100
```

## Validated (offline)

`freqtrade list-strategies` loads it (OK, 4 hyperopt params); config passes
schema validation; run through freqtrade's real `populate_*` pipeline on
generated 1m futures data — every long entry poked below the 2SD band (location
gate holds), the regime guard filters as designed, and the 0.5%/ladder sizing
produces an exact loss-at-stop of the intended % of equity. A full `backtesting`
run additionally needs exchange metadata (network-blocked in the build sandbox;
runs on your machine).
