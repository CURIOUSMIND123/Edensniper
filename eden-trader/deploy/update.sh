#!/usr/bin/env bash
# Pulls the branch; on new commits (or the first time) runs install.sh; then tick.sh. Runs every 2 minutes, from the
# Munimo updater (ne-construction-erp deploy/companions.sh) or from eden-trader-update.timer (bootstrap.sh).
set -uo pipefail
DIR=/opt/eden-trader
BRANCH=claude/trading-cafe-strategy-analysis-jnh595
exec 9>/run/eden-trader-update.lock
flock -n 9 || exit 0
git config --system --add safe.directory "$DIR" 2>/dev/null || true
run_install=0
[ -f /etc/systemd/system/eden-trader.service ] || run_install=1
if git -C "$DIR" fetch --quiet --depth 1 origin "$BRANCH" 2>/dev/null; then
  if [ "$(git -C "$DIR" rev-parse HEAD)" != "$(git -C "$DIR" rev-parse FETCH_HEAD)" ]; then
    git -C "$DIR" reset --quiet --hard FETCH_HEAD
    echo "[eden-trader] code updated to $(git -C "$DIR" rev-parse --short HEAD)"
    run_install=1
  fi
fi
[ "$run_install" = 1 ] && { bash "$DIR/eden-trader/deploy/install.sh" || echo "[eden-trader] install.sh failed"; }
bash "$DIR/eden-trader/deploy/tick.sh"
exit 0
