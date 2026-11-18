#!/bin/bash
# Safe deploy for the Premium Villa bot.
#
#   1. Upload the new files to your home folder (the SSH upload button).
#   2. Run:  ~/premium-villa-bot/deploy.sh        (add -y to skip the question)
#
# It finds the newest uploaded copy of each file (even named "bot (21).py"),
# backs up the current files, installs the new ones, checks they compile,
# restarts the bot ONCE, waits until the bot is really running, and rolls
# everything back automatically if it is not.

set -u
APP="${APP:-$HOME/premium-villa-bot}"
UPLOADS="${UPLOADS:-$HOME}"
SERVICE="${SERVICE:-premium-villa-bot}"
MAX_AGE_MIN=240
TARGETS="bot.py payments.py cart.py smm.py orders.py store.py orders_bot.py myorders.py analytics.py seed_myorders.py invoice.py invoice_assets.py disk_alert.sh"

find_upload() {   # $1 = target file name, e.g. bot.py
  local base="${1%.*}" ext="${1##*.}"
  find "$UPLOADS" -maxdepth 1 -type f -mmin -"$MAX_AGE_MIN" \
       \( -name "$base.$ext" -o -name "$base ([0-9]*).$ext" \) \
       -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-
}

cd "$APP" || { echo "Cannot find $APP"; exit 1; }

declare -A NEW
for t in $TARGETS; do
  p="$(find_upload "$t")"
  [ -n "$p" ] && NEW["$t"]="$p"
done
if [ "${#NEW[@]}" -eq 0 ]; then
  echo "No new files found in $UPLOADS (uploaded in the last $MAX_AGE_MIN minutes). Nothing to do."
  exit 1
fi

echo "Will deploy:"
for t in "${!NEW[@]}"; do echo "  $t   <-   ${NEW[$t]}"; done
if [ "${1:-}" != "-y" ]; then
  read -r -p "Continue? [y/N] " ans
  [ "$ans" = "y" ] || { echo "Cancelled. Nothing was changed."; exit 1; }
fi

# ---- the new bot.py must read its settings from .env (no hard-coded token) ----
if [ -n "${NEW[bot.py]:-}" ]; then
  if ! grep -q '_setting("BOT_TOKEN")' "${NEW[bot.py]}" || grep -q '^BOT_TOKEN = "' "${NEW[bot.py]}"; then
    echo "The uploaded bot.py is an old-style file (token inside the file). Refusing to install it."
    exit 1
  fi
fi

# ---- backup ----
TS="$(date +%Y%m%d_%H%M%S)"
BK="$APP/backups/$TS"
mkdir -p "$BK"
for t in "${!NEW[@]}"; do [ -f "$APP/$t" ] && cp -p "$APP/$t" "$BK/$t"; done
[ -f "$APP/.env" ] && cp -p "$APP/.env" "$BK/.env"
echo "Backup of current files: $BK"

# ---- first time only: move token + admin id out of bot.py into .env ----
if [ ! -f "$APP/.env" ]; then
  tok="$(grep -m1 '^BOT_TOKEN' "$APP/bot.py" | grep -oE '[0-9]{6,}:[A-Za-z0-9_-]{30,}' | head -1)"
  adm="$(grep -m1 '^ADMIN_ID *= *[0-9]' "$APP/bot.py" | grep -oE '[0-9]+' | head -1)"
  if [ -z "$tok" ] || [ -z "$adm" ]; then
    echo "Could not read the token/admin id from the current bot.py, and there is no .env."
    echo "Nothing was changed. Create $APP/.env by hand (see instructions) and run again."
    exit 1
  fi
  ( umask 077; printf 'BOT_TOKEN=%s\nADMIN_ID=%s\n' "$tok" "$adm" > "$APP/.env" )
  echo "Created $APP/.env from your current bot.py (token not shown)."
fi

rollback() {   # $1 = "norestart" when the bot was never restarted with the new files
  echo "!! Problem detected - rolling back to the previous files."
  for t in "${!NEW[@]}"; do [ -f "$BK/$t" ] && cp -p "$BK/$t" "$APP/$t"; done
  if [ "${1:-}" = "norestart" ]; then
    echo "Rolled back. The bot was never restarted, so it is still running the old version."
  else
    sudo systemctl restart "$SERVICE"
    echo "Rolled back and restarted. The bot is running the OLD version again."
  fi
  echo "Previous files are also in $BK."
  exit 1
}

# ---- install + syntax check ----
for t in "${!NEW[@]}"; do cp "${NEW[$t]}" "$APP/$t"; done
[ -f "$APP/disk_alert.sh" ] && chmod +x "$APP/disk_alert.sh"
for t in "${!NEW[@]}"; do
  case "$t" in
    *.py) python3 -m py_compile "$APP/$t" || { echo "Syntax error in $t"; rollback norestart; } ;;
    *.sh) bash -n "$APP/$t" || { echo "Syntax error in $t"; rollback norestart; } ;;
  esac
done
echo "All files compile."

# ---- invoices need the reportlab package (installed once) ----
if ! "$APP/venv/bin/python" -c "import reportlab" 2>/dev/null; then
  echo "Installing reportlab (needed for invoices)..."
  "$APP/venv/bin/pip" install -q reportlab \
    || echo "WARNING: could not install reportlab - the Download Invoice button will not work until it is installed."
fi

# ---- restart once, then wait until the bot is really up ----
START_EPOCH="$(date +%s)"
START="$(date '+%Y-%m-%d %H:%M:%S')"
sudo systemctl restart "$SERVICE"

ok=0
for i in $(seq 1 30); do
  sleep 2
  logs="$(sudo journalctl -u "$SERVICE" --since "$START" --no-pager 2>/dev/null)"
  if echo "$logs" | grep -qE "InvalidToken|Missing BOT_TOKEN|Missing ADMIN_ID|SyntaxError|ModuleNotFoundError|ImportError|NameError"; then
    ok=0; break
  fi
  if echo "$logs" | grep -q "Bot running" && [ -f "$APP/heartbeat.txt" ] \
     && [ "$(date -r "$APP/heartbeat.txt" +%s)" -ge "$START_EPOCH" ]; then
    ok=1; break
  fi
done
[ "$ok" -eq 1 ] || { echo "Bot did not come up healthy."; sudo journalctl -u "$SERVICE" --since "$START" --no-pager | tail -15; rollback; }

# ---- success: move the uploaded copies away so they are not reused ----
mkdir -p "$HOME/deployed"
for t in "${!NEW[@]}"; do mv "${NEW[$t]}" "$HOME/deployed/" 2>/dev/null; done
echo
echo "DONE - bot restarted once and is healthy (heartbeat is fresh)."
echo "Backup of the previous version: $BK"
echo "To undo manually:  cp $BK/<file> $APP/<file>  then  sudo systemctl restart $SERVICE"
