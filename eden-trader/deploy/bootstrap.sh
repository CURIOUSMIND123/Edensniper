#!/usr/bin/env bash
# One paste on the server, for when the Munimo link (ne-construction-erp deploy/companions.sh) isn't used: clones the
# Edensniper repository to /opt/eden-trader, installs Eden Trader, and adds eden-trader-update.timer, which pulls new
# commits every 2 minutes from then on.
#   curl -fsSL https://raw.githubusercontent.com/CURIOUSMIND123/Edensniper/claude/trading-cafe-strategy-analysis-jnh595/eden-trader/deploy/bootstrap.sh | sudo bash
set -euo pipefail
DIR=/opt/eden-trader
[ "$(id -u)" -eq 0 ] || { echo "Run it with sudo."; exit 1; }
command -v git >/dev/null || { apt-get update -y && apt-get install -y git; }
[ -d "$DIR/.git" ] || git clone --quiet --depth 1 --branch claude/trading-cafe-strategy-analysis-jnh595 https://github.com/CURIOUSMIND123/Edensniper "$DIR"
bash "$DIR/eden-trader/deploy/update.sh"
cp "$DIR/eden-trader/deploy/eden-trader-update.service" "$DIR/eden-trader/deploy/eden-trader-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now eden-trader-update.timer
echo "Eden Trader: $(systemctl is-active eden-trader) | updates every 2 minutes | app: https://trade.munimo.online/app.apk"
