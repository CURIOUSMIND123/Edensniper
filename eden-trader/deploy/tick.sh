#!/usr/bin/env bash
# Run by the Munimo updater every 2 minutes (after install.sh when there is new code): a restart postponed during
# market hours happens here once the market has closed, and a stopped service is started again.
DATA=/var/lib/eden-trader
hm=$((10#$(TZ=Asia/Kolkata date +%H%M))); dow=$(TZ=Asia/Kolkata date +%u)
in_market=0; [ "$dow" -le 5 ] && [ "$hm" -ge 900 ] && [ "$hm" -le 1535 ] && in_market=1
if [ -f "$DATA/.restart-pending" ] && [ "$in_market" = 0 ]; then
  rm -f "$DATA/.restart-pending" && systemctl restart eden-trader.service && echo "[eden-trader] restarted with the new code"
fi
systemctl is-active --quiet eden-trader.service || systemctl start eden-trader.service
exit 0
