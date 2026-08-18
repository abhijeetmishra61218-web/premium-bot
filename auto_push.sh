#!/bin/bash
cd ~/premium-villa-bot
git add -f products.json settings.json menu.json action_emojis.json cart_config.json cryptos.json support.json tgpremium.json smmdata.json bot.py orders.py payments.py smm.py store.py cart.py orders_bot.py
git commit -m "Auto sync: $(date '+%Y-%m-%d %H:%M')"
git push origin main
