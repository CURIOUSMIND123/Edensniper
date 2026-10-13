# The link from the Munimo (ne-construction-erp) server

The Oracle server already updates itself from `ne-construction-erp` (branch `claude/production-software-push-vd1cpz`):
`deploy/munimo-update.sh` runs every 2 minutes as root. Two small changes there make it also install and update
Eden Trader (the `eden-trader/` folder of the Edensniper repository), only on the Oracle server:

1. Add `companions.sh` (this folder) as `deploy/companions.sh` in ne-construction-erp.
2. In `deploy/munimo-update.sh`, right after the `git config ... safe.directory` lines and before
   `# Which branch to deploy`, add:

```bash
# Companion apps from their own repositories (deploy/companions.sh: Eden Trader, Oracle server only). Time-limited,
# logged to /var/log/munimo-companions.log, and never able to stop or fail this Munimo deploy.
if [ -f "$APP_DIR/deploy/companions.sh" ]; then
  timeout 600 bash "$APP_DIR/deploy/companions.sh" >>/var/log/munimo-companions.log 2>&1 || true
fi
```

The first push of these lands like any Munimo update (the updater pulls it and restarts Munimo, with its health
check); from the next run on, the Edensniper branch is cloned to `/opt/eden-trader` and Eden Trader installed, and every
later push to that branch reaches the server within 2 minutes. Without these changes, `../deploy/bootstrap.sh` (one
paste on the server) does the same with its own 2-minute timer. `MUNIMO_COMPANIONS=0` in `/etc/munimo.env` turns it off.
