#!/usr/bin/env bash
# Run every 2 minutes (after install.sh when there is new code). A restart for new code waits for a safe moment:
#  - outside market hours (before 9:00, after 15:35 IST, weekends): at once;
#  - in market hours: only when no trade is open (today's entries in events.jsonl all have their exit), not from 9:10
#    to 10:05 (the Magnet and the 9:30 breakout), and 1-2 minutes after a 5-minute candle closed (the volume-line
#    signals come at the 5-minute closes). The program is back within seconds and goes through the day again; it
#    doesn't send an alert it already sent.
# A stopped service is started again.
DATA="${EDEN_DATA:-/var/lib/eden-trader}"
hm=$((10#$(TZ=Asia/Kolkata date +%H%M))); dow=$(TZ=Asia/Kolkata date +%u)
in_market=0; [ "$dow" -le 5 ] && [ "$hm" -ge 900 ] && [ "$hm" -le 1535 ] && in_market=1

open_trades() {
  python3 - "$DATA/events.jsonl" <<'PY' 2>/dev/null || echo 1
import datetime as dt, json, sys
today = (dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d')
n = 0
try:
    with open(sys.argv[1], encoding='utf-8') as f:
        for x in f:
            try:
                e = json.loads(x)
            except ValueError:
                continue
            if str(e.get('at', '')).startswith(today):
                n += (e.get('kind') == 'entry') - (e.get('kind') == 'exit')
except OSError:
    pass
print(max(n, 0))
PY
}

safe_now() {
  [ "$in_market" = 0 ] && return 0
  [ "$hm" -ge 910 ] && [ "$hm" -le 1005 ] && return 1
  local m=$(( 10#$(TZ=Asia/Kolkata date +%H) * 60 + 10#$(TZ=Asia/Kolkata date +%M) ))
  local k=$(( (m - 555) % 5 ))
  { [ "$k" = 1 ] || [ "$k" = 2 ]; } || return 1
  [ "$(open_trades)" = 0 ]
}

[ "${1:-}" = "--open-trades" ] && { open_trades; exit 0; }       # for a check by hand

if [ -f "$DATA/.restart-pending" ] && safe_now; then
  rm -f "$DATA/.restart-pending" && systemctl restart eden-trader.service && echo "[eden-trader] restarted with the new code ($(TZ=Asia/Kolkata date +%H:%M) IST)"
fi
systemctl is-active --quiet eden-trader.service || systemctl start eden-trader.service
exit 0
