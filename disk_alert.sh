#!/bin/bash
USE=$(df / --output=pcent | tail -1 | tr -dc '0-9')
if [ "$USE" -ge 80 ]; then
  TOKEN=$(grep -m1 'BOT_TOKEN = "' ~/premium-villa-bot/bot.py | sed -E 's/.*"(.*)".*/\1/')
  ADMIN_ID=$(grep -m1 'ADMIN_ID = ' ~/premium-villa-bot/bot.py | grep -oE '[0-9]+')
  curl -s "https://api.telegram.org/bot$TOKEN/sendMessage" \
    -d chat_id="$ADMIN_ID" -d text="⚠️ VM disk is at ${USE}% — clean up before it fills." > /dev/null
fi
