#!/usr/bin/env bash
# One command to set everything up and start making videos.
#   bash start.sh
# Safe to run again any time — it skips whatever is already done.

set -u
cd "$(dirname "$0")"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[31m--\033[0m  %s\n' "$*"; }

# ---------------------------------------------------------------- platform
if [ -n "${PREFIX:-}" ] && [ -d "/data/data/com.termux" ]; then
  PLATFORM=termux
elif [ "$(uname -s)" = "Darwin" ]; then
  PLATFORM=mac
else
  PLATFORM=linux
fi

say "AutoShorts setup  (detected: $PLATFORM)"

# ---------------------------------------------------------------- python
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
  bad "Python is not installed."
  case "$PLATFORM" in
    termux) info "Run:  pkg install python" ;;
    mac)    info "Run:  brew install python" ;;
    *)      info "Run:  sudo apt install python3 python3-pip" ;;
  esac
  exit 1
fi
ok "python ($($PY --version 2>&1))"

# ---------------------------------------------------------------- ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  say "Installing ffmpeg (needed to join the clips together)"
  case "$PLATFORM" in
    termux) pkg install -y ffmpeg ;;
    mac)    brew install ffmpeg ;;
    *)      sudo apt-get update -qq && sudo apt-get install -y ffmpeg ;;
  esac
fi
if command -v ffmpeg >/dev/null 2>&1; then ok "ffmpeg"; else
  bad "ffmpeg still missing — install it, then run this again."
  exit 1
fi

# ---------------------------------------------------------------- packages
say "Installing Python packages"
"$PY" -m pip install --quiet --disable-pip-version-check -r requirements.txt 2>&1 | tail -2
ok "packages"

# ------------------------------------------------------- storage (Termux)
if [ "$PLATFORM" = termux ] && [ ! -d "$HOME/storage" ]; then
  say "Giving Termux access to your phone storage"
  info "Tap ALLOW on the popup that appears."
  termux-setup-storage
  sleep 3
fi

# ---------------------------------------------------------------- config
if [ ! -f config.yaml ]; then
  say "First-time setup — three quick questions"

  printf '\n1. What should the channel be about?\n'
  printf '   (press Enter for: virology and infectious disease explained simply)\n   > '
  read -r NICHE
  [ -z "$NICHE" ] && NICHE="virology and infectious disease explained simply"

  printf '\n2. Paste your free Gemini API key.\n'
  printf '   Get one in 30 seconds at https://aistudio.google.com/apikey\n'
  printf '   This is FREE and is only used to write the scripts, not the video.\n'
  printf '   (press Enter to skip — the app still works, the writing is just plainer)\n   > '
  read -r KEY

  printf '\n3. Where should finished videos be copied to?\n'
  if [ "$PLATFORM" = termux ]; then
    printf '   (press Enter for your gallery: /sdcard/Movies/AutoShorts)\n   > '
    read -r DEST
    [ -z "$DEST" ] && DEST="/sdcard/Movies/AutoShorts"
  else
    printf '   A folder your phone syncs, if you have one (Google Drive, Syncthing).\n'
    printf '   (press Enter to skip — videos just stay in the out/ folder)\n   > '
    read -r DEST
  fi

  "$PY" -m autoshorts init >/dev/null 2>&1 || "$PY" -m autoshorts init

  "$PY" - "$NICHE" "$DEST" <<'PYEOF'
import re, sys
from pathlib import Path

niche, dest = sys.argv[1], sys.argv[2]
path = Path("config.yaml")
text = path.read_text()
text = re.sub(r'^niche:.*$', f'niche: "{niche}"', text, count=1, flags=re.M)
if dest:
    text = re.sub(r'^(  dest:).*$', rf'\1 "{dest}"', text, count=1, flags=re.M)
else:
    # No separate destination, so copying anywhere would just duplicate out/.
    text = re.sub(r'^(sync:\n  enabled:).*$', r'\1 false', text, count=1, flags=re.M)
path.write_text(text)
print(f"  config written: {niche}")
PYEOF

  if [ -n "$KEY" ]; then
    printf 'export GEMINI_API_KEY=%s\n' "$KEY" > .env
    chmod 600 .env
    ok "API key saved to shorts/.env"
  fi
else
  ok "config.yaml already exists (delete it to start over)"
fi

# shellcheck disable=SC1091
[ -f .env ] && . ./.env

# ---------------------------------------------------------------- check
say "Checking everything"
"$PY" -m autoshorts doctor

# ---------------------------------------------------------------- go
INBOX="$(pwd)/inbox"
cat <<EOF

$(printf '\033[1mYou are set up. Here is what happens now.\033[0m')

  1. This will start and write your video prompts to:
       $INBOX/PROMPTS.md

  2. Open that file. Copy the first prompt.

  3. Paste it into the Gemini app. Download the clip it makes.

  4. Move the downloaded file into:
       $INBOX

  5. Repeat. When Gemini says you have hit your limit, just stop and
     come back later — this keeps your place and waits for you.

  6. After 6 clips it builds the finished video by itself and saves it
     to your phone. Nothing else for you to do.

Press Enter to start, or Ctrl-C to quit.
EOF
read -r _

exec "$PY" -m autoshorts run
