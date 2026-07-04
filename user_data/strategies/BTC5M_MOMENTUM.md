# BTC 5m momentum-persistence test

`Btc5mMomentumPersistence.py` is a **hypothesis test**, not a production
strategy. It asks: *do BTC moves inside a 5-minute window tend to extend to the
window's close?* That persistence is the entire edge assumed by a Polymarket
"BTC 5m Up/Down" momentum strategy (enter with the move ~2 minutes before
close). Run this over years of 1-minute Binance data before risking anything on
the prediction-market version.

## The mapped bet

| Polymarket bet | This strategy |
|---|---|
| Watch BTC for the first ~3 min of the 5m window | measure `close(min 3) - open(min 1)` |
| Enter with the move at ~2 min left if it moved "enough" | enter long/short at min-4 open when |move| ≥ `move_min_pct` |
| Market resolves at window close | exit at the bucket-end candle open (~120 s hold) |

Default `move_min_pct` = 0.11% (≈ the original "$70 on $65k BTC" rule),
hyperopt-able from 0.03% to 0.50%.

## Run it

```bash
# 1) Get data (no API keys needed for downloads)
freqtrade download-data -c user_data/config_btc5m_momentum.example.json \
    --timeframe 1m --timerange 20230101-

# 2) Backtest
freqtrade backtesting -c user_data/config_btc5m_momentum.example.json \
    --strategy Btc5mMomentumPersistence --timerange 20230101-

# 3) Sweep the impulse threshold
freqtrade hyperopt -c user_data/config_btc5m_momentum.example.json \
    --strategy Btc5mMomentumPersistence --hyperopt-loss SharpeHyperOptLoss \
    --spaces buy -e 60
```

The example config uses `trading_mode: futures` (pair `BTC/USDT:USDT`) so both
up- and down-impulses are tested symmetrically. For a spot-only, long-only test
set `can_short = False` in the strategy and switch the config to spot with pair
`BTC/USDT`.

## Reading the result

- The number that matters is **avg profit per trade vs your real cost hurdle**,
  and whether it is stable across years/regimes (run separate `--timerange`
  slices; don't trust one aggregate).
- Trade counts will be large (many windows qualify) — good: significance comes
  cheap here.
- **If persistence ≈ 0 or negative**: the Polymarket momentum strategy has no
  underlying edge; its fees/spread make it strictly worse. Stop there.
- **If persistence is real**: it still has to clear the *Polymarket* cost
  structure (crossing a 1–2¢ spread on ~70¢ binary shares). Validate that
  second step with the companion toolkit in
  `personal-os/btc-5m-polymarket/` (`fetch` real markets → `backtest`), which
  models the binary-market pricing this spot test deliberately leaves out.
- Freqtrade's backtest fills at candle opens with market orders and ignores
  intra-minute latency; treat a marginal positive result (< ~2× fees) as noise.
