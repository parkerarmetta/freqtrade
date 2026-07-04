# Quickstart — running the bot today

Fastest safe path: **dry-run** — the bot trades real live prices with fake
money, needs **no API keys**, and you watch it in a web UI. Go live only after
it has dry-run cleanly for days and the strategy backtests well on your data.

## Option A: Docker (fastest, no Python setup)

```bash
git clone -b claude/btc5m-momentum-strategy https://github.com/parkerarmetta/freqtrade.git
cd freqtrade

cp user_data/config_dryrun_spot.example.json user_data/config_dryrun_spot.json
# edit user_data/config_dryrun_spot.json: set api_server username/password/secrets

docker compose run --rm freqtrade trade \
    -c /freqtrade/user_data/config_dryrun_spot.json \
    --strategy EmaTrendPullback
```

(Or use the stock `docker-compose.yml` service and set the same args there —
see https://www.freqtrade.io/en/stable/docker_quickstart/.)

Open http://127.0.0.1:8080 → FreqUI shows open trades, profit, charts, logs.

## Option B: Native install

```bash
./setup.sh -i            # creates .venv, installs deps (Linux/macOS)
source .venv/bin/activate

cp user_data/config_dryrun_spot.example.json user_data/config_dryrun_spot.json
freqtrade trade -c user_data/config_dryrun_spot.json --strategy EmaTrendPullback
```

## Backtest before you trust anything

```bash
freqtrade download-data -c user_data/config_dryrun_spot.json \
    --timeframe 15m --timerange 20220101-

freqtrade backtesting -c user_data/config_dryrun_spot.json \
    --strategy EmaTrendPullback --timerange 20220101-

# tune the RSI thresholds
freqtrade hyperopt -c user_data/config_dryrun_spot.json \
    --strategy EmaTrendPullback --hyperopt-loss SharpeHyperOptLoss \
    --spaces buy sell -e 100
```

Also in this branch: `Btc5mMomentumPersistence` (see
`user_data/strategies/BTC5M_MOMENTUM.md`) — a hypothesis test for the 5-minute
momentum idea, run with `user_data/config_btc5m_momentum.example.json`.

## What's what

| File | Purpose |
|---|---|
| `user_data/strategies/EmaTrendPullback.py` | starter strategy: buy RSI pullbacks in an EMA uptrend, long-only spot. A BASELINE to run today, not a validated edge. |
| `user_data/config_dryrun_spot.example.json` | dry-run spot config: BTC/ETH/SOL vs USDT, $100 fake stakes, web UI on :8080 |
| `user_data/strategies/Btc5mMomentumPersistence.py` | 5m momentum-persistence hypothesis test (futures config) |

## Go-live checklist (when — and only when — you're ready)

1. Strategy backtests positively across **multiple years and regimes**, not one
   lucky timerange, and survives hyperopt out-of-sample.
2. It has dry-run for **at least 1–2 weeks** and live behavior roughly matches
   the backtest (trade frequency, win rate).
3. Create exchange API keys with **trade-only permissions (no withdrawals)**,
   IP-restricted.
4. In the config: `dry_run: false`, keys in place, and start with a **small
   `stake_amount`** and low `max_open_trades`. No leverage until everything
   above has been true for a while.
5. Keep the kill switches in mind: `/stopentry` (no new entries) and `/stop`
   via FreqUI/Telegram, and freqtrade's `max_drawdown` /
   `StoplossGuard` protections (see docs → Protections) are worth enabling.

Freqtrade docs: https://www.freqtrade.io/en/stable/
