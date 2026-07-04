# Desktop setup (US / Kraken) — dry-run checklist

Get the bot running on your desktop with **fake money** (dry-run) — no API keys,
no risk. Uses **Docker** (identical on Mac/Windows/Linux) and **Kraken** (US-legal,
freqtrade-supported; Binance blocks US IPs so we don't use it).

## 1. Install prerequisites
- **Docker Desktop** (Mac/Windows) or Docker Engine + compose plugin (Linux):
  https://docs.docker.com/get-docker/ — on **Windows, reboot after installing**.
- **git**. Verify everything:
  ```bash
  docker --version && docker compose version && git --version
  ```
  (No git? Download the branch as a ZIP from GitHub instead of cloning.)

## 2. Get the bot
```bash
git clone -b claude/btc5m-momentum-strategy https://github.com/parkerarmetta/freqtrade.git
cd freqtrade
docker compose pull
```

## 3. Make your config (Kraken)
```bash
cp user_data/config_dryrun_kraken.example.json user_data/config_dryrun_kraken.json
```
Edit `user_data/config_dryrun_kraken.json` → in the `api_server` block change **4**
things:
1. `"listen_ip_address"`: `127.0.0.1` → **`"0.0.0.0"`** (required for Docker)
2. `"username"`: anything (e.g. `"parker"`)
3. `"password"`: a real password (you log into the UI with it)
4. `"jwt_secret_key"` (**32+ chars**) and `"ws_token"`: random strings
   (`python -c "import secrets; print(secrets.token_urlsafe(32))"` if you have Python)

Leave `"dry_run": true`.

## 4. Point Docker at your config + strategy
In `docker-compose.yml`, edit the `command:` block:
```yaml
    command: >
      trade
      --logfile /freqtrade/user_data/logs/freqtrade.log
      --db-url sqlite:////freqtrade/user_data/tradesv3.sqlite
      --config /freqtrade/user_data/config_dryrun_kraken.json
      --strategy EmaTrendPullback
```
Start with `EmaTrendPullback` just to confirm the plumbing. (See the strategy note
at the bottom before switching to `ParagonVwapReversion`.)

## 5. Launch + watch
```bash
docker compose up -d
docker compose logs -f      # Ctrl-C stops watching, not the bot
```
Look for config validation, pairs loading, "Bot started", no errors.

## 6. Open the dashboard
http://127.0.0.1:8080 → log in with your username/password → FreqUI (trades,
$1,000 dry-run wallet, charts). Same URL works from your phone on the same wifi.

Stop later with: `docker compose down`.

## 7. Backtest (the step that actually matters)
```bash
docker compose run --rm freqtrade download-data \
  --config /freqtrade/user_data/config_dryrun_kraken.json --timeframe 15m --timerange 20220101-
docker compose run --rm freqtrade backtesting \
  --config /freqtrade/user_data/config_dryrun_kraken.json --strategy EmaTrendPullback --timerange 20220101-
```
Kraken data is US-accessible, so this works where Binance downloads would fail.

## Troubleshooting
- **Port 8080 already in use** → change the left side of `"127.0.0.1:8080:8080"` in
  `docker-compose.yml` (e.g. `8081`), reopen on that port.
- **Windows network errors** → reboot after installing Docker Desktop.
- **A pair errors as unavailable on Kraken** → remove it from `pair_whitelist`
  (or switch that pair to a `/USD` variant; for live, US users often prefer
  `/USD` pairs + `"stake_currency": "USD"`).

## Important note on strategy + US venue
- `EmaTrendPullback` is **spot, long-only** — perfect for a first Kraken dry-run.
- `ParagonVwapReversion` (your S1 strategy) is written for **perps with shorting**.
  US retail generally can't access crypto perps on a compliant exchange, and
  Kraken **spot** can't short — so on Kraken you'd only get the **long half** of the
  reversion setups. Backtesting the full long+short version needs perp data/venue.
  This venue question is worth solving deliberately (see chat) before going live.
