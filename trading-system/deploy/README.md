# Running the alerts on a server (every trading day, without a phone)

A phone closes apps it isn't showing; a server doesn't. `install.sh` sets up `alerts/cprb_alerts.py` on an Ubuntu
server (for example the Oracle Cloud one) so that it:

- runs **every trading day by itself**: at 8:45 IST it sends the day's plan to Telegram, then every alert during
  the day (BUY / SELL with the strike, stop, target, book half, exit) and the day's result after 3:30;
- serves the **live chart** at `https://<name>/?key=<your key>` (through Caddy, with its own HTTPS certificate),
  which you can add to your phone's home screen (Chrome menu > Add to Home screen) and open like an app;
- **updates itself**: every 5 minutes (outside 9:00-15:35 IST) it checks this repository's branch on GitHub and
  restarts with the new code when something changed, so a change pushed here reaches the server by itself;
- starts again by itself after an error, a crash or a server restart.

It runs as its own user (`cprb`) in `/opt/cprb`, with its settings in `/etc/cprb.env` (only root can read it). It
does not touch anything else on the server; with a name given, it adds one separate site block to Caddy's config
(after checking it, and putting the old file back if Caddy doesn't accept it).

## Install (once, about 2 minutes)

1. Open a terminal on the server. Oracle Cloud: sign in at cloud.oracle.com, open **Cloud Shell** (the `>_` icon at
   the top right), then connect: `ssh -i ~/munimo.key ubuntu@68.233.118.222`.
2. Paste this, with your bot's token and chat id (the two values at the top of `cprb_alerts.py` on your phone) and
   the name for the chart:

       curl -fsSL https://raw.githubusercontent.com/CURIOUSMIND123/Edensniper/claude/trading-cafe-strategy-analysis-jnh595/trading-system/deploy/install.sh \
         | sudo bash -s -- 'TELEGRAM_TOKEN' 'TELEGRAM_CHAT_ID' trade.munimo.online

   Leave the chat id as `''` if you don't have it: send your bot any message first and it is found by itself.
3. It ends with a Telegram test message and prints the chart address with its key. Stop Pydroid 3 on the phone
   (otherwise you get every alert twice).

## Every day

Nothing to do. Useful commands on the server:

| What | Command |
|---|---|
| Is it running? | `systemctl status cprb` |
| What it is printing (live) | `sudo journalctl -u cprb -f` |
| Updates it pulled | `sudo journalctl -u cprb-update` |
| Change settings (Telegram, lots, chart key) | `sudo nano /etc/cprb.env`, then `sudo systemctl restart cprb` |
| Stop it / start it again | `sudo systemctl stop cprb` / `sudo systemctl start cprb` |
| Remove it | `sudo systemctl disable --now cprb cprb-update.timer`, delete `/opt/cprb` and `/etc/cprb.env`, and the chart's block at the end of `/etc/caddy/Caddyfile` |

Settings in `/etc/cprb.env`: `CPRB_TELEGRAM_TOKEN`, `CPRB_TELEGRAM_CHAT_ID`, `CPRB_LOTS` (lots for the rupee
estimates), `CPRB_CHART_KEY` (the chart's key), `CPRB_CHART_HOST` / `CPRB_CHART_PORT` (127.0.0.1:8000: only Caddy
reaches it), `CPRB_BRANCH` (the GitHub branch it follows). The trading rules are the ones at the top of
`cprb_alerts.py` in the repository.
