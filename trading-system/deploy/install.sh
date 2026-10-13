#!/usr/bin/env bash
# One-time setup on an Ubuntu server (for example Oracle Cloud): runs the CPR Breakout alerts every trading day
# without stopping, sends every alert to Telegram, serves the live chart over HTTPS with a private key, and updates
# itself from GitHub within 5 minutes of every push (outside market hours).
#
#   curl -fsSL https://raw.githubusercontent.com/CURIOUSMIND123/Edensniper/claude/trading-cafe-strategy-analysis-jnh595/trading-system/deploy/install.sh \
#     | sudo bash -s -- TELEGRAM_TOKEN TELEGRAM_CHAT_ID trade.example.com
#
# TELEGRAM_CHAT_ID can be left as '' if you have sent your bot a message: it is found by itself. The last argument
# (a name that points at this server) is optional: without it the chart stays private to the server.
# Running it again is safe: it keeps the settings it already has unless new ones are given.
set -euo pipefail
REPO="${CPRB_REPO:-https://github.com/CURIOUSMIND123/Edensniper}"
BRANCH="${CPRB_BRANCH:-claude/trading-cafe-strategy-analysis-jnh595}"
APP=/opt/cprb
ENV=/etc/cprb.env
TOKEN="${1:-}"; CHAT="${2:-}"; DOMAIN="${3:-}"
say() { printf '\n==> %s\n' "$*"; }
run_as() { if command -v sudo >/dev/null; then sudo -E -u cprb "$@"; else runuser -u cprb -- "$@"; fi; }
[ "$(id -u)" -eq 0 ] || { echo "Run it with sudo."; exit 1; }

say "Python and git"
command -v python3 >/dev/null && command -v git >/dev/null || { apt-get update -y && apt-get install -y python3 git; }

say "User 'cprb' and the code in $APP (branch $BRANCH)"
id cprb >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin cprb
git config --system --add safe.directory "$APP" 2>/dev/null || true
if [ -d "$APP/.git" ]; then
  git -C "$APP" fetch --quiet --depth 1 origin "$BRANCH" && git -C "$APP" reset --hard --quiet FETCH_HEAD
else
  git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$APP"
fi
chown -R cprb:cprb "$APP"

say "Settings in $ENV (only root can read it)"
touch "$ENV"; chmod 600 "$ENV"
setkv() { [ -n "$2" ] || return 0; if grep -qE "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi; }
getkv() { grep -E "^$1=" "$ENV" | head -n1 | cut -d= -f2- || true; }
setkv CPRB_BRANCH "$BRANCH"
setkv CPRB_TELEGRAM_TOKEN "$TOKEN"
setkv CPRB_CHART_HOST 127.0.0.1
setkv CPRB_CHART_PORT 8000
[ -n "$(getkv CPRB_CHART_KEY)" ] || setkv CPRB_CHART_KEY "$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
if [ -z "$CHAT" ] && [ -z "$(getkv CPRB_TELEGRAM_CHAT_ID)" ] && [ -n "$(getkv CPRB_TELEGRAM_TOKEN)" ]; then
  CHAT="$(cd "$APP/trading-system/alerts" && set -a && . "$ENV" && set +a && run_as python3 cprb_alerts.py --telegram-chat-id 2>/dev/null \
          | grep -oE 'chat id: -?[0-9]+' | grep -oE -- '-?[0-9]+' | head -n1 || true)"
  [ -n "$CHAT" ] && echo "Found your Telegram chat id: $CHAT" || echo "No chat id found yet: send your bot a message and run this again."
fi
setkv CPRB_TELEGRAM_CHAT_ID "$CHAT"

say "Services: the alerts (all day, every trading day) and the 5-minute updater"
for f in cprb.service cprb-update.service cprb-update.timer; do cp "$APP/trading-system/deploy/$f" "/etc/systemd/system/$f"; done
systemctl daemon-reload
systemctl enable --quiet cprb.service cprb-update.timer
systemctl restart cprb.service
systemctl start cprb-update.timer

URL=""
if [ -n "$DOMAIN" ]; then
  if command -v caddy >/dev/null && [ -f /etc/caddy/Caddyfile ]; then
    if grep -qE "^$DOMAIN[ ,{]" /etc/caddy/Caddyfile; then
      echo "Caddy already serves $DOMAIN."
    else
      say "The chart at https://$DOMAIN (Caddy, its own HTTPS certificate; nothing else in the Caddyfile changes)"
      bak="/etc/caddy/Caddyfile.before-cprb-$(date +%Y%m%d%H%M%S)"
      cp /etc/caddy/Caddyfile "$bak"
      printf '\n# CPR Breakout live chart (added by Edensniper trading-system/deploy/install.sh)\n%s {\n\tencode gzip\n\treverse_proxy 127.0.0.1:%s\n}\n' "$DOMAIN" "$(getkv CPRB_CHART_PORT)" >> /etc/caddy/Caddyfile
      if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
        systemctl reload caddy
      else
        cp "$bak" /etc/caddy/Caddyfile
        echo "Caddy did not accept the new site; the Caddyfile is back as it was. The chart stays private."
        DOMAIN=""
      fi
    fi
    [ -n "$DOMAIN" ] && URL="https://$DOMAIN/?key=$(getkv CPRB_CHART_KEY)"
  else
    echo "Caddy is not installed: the chart stays private to the server (see trading-system/deploy/README.md)."
  fi
fi

say "Telegram test"
if [ -n "$(getkv CPRB_TELEGRAM_TOKEN)" ] && [ -n "$(getkv CPRB_TELEGRAM_CHAT_ID)" ]; then
  (cd "$APP/trading-system/alerts" && set -a && . "$ENV" && set +a && run_as python3 cprb_alerts.py --telegram-test | grep -v '=====') || true
else
  echo "Telegram is not set up yet (token or chat id missing): run this again with them."
fi

sleep 5
say "DONE"
echo "  Alerts service : $(systemctl is-active cprb)   (log: sudo journalctl -u cprb -f)"
echo "  Auto-update    : $(systemctl is-active cprb-update.timer)   (every 5 minutes, outside 9:00-15:35 IST)"
[ -n "$URL" ] && echo "  Live chart     : $URL" && echo "                   (open it on your phone, then Chrome menu > Add to Home screen)"
echo "  Settings       : sudo nano $ENV, then: sudo systemctl restart cprb"
