"""
Premium Villa - Orders Bot (orders_bot.py)
Run this SEPARATELY from bot.py:
    python3 orders_bot.py

This bot receives order notifications and lets admins click
"Order Completed" / "Cancel Order" buttons.
Admins must /start this bot to register for notifications.
"""

from telegram.ext import Application, CommandHandler
import orders
import store

def main():
    print("Starting Orders Bot...")
    app = Application.builder().token(store.ORDERS_BOT_TOKEN).build()

    # /start -> let admins register
    app.add_handler(CommandHandler("start", orders.orders_start))

    # all admin slash commands (orders, stats, ban, ad, etc.)
    orders.register_commands(app)

    # "Order Completed" / "Cancel Order" inline button handler
    orders.register_order_buttons(app)

    print("Orders Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()