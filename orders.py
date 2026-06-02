"""
Premium Villa - Orders & Admin module (orders.py)

Shared by BOTH bots:
  * the New Order notification (sent to admins through the ORDERS bot) with
    "Order Completed" / "Cancel Order" buttons that DM the customer (through
    the MAIN bot, since that's the bot they actually started).
  * all owner/admin slash commands: /orders /stats /ban /unban /ad
    /maintenance /active /add /refund /admin /removeadmin
  * a ban + maintenance "gate" installed on the MAIN bot.

register_commands(app)      -> add all slash commands (+ /ad media) to an app
register_order_buttons(app) -> add the Order Completed/Cancel callback handler
register_gate(app)          -> add the ban/maintenance gate (MAIN bot only)
"""

import html
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
)

import store

NL = chr(10)

BANNED_TEXT = "You Are Banned From Using This Bot !!"
MAINTENANCE_TEXT = ("The bot is currently undergoing maintenance. "
                    "We appreciate your patience and understanding")
DELIVERED_TEXT = "<b>Your order has been delivered. Thank you for trusting us</b>"
CANCELLED_TEXT = "<b>Your order has been cancelled</b>"

CMD_GROUP = -5      # commands run before the shop handlers
GATE_GROUP = -100   # the gate runs before everything

# ========================= order notification =========================
def _esc(v):
    return html.escape(str(v)) if v is not None else ""

def _order_breakdown(record):
    items = record.get("items", []) or []
    prods, plans, answers = [], [], []
    for it in items:
        name = it.get("product") or it.get("title") or "Item"
        qty = it.get("qty", 1)
        prods.append(_esc(name) + " (x" + str(qty) + ")")
        if it.get("plan"):
            plans.append(_esc(it["plan"]))
        if it.get("target"):
            label = it.get("target_label") or "Detail"
            answers.append((_esc(label), _esc(it["target"])))
    return prods, plans, answers

def build_order_notification(record):
    prods, plans, answers = _order_breakdown(record)
    uname = record.get("username")
    lines = [
        "<b>New Order</b>",
        "",
        "Product : " + (", ".join(prods) if prods else "-"),
        "Plan : " + (", ".join(plans) if plans else "-"),
        "Order id : " + _esc(record.get("order_id")),
        "Crypto : " + _esc(record.get("crypto") or "-"),
        "Transaction Hash : " + _esc(record.get("hash") or "-"),
        "Customer Username : " + ("@" + _esc(uname) if uname else "-"),
        "Customer Userid : " + _esc(record.get("user_id")),
    ]
    for label, val in answers:
        lines.append(label + " : " + val)
    oid = str(record.get("order_id"))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Order Completed", callback_data="ord:done:" + oid)],
        [InlineKeyboardButton("Cancel Order", callback_data="ord:cancel:" + oid)],
    ])
    return NL.join(lines), kb

async def send_new_order(record):
    """Record the order and push the notification to every admin via the orders bot."""
    store.add_order(record)
    text, kb = build_order_notification(record)
    kb_dict = kb.to_dict()
    for admin_id in store.list_admins():
        await asyncio.to_thread(store.send_message_as_orders, admin_id, text, kb_dict)

# ========================= order action buttons =========================
async def on_order_action(update, context):
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith("ord:"):
        return
    if not store.is_admin(query.from_user.id):
        await query.answer("Not allowed", show_alert=True)
        raise ApplicationHandlerStop
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    oid = parts[2] if len(parts) > 2 else ""
    order = store.get_order(oid)
    if not order:
        await query.answer("Order not found", show_alert=True)
        raise ApplicationHandlerStop

    customer = order.get("user_id")
    if action == "done":
        store.set_order_status(oid, "completed")
        await asyncio.to_thread(store.send_message_as_main, customer, DELIVERED_TEXT)
        suffix = "Order Completed"
    elif action == "cancel":
        store.set_order_status(oid, "cancelled")
        await asyncio.to_thread(store.send_message_as_main, customer, CANCELLED_TEXT)
        suffix = "Order Cancelled"
    else:
        await query.answer()
        raise ApplicationHandlerStop

    try:
        base = query.message.text_html if query.message and query.message.text else ""
        await query.edit_message_text(base + NL + NL + "<b>" + suffix + "</b>", parse_mode="HTML")
    except Exception:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    await query.answer(suffix)
    raise ApplicationHandlerStop

# ========================= the gate (MAIN bot) =========================
async def _gate_message(update, context):
    user = update.effective_user
    if user is None:
        return
    store.register_user(user.id, user.username, user.first_name)
    if store.is_admin(user.id):
        return
    if store.is_banned(user.id):
        try:
            await update.effective_message.reply_text(BANNED_TEXT)
        except Exception:
            pass
        raise ApplicationHandlerStop
    if store.is_maintenance():
        try:
            await update.effective_message.reply_text(MAINTENANCE_TEXT)
        except Exception:
            pass
        raise ApplicationHandlerStop

async def _gate_callback(update, context):
    query = update.callback_query
    if query is None:
        return
    user = query.from_user
    store.register_user(user.id, user.username, user.first_name)
    if store.is_admin(user.id):
        return
    if store.is_banned(user.id):
        await query.answer(BANNED_TEXT, show_alert=True)
        raise ApplicationHandlerStop
    if store.is_maintenance():
        await query.answer(MAINTENANCE_TEXT, show_alert=True)
        raise ApplicationHandlerStop

def register_gate(application):
    application.add_handler(MessageHandler(filters.ALL, _gate_message), group=GATE_GROUP)
    application.add_handler(CallbackQueryHandler(_gate_callback), group=GATE_GROUP)

# ========================= helpers for commands =========================
def _resolve_arg_username(context):
    if not context.args:
        return None, None
    raw = context.args[0]
    uid = store.get_uid_by_username(raw)
    return uid, store.norm_username(raw)

async def _admin_only(update):
    return store.is_admin(update.effective_user.id)

# ========================= commands =========================
async def cmd_orders(update, context):
    if not await _admin_only(update):
        return
    s = store.global_stats()
    text = (
        "<b>ORDERS</b>" + NL + NL
        + "Total Orders : " + str(s["total_orders"]) + NL
        + "Today's Orders : " + str(s["today_orders"]) + NL
        + "Total Revenue : " + store.fmt_money(s["total_revenue"]) + NL
        + "Today's Revenue : " + store.fmt_money(s["today_revenue"]) + NL
        + "Total Cancelled Orders : " + str(s["cancelled"])
    )
    await update.message.reply_text(text, parse_mode="HTML")
    raise ApplicationHandlerStop

async def cmd_stats(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    if not uname:
        await update.message.reply_text("Usage: /stats @username")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found (they must have started the bot).")
        raise ApplicationHandlerStop
    cs = store.customer_stats(uid)
    text = (
        "<b>STATS - @" + html.escape(uname) + "</b>" + NL + NL
        + "Total Orders : " + str(cs["total_orders"]) + NL
        + "Total Revenue : " + store.fmt_money(cs["total_revenue"]) + NL
        + "Type Of Customer : " + cs["type"]
    )
    await update.message.reply_text(text, parse_mode="HTML")
    raise ApplicationHandlerStop

async def cmd_ban(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    if not uname:
        await update.message.reply_text("Usage: /ban @username")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found (they must have started the bot).")
        raise ApplicationHandlerStop
    if store.is_admin(uid):
        await update.message.reply_text("You cannot ban an admin/owner.")
        raise ApplicationHandlerStop
    store.ban(uid)
    await update.message.reply_text("Banned @" + uname + ".")
    raise ApplicationHandlerStop

async def cmd_unban(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    if not uname:
        await update.message.reply_text("Usage: /unban @username")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found.")
        raise ApplicationHandlerStop
    store.unban(uid)
    await update.message.reply_text("Unbanned @" + uname + ".")
    raise ApplicationHandlerStop

async def cmd_maintenance(update, context):
    if not await _admin_only(update):
        return
    store.set_maintenance(True)
    await update.message.reply_text("Maintenance mode is now ON. Customers can't use the bot.")
    raise ApplicationHandlerStop

async def cmd_active(update, context):
    if not await _admin_only(update):
        return
    store.set_maintenance(False)
    await update.message.reply_text("Maintenance mode is now OFF. The bot is live again.")
    raise ApplicationHandlerStop

async def cmd_add(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    amount = store.parse_money(context.args[1]) if context.args and len(context.args) > 1 else None
    if not uname or amount is None:
        await update.message.reply_text("Usage: /add @username 10")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found (they must have started the bot).")
        raise ApplicationHandlerStop
    new_bal = store.wallet_add(uid, amount)
    await asyncio.to_thread(store.send_message_as_main, uid,
                            store.fmt_money(amount) + " successfully added to your wallet")
    await update.message.reply_text("Added " + store.fmt_money(amount) + " to @" + uname
                                    + ". New balance: " + store.fmt_money(new_bal))
    raise ApplicationHandlerStop

async def cmd_refund(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    amount = store.parse_money(context.args[1]) if context.args and len(context.args) > 1 else None
    if not uname or amount is None:
        await update.message.reply_text("Usage: /refund @username 10")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found.")
        raise ApplicationHandlerStop
    new_bal = store.wallet_add(uid, amount)
    await asyncio.to_thread(store.send_message_as_main, uid,
                            store.fmt_money(amount) + " refunded to your wallet")
    await update.message.reply_text("Refunded " + store.fmt_money(amount) + " to @" + uname
                                    + ". New balance: " + store.fmt_money(new_bal))
    raise ApplicationHandlerStop

async def cmd_admin(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    if not uname:
        await update.message.reply_text("Usage: /admin @username")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found (they must have started the bot).")
        raise ApplicationHandlerStop
    store.add_admin(uid)
    await asyncio.to_thread(store.send_message_as_main, uid,
                            "You are now an admin. Start the orders bot to receive order notifications.")
    await update.message.reply_text("@" + uname + " is now an admin.")
    raise ApplicationHandlerStop

async def cmd_removeadmin(update, context):
    if not await _admin_only(update):
        return
    uid, uname = _resolve_arg_username(context)
    if not uname:
        await update.message.reply_text("Usage: /removeadmin @username")
        raise ApplicationHandlerStop
    if uid is None:
        await update.message.reply_text("User @" + uname + " not found.")
        raise ApplicationHandlerStop
    store.remove_admin(uid)
    await update.message.reply_text("@" + uname + " is no longer an admin.")
    raise ApplicationHandlerStop

async def cmd_ad(update, context):
    if not await _admin_only(update):
        return
    msg = update.effective_message
    raw = msg.text if msg.text else (msg.caption or "")
    parts = raw.split(None, 1)
    content = parts[1] if len(parts) > 1 else ""
    photo = msg.photo[-1].file_id if msg.photo else None
    video = msg.video.file_id if getattr(msg, "video", None) else None
    is_main = (context.bot.token == store.MAIN_BOT_TOKEN)

    if not content and not photo and not video:
        await msg.reply_text("Usage: /ad your message (you can also attach a photo or video).")
        raise ApplicationHandlerStop

    def _broadcast():
        ok = 0
        for uid in store.all_user_ids():
            if (photo or video) and is_main:
                if photo:
                    r = store.api_call(store.MAIN_BOT_TOKEN, "sendPhoto", chat_id=uid,
                                       photo=photo, caption=(content or None), parse_mode="HTML")
                else:
                    r = store.api_call(store.MAIN_BOT_TOKEN, "sendVideo", chat_id=uid,
                                       video=video, caption=(content or None), parse_mode="HTML")
            else:
                if not content:
                    continue  # cross-bot media with no text -> nothing we can send
                r = store.api_call(store.MAIN_BOT_TOKEN, "sendMessage", chat_id=uid,
                                   text=content, parse_mode="HTML")
            if r and r.get("ok"):
                ok += 1
        return ok

    sent = await asyncio.to_thread(_broadcast)
    note = ""
    if (photo or video) and not is_main:
        note = NL + "(Tip: attach media with /ad on the MAIN bot to broadcast it.)"
    await msg.reply_text("Broadcast delivered to " + str(sent) + " users." + note)
    raise ApplicationHandlerStop

async def orders_start(update, context):
    """/start on the ORDERS bot - lets admins register to receive notifications."""
    user = update.effective_user
    if store.is_admin(user.id):
        await update.message.reply_text(
            "Orders bot ready. You will receive new order notifications here.")
    else:
        await update.message.reply_text("This bot is for store administrators only.")

# ========================= registration =========================
def register_commands(application):
    application.add_handler(CommandHandler("orders", cmd_orders), group=CMD_GROUP)
    application.add_handler(CommandHandler("stats", cmd_stats), group=CMD_GROUP)
    application.add_handler(CommandHandler("ban", cmd_ban), group=CMD_GROUP)
    application.add_handler(CommandHandler("unban", cmd_unban), group=CMD_GROUP)
    application.add_handler(CommandHandler("maintenance", cmd_maintenance), group=CMD_GROUP)
    application.add_handler(CommandHandler("active", cmd_active), group=CMD_GROUP)
    application.add_handler(CommandHandler("add", cmd_add), group=CMD_GROUP)
    application.add_handler(CommandHandler("refund", cmd_refund), group=CMD_GROUP)
    application.add_handler(CommandHandler("admin", cmd_admin), group=CMD_GROUP)
    application.add_handler(CommandHandler("removeadmin", cmd_removeadmin), group=CMD_GROUP)
    application.add_handler(CommandHandler("ad", cmd_ad), group=CMD_GROUP)
    # /ad with an attached photo/video (command sits in the caption)
    application.add_handler(
        MessageHandler((filters.PHOTO | filters.VIDEO) & filters.CaptionRegex(r"^/ad(\s|$)"), cmd_ad),
        group=CMD_GROUP,
    )

def register_order_buttons(application):
    application.add_handler(CallbackQueryHandler(on_order_action, pattern=r"^ord:"), group=CMD_GROUP)
