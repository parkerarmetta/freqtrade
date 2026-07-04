# Quickstart — running the bot

Fastest safe path: **dry-run** — the bot trades real live prices with fake
money, needs **no API keys**, and you watch it in a web UI (FreqUI). Go live
only after it has dry-run cleanly for days and the strategy backtests well on
your own data.

Two strategies ship in this branch:

| Strategy | Config | Purpose |
|---|---|---|
| `EmaTrendPullback` | `config_dryrun_spot.example.json` | long-only spot baseline to run today |
| `Btc5mMomentumPersistence` | `config_btc5m_momentum.example.json` | 5-minute momentum hypothesis test (futures) |

Both are verified to load and execute in freqtrade's engine (see
"What's been validated" at the bottom).

---

## Option A — Docker (recommended; follows the official quickstart)

This mirrors <https://www.freqtrade.io/en/stable/docker_quickstart/>, using the
`docker-compose.yml` already in this repo (it mounts `./user_data` and exposes
`127.0.0.1:8080`).

```bash
git clone -b claude/btc5m-momentum-strategy https://github.com/parkerarmetta/freqtrade.git
cd freqtrade
docker compose pull

# make your own config from the example
cp user_data/config_dryrun_spot.example.json user_data/config_dryrun_spot.json
```

Now edit `user_data/config_dryrun_spot.json`:

1. **`api_server.listen_ip_address`: change `127.0.0.1` → `0.0.0.0`.** Required
   under Docker (the container must listen on all interfaces; docker still only
   maps the port to your host's localhost). Leave it `127.0.0.1` for native runs.
2. Set `api_server.username` / `password` (used to log into FreqUI).
3. Replace the `jwt_secret_key` and `ws_token` placeholders with random strings
   (jwt must be ≥ 32 chars).

Then point the compose `command` at this config + strategy — edit the
`command:` block near the bottom of `docker-compose.yml`:

```yaml
    command: >
      trade
      --logfile /freqtrade/user_data/logs/freqtrade.log
      --db-url sqlite:////freqtrade/user_data/tradesv3.sqlite
      --config /freqtrade/user_data/config_dryrun_spot.json
      --strategy EmaTrendPullback
```

Launch and open the UI:

```bash
docker compose up -d          # start (restarts automatically)
docker compose logs -f        # watch it work
# browse to http://127.0.0.1:8080
docker compose down           # stop
```

---

## Option B — Native install

```bash
git clone -b claude/btc5m-momentum-strategy https://github.com/parkerarmetta/freqtrade.git
cd freqtrade
./setup.sh -i                 # creates .venv and installs deps (Linux/macOS)
source .venv/bin/activate

cp user_data/config_dryrun_spot.example.json user_data/config_dryrun_spot.json
# (native: leave listen_ip_address as 127.0.0.1; still set username/password/secrets)

freqtrade trade -c user_data/config_dryrun_spot.json --strategy EmaTrendPullback
```

---

## Backtest and tune before trusting anything

```bash
# Download real candles (no API keys needed for historical data)
freqtrade download-data -c user_data/config_dryrun_spot.json \
    --timeframe 15m --timerange 20220101-

# Backtest across a long, multi-regime window
freqtrade backtesting -c user_data/config_dryrun_spot.json \
    --strategy EmaTrendPullback --timerange 20220101-

# Sweep the RSI thresholds (hyperopt)
freqtrade hyperopt -c user_data/config_dryrun_spot.json \
    --strategy EmaTrendPullback --hyperopt-loss SharpeHyperOptLoss \
    --spaces buy sell -e 100
```

For the 5m momentum test, use `config_btc5m_momentum.example.json` and the
`Btc5mMomentumPersistence` strategy — details in `strategies/BTC5M_MOMENTUM.md`.

---

## Go-live checklist (only when all are true)

1. Strategy backtests **positively across multiple years/regimes**, not one lucky
   window, and holds up out-of-sample after hyperopt.
2. It has dry-run for **1–2 weeks** and live behavior matches the backtest
   (trade frequency, win rate).
3. Exchange API keys are **trade-only (no withdrawal permission)**, IP-restricted.
4. In the config: `dry_run: false`, keys set, **small `stake_amount`**, low
   `max_open_trades`. **No leverage** until the above has held for a while.
5. Know the kill switches: `/stopentry` and `/stop` (FreqUI/Telegram), and enable
   freqtrade Protections (`StoplossGuard`, `MaxDrawdown`) — see the docs.

Docs: <https://www.freqtrade.io/en/stable/>

---

## What's been validated (offline, in this branch)

- `freqtrade list-strategies` recognizes **both** strategies (status **OK**,
  hyperoptable).
- Both configs **pass freqtrade's schema validation**.
- Both strategies were **run through freqtrade's real strategy engine**
  (`advise_indicators`/`advise_entry`/`advise_exit`) on generated OHLCV data and
  produced entry/exit signals with no errors; `Btc5mMomentumPersistence` fired
  every entry exactly on its 2-minutes-left signal candle (bucket math correct).
- A full `backtesting` run additionally needs exchange market metadata from
  Binance, which was network-blocked in the build sandbox — it will run on your
  machine, where Binance is reachable.
