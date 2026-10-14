#!/usr/bin/env bash
# Sets up / updates Eden Trader on the server. Run as root from the checkout of the Edensniper repository in
# /opt/eden-trader; safe to run any number of times. The Munimo updater (ne-construction-erp deploy/companions.sh) or
# eden-trader-update.timer (deploy/bootstrap.sh) runs it whenever the branch changes, so nobody has to log in.
#
# What it does: user 'eden', data in /var/lib/eden-trader, settings in /etc/eden-trader.env, the systemd service
# 'eden-trader' (trading-system/alerts/cprb_alerts.py: the calls + the app's API on 127.0.0.1:8010; the app
# itself at /app.apk), and the site https://trade.munimo.online in
# Caddy (its own block between '# >>> eden-trader' and '# <<< eden-trader'; checked before Caddy reloads, and the
# previous file is put back if Caddy doesn't accept it). Restarts during market hours are postponed to 15:36 IST.
set -uo pipefail
APP=/opt/eden-trader
DATA=/var/lib/eden-trader
ENV=/etc/eden-trader.env
DOMAIN=trade.munimo.online
PORT=8010
log() { printf '[eden-trader install] %s\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Run it as root."; exit 1; }
command -v python3 >/dev/null || { apt-get update -y && apt-get install -y python3; }

id eden >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin eden
mkdir -p "$DATA" && chown -R eden:eden "$DATA" && chmod 750 "$DATA"

# settings: kept between runs; the key's SHA-256 comes from this repository (deploy/app-key.sha256)
touch "$ENV" && chmod 600 "$ENV"
setkv() { if grep -qE "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi; }
setkv CPRB_DATA_DIR "$DATA"
setkv CPRB_CHART_HOST 127.0.0.1
setkv CPRB_CHART_PORT "$PORT"
setkv CPRB_CHART_KEY_SHA256 "$(tr -d ' \n' < "$APP/eden-trader/deploy/app-key.sha256")"
setkv CPRB_APP_APK "$APP/eden-trader/dist/eden-trader.apk"
setkv CPRB_APP_WWW "$APP/eden-trader/app/www"
grep -qE '^CPRB_TELEGRAM_TOKEN=' "$ENV" || echo "CPRB_TELEGRAM_TOKEN=" >> "$ENV"
grep -qE '^CPRB_TELEGRAM_CHAT_ID=' "$ENV" || echo "CPRB_TELEGRAM_CHAT_ID=" >> "$ENV"

# the earlier phone-free setup from the Edensniper repository (service 'cprb'), if it was installed: retire it
if systemctl list-unit-files cprb.service >/dev/null 2>&1 && systemctl is-enabled cprb.service >/dev/null 2>&1; then
  log "stopping the older 'cprb' service (Eden Trader replaces it)"
  systemctl disable --now cprb.service cprb-update.timer >/dev/null 2>&1 || true
fi

if ! cmp -s "$APP/eden-trader/deploy/eden-trader.service" /etc/systemd/system/eden-trader.service; then
  cp "$APP/eden-trader/deploy/eden-trader.service" /etc/systemd/system/eden-trader.service
  systemctl daemon-reload
fi
systemctl enable --quiet eden-trader.service

# Caddy: the app's address
if command -v caddy >/dev/null && [ -f /etc/caddy/Caddyfile ]; then
  CF=/etc/caddy/Caddyfile
  want="$(printf '# >>> eden-trader (managed by /opt/eden-trader/eden-trader/deploy/install.sh)\n%s {\n\tencode gzip\n\treverse_proxy 127.0.0.1:%s\n}\n# <<< eden-trader' "$DOMAIN" "$PORT")"
  if ! grep -qF "reverse_proxy 127.0.0.1:$PORT" "$CF" || ! grep -qF '# >>> eden-trader' "$CF"; then
    bak="$CF.before-eden-$(date +%Y%m%d%H%M%S)"
    cp "$CF" "$bak"
    # drop an earlier block of ours, and the older Edensniper chart block for the same name
    python3 - "$CF" "$DOMAIN" <<'PY'
import re, sys
f, dom = sys.argv[1], sys.argv[2]
s = open(f).read()
s = re.sub(r'\n?# >>> eden-trader.*?# <<< eden-trader\n?', '\n', s, flags=re.S)
s = re.sub(r'\n?# CPR Breakout live chart \(added by Edensniper[^\n]*\n' + re.escape(dom) + r' \{.*?\n\}\n?', '\n', s, flags=re.S)
open(f, 'w').write(s.rstrip('\n') + '\n')
PY
    printf '\n%s\n' "$want" >> "$CF"
    if caddy validate --config "$CF" --adapter caddyfile >/dev/null 2>&1; then
      systemctl reload caddy && log "Caddy: https://$DOMAIN -> 127.0.0.1:$PORT"
    else
      cp "$bak" "$CF"
      log "Caddy did not accept the new block; Caddyfile restored, the app's address is not served yet"
    fi
  fi
else
  log "Caddy not found: the app's API stays on 127.0.0.1:$PORT"
fi

# start now if it isn't running; restart only when the program, its history or these files changed; in market hours
# tick.sh restarts it at a safe moment (no trade open, between 5-minute candles, not 9:10-10:05) or after the close
sum="$(cat "$APP/trading-system/alerts/cprb_alerts.py" "$APP/trading-system/alerts/history-2026.json" "$APP"/eden-trader/deploy/* "$ENV" 2>/dev/null | sha256sum | cut -d' ' -f1)"
if ! systemctl is-active --quiet eden-trader.service; then
  systemctl start eden-trader.service && log "started"
  echo "$sum" > "$DATA/.deployed"
elif [ "$sum" = "$(cat "$DATA/.deployed" 2>/dev/null)" ]; then
  :
else
  echo "$sum" > "$DATA/.deployed"
  hm=$((10#$(TZ=Asia/Kolkata date +%H%M))); dow=$(TZ=Asia/Kolkata date +%u)
  if [ "$dow" -le 5 ] && [ "$hm" -ge 900 ] && [ "$hm" -le 1535 ]; then
    touch "$DATA/.restart-pending" && log "new code: restart at a safe moment (tick.sh)"
  else
    systemctl restart eden-trader.service && log "restarted with the new code"
  fi
fi
exit 0
