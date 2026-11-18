"""
Premium Villa - Crypto Payments module (payments.py)
Powered by our own on-chain verification engine (payments_engine.py):
  - each coin has ONE fixed deposit address that you (the admin) set
  - buyer picks a crypto, gets shown the exact amount + address, and pastes
    the transaction hash (TXID) back into the chat once they've paid
  - the bot verifies that hash directly against the blockchain (Blockstream/
    Tronscan/Solana RPC/BSC+ETH RPCs) - no third-party payment processor,
    no webhooks, nothing ever leaves Telegram

Uses raw API for ALL displays to support animated emojis (unchanged from
the previous version).
"""

import os
import json
import time
import html
import uuid
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
    ContextTypes,
)

import payments_engine as pe

NL = chr(10)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAY_FILE = os.path.join(BASE_DIR, "cryptos.json")
ORDERS_FILE = os.path.join(BASE_DIR, "orders.json")
ADMIN_ID = 0

BOT_TOKEN = None
TG_API = None

# ----- buyer payment flow tunables -----
PAY_WINDOW_MINUTES = 15      # how long a generated address+amount stays valid
PAY_COUNTDOWN_TICK = 1

_ACTIVE_TASKS = {}   # user_id -> countdown asyncio.Task

# ========================= storage =========================
def _default_data():
    return {"cryptos": [], "picker_text": "", "pay_image": None, "wallet_image": None, "wallet_choice_image": None}

def load_cryptos():
    data = pe.load_cryptos()
    if not isinstance(data, dict) or not isinstance(data.get("cryptos"), list):
        data = _default_data()
        save_cryptos(data)
    return data

def save_cryptos(data):
    pe.save_cryptos(data)

def all_cryptos():
    return pe.all_cryptos()

def enabled_cryptos():
    return pe.enabled_cryptos()

def get_crypto(cid):
    return pe.get_crypto(cid)

def _save_crypto(updated):
    pe.save_crypto(updated)

def _move_crypto(cid, direction):
    """direction: -1 to move up (earlier), +1 to move down (later).
    Display order on the buyer picker screen follows this list order."""
    data = load_cryptos()
    items = data["cryptos"]
    idx = next((i for i, c in enumerate(items) if c["id"] == cid), None)
    if idx is None:
        return False
    new_idx = idx + direction
    if new_idx < 0 or new_idx >= len(items):
        return False
    items[idx], items[new_idx] = items[new_idx], items[idx]
    save_cryptos(data)
    return True

def _new_id():
    import uuid
    return uuid.uuid4().hex[:8]

def _unused_chains():
    used = {c.get("chain") for c in all_cryptos()}
    return [cid for cid in pe.SUPPORTED_CHAINS if cid not in used]

# ========================= formatting helpers =========================
def _fmt_money(value):
    try:
        v = float(value)
    except Exception:
        return "$0"
    if abs(v - round(v)) < 0.005:
        return "$" + str(int(round(v)))
    return "$" + ("%.2f" % v)

def _fmt_crypto(amount):
    try:
        v = float(amount)
    except Exception:
        return str(amount)
    s = ("%.8f" % v).rstrip("0").rstrip(".")
    return s or "0"

def _mmss(seconds):
    seconds = max(0, int(seconds))
    return "%02d:%02d" % (seconds // 60, seconds % 60)

# ========================= RAW API for animated emojis =========================
def _build_raw_keyboard(rows_spec):
    raw_rows = []
    for row in rows_spec:
        raw_row = []
        for btn in row:
            raw_btn = {"text": btn["text"], "callback_data": btn["callback_data"]}
            eid = btn.get("emoji_id")
            if eid and str(eid).isdigit():
                raw_btn["icon_custom_emoji_id"] = eid
            raw_row.append(raw_btn)
        raw_rows.append(raw_row)
    return {"inline_keyboard": raw_rows}

class TelegramRawError(Exception):
    pass

def _raw_check(resp_json, what):
    if isinstance(resp_json, dict) and resp_json.get("ok") is False:
        desc = resp_json.get("description")
        print(f"[payments] Telegram API rejected {what}: {desc}")
        raise TelegramRawError(f"{what}: {desc}")
    return resp_json

async def raw_send_message(chat_id, text, keyboard_rows, photo=None, parse_mode="HTML"):
    global TG_API, BOT_TOKEN
    if not TG_API:
        TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
    import httpx
    if photo:
        payload = {
            "chat_id": chat_id, "photo": photo, "caption": text,
            "parse_mode": parse_mode, "reply_markup": _build_raw_keyboard(keyboard_rows),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{TG_API}/sendPhoto", json=payload)
        return _raw_check(r.json(), "sendPhoto")
    payload = {
        "chat_id": chat_id, "text": text, "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{TG_API}/sendMessage", json=payload)
    return _raw_check(r.json(), "sendMessage")

async def raw_edit_message(chat_id, message_id, text, keyboard_rows, photo=None, parse_mode="HTML"):
    global TG_API, BOT_TOKEN
    if not TG_API:
        TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
    import httpx
    if photo:
        payload = {
            "chat_id": chat_id, "message_id": message_id,
            "media": {"type": "photo", "media": photo, "caption": text, "parse_mode": parse_mode},
            "reply_markup": _build_raw_keyboard(keyboard_rows),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{TG_API}/editMessageMedia", json=payload)
        return _raw_check(r.json(), "editMessageMedia")
    payload = {
        "chat_id": chat_id, "message_id": message_id, "text": text,
        "parse_mode": parse_mode, "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{TG_API}/editMessageText", json=payload)
    return _raw_check(r.json(), "editMessageText")

# ========================= admin panels =========================
def admin_home_panel():
    cryptos = all_cryptos()
    lines = ["<b>CRYPTO PAYMENTS (on-chain, no processor)</b>", ""]
    if not cryptos:
        lines.append("No cryptocurrencies configured yet. Tap 'Add Crypto' to add one.")
    else:
        for c in cryptos:
            state = "ON" if c.get("enabled") else "OFF"
            addr = c.get("address") or "(no address set)"
            emoji_info = " 🎨" if c.get("emoji_id") else ""
            lines.append("<b>" + html.escape(c["name"]) + emoji_info + "</b>  [" + state + "]")
            lines.append("  " + html.escape(pe.chain_label(c.get("chain"))))
            lines.append("  <code>" + html.escape(addr) + "</code>")
            lines.append("")
    kb = []
    for c in cryptos:
        tag = " (off)" if not c.get("enabled") else ""
        emoji_tag = " 🎨" if c.get("emoji_id") else ""
        kb.append([InlineKeyboardButton(c["name"] + emoji_tag + tag, callback_data="pay:c:" + c["id"])])
    kb.append([InlineKeyboardButton("➕ Add Crypto", callback_data="pay:add")])
    kb.append([InlineKeyboardButton("🧪 Test Transaction", callback_data="pay:test")])
    kb.append([InlineKeyboardButton("📝 Edit Page Text", callback_data="pay:pickedit")])
    kb.append([InlineKeyboardButton("🖼️ Payment Image", callback_data="pay:img")])
    kb.append([InlineKeyboardButton("👛 Wallet Image", callback_data="pay:walletimg")])
    kb.append([InlineKeyboardButton("💳 Wallet Checkout Image", callback_data="pay:walletchoiceimg")])
    kb.append([InlineKeyboardButton("❌ Close", callback_data="pay:close")])
    return NL.join(lines), InlineKeyboardMarkup(kb)

def crypto_panel(cid):
    c = get_crypto(cid)
    if not c:
        return None
    addr = c.get("address") or "(no address set)"
    text = (
        "<b>" + html.escape(c["name"]) + "</b>" + NL
        + "Chain: <code>" + html.escape(pe.chain_label(c.get("chain"))) + "</code>" + NL
        + "Status: " + ("✅ Enabled" if c.get("enabled") else "❌ Disabled") + NL
        + "Min confirmations: " + str(c.get("min_conf", 1)) + NL
        + "Payment window: " + str(int(c.get("window_minutes") or PAY_WINDOW_MINUTES)) + " min" + NL
        + "Animated Emoji: " + ("✅ Set" if c.get("emoji_id") else "❌ Not set") + NL + NL
        + "Address:" + NL + "<code>" + html.escape(addr) + "</code>"
    )
    toggle = "Disable" if c.get("enabled") else "Enable"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📬 Edit Address", callback_data="pay:addr:" + cid)],
        [InlineKeyboardButton("🔢 Edit Min Confirmations", callback_data="pay:conf:" + cid)],
        [InlineKeyboardButton("⏱️ Edit Payment Window", callback_data="pay:window:" + cid)],
        [InlineKeyboardButton("🎨 Set Animated Emoji", callback_data="pay:emoji:" + cid)],
        [InlineKeyboardButton("⬆️ Move Up", callback_data="pay:up:" + cid),
         InlineKeyboardButton("⬇️ Move Down", callback_data="pay:dn:" + cid)],
        [InlineKeyboardButton("🔘 " + toggle, callback_data="pay:tgl:" + cid)],
        [InlineKeyboardButton("🧪 Test This Crypto", callback_data="pay:testc:" + cid)],
        [InlineKeyboardButton("🗑️ Remove", callback_data="pay:rm:" + cid)],
        [InlineKeyboardButton("🔙 Back", callback_data="pay:admin")],
    ])
    return text, kb

def _format_test_result(crypto, txhash, res):
    lines = ["<b>TEST RESULT - " + html.escape(crypto["name"]) + "</b>", pe.chain_label(crypto.get("chain")), "",
              "Hash: <code>" + html.escape(txhash) + "</code>", ""]
    if not res.get("ok"):
        lines.append("Could not query the blockchain. Error: " + html.escape(str(res.get("error"))))
        return NL.join(lines)
    if not res.get("found"):
        lines.append("Transaction not found on this chain.")
        if res.get("error"):
            lines.append(html.escape(str(res.get("error"))))
        return NL.join(lines)
    dec = int(crypto.get("decimals", 8))
    amount = res.get("amount", 0.0)
    amount_str = pe.fmt_crypto(amount, dec)
    if crypto.get("is_usd_stable"):
        usd_str = pe.fmt_money(amount)
    else:
        price = pe.get_usd_price(crypto.get("coingecko_id"))
        usd_str = pe.fmt_money(amount * price) if price else "price unavailable"
    lines.append("Amount: " + amount_str + " " + crypto["name"] + " (approx " + usd_str + ")")
    lines.append("From: <code>" + html.escape(str(res.get("from_address") or "unknown")) + "</code>")
    lines.append("To: <code>" + html.escape(str(res.get("to_address") or "unknown")) + "</code>")
    lines.append("Confirmations: " + str(res.get("confirmations", 0)))
    lines.append("Confirmed: " + ("Yes" if res.get("confirmed") else "No"))
    target = crypto.get("address")
    if target:
        matches = pe.addr_match(res.get("to_address"), target)
        lines.append("Matches your address: " + ("Yes" if matches else "No"))
    return NL.join(lines)

# ========================= render helper for admin =========================
async def _safe_edit(query, context, text, kb=None):
    msg = query.message
    if msg.photo:
        try:
            await msg.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=kb, parse_mode="HTML")
        return
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

# ========================= buyer payment flow =========================
# Each "order expired" notice is sent at most once per order, even across
# restarts/crashes: the order is recorded here BEFORE the message is sent.
NOTIFIED_FILE = os.path.join(BASE_DIR, "expired_notified.json")

def _expiry_key(user_id, order):
    return "%s:%s:%s" % (user_id, int(order.get("deadline") or 0), order.get("msg_id"))

def _load_notified():
    try:
        with open(NOTIFIED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _was_notified(key):
    return key in _load_notified()

def _mark_notified(key):
    keys = _load_notified()
    if key in keys:
        return
    keys.append(key)
    keys = keys[-1000:]
    tmp = NOTIFIED_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(keys, f)
        os.replace(tmp, NOTIFIED_FILE)
    except Exception as e:
        print(f"[payments] could not record expiry notice: {e}")

STALE_NOTIFY_WINDOW = 3600   # only tell customers about orders that expired within the last hour

EXPIRED_TEXT = (
    "⏰ This Order Has Expired. Please Create A New Order To Proceed With Your Purchase."
    + NL + NL
    + "If You Have Already Made A Payment And It Was Not Detected, Kindly Contact Support For Assistance."
)

def get_picker_text():
    return load_cryptos().get("picker_text") or "Please choose your preferred cryptocurrency for payment"

def set_picker_text(t):
    data = load_cryptos()
    data["picker_text"] = t
    save_cryptos(data)

def get_pay_image():
    return load_cryptos().get("pay_image")

def set_pay_image(file_id):
    data = load_cryptos()
    data["pay_image"] = file_id
    save_cryptos(data)

def get_wallet_image():
    return load_cryptos().get("wallet_image") or get_pay_image()

def get_wallet_choice_image():
    """Image for the 'Your current balance is ...' (Use Wallet Balance / Use Crypto)
    screen. Own setting; falls back to the Wallet image, then the Payment image."""
    return load_cryptos().get("wallet_choice_image") or get_wallet_image()

def set_wallet_choice_image(file_id):
    data = load_cryptos()
    data["wallet_choice_image"] = file_id
    save_cryptos(data)

def _btn_emoji(key, fallback_key=None):
    """Animated/custom emoji id for a button (admin-settable via action emojis)."""
    try:
        import bot
        return bot.get_action_emoji(key) or (bot.get_action_emoji(fallback_key) if fallback_key else None)
    except Exception:
        return None

def set_wallet_image(file_id):
    data = load_cryptos()
    data["wallet_image"] = file_id
    save_cryptos(data)

def _is_admin(uid):
    try:
        import store
        return store.is_admin(uid)
    except Exception:
        return uid == ADMIN_ID

def _load_orders():
    if not os.path.exists(ORDERS_FILE):
        return {}
    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_orders(d):
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def increment_order_count(user_id):
    d = _load_orders()
    key = str(user_id)
    d[key] = int(d.get(key, 0)) + 1
    _save_orders(d)
    return d[key]

def _amount_display(order):
    disp_usd = order.get("charge_usd", order.get("usd"))
    crypto_amount = order.get("crypto_amount")
    crypto_name = order.get("crypto_name") or ""
    if crypto_amount is None:
        return _fmt_money(disp_usd)
    return _fmt_crypto(crypto_amount) + " " + crypto_name + " (" + _fmt_money(disp_usd) + ")"

# ========== PICKER SCREEN WITH ANIMATED EMOJIS using RAW API ==========
# Fixed picker layout, one inner list per row. Matches by crypto id, so it does
# not depend on the order in cryptos.json. Disabled cryptos are simply skipped
# (their row gets shorter); any crypto not listed here (e.g. one added later)
# goes in extra rows of 3 at the bottom.
PICKER_LAYOUT = [
    ["btc"],
    ["ltc", "sol", "eth"],
    ["usdt_trc20", "usdt_bep20"],
    ["usdc_erc20", "usdc_sol"],
]

def _build_crypto_buttons_raw(cryptos):
    by_id = {c.get("id"): c for c in cryptos}
    placed = set()

    def make(c):
        button = {"text": c["name"], "callback_data": "pay:pick:" + c["id"]}
        if c.get("emoji_id"):
            button["emoji_id"] = c["emoji_id"]
        return button

    rows = []
    for ids in PICKER_LAYOUT:
        row = [make(by_id[i]) for i in ids if i in by_id]
        placed.update(ids)
        if row:
            rows.append(row)
    rest = [make(c) for c in cryptos if c.get("id") not in placed]
    for i in range(0, len(rest), 3):
        rows.append(rest[i:i + 3])
    return rows

def _picker_screen_raw(is_admin=False, show_wallet=False, wallet_balance=0.0, note=None):
    body = get_picker_text()
    text = "<b>" + html.escape(body) + "</b>"
    if note:
        text += NL + NL + note

    keyboard_rows = _build_crypto_buttons_raw(enabled_cryptos())

    wallet_emoji_id = None
    try:
        import bot
        wallet_emoji_id = bot.get_action_emoji("use_wallet")
    except Exception:
        pass

    if show_wallet and wallet_balance > 0:
        wallet_btn = {"text": f"Use Wallet (${wallet_balance:.2f})", "callback_data": "pay:usewallet"}
        if wallet_emoji_id:
            wallet_btn["emoji_id"] = wallet_emoji_id
        keyboard_rows.append([wallet_btn])

    keyboard_rows.append([{"text": "Cancel", "callback_data": "pay:cancel", "emoji_id": _btn_emoji("cancel")}])

    if is_admin:
        keyboard_rows.append([
            {"text": "Edit Text", "callback_data": "pay:pickedit"},
            {"text": "Change Image", "callback_data": "pay:pickimg"},
        ])

    return text, keyboard_rows, get_pay_image()

async def _render_buyer_raw(query, context, text, keyboard_rows, photo=None):
    msg = query.message
    chat_id = msg.chat_id
    if photo:
        if msg.photo:
            try:
                await raw_edit_message(chat_id, msg.message_id, text, keyboard_rows, photo)
                return
            except Exception:
                pass
        try:
            await msg.delete()
        except Exception:
            pass
        await raw_send_message(chat_id, text, keyboard_rows, photo)
    else:
        if not msg.photo:
            try:
                await raw_edit_message(chat_id, msg.message_id, text, keyboard_rows)
                return
            except Exception:
                pass
        try:
            await msg.delete()
        except Exception:
            pass
        await raw_send_message(chat_id, text, keyboard_rows)

async def raw_edit_message_caption(chat_id, message_id, caption, keyboard_rows, parse_mode="HTML"):
    """Edit ONLY the caption/keyboard of a message that already has a photo -
    unlike editMessageText (which Telegram rejects on photo messages) or
    editMessageMedia (which needlessly re-specifies the photo), this is the
    correct call for updating text on a message that already has an image."""
    global TG_API, BOT_TOKEN
    if not TG_API:
        TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
    import httpx
    payload = {
        "chat_id": chat_id, "message_id": message_id, "caption": caption,
        "parse_mode": parse_mode, "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{TG_API}/editMessageCaption", json=payload)
    return _raw_check(r.json(), "editMessageCaption")

async def _show_screen_raw(context, order, text, keyboard_rows, photo=None):
    """Show a screen in the order's live message, switching the image too.
    photo -> swap the picture in place (editMessageMedia) when the message already
    has one, otherwise delete + resend (a text message cannot become a photo).
    No photo -> plain caption/text edit. Keeps order['msg_id'/'has_photo'] current."""
    chat_id, msg_id = order["chat_id"], order["msg_id"]
    has_photo = bool(order.get("has_photo"))
    if photo and has_photo:
        try:
            await raw_edit_message(chat_id, msg_id, text, keyboard_rows, photo)
            return
        except Exception as e:
            print(f"[show_screen_raw] media edit failed, resending: {e}")
    if photo:
        await _replace_msg_raw(context, order, text, keyboard_rows, photo)
        return
    await _edit_live_raw(context, chat_id, msg_id, has_photo, text, keyboard_rows)

async def _delete_order_msg(context, order):
    """Delete the live payment-selection message once (idempotent)."""
    if order.get("_msg_deleted") or not order.get("msg_id"):
        return
    try:
        await context.bot.delete_message(order["chat_id"], order["msg_id"])
    except Exception:
        pass
    order["_msg_deleted"] = True

async def _edit_live_raw(context, chat_id, msg_id, has_photo, text, keyboard_rows=None):
    try:
        if keyboard_rows is None:
            keyboard_rows = []
        if has_photo:
            await raw_edit_message_caption(chat_id, msg_id, text, keyboard_rows)
        else:
            await raw_edit_message(chat_id, msg_id, text, keyboard_rows)
    except Exception as e:
        print(f"[edit_live_raw] Error: {e}")

# ===================== WALLET =====================
def _wallet_balance(user_id):
    try:
        import store
        return store.wallet_balance(user_id)
    except Exception:
        return 0.0

def _wallet_home_screen_raw(user_id):
    bal = _wallet_balance(user_id)
    text = "<b>Your current balance is: " + _fmt_money(bal) + "</b>"
    deposit_emoji_id = None
    back_emoji_id = None
    try:
        import bot
        deposit_emoji_id = bot.get_action_emoji("deposit")
        back_emoji_id = bot.get_action_emoji("back_button")
    except Exception:
        pass
    keyboard_rows = [
        [{"text": "Deposit", "callback_data": "pay:deposit", "emoji_id": deposit_emoji_id}],
        [{"text": "Back", "callback_data": "pay:walletclose", "emoji_id": back_emoji_id}]
    ]
    return text, keyboard_rows, get_wallet_image()

async def open_wallet(query, context):
    user_id = query.from_user.id
    _cancel_task(user_id)
    context.user_data.pop("pay_order", None)
    text, keyboard_rows, photo = _wallet_home_screen_raw(user_id)
    if photo:
        await raw_send_message(query.message.chat_id, text, keyboard_rows, photo)
    else:
        await raw_send_message(query.message.chat_id, text, keyboard_rows)
    await query.answer()

async def begin_payment_from_cart(query, context):
    user_id = query.from_user.id
    try:
        import cart
        items = cart._get_cart(user_id)
        usd = cart._cart_total(items)
    except Exception:
        items, usd = [], 0.0
    if not items:
        await _render_buyer_raw(query, context, "<b>🛒 Your cart is empty.</b>",
                                [[{"text": "Back", "callback_data": "cart:open"}]])
        return
    await _begin_payment_raw(query, context, [dict(it) for it in items], usd, source="cart")

async def begin_payment_buynow(query, context, item):
    user_id = query.from_user.id
    try:
        import cart
        usd = cart._line_total(item)
    except Exception:
        usd = 0.0
    await _begin_payment_raw(query, context, [dict(item)], usd, source="buynow")

async def cmd_cancel(update, context):
    user_id = update.effective_user.id
    order = context.user_data.get("pay_order")
    if not order or order.get("state") not in ("choosing", "await_payment"):
        await update.message.reply_text("You don't have an ongoing order.")
        return
    _cancel_task(user_id)
    context.user_data.pop("pay_order", None)
    try:
        import analytics
        analytics.track(user_id, "cancel", aid=order.get("aid"))
        await analytics.notify(context.bot, order.get("aid"), user_id, "cancel")
    except Exception:
        pass
    try:
        await context.bot.delete_message(order["chat_id"], order["msg_id"])
    except Exception:
        pass
    await update.message.reply_text("✅ Your ongoing order has been cancelled. You can start a new one now.")

async def _begin_payment_raw(query, context, items, usd, source="cart"):
    user_id = query.from_user.id
    existing = context.user_data.get("pay_order")
    if existing and existing.get("state") == "await_payment":
        # Can't use query.answer(..., show_alert=True) here: every caller in
        # cart.py has already answered this tap, and Telegram only allows one
        # answer per callback query - a second one is silently rejected, which
        # is why the guard blocked the order but no message ever showed up.
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=("You already have an ongoing order. Please use /cancel to cancel "
                      "the previous transaction and make a new one."),
            )
        except Exception as e:
            print(f"[payments] could not send ongoing-order notice: {e}")
        return
    if not items:
        await _render_buyer_raw(query, context, "<b>❌ Nothing to pay for.</b>",
                                [[{"text": "Back", "callback_data": "cart:open"}]])
        return
    if not enabled_cryptos():
        await _render_buyer_raw(query, context,
                                "<b>⚠️ Payment is not available right now.</b>" + NL
                                + "No cryptocurrency is configured. Please contact support.",
                                [[{"text": "Back", "callback_data": "cart:open"}]])
        return
    label = ", ".join((it.get("title", "Order") + " (x" + str(it.get("qty", 1)) + ")") for it in items)
    _cancel_task(user_id)
    context.user_data["pay_order"] = {"state": "choosing", "label": label, "usd": float(usd),
                                      "charge_usd": float(usd), "wallet_used": 0.0,
                                      "user_id": user_id, "items": [dict(it) for it in items],
                                      "source": source, "aid": uuid.uuid4().hex[:10]}
    try:
        import analytics
        analytics.track_pay_page(user_id, context.user_data["pay_order"]["aid"], items, usd, source)
        await analytics.notify(context.bot, context.user_data["pay_order"]["aid"], user_id, "open",
                               items=items, total=usd, source=source)
    except Exception:
        pass
    bal = _wallet_balance(user_id)
    text, keyboard_rows, photo = _picker_screen_raw(_is_admin(user_id), show_wallet=True, wallet_balance=bal)
    await _render_buyer_raw(query, context, text, keyboard_rows, photo)

async def _on_pick_raw(query, context, cid):
    user_id = query.from_user.id
    order = context.user_data.get("pay_order")
    if not order:
        await query.answer("Session expired, please start again", show_alert=True)
        return
    crypto = get_crypto(cid)
    if not crypto or not crypto.get("enabled") or not crypto.get("address"):
        await query.answer("That option is unavailable", show_alert=True)
        return

    charge = float(order.get("charge_usd", order.get("usd", 0)))
    await query.answer("Preparing your payment address…")

    crypto_amount, _price = pe.usd_to_crypto(charge, crypto)
    if crypto_amount is None:
        await context.bot.send_message(query.message.chat_id, "⚠️ Price feed unavailable right now. Please try again or pick another crypto.")
        return

    order.update({
        "state": "await_payment", "cid": cid,
        "crypto_name": crypto["name"],
        "crypto_amount": float(crypto_amount),
        "address": crypto["address"],
        "decimals": int(crypto.get("decimals", 8)),
        "is_stable": bool(crypto.get("is_usd_stable")),
        "min_conf": int(crypto.get("min_conf", 1)),
        "deadline": time.time() + int(crypto.get("window_minutes") or PAY_WINDOW_MINUTES) * 60,
        "started_at": time.time(),
        "hash": None,
        "chat_id": query.message.chat_id, "msg_id": query.message.message_id,
        "has_photo": bool(query.message.photo),
    })
    context.user_data["pay_order"] = order
    try:
        import analytics
        analytics.track(user_id, "crypto", aid=order.get("aid"), crypto=crypto["name"], total=round(charge, 2))
        await analytics.notify(context.bot, order.get("aid"), user_id, "crypto", crypto=crypto["name"],
                               crypto_amount=_fmt_crypto(crypto_amount) + " " + crypto["name"])
    except Exception:
        pass
    remaining = int(order["deadline"] - time.time())
    text = _payment_detail_text(order, remaining)
    await _edit_live_raw(context, order["chat_id"], order["msg_id"], order["has_photo"], text)
    _spawn(user_id, _countdown_raw(context, user_id))

def _payment_detail_text(order, remaining):
    disp_usd = order.get("charge_usd", order.get("usd"))
    crypto_amount = order.get("crypto_amount")
    crypto_name = html.escape(order.get("crypto_name") or "")
    if crypto_amount is None:
        num_str = html.escape(_fmt_money(disp_usd))
        amt_line = num_str
        amt_code = num_str
    else:
        num_str = html.escape(_fmt_crypto(crypto_amount))
        usd_str = html.escape(_fmt_money(disp_usd))
        amt_line = num_str + " " + crypto_name + " (" + usd_str + ")"
        amt_code = "<code>" + num_str + "</code> " + crypto_name + " (" + usd_str + ")"
    lines = [
        "<b>Product :</b> " + html.escape(order.get("label", "Wallet Deposit")),
        "",
        "<b>Crypto :</b> " + crypto_name,
        "",
        "<b>Amount :</b> " + amt_line,
        "",
        "<b>Time Left :</b> " + _mmss(remaining),
        "",
        "Kindly Send The Funds Before The Timer Runs Out.",
        "",
        "Please Send Exactly " + amt_code + " To:",
        "",
        "<code>" + html.escape(order["address"]) + "</code>",
        "",
        "After sending, please paste the transaction hash (TXID) here in the chat and we'll verify it on the blockchain.",
    ]
    return NL.join(lines)

async def _countdown_raw(context, user_id):
    try:
        while True:
            order = context.user_data.get("pay_order")
            if not order or order.get("user_id") != user_id or order.get("state") != "await_payment":
                return
            remaining = int(order["deadline"] - time.time())
            if remaining <= 0:
                await _expire_order_raw(context, user_id)
                return
            text = _payment_detail_text(order, remaining)
            await _edit_live_raw(context, order["chat_id"], order["msg_id"], order["has_photo"], text)
            await asyncio.sleep(min(PAY_COUNTDOWN_TICK, max(1, remaining)))
    except asyncio.CancelledError:
        return
    except Exception:
        return

async def _expire_order_raw(context, user_id):
    order = context.user_data.get("pay_order")
    if not order:
        return
    order["state"] = "expired"
    try:
        import analytics
        analytics.track(user_id, "expired", aid=order.get("aid"))
        await analytics.notify(context.bot, order.get("aid"), user_id, "expired")
    except Exception:
        pass
    try:
        await context.bot.delete_message(order["chat_id"], order["msg_id"])
    except Exception:
        pass
    key = _expiry_key(user_id, order)
    if not _was_notified(key):
        _mark_notified(key)      # record first: at most one notice, ever
        try:
            await context.bot.send_message(order["chat_id"], EXPIRED_TEXT, parse_mode="HTML")
        except Exception:
            pass
    context.user_data.pop("pay_order", None)
    _ACTIVE_TASKS.pop(user_id, None)

def _validate_payment(order, res):
    """Returns (ok, reason_if_not_ok)."""
    if not res or not res.get("ok"):
        return False, "⚠️ Could not reach the blockchain to verify that hash. Please try again in a moment."
    if not res.get("found"):
        return False, "Transaction not found yet. If you just sent it, wait a minute and paste the hash again."
    if not res.get("status_ok"):
        return False, "❌ That transaction failed on-chain."
    if not pe.addr_match(res.get("to_address"), order["address"]):
        return False, "❌ That payment did not go to our address."
    if not pe.amount_ok(res.get("amount"), order["crypto_amount"]):
        return False, ("❌ Amount does not match. Please send exactly "
                        + _fmt_crypto(order["crypto_amount"]) + " " + order["crypto_name"] + ".")
    if not pe.time_ok(order.get("started_at"), res):
        return False, "❌ That transaction predates this payment - please start a new order."
    min_conf = int(order.get("min_conf", 1))
    confs = int(res.get("confirmations", 0))
    if confs < min_conf:
        return False, ("🔄 Transaction found! Waiting for confirmations (" + str(confs) + "/" + str(min_conf)
                        + "). Please check back shortly and paste the same hash again.")
    return True, None

async def on_payment_hash_text(update, context, order):
    user_id = order.get("user_id") or update.effective_user.id
    crypto = get_crypto(order.get("cid"))
    if not crypto:
        return
    raw_text = (update.message.text or "").strip()
    if not raw_text:
        return
    txhash = pe.extract_hash(raw_text)
    if pe.hash_used(txhash):
        try:
            await update.message.reply_text("❌ That transaction hash has already been used.")
        except Exception:
            pass
        return

    wait_msg = await update.message.reply_text("🔄 Verifying the transaction on the blockchain, please wait...")
    res = await pe.verify_tx(crypto, txhash)

    ok, reason = _validate_payment(order, res)
    if not ok:
        try:
            await wait_msg.edit_text(reason)
        except Exception:
            pass
        return

    order["hash"] = txhash
    pe.mark_hash_used(txhash)
    _cancel_task(user_id)
    try:
        await wait_msg.delete()
    except Exception:
        pass
    await _mark_received_raw(context, user_id, res)

async def _mark_received_raw(context, user_id, verify_res=None):
    order = context.user_data.get("pay_order")
    if not order:
        return
    order["state"] = "done"
    await _delete_order_msg(context, order)

    if order.get("kind") == "deposit":
        amount = float(order.get("usd", 0) or 0)
        new_bal = amount
        try:
            import store
            new_bal = store.wallet_add(user_id, amount)
        except Exception:
            pass
        msg = (
            "<b>✅ We Have Received The Payment</b>" + NL + NL
            + _fmt_money(amount) + " has been added to your wallet." + NL + NL
            + "Your current balance is: <b>" + _fmt_money(new_bal) + "</b>"
        )
        try:
            await context.bot.send_message(order["chat_id"], msg, parse_mode="HTML")
        except Exception:
            pass
        context.user_data.pop("pay_order", None)
        _ACTIVE_TASKS.pop(user_id, None)
        return

    wallet_used = float(order.get("wallet_used", 0) or 0)
    if wallet_used > 0:
        try:
            import store
            store.wallet_deduct(user_id, wallet_used)
        except Exception:
            pass
    await _finish_purchase_raw(context, user_id, order)

def _success_video(order):
    """The payment-success video of the first purchased product that has one: (file_id, kind) or (None, None)."""
    try:
        import store
        for it in (order.get("items") or []):
            prod = None
            if it.get("pid"):
                prod = store.get_product(it["pid"])
            if not prod and it.get("product"):
                nm = (it.get("product") or "").strip().lower()
                for pr in store.load_products()["items"].values():
                    if (pr.get("name") or "").strip().lower() == nm:
                        prod = pr
                        break
            if prod and prod.get("success_video"):
                return prod["success_video"], prod.get("success_video_type") or "video"
    except Exception as e:
        print(f"[payments] success video lookup failed: {e}")
    return None, None

async def _finish_purchase_raw(context, user_id, order):
    # Remove the leftover payment-selection / wallet-choice message so only the
    # "Payment Received Successfully" message remains in the chat.
    await _delete_order_msg(context, order)
    count = increment_order_count(user_id)
    order_id = str(user_id) + str(count)
    try:
        import analytics
        analytics.track(user_id, "paid", aid=order.get("aid"), order_id=order_id,
                        total=round(float(order.get("usd", 0) or 0), 2),
                        method=("wallet" if order.get("wallet_full") or not order.get("crypto_name") else "crypto"))
        await analytics.notify(context.bot, order.get("aid"), user_id, "paid", order_id=order_id)
    except Exception:
        pass
    msg = (
        "<b>Payment Received Successfully!</b>" + NL + NL
        + "Chef Boba is preparing your order." + NL + NL
        + "<b>Order ID:</b> <code>" + html.escape(order_id) + "</code>" + NL + NL
        + "Your order will be delivered shortly. Thank you for your purchase!"
    )
    video, vkind = _success_video(order)
    sent = False
    if video:                                   # same message: video on top, text as its caption
        try:
            if vkind == "animation":
                await context.bot.send_animation(order["chat_id"], video, caption=msg, parse_mode="HTML")
            else:
                await context.bot.send_video(order["chat_id"], video, caption=msg, parse_mode="HTML")
            sent = True
        except Exception as e:
            print(f"[payments] could not send payment video: {e}")
    if not sent:
        try:
            await context.bot.send_message(order["chat_id"], msg, parse_mode="HTML")
        except Exception:
            pass
    try:
        import cart
        if order.get("source") != "buynow":
            cart._set_cart(user_id, [])
    except Exception:
        pass
    try:
        import myorders
        myorders.record_purchase(user_id, order_id, order)
    except Exception as e:
        print(f"[payments] could not save purchase to My Orders: {e}")
    try:
        import orders, store
        record = {
            "order_id": order_id,
            "user_id": user_id,
            "username": store.get_username(user_id),
            "items": order.get("items", []),
            "crypto": order.get("crypto_name") or ("Wallet" if order.get("wallet_full") else None),
            "hash": order.get("hash"),
            "amount": float(order.get("usd", 0) or 0),
        }
        await orders.send_new_order(record)
    except Exception:
        pass
    context.user_data.pop("pay_order", None)
    _ACTIVE_TASKS.pop(user_id, None)

def _cancel_task(user_id):
    t = _ACTIVE_TASKS.pop(user_id, None)
    try:
        current = asyncio.current_task()
    except Exception:
        current = None
    if t and t is not current and not t.done():
        t.cancel()

def _spawn(user_id, coro):
    _cancel_task(user_id)
    try:
        _ACTIVE_TASKS[user_id] = asyncio.create_task(coro)
    except RuntimeError:
        pass

# ========================= DEPOSIT HANDLERS =========================
async def _handle_deposit_amount(update, context):
    order = context.user_data.get("pay_order")
    if not order or order.get("state") != "await_deposit_amount":
        return
    amt = _parse_money(update.message.text)
    try:
        await update.message.delete()
    except Exception:
        pass
    if amt is None:
        try:
            await context.bot.send_message(order["chat_id"], "Please enter a valid amount (example: 10 or $10).")
        except Exception:
            pass
        return
    order["usd"] = float(amt)
    order["charge_usd"] = float(amt)
    order["label"] = "Wallet Deposit"
    order["state"] = "choosing"
    context.user_data["pay_order"] = order
    note = "💰 Depositing: <b>" + _fmt_money(amt) + "</b>"
    text, keyboard_rows, photo = _picker_screen_raw(_is_admin(order["user_id"]), note=note)
    await _replace_msg_raw(context, order, text, keyboard_rows, photo)

async def _handle_wallet_amount(update, context):
    order = context.user_data.get("pay_order")
    if not order or order.get("state") != "await_wallet_amount":
        return
    user_id = order["user_id"]
    amt = _parse_money(update.message.text)
    try:
        await update.message.delete()
    except Exception:
        pass
    bal = _wallet_balance(user_id)
    total = float(order.get("usd", 0))
    if amt is None or amt <= 0:
        try:
            await context.bot.send_message(order["chat_id"], "Please enter a valid amount (example: 1 or $1).")
        except Exception:
            pass
        return
    use = min(amt, bal, total)
    order["wallet_used"] = round(use, 2)
    order["charge_usd"] = round(max(0.0, total - use), 2)
    if order["charge_usd"] <= 0:
        order["wallet_full"] = True
        order["state"] = "done"
        context.user_data["pay_order"] = order
        try:
            import store
            store.wallet_deduct(user_id, order["wallet_used"])
        except Exception:
            pass
        await _finish_purchase_raw(context, user_id, order)
        return
    order["state"] = "choosing"
    context.user_data["pay_order"] = order
    note = ("💳 Wallet applied: <b>" + _fmt_money(order["wallet_used"]) + "</b>" + NL
            + "💰 Remaining to pay: <b>" + _fmt_money(order["charge_usd"]) + "</b>")
    text, keyboard_rows, photo = _picker_screen_raw(_is_admin(user_id), note=note)
    await _replace_msg_raw(context, order, text, keyboard_rows, photo)

def _parse_money(text):
    try:
        import store
        return store.parse_money(text)
    except Exception:
        pass
    import re as _re
    if not text:
        return None
    m = _re.search(r"[-+]?\d*\.?\d+", str(text).replace(",", "").replace("$", ""))
    if not m:
        return None
    try:
        v = float(m.group(0))
    except Exception:
        return None
    return v if v > 0 else None

async def _replace_msg_raw(context, order, text, keyboard_rows, photo=None):
    chat_id = order.get("chat_id")
    old_id = order.get("msg_id")
    if old_id:
        try:
            await context.bot.delete_message(chat_id, old_id)
        except Exception:
            pass
    if photo is not None:
        m = await raw_send_message(chat_id, text, keyboard_rows, photo)
    else:
        m = await raw_send_message(chat_id, text, keyboard_rows)
    if isinstance(m, dict) and m.get("result"):
        order["msg_id"] = m["result"]["message_id"]
        order["_msg_deleted"] = False
    order["has_photo"] = photo is not None
    return m

# ========================= CALLBACKS =========================
async def _on_callback(update, context):
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith("pay:"):
        return
    user_id = query.from_user.id
    action = data[4:]

    if action.startswith("pick:"):
        await _on_pick_raw(query, context, action[5:])
        raise ApplicationHandlerStop

    if action == "cancel":
        _cancel_task(user_id)
        _o = context.user_data.pop("pay_order", None) or {}
        try:
            import analytics
            analytics.track(user_id, "cancel", aid=_o.get("aid"))
            await analytics.notify(context.bot, _o.get("aid"), user_id, "cancel")
        except Exception:
            pass
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer("Cancelled")
        raise ApplicationHandlerStop

    if action == "walletclose":
        context.user_data.pop("pay_order", None)
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        raise ApplicationHandlerStop

    if action == "wallet":
        await open_wallet(query, context)
        raise ApplicationHandlerStop

    if action == "deposit":
        if not enabled_cryptos():
            await query.answer("Deposits are unavailable right now.", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["pay_order"] = {
            "state": "await_deposit_amount", "kind": "deposit", "user_id": user_id,
            "chat_id": query.message.chat_id, "msg_id": query.message.message_id,
            "has_photo": bool(query.message.photo),
        }
        await _edit_live_raw(context, query.message.chat_id, query.message.message_id,
                             bool(query.message.photo),
                             "<b>💰 How much would you like to deposit? (USD)</b>")
        await query.answer()
        raise ApplicationHandlerStop

    if action == "usewallet":
        order = context.user_data.get("pay_order")
        if not order:
            await query.answer("Session expired, please start again", show_alert=True)
            raise ApplicationHandlerStop
        order["chat_id"] = query.message.chat_id
        order["msg_id"] = query.message.message_id
        order["has_photo"] = bool(query.message.photo)
        bal = _wallet_balance(user_id)
        total = float(order.get("usd", 0))
        if bal <= 0:
            await query.answer("Your wallet is empty.", show_alert=True)
            raise ApplicationHandlerStop
        if bal >= total:
            order["state"] = "wallet_choice"
            context.user_data["pay_order"] = order
            text = f"<b>Your current balance is: {_fmt_money(bal)}</b>"
            keyboard_rows = [
                [{"text": "Use Wallet Balance", "callback_data": "pay:walletfull",
                  "emoji_id": _btn_emoji("use_wallet_balance", "use_wallet")}],
                [{"text": "Use Crypto", "callback_data": "pay:usecrypto", "emoji_id": _btn_emoji("use_crypto")}],
                [{"text": "Cancel", "callback_data": "pay:cancel", "emoji_id": _btn_emoji("cancel")}],
            ]
            await _show_screen_raw(context, order, text, keyboard_rows, get_wallet_choice_image())
            await query.answer()
            raise ApplicationHandlerStop
        order["state"] = "await_wallet_amount"
        context.user_data["pay_order"] = order
        msg = ("<b>Your current balance is: " + _fmt_money(bal) + "</b>" + NL
               + "How much would you like to use?")
        await _show_screen_raw(context, order, msg, [], get_wallet_choice_image())
        await query.answer()
        raise ApplicationHandlerStop

    if action == "walletfull":
        order = context.user_data.get("pay_order")
        if not order:
            await query.answer("Session expired, please start again", show_alert=True)
            raise ApplicationHandlerStop
        order["chat_id"] = query.message.chat_id
        order["msg_id"] = query.message.message_id
        order["has_photo"] = bool(query.message.photo)
        bal = _wallet_balance(user_id)
        total = float(order.get("usd", 0))
        if bal + 1e-9 < total:
            await query.answer("Not enough wallet balance.", show_alert=True)
            raise ApplicationHandlerStop
        order["wallet_used"] = total
        order["wallet_full"] = True
        order["state"] = "done"
        context.user_data["pay_order"] = order
        try:
            import store
            store.wallet_deduct(user_id, total)
        except Exception:
            pass
        await query.answer()
        await _finish_purchase_raw(context, user_id, order)
        raise ApplicationHandlerStop

    if action == "usecrypto":
        order = context.user_data.get("pay_order")
        if not order:
            await query.answer("Session expired, please start again", show_alert=True)
            raise ApplicationHandlerStop
        order["chat_id"] = query.message.chat_id
        order["msg_id"] = query.message.message_id
        order["has_photo"] = bool(query.message.photo)
        order["state"] = "choosing"
        context.user_data["pay_order"] = order
        note = None
        if float(order.get("wallet_used", 0)) > 0:
            note = ("💳 Wallet applied: <b>" + _fmt_money(order["wallet_used"]) + "</b>" + NL
                    + "💰 Remaining to pay: <b>" + _fmt_money(order["charge_usd"]) + "</b>")
        text, keyboard_rows, photo = _picker_screen_raw(_is_admin(user_id), note=note)
        await _show_screen_raw(context, order, text, keyboard_rows, photo)
        await query.answer()
        raise ApplicationHandlerStop

    # ----- admin-only below -----
    if user_id != ADMIN_ID:
        await query.answer("Not allowed", show_alert=True)
        raise ApplicationHandlerStop

    if action == "admin":
        context.user_data.pop("pay_flow", None)
        text, kb = admin_home_panel()
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if action == "close":
        context.user_data.pop("pay_flow", None)
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        raise ApplicationHandlerStop

    if action == "add":
        chains = _unused_chains()
        if not chains:
            await _safe_edit(query, context, "All supported chains are already added.", admin_home_panel()[1])
            await query.answer()
            raise ApplicationHandlerStop
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(pe.SUPPORTED_CHAINS[c]["label"], callback_data="pay:addchain:" + c)] for c in chains]
            + [[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]]
        )
        await _safe_edit(query, context, "➕ <b>ADD CRYPTO</b>" + NL + "Pick a chain:", kb)
        await query.answer()
        raise ApplicationHandlerStop

    if action == "img":
        context.user_data["pay_flow"] = {"step": "set_pay_image"}
        cur = "yes" if get_pay_image() else "no"
        await _safe_edit(query, context,
                         "🖼️ Send the IMAGE buyers will see on the payment screens." + NL
                         + "Currently set: " + cur + NL
                         + "(send 0 to remove it)")
        await query.answer()
        raise ApplicationHandlerStop

    if action == "walletimg":
        context.user_data["pay_flow"] = {"step": "set_wallet_image"}
        cur = "yes" if load_cryptos().get("wallet_image") else "no (falls back to Payment Image)"
        await _safe_edit(query, context,
                         "👛 Send the IMAGE buyers will see on the Wallet screen." + NL
                         + "Currently set: " + cur + NL
                         + "(send 0 to remove it and fall back to the Payment Image)")
        await query.answer()
        raise ApplicationHandlerStop

    if action == "walletchoiceimg":
        context.user_data["pay_flow"] = {"step": "set_wallet_choice_image"}
        cur = "yes" if load_cryptos().get("wallet_choice_image") else "no (falls back to Wallet / Payment Image)"
        await _safe_edit(query, context,
                         "💳 Send the IMAGE buyers will see on the wallet checkout screen "
                         "(Use Wallet Balance / Use Crypto / Cancel)." + NL
                         + "Currently set: " + cur + NL
                         + "(send 0 to remove it)")
        await query.answer()
        raise ApplicationHandlerStop

    if action == "pickedit":
        context.user_data["pay_flow"] = {"step": "edit_picker_text"}
        await _safe_edit(query, context,
                         "📝 Send the new TEXT for the crypto-choosing page:" + NL
                         + "Current: " + get_picker_text())
        await query.answer()
        raise ApplicationHandlerStop

    if action == "pickimg":
        context.user_data["pay_flow"] = {"step": "set_pay_image"}
        cur = "yes" if get_pay_image() else "no"
        await _safe_edit(query, context,
                         "🖼️ Send the IMAGE for the crypto-choosing page." + NL
                         + "Currently set: " + cur + NL
                         + "(send 0 to remove it)")
        await query.answer()
        raise ApplicationHandlerStop

    if action == "test":
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c["name"], callback_data="pay:testc:" + c["id"])] for c in all_cryptos()]
            + [[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]]
        )
        await _safe_edit(query, context, "🧪 <b>TEST TRANSACTION</b>" + NL + "Pick a crypto to test:", kb)
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("testc:"):
        cid = action[6:]
        c = get_crypto(cid)
        if not c:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["pay_flow"] = {"step": "test_hash", "id": cid}
        await _safe_edit(query, context, "🧪 Send a transaction hash (TXID) to test against <b>" + html.escape(c["name"]) + "</b>.")
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("addr:"):
        cid = action[5:]
        c = get_crypto(cid)
        if not c:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["pay_flow"] = {"step": "edit_address", "id": cid}
        await _safe_edit(query, context,
                         "📬 Send the new deposit ADDRESS for <b>" + html.escape(c["name"]) + "</b>." + NL
                         + "Current: <code>" + html.escape(c.get("address") or "(none)") + "</code>")
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("conf:"):
        cid = action[5:]
        c = get_crypto(cid)
        if not c:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["pay_flow"] = {"step": "edit_min_conf", "id": cid}
        await _safe_edit(query, context,
                         "🔢 Send the minimum confirmations required for <b>" + html.escape(c["name"]) + "</b>." + NL
                         + "Current: " + str(c.get("min_conf", 1)))
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("window:"):
        cid = action[7:]
        c = get_crypto(cid)
        if not c:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["pay_flow"] = {"step": "edit_window", "id": cid}
        await _safe_edit(query, context,
                         "⏱️ Send the payment window (in MINUTES) for <b>" + html.escape(c["name"]) + "</b>." + NL
                         + "Current: " + str(int(c.get("window_minutes") or PAY_WINDOW_MINUTES)) + " min")
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("addchain:"):
        chain = action[len("addchain:"):]
        info = pe.SUPPORTED_CHAINS.get(chain)
        if not info:
            await query.answer("Unknown chain", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["pay_flow"] = {"step": "add_name", "chain": chain}
        await _safe_edit(query, context, "📛 Send a display NAME for this crypto (example: " + info["label"] + "):")
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("c:"):
        cid = action[2:]
        res = crypto_panel(cid)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        text, kb = res
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("emoji:"):
        cid = action[6:]
        context.user_data["pay_flow"] = {"step": "set_crypto_emoji", "id": cid}
        c = get_crypto(cid)
        cur = "Set" if c and c.get("emoji_id") else "Not set"
        await _safe_edit(query, context,
                         f"🎨 SET ANIMATED EMOJI for {c['name'] if c else cid}\n\n"
                         f"Current: {cur}\n\n"
                         f"How to set animated emoji:\n"
                         f"1. Send a message with the animated emoji\n"
                         f"2. Reply to that message with /getid\n"
                         f"3. Copy the emoji ID (looks like: CAACAgIAAxkBAA...)\n"
                         f"4. Send that ID here\n\n"
                         f"Or send 0 to REMOVE the current emoji.")
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("up:") or action.startswith("dn:"):
        direction = -1 if action.startswith("up:") else 1
        cid = action.split(":", 1)[1]
        moved = _move_crypto(cid, direction)
        res = crypto_panel(cid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer("Moved" if moved else "Already at that end")
        raise ApplicationHandlerStop

    if action.startswith("tgl:"):
        cid = action[4:]
        c = get_crypto(cid)
        if c:
            c["enabled"] = not bool(c.get("enabled"))
            _save_crypto(c)
        res = crypto_panel(cid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer("Updated")
        raise ApplicationHandlerStop

    if action.startswith("rmok:"):
        cid = action[5:]
        data_all = load_cryptos()
        data_all["cryptos"] = [c for c in data_all["cryptos"] if c["id"] != cid]
        save_cryptos(data_all)
        text, kb = admin_home_panel()
        await _safe_edit(query, context, "Removed." + NL + NL + text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if action.startswith("rm:"):
        cid = action[3:]
        c = get_crypto(cid)
        nm = c["name"] if c else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, remove", callback_data="pay:rmok:" + cid)],
            [InlineKeyboardButton("❌ No, go back", callback_data="pay:c:" + cid)],
        ])
        await _safe_edit(query, context, "🗑️ Remove '" + nm + "' from accepted cryptos?", kb)
        await query.answer()
        raise ApplicationHandlerStop

    await query.answer()
    raise ApplicationHandlerStop

# ========================= TEXT INPUT =========================
async def _on_text(update, context):
    order = context.user_data.get("pay_order")
    if order:
        st = order.get("state")
        if st == "await_deposit_amount":
            await _handle_deposit_amount(update, context)
            raise ApplicationHandlerStop
        if st == "await_wallet_amount":
            await _handle_wallet_amount(update, context)
            raise ApplicationHandlerStop
        if st == "await_payment":
            await on_payment_hash_text(update, context, order)
            raise ApplicationHandlerStop
        if st == "done":
            raise ApplicationHandlerStop
        raise ApplicationHandlerStop

    flow = context.user_data.get("pay_flow")
    if not flow:
        return
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("pay_flow", None)
        return
    step = flow.get("step")
    text = (update.message.text or "").strip()

    if step == "edit_address":
        cid = flow["id"]
        c = get_crypto(cid)
        if not c:
            context.user_data.pop("pay_flow", None)
            await update.message.reply_text("Crypto not found.")
            raise ApplicationHandlerStop
        c["address"] = text
        if text:
            c["enabled"] = True
        _save_crypto(c)
        context.user_data.pop("pay_flow", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:c:" + cid)]])
        await update.message.reply_text("✅ Address updated for " + c["name"] + ".", reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "edit_min_conf":
        cid = flow["id"]
        c = get_crypto(cid)
        if not c:
            context.user_data.pop("pay_flow", None)
            await update.message.reply_text("Crypto not found.")
            raise ApplicationHandlerStop
        if not text.isdigit():
            await update.message.reply_text("Please send a whole number (e.g. 1, 3, 12).")
            raise ApplicationHandlerStop
        c["min_conf"] = int(text)
        _save_crypto(c)
        context.user_data.pop("pay_flow", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:c:" + cid)]])
        await update.message.reply_text("✅ Min confirmations set to " + text + " for " + c["name"] + ".", reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "edit_window":
        cid = flow["id"]
        c = get_crypto(cid)
        if not c:
            context.user_data.pop("pay_flow", None)
            await update.message.reply_text("Crypto not found.")
            raise ApplicationHandlerStop
        if not text.isdigit() or int(text) <= 0:
            await update.message.reply_text("Please send a whole number of minutes (e.g. 15, 30, 60).")
            raise ApplicationHandlerStop
        c["window_minutes"] = int(text)
        _save_crypto(c)
        context.user_data.pop("pay_flow", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:c:" + cid)]])
        await update.message.reply_text("✅ Payment window set to " + text + " min for " + c["name"] + ".", reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "set_crypto_emoji":
        cid = flow["id"]
        c = get_crypto(cid)
        if not c:
            context.user_data.pop("pay_flow", None)
            await update.message.reply_text("Crypto not found.")
            raise ApplicationHandlerStop
        if text == "0":
            c["emoji_id"] = None
            _save_crypto(c)
            context.user_data.pop("pay_flow", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:c:" + cid)]])
            await update.message.reply_text("✅ Emoji removed from crypto.", reply_markup=kb)
        else:
            c["emoji_id"] = text
            _save_crypto(c)
            context.user_data.pop("pay_flow", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:c:" + cid)]])
            await update.message.reply_text(f"✅ Animated emoji set for {c['name']}!\n\nID: {text}", reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "set_pay_image":
        if text == "0":
            set_pay_image(None)
            context.user_data.pop("pay_flow", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]])
            await update.message.reply_text("🖼️ Payment image removed.", reply_markup=kb)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove it.")
        raise ApplicationHandlerStop

    if step == "set_wallet_image":
        if text == "0":
            set_wallet_image(None)
            context.user_data.pop("pay_flow", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]])
            await update.message.reply_text("👛 Wallet image removed (falls back to Payment Image).", reply_markup=kb)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove it.")
        raise ApplicationHandlerStop

    if step == "set_wallet_choice_image":
        if text == "0":
            set_wallet_choice_image(None)
            context.user_data.pop("pay_flow", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]])
            await update.message.reply_text("💳 Wallet checkout image removed.", reply_markup=kb)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove it.")
        raise ApplicationHandlerStop

    if step == "edit_picker_text":
        set_picker_text(text)
        context.user_data.pop("pay_flow", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]])
        await update.message.reply_text("✅ Crypto-choosing page text updated.", reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "add_name":
        chain = flow["chain"]
        info = pe.SUPPORTED_CHAINS.get(chain, {})
        new = {
            "id": _new_id(),
            "name": text,
            "chain": chain,
            "address": "",
            "coingecko_id": info.get("coingecko"),
            "decimals": info.get("decimals", 8),
            "enabled": False,
            "min_conf": 1,
            "is_usd_stable": info.get("stable", False),
            "token_contract": info.get("token"),
            "emoji_id": None,
        }
        data_all = load_cryptos()
        data_all["cryptos"].append(new)
        save_cryptos(data_all)
        context.user_data.pop("pay_flow", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📬 Set Address Now", callback_data="pay:addr:" + new["id"])],
                                    [InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]])
        await update.message.reply_text(
            "✅ Added '" + text + "' (" + info.get("label", chain) + "). It's disabled until you set an address.",
            reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "test_hash":
        cid = flow["id"]
        c = get_crypto(cid)
        context.user_data.pop("pay_flow", None)
        if not c:
            await update.message.reply_text("Crypto not found.")
            raise ApplicationHandlerStop
        wait = await update.message.reply_text("🔄 Checking the blockchain…")
        res = await pe.verify_tx(c, text)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:c:" + cid)]])
        await wait.edit_text(_format_test_result(c, text, res), parse_mode="HTML", reply_markup=kb)
        raise ApplicationHandlerStop

# ========================= PHOTO INPUT =========================
async def _on_photo(update, context):
    flow = context.user_data.get("pay_flow")
    if not flow or flow.get("step") not in ("set_pay_image", "set_wallet_image", "set_wallet_choice_image"):
        return
    if update.effective_user.id != ADMIN_ID:
        return
    file_id = update.message.photo[-1].file_id
    if flow.get("step") == "set_wallet_choice_image":
        set_wallet_choice_image(file_id)
        confirm_text = "✅ Wallet checkout image updated."
    elif flow.get("step") == "set_wallet_image":
        set_wallet_image(file_id)
        confirm_text = "✅ Wallet image updated."
    else:
        set_pay_image(file_id)
        confirm_text = "✅ Payment image updated."
    context.user_data.pop("pay_flow", None)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pay:admin")]])
    await update.message.reply_text(confirm_text, reply_markup=kb)
    raise ApplicationHandlerStop

# ========================= /payments COMMAND =========================
async def _cmd_payments(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data.pop("pay_flow", None)
    text, kb = admin_home_panel()
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

# ========================= SETUP =========================
def setup(application, admin_id, bot_token=None):
    global ADMIN_ID, BOT_TOKEN, TG_API
    ADMIN_ID = admin_id
    BOT_TOKEN = bot_token
    if BOT_TOKEN:
        TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

    application.add_handler(CallbackQueryHandler(_on_callback), group=-3)
    application.add_handler(MessageHandler(filters.PHOTO, _on_photo), group=-3)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text), group=-3)
    application.add_handler(CommandHandler("payments", _cmd_payments))

    n = len(all_cryptos())
    enabled_n = len(enabled_cryptos())
    print(f"Crypto Payments module loaded (on-chain, no processor). {n} cryptos configured, {enabled_n} enabled.")


async def resume_pending_orders(application):
    """Re-spawn countdown tasks for orders still in-flight when the bot last
    stopped, so a restart never abandons an order the buyer was mid-paying."""
    resumed = 0
    expired = 0
    touched = []   # user ids whose saved data we changed
    now = time.time()
    for user_id, data in list(application.user_data.items()):
        order = data.get("pay_order")
        if not order or order.get("state") != "await_payment":
            continue
        context = ContextTypes.DEFAULT_TYPE(application=application, chat_id=order.get("chat_id"), user_id=user_id)
        if order.get("deadline", 0) <= now:
            expired += 1
            touched.append(user_id)
            if now - order.get("deadline", 0) > STALE_NOTIFY_WINDOW:
                # Long dead (e.g. abandoned days ago): just clean it up, do not
                # message the customer about an old order out of the blue.
                data.pop("pay_order", None)
                continue
            try:
                await _expire_order_raw(context, user_id)
            except Exception as e:
                print(f"[payments] error expiring stale order for {user_id}: {e}")
            continue
        _spawn(user_id, _countdown_raw(context, user_id))
        resumed += 1
    if resumed or expired:
        print(f"[payments] resumed {resumed} pending order(s), expired {expired} stale order(s) after restart")
    if expired:
        # Without this, the pop("pay_order") above only changes the
        # in-memory copy - PicklePersistence's normal auto-save only
        # triggers after processing a real Telegram update, which never
        # happens here (this runs once at startup, outside that flow). The
        # stale order would stay on disk and get "expired" again - resending
        # the same notification to the same customer - on every future
        # restart. Force a flush now so it's actually gone for good.
        # update_persistence() alone is not enough: it only saves users flagged
        # by a real Telegram update, so the cleared orders were never written
        # and were "expired" (and the customer messaged) again on every restart.
        # Save the changed users explicitly, then flush to disk.
        try:
            for uid in touched:
                await application.persistence.update_user_data(uid, application.user_data[uid])
            await application.persistence.flush()
        except Exception as e:
            print(f"[payments] failed to persist cleared stale orders: {e}")
