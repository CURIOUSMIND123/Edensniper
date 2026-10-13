#!/usr/bin/env bash
# For the ne-construction-erp repository: deploy/companions.sh (called from deploy/munimo-update.sh, see
# README.md here). Companion apps that run on the Oracle server next to Munimo, each from its own GitHub
# repository, with its own user, folder and service; nothing of Munimo is touched. munimo-update.sh calls this every
# run (every 2 minutes): the first time it clones the app's repository, and every time it runs the app's own
# update script (which pulls new commits and installs them). Output: /var/log/munimo-companions.log.
#
# Only on the Oracle server (public IP 68.233.118.222), never on another server that deploys that repository.
# In /etc/munimo.env: MUNIMO_COMPANIONS=0 turns this off, MUNIMO_COMPANIONS=force skips the IP check.
#
#   eden-trader  https://github.com/CURIOUSMIND123/Edensniper (eden-trader/)  Nifty / Sensex calls for the Eden Trader app
set -uo pipefail
ORACLE_IP=68.233.118.222
STATE=/var/lib/munimo-companions
mkdir -p "$STATE"
log() { printf '%s [companions] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
flag="$(grep -E '^MUNIMO_COMPANIONS=' /etc/munimo.env 2>/dev/null | head -n1 | cut -d= -f2- || true)"
[ "$flag" = "0" ] && exit 0

on_oracle() {
  [ "$flag" = "force" ] && return 0
  local f="$STATE/public-ip"
  if [ ! -s "$f" ] || [ -n "$(find "$f" -mmin +720 2>/dev/null)" ]; then
    local ip
    ip="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || curl -fsS --max-time 5 https://ifconfig.me/ip 2>/dev/null || true)"
    [ -n "$ip" ] && printf '%s\n' "$ip" > "$f"
  fi
  [ "$(tr -d ' \n' < "$f" 2>/dev/null)" = "$ORACLE_IP" ]
}

companion() {
  # name, repository, branch, the script in it that pulls and installs (run every time)
  local name="$1" repo="$2" branch="$3" script="$4" dir="/opt/$1"
  if [ ! -d "$dir/.git" ]; then
    log "$name: first install from $repo ($branch)"
    rm -rf "$dir.partial"
    if ! git clone --quiet --depth 1 --branch "$branch" "$repo" "$dir.partial"; then
      log "$name: clone failed; trying again next run"
      rm -rf "$dir.partial"
      return 0
    fi
    mv "$dir.partial" "$dir"
  fi
  bash "$dir/$script" || log "$name: $script failed"
  return 0
}

on_oracle || exit 0
companion eden-trader "${EDEN_TRADER_REPO:-https://github.com/CURIOUSMIND123/Edensniper}" claude/trading-cafe-strategy-analysis-jnh595 eden-trader/deploy/update.sh
exit 0
