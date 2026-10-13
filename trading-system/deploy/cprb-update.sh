#!/usr/bin/env bash
# Pulls the latest code of the deploy branch and restarts the alerts, but only when something changed and never
# during market hours (a restart then would send the morning plan again). Runs every 5 minutes (cprb-update.timer).
# Log: journalctl -u cprb-update
set -euo pipefail
APP=/opt/cprb
ENV=/etc/cprb.env
BRANCH="$(grep -E '^CPRB_BRANCH=' "$ENV" | head -n1 | cut -d= -f2-)"
[ -n "$BRANCH" ] || { echo "no CPRB_BRANCH in $ENV"; exit 0; }
hm=$((10#$(TZ=Asia/Kolkata date +%H%M))); dow=$(TZ=Asia/Kolkata date +%u)
if [ "$dow" -le 5 ] && [ "$hm" -ge 900 ] && [ "$hm" -le 1535 ]; then exit 0; fi
git config --system --add safe.directory "$APP" 2>/dev/null || true
if ! git -C "$APP" fetch --quiet --depth 1 origin "$BRANCH"; then echo "fetch failed; next try in 5 minutes"; exit 0; fi
[ "$(git -C "$APP" rev-parse HEAD)" = "$(git -C "$APP" rev-parse FETCH_HEAD)" ] && exit 0
old="$(git -C "$APP" rev-parse --short HEAD)"
git -C "$APP" reset --hard --quiet FETCH_HEAD
chown -R cprb:cprb "$APP"
for f in cprb.service cprb-update.service cprb-update.timer; do
  cp "$APP/trading-system/deploy/$f" "/etc/systemd/system/$f"
done
systemctl daemon-reload
systemctl restart cprb
echo "updated $old -> $(git -C "$APP" rev-parse --short HEAD) and restarted the alerts"
