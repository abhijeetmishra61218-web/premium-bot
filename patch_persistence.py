with open("bot.py", "r", encoding="utf-8") as f:
    bot_src = f.read()

old_import = """from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)"""
new_import = """from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    PicklePersistence,
)"""
assert old_import in bot_src, "bot.py import block not found - aborting, NO changes made"
bot_src = bot_src.replace(old_import, new_import, 1)

old_builder = 'app = Application.builder().token(BOT_TOKEN).build()'
new_builder = '''persistence = PicklePersistence(filepath=os.path.join(BASE_DIR, "bot_persistence.pkl"), update_interval=1)

    async def _post_init(application):
        await payments.resume_pending_orders(application)

    app = Application.builder().token(BOT_TOKEN).persistence(persistence).post_init(_post_init).build()'''
assert old_builder in bot_src, "bot.py builder line not found - aborting, NO changes made"
bot_src = bot_src.replace(old_builder, new_builder, 1)

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(bot_src)
print("bot.py patched OK")

with open("payments.py", "r", encoding="utf-8") as f:
    pay_src = f.read()

old_pay_import = """from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
)"""
new_pay_import = """from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
    ContextTypes,
)"""
assert old_pay_import in pay_src, "payments.py import block not found - aborting, NO changes made"
pay_src = pay_src.replace(old_pay_import, new_pay_import, 1)

resume_fn = '''

async def resume_pending_orders(application):
    """Re-spawn countdown + OxaPay poll tasks for orders still in-flight
    when the bot last stopped, so a restart never abandons a paid order."""
    resumed = 0
    expired = 0
    for user_id, data in application.user_data.items():
        order = data.get("pay_order")
        if not order or order.get("state") not in ("await_payment", "waiting_conf"):
            continue
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=order.get("chat_id"), user_id=user_id)
        if order.get("deadline", 0) <= time.time():
            expired += 1
            try:
                await _expire_order_raw(context, user_id)
            except Exception as e:
                print(f"[payments] error expiring stale order for {user_id}: {e}")
            continue
        _spawn(user_id, _countdown_raw(context, user_id))
        _spawn_poll(user_id, _poll_status_raw(context, user_id))
        resumed += 1
    if resumed or expired:
        print(f"[payments] resumed {resumed} pending order(s), expired {expired} stale order(s) after restart")
'''
assert "async def resume_pending_orders" not in pay_src, "already patched, skipping"
pay_src = pay_src.rstrip() + "\n" + resume_fn

with open("payments.py", "w", encoding="utf-8") as f:
    f.write(pay_src)
print("payments.py patched OK")
