#!/bin/bash
# Uploads the bot's code and settings to GitHub.
#   ./auto_push.sh              upload now (manual)
#   ./auto_push.sh --scheduled  used by cron: does nothing unless 3 days passed since the last check
# Tokens live in .env, which is never uploaded. A safety check refuses to upload anything that
# looks like a Telegram bot token.

APP="${APP:-$HOME/premium-villa-bot}"
EVERY_MIN=4260                                   # 3 days minus an hour of slack (cron runs daily)
MARK="$APP/.last_auto_push"
export GIT_TERMINAL_PROMPT=0                     # never sit waiting for a password

cd "$APP" || exit 1
exec 9>"$APP/.auto_push.lock"
flock -n 9 || { echo "$(date '+%F %T') another upload is running - skipping."; exit 0; }

if [ "${1:-}" = "--scheduled" ] && [ -f "$MARK" ] && [ -n "$(find "$MARK" -mmin -"$EVERY_MIN" 2>/dev/null)" ]; then
  exit 0                                          # checked less than 3 days ago
fi

echo "$(date '+%F %T') checking for changes..."
for f in products.json settings.json menu.json action_emojis.json cart_config.json cryptos.json support.json tgpremium.json smmdata.json \
         bot.py orders.py payments.py smm.py store.py cart.py orders_bot.py myorders.py analytics.py invoice.py invoice_assets.py \
         payments_engine.py requirements.txt deploy.sh watchdog.sh disk_alert.sh auto_push.sh .gitignore; do
  [ -e "$f" ] && git add -f -- "$f"          # a missing file must never stop the others
done

git fetch -q origin main 2>/dev/null          # so we know what GitHub already has
UNSENT="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"

if git diff --cached --quiet && [ "${UNSENT:-0}" = "0" ]; then
  echo "Nothing new - GitHub is already up to date."
  touch "$MARK"
  exit 0
fi

if git diff --cached | grep -qE '^\+.*[0-9]{8,}:[A-Za-z0-9_-]{30,}'; then
  echo "STOPPED: one of the changed files contains something that looks like a bot token. Nothing was uploaded."
  git reset -q
  exit 1
fi

if ! git diff --cached --quiet; then
  git commit -q -m "Auto sync: $(date '+%Y-%m-%d %H:%M')" || { echo "Could not save the changes (git commit failed)."; exit 1; }
fi
if git push -q origin main; then
  echo "Uploaded to GitHub."
  touch "$MARK"
else
  echo "UPLOAD FAILED. The changes are saved on the server and will be retried on the next run."
  echo "Common reasons: GitHub login/token expired, or GitHub's secret scanner blocked a file (read the message above)."
  exit 1
fi
