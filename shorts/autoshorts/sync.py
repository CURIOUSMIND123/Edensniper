"""Getting files onto the phone.

Two ways, because which one works depends on where you run this:
  copy   — a plain filesystem copy. On Termux, /sdcard/Movies/AutoShorts
           shows up in the phone's gallery straight away.
  rclone — push to Google Drive (or any rclone remote) from a PC, then the
           Drive app on the phone pulls it down.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _copy(src: Path, dest_dir: str, log) -> bool:
    dest = Path(dest_dir).expanduser()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / src.name
        if target.exists() and target.samefile(src):
            # The sync folder is the output folder. Already where it belongs.
            return True
        shutil.copy2(src, target)
        log(f"  copied to {target}")
        return True
    except OSError as exc:
        log(f"  copy failed: {exc}")
        return False


def _rclone(src: Path, remote: str, log) -> bool:
    if not shutil.which("rclone"):
        log("  rclone not installed — skipping sync")
        return False
    proc = subprocess.run(
        ["rclone", "copy", str(src), remote, "--no-traverse"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        log(f"  rclone failed: {(proc.stderr or '').strip()[:200]}")
        return False
    log(f"  synced to {remote}")
    return True


def push(cfg, paths: list[Path], log=print) -> int:
    """Send files to the phone. Returns how many made it."""
    settings = cfg["sync"]
    if not settings.get("enabled"):
        return 0
    method = str(settings.get("method", "none")).lower()
    if method == "none":
        return 0

    sent = 0
    for path in paths:
        if not path or not Path(path).exists():
            continue
        path = Path(path)
        if method == "copy":
            ok = _copy(path, settings.get("dest") or ".", log)
        elif method == "rclone":
            ok = _rclone(path, settings.get("rclone_remote") or "", log)
        else:
            log(f"  unknown sync method {method!r}")
            return sent
        sent += int(ok)
    return sent
