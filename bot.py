"""
Premium Villa - Telegram Shop Bot (main file)
"""

import os
import html
import json
import uuid
import httpx

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, MessageEntity
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import smm
import cart
import payments
import store
import orders

# --- Your settings ---
BOT_TOKEN = "8712977638:AAFyazkpU-69d-5aokGYN_vb3JHWk6u_GfE"
ADMIN_ID = 6684244590
# ---------------------

PRODUCT_CATEGORIES = {"ott", "vpn"}

NL = chr(10)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MENU_FILE = os.path.join(BASE_DIR, "menu.json")
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
TG_FILE = os.path.join(BASE_DIR, "tgpremium.json")
ACTION_EMOJI_FILE = os.path.join(BASE_DIR, "action_emojis.json")

VIEW_CART_ID = "viewcart"

DEFAULT_BUTTONS = [
    {"id": "ott",        "text": "OTT Premium",          "size": "half", "emoji_id": None},
    {"id": "vpn",        "text": "VPN's",                 "size": "half", "emoji_id": None},
    {"id": "tg",         "text": "Telegram Premium",       "size": "full", "emoji_id": None},
    {"id": "smm",        "text": "Social Media Services",  "size": "full", "emoji_id": None},
    {"id": "wallet",     "text": "Wallet",                 "size": "full", "emoji_id": None},
    {"id": "support",    "text": "Support",                "size": "full", "emoji_id": None},
    {"id": VIEW_CART_ID, "text": "View Cart",              "size": "full", "emoji_id": None},
]

DEFAULT_WELCOME_TEXT = (
    "Hi {name}," + NL + NL
    + "Welcome To Premium Villa." + NL + NL
    + "Premium Services At Exceptional Value-Browse Our Offerings Below"
)

DEFAULT_TG = {
    "select_text": "Please select how many months you would like to buy.",
    "select_image": None,
    "username_text": "Please Type the USERNAME On Which You Want The Telegram Premium",
    "username_image": None,
    "plans": [
        {"id": "m3",  "name": "3 Months",  "price": "$30", "image": None},
        {"id": "m6",  "name": "6 Months",  "price": "$45", "image": None},
        {"id": "m12", "name": "12 Months", "price": "$60", "image": None},
    ],
}

DEFAULT_ACTION_EMOJIS = {
    "buy_now": None,
    "add_to_cart": None,
    "back_button": None,
    "increment": None,
    "decrement": None,
    "use_wallet": None,
}

# ========== RAW API HELPERS ==========

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def _build_raw_keyboard(rows_spec):
    raw_rows = []
    for row in rows_spec:
        raw_row = []
        for btn in row:
            raw_btn = {
                "text": btn["text"],
                "callback_data": btn["callback_data"],
            }
            if btn.get("emoji_id"):
                raw_btn["icon_custom_emoji_id"] = btn["emoji_id"]
            raw_row.append(raw_btn)
        raw_rows.append(raw_row)
    return {"inline_keyboard": raw_rows}

async def raw_send_message(chat_id, text, keyboard_rows, photo=None, parse_mode="HTML"):
    if photo:
        return await raw_send_photo(chat_id, photo, text, keyboard_rows, parse_mode)
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API}/sendMessage", json=payload)
    return r.json()

async def raw_send_photo(chat_id, photo, caption, keyboard_rows, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API}/sendPhoto", json=payload)
    return r.json()

async def raw_edit_message_text(chat_id, message_id, text, keyboard_rows, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API}/editMessageText", json=payload)
    return r.json()

async def raw_edit_message_media(chat_id, message_id, photo, caption, keyboard_rows, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "media": {"type": "photo", "media": photo, "caption": caption, "parse_mode": parse_mode},
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API}/editMessageMedia", json=payload)
    return r.json()

# ========== storage helpers ==========
def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return json.loads(json.dumps(default))
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                save_json(path, default)
                return json.loads(json.dumps(default))
            return json.loads(content)
    except json.JSONDecodeError:
        save_json(path, default)
        return json.loads(json.dumps(default))

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_action_emojis():
    return load_json(ACTION_EMOJI_FILE, DEFAULT_ACTION_EMOJIS)

def save_action_emojis(emojis):
    save_json(ACTION_EMOJI_FILE, emojis)

def get_action_emoji(key):
    return load_action_emojis().get(key)

def load_buttons():
    buttons = load_json(MENU_FILE, DEFAULT_BUTTONS)
    for b in buttons:
        if "emoji_id" not in b:
            b["emoji_id"] = None
    return buttons

def save_buttons(buttons):
    save_json(MENU_FILE, buttons)

def find_button(buttons, button_id):
    for b in buttons:
        if b["id"] == button_id:
            return b
    return None

def button_name(button_id):
    b = find_button(load_buttons(), button_id)
    return b["text"] if b else button_id

def menu_callback_for(button):
    if button["id"] == VIEW_CART_ID:
        return "cart:open"
    return "open:" + button["id"]

def ensure_viewcart_button():
    settings = load_settings()
    if settings.get("viewcart_added"):
        return
    buttons = load_buttons()
    if not any(b.get("id") == VIEW_CART_ID for b in buttons):
        buttons.append({"id": VIEW_CART_ID, "text": "View Cart", "size": "full", "emoji_id": None})
        save_buttons(buttons)
    settings["viewcart_added"] = True
    save_settings(settings)

def load_products():
    return store.load_products()

def save_products(data):
    store.save_products(data)

def products_in_category(cat_id):
    data = load_products()
    return [(pid, p) for pid, p in data["items"].items() if p.get("category") == cat_id]

def get_product(pid):
    return store.get_product(pid)

def find_plan(product, plan_id):
    for pl in product.get("plans", []):
        if pl["id"] == plan_id:
            return pl
    return None

def load_settings():
    return load_json(SETTINGS_FILE, {"welcome_text": DEFAULT_WELCOME_TEXT, "welcome_image": None})

def save_settings(settings):
    save_json(SETTINGS_FILE, settings)

def get_category_image(cat_id):
    settings = load_settings()
    cat_images = settings.get("category_images", {})
    return cat_images.get(cat_id)

def set_category_image(cat_id, image_id):
    settings = load_settings()
    cat_images = settings.get("category_images", {})
    if image_id is None:
        cat_images.pop(cat_id, None)
    else:
        cat_images[cat_id] = image_id
    settings["category_images"] = cat_images
    save_settings(settings)

SUPPORT_FILE = os.path.join(BASE_DIR, "support.json")
DEFAULT_SUPPORT = {
    "text": "Hi {name}, please reach out to @MishraCo for support. Thank you!",
    "image": None,
}

def load_support():
    return load_json(SUPPORT_FILE, DEFAULT_SUPPORT)

def save_support(data):
    save_json(SUPPORT_FILE, data)

def get_welcome_text():
    return load_settings().get("welcome_text") or DEFAULT_WELCOME_TEXT

def get_welcome_image_id():
    return load_settings().get("welcome_image")

def get_category_intro(cat_id):
    intros = load_settings().get("category_intro", {})
    return intros.get(cat_id) or "Choose a product:"

def set_category_intro(cat_id, text):
    settings = load_settings()
    intros = settings.get("category_intro", {})
    intros[cat_id] = text
    settings["category_intro"] = intros
    save_settings(settings)

def load_tg():
    return load_json(TG_FILE, DEFAULT_TG)

def save_tg(d):
    save_json(TG_FILE, d)

def find_tg_plan(plan_id):
    for pl in load_tg().get("plans", []):
        if pl["id"] == plan_id:
            return pl
    return None

def update_tg_plan(plan_id, field, value):
    d = load_tg()
    for pl in d.get("plans", []):
        if pl["id"] == plan_id:
            pl[field] = value
            break
    save_tg(d)

def add_tg_plan(plan):
    d = load_tg()
    d.setdefault("plans", []).append(plan)
    save_tg(d)

def delete_tg_plan(plan_id):
    d = load_tg()
    d["plans"] = [pl for pl in d.get("plans", []) if pl["id"] != plan_id]
    save_tg(d)

def reorder_tg_plan(plan_id, up):
    d = load_tg()
    plans = d.get("plans", [])
    idx = next((i for i, pl in enumerate(plans) if pl["id"] == plan_id), None)
    if idx is None:
        return
    if up and idx > 0:
        plans[idx - 1], plans[idx] = plans[idx], plans[idx - 1]
    elif (not up) and idx < len(plans) - 1:
        plans[idx + 1], plans[idx] = plans[idx], plans[idx + 1]
    save_tg(d)

def reorder_product(pid, up):
    data = load_products()
    items = data["items"]
    product = items.get(pid)
    if not product:
        return
    cat = product["category"]
    keys = list(items.keys())
    cat_keys = [k for k in keys if items[k]["category"] == cat]
    pos = cat_keys.index(pid)
    if up and pos > 0:
        neighbor = cat_keys[pos - 1]
    elif (not up) and pos < len(cat_keys) - 1:
        neighbor = cat_keys[pos + 1]
    else:
        return
    i, j = keys.index(pid), keys.index(neighbor)
    keys[i], keys[j] = keys[j], keys[i]
    data["items"] = {k: items[k] for k in keys}
    save_products(data)

def reorder_plan(pid, plan_id, up):
    data = load_products()
    product = data["items"].get(pid)
    if not product:
        return
    plans = product.get("plans", [])
    idx = next((i for i, pl in enumerate(plans) if pl["id"] == plan_id), None)
    if idx is None:
        return
    if up and idx > 0:
        plans[idx - 1], plans[idx] = plans[idx], plans[idx - 1]
    elif (not up) and idx < len(plans) - 1:
        plans[idx + 1], plans[idx] = plans[idx], plans[idx + 1]
    save_products(data)

def find_welcome_image_file():
    for fname in os.listdir(BASE_DIR):
        low = fname.lower()
        if low.startswith("welcome") and low.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return os.path.join(BASE_DIR, fname)
    return None

# ========== MENU KEYBOARD BUILDER ==========
def build_menu_rows(user_id):
    buttons = load_buttons()
    rows = []
    pending = None
    for b in buttons:
        spec = {"text": b["text"], "callback_data": menu_callback_for(b), "emoji_id": b.get("emoji_id")}
        if b["size"] == "full":
            if pending:
                rows.append([pending])
                pending = None
            rows.append([spec])
        else:
            if pending:
                rows.append([pending, spec])
                pending = None
            else:
                pending = spec
    if pending:
        rows.append([pending])
    if user_id == ADMIN_ID:
        rows.append([{"text": "EDIT", "callback_data": "edit", "emoji_id": None}])
    return rows

def build_menu_kb(user_id):
    buttons = load_buttons()
    rows = []
    pending = None
    for b in buttons:
        btn = InlineKeyboardButton(b["text"], callback_data=menu_callback_for(b))
        if b["size"] == "full":
            if pending:
                rows.append([pending])
                pending = None
            rows.append([btn])
        else:
            if pending:
                rows.append([pending, btn])
                pending = None
            else:
                pending = btn
    if pending:
        rows.append([pending])
    if user_id == ADMIN_ID:
        rows.append([InlineKeyboardButton("EDIT", callback_data="edit")])
    return InlineKeyboardMarkup(rows)

def build_welcome_caption(first_name):
    template = get_welcome_text()
    safe_template = html.escape(template)
    safe_name = "<b>" + html.escape(first_name or "there") + "</b>"
    return safe_template.replace("{name}", safe_name)

# ========== render helpers ==========
async def render_screen(query, context, caption, keyboard, photo=None):
    msg = query.message
    has_photo = bool(msg.photo)
    want_photo = photo is not None
    if want_photo and has_photo:
        try:
            return await msg.edit_media(
                media=InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                reply_markup=keyboard,
            )
        except Exception:
            pass
    elif not want_photo and not has_photo:
        try:
            return await msg.edit_text(caption, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass
    try:
        await msg.delete()
    except Exception:
        pass
    if want_photo:
        return await context.bot.send_photo(
            chat_id=msg.chat_id, photo=photo, caption=caption,
            reply_markup=keyboard, parse_mode="HTML",
        )
    return await context.bot.send_message(
        chat_id=msg.chat_id, text=caption, reply_markup=keyboard, parse_mode="HTML",
    )

async def render_to_message(context, chat_id, msg_id, had_photo, caption, keyboard, photo=None):
    want_photo = photo is not None
    if msg_id is not None:
        try:
            if want_photo and had_photo:
                return await context.bot.edit_message_media(
                    chat_id=chat_id, message_id=msg_id,
                    media=InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                    reply_markup=keyboard,
                )
            if (not want_photo) and (not had_photo):
                return await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id, text=caption,
                    reply_markup=keyboard, parse_mode="HTML",
                )
        except Exception:
            pass
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    if want_photo:
        return await context.bot.send_photo(
            chat_id=chat_id, photo=photo, caption=caption,
            reply_markup=keyboard, parse_mode="HTML",
        )
    return await context.bot.send_message(
        chat_id=chat_id, text=caption, reply_markup=keyboard, parse_mode="HTML",
    )

async def safe_edit(query, context, text, reply_markup=None):
    msg = query.message
    if msg.photo:
        try:
            await msg.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=reply_markup)
        return
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        pass

# ========== /start ==========
async def start(update, context):
    user = update.effective_user
    store.register_user(user.id, user.username, user.first_name)
    context.user_data.clear()
    caption = build_welcome_caption(user.first_name)
    menu_rows = build_menu_rows(user.id)

    image_id = get_welcome_image_id()
    if not image_id:
        image_file = find_welcome_image_file()
        if image_file:
            sent = await update.message.reply_photo(
                photo=open(image_file, "rb"),
                caption=caption,
                reply_markup=build_menu_kb(user.id),
                parse_mode="HTML",
            )
            try:
                await raw_edit_message_media(
                    user.id, sent.message_id,
                    sent.photo[-1].file_id, caption, menu_rows
                )
            except Exception:
                pass
            return

    if image_id:
        await raw_send_photo(user.id, image_id, caption, menu_rows)
    else:
        await raw_send_message(user.id, caption, menu_rows)

async def send_home(context, chat_id, user_id, first_name):
    caption = build_welcome_caption(first_name)
    menu_rows = build_menu_rows(user_id)
    image_id = get_welcome_image_id()
    if image_id:
        await raw_send_photo(chat_id, image_id, caption, menu_rows)
        return
    image_file = find_welcome_image_file()
    if image_file:
        await raw_send_message(chat_id, caption, menu_rows)
        return
    await raw_send_message(chat_id, caption, menu_rows)

# ========== /getid command ==========
async def cmd_getid(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = update.message
    target = msg.reply_to_message or msg
    all_entities = list(target.entities or []) + list(target.caption_entities or [])
    custom_emojis = [e for e in all_entities if e.type == MessageEntity.CUSTOM_EMOJI]
    if not custom_emojis:
        await update.message.reply_text(
            "No custom emoji found!" + NL + NL
            + "Reply to a message containing a custom animated emoji with /getid" + NL
            + "OR send /getid then send a message with the custom emoji in it."
        )
        context.user_data["state"] = "await_emoji_for_id"
        return
    text = target.text or target.caption or ""
    lines = ["Found custom emoji(s):" + NL]
    for e in custom_emojis:
        emoji_char = text[e.offset: e.offset + e.length]
        lines.append(f"Emoji: {emoji_char}")
        lines.append(f"ID: <code>{e.custom_emoji_id}</code>" + NL)
    lines.append("Go to EDIT -> Set Button Emoji and send this emoji to apply it.")
    await update.message.reply_text(NL.join(lines), parse_mode="HTML")

# ========== Admin Commands ==========
async def cmd_commands(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    
    commands_list = """
ADMIN COMMANDS LIST:

Wallet Management:
/wallet @username - Show user's wallet balance
/remove @username amount - Remove money from user's wallet
/add @username amount - Add money to user's wallet

Stock Management:
/setstock product PRODUCT_ID STOCK - Set product stock (-1=unlimited, 0=out)
/setstock plan PRODUCT_ID PLAN_ID STOCK - Set plan stock
/pause product PRODUCT_ID - Pause/unpause a product
/pause plan PRODUCT_ID PLAN_ID - Pause/unpause a plan
/stockstatus - Check stock status

User Management:
/admin @username - Make a user admin
/removeadmin @username - Remove admin privileges
/ban @username - Ban a user
/unban @username - Unban a user
/active - Show active users

Bot Settings:
/maintenance - Put bot in maintenance mode

Order Management:
/orders - Show all orders statistics
/stats @username - Show order statistics of a specific user

Broadcast:
/broadcast message - Send message to all users

Info:
/commands - Show this help menu
/stats - Show bot statistics
"""
    await update.message.reply_text(commands_list)

async def cmd_wallet(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /wallet @username")
        return
    username = context.args[0].lstrip('@')
    user_data = store.find_user_by_username(username)
    if not user_data:
        await update.message.reply_text(f"User @{username} not found.")
        return
    user_id = user_data['user_id']
    balance = store.wallet_balance(user_id)
    await update.message.reply_text(
        f"WALLET INFORMATION\n\nUser: @{username}\nUser ID: <code>{user_id}</code>\nBalance: <b>${balance:.2f}</b> USD",
        parse_mode="HTML"
    )

async def cmd_remove(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /remove @username amount")
        return
    username = context.args[0].lstrip('@')
    try:
        amount = float(context.args[1])
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0.")
            return
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    user_data = store.find_user_by_username(username)
    if not user_data:
        await update.message.reply_text(f"User @{username} not found.")
        return
    user_id = user_data['user_id']
    current_balance = store.wallet_balance(user_id)
    if current_balance < amount:
        await update.message.reply_text(
            f"Insufficient balance!\n\nUser: @{username}\nCurrent balance: ${current_balance:.2f}\nRequested deduction: ${amount:.2f}",
            parse_mode="HTML"
        )
        return
    new_balance = store.wallet_deduct(user_id, amount)
    await update.message.reply_text(
        f"WALLET DEDUCTION SUCCESSFUL\n\nUser: @{username}\nAmount Deducted: <b>${amount:.2f}</b>\nPrevious Balance: ${current_balance:.2f}\nNew Balance: <b>${new_balance:.2f}</b>",
        parse_mode="HTML"
    )

async def cmd_add(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add @username amount")
        return
    username = context.args[0].lstrip('@')
    try:
        amount = float(context.args[1])
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0.")
            return
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    user_data = store.find_user_by_username(username)
    if not user_data:
        await update.message.reply_text(f"User @{username} not found.")
        return
    user_id = user_data['user_id']
    current_balance = store.wallet_balance(user_id)
    new_balance = store.wallet_add(user_id, amount)
    await update.message.reply_text(
        f"WALLET ADDITION SUCCESSFUL\n\nUser: @{username}\nPrevious Balance: ${current_balance:.2f}\nAmount Added: <b>+${amount:.2f}</b>\nNew Balance: <b>${new_balance:.2f}</b>",
        parse_mode="HTML"
    )

async def cmd_ban(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban @username")
        return
    username = context.args[0].lstrip('@')
    user_data = store.find_user_by_username(username)
    if not user_data:
        await update.message.reply_text(f"User @{username} not found.")
        return
    user_id = user_data['user_id']
    if store.is_banned(user_id):
        await update.message.reply_text(f"User @{username} is already banned.")
        return
    store.ban(user_id)
    await update.message.reply_text(f"User @{username} has been banned.")

async def cmd_unban(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban @username")
        return
    username = context.args[0].lstrip('@')
    user_data = store.find_user_by_username(username)
    if not user_data:
        await update.message.reply_text(f"User @{username} not found.")
        return
    user_id = user_data['user_id']
    if not store.is_banned(user_id):
        await update.message.reply_text(f"User @{username} is not banned.")
        return
    store.unban(user_id)
    await update.message.reply_text(f"User @{username} has been unbanned.")

async def cmd_active(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    users = store.load_users()
    active_count = len(users)
    await update.message.reply_text(
        f"ACTIVE USERS\n\nTotal registered users: <b>{active_count}</b>",
        parse_mode="HTML"
    )

async def cmd_orders(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    stats = store.global_stats()
    await update.message.reply_text(
        f"ORDER STATISTICS\n\nTotal Orders: <b>{stats['total_orders']}</b>\nToday's Orders: <b>{stats['today_orders']}</b>\nTotal Revenue: <b>{store.fmt_money(stats['total_revenue'])}</b>\nToday's Revenue: <b>{store.fmt_money(stats['today_revenue'])}</b>\nCancelled Orders: <b>{stats['cancelled']}</b>",
        parse_mode="HTML"
    )

async def cmd_broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return
    message = ' '.join(context.args)
    users = store.load_users()
    sent = 0
    failed = 0
    status_msg = await update.message.reply_text("Broadcasting message to all users...")
    for user_id_str in users:
        try:
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=f"BROADCAST MESSAGE\n\n{message}"
            )
            sent += 1
        except Exception:
            failed += 1
    await status_msg.edit_text(
        f"Broadcast completed!\n\nSent: {sent}\nFailed: {failed}\nTotal users: {len(users)}"
    )

async def cmd_stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    stats = store.global_stats()
    users = store.load_users()
    await update.message.reply_text(
        f"BOT STATISTICS\n\nUsers:\n  Registered: {len(users)}\n\nOrders:\n  Total: {stats['total_orders']}\n  Today: {stats['today_orders']}\n  Cancelled: {stats['cancelled']}\n\nRevenue:\n  Total: {store.fmt_money(stats['total_revenue'])}\n  Today: {store.fmt_money(stats['today_revenue'])}",
        parse_mode="HTML"
    )

async def cmd_set_stock(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\nFor product: /setstock product PRODUCT_ID STOCK\nFor plan: /setstock plan PRODUCT_ID PLAN_ID STOCK\n\nStock: -1 for unlimited, 0 for out of stock, positive for limited"
        )
        return
    type_arg = context.args[0].lower()
    if type_arg == "product":
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /setstock product PRODUCT_ID STOCK")
            return
        pid = context.args[1]
        try:
            stock = int(context.args[2])
        except ValueError:
            await update.message.reply_text("Stock must be a number")
            return
        if store.update_product_stock(pid, stock):
            stock_text = "Unlimited" if stock == -1 else str(stock)
            await update.message.reply_text(f"Stock updated for product! Stock: {stock_text}")
        else:
            await update.message.reply_text("Product not found")
    elif type_arg == "plan":
        if len(context.args) < 4:
            await update.message.reply_text("Usage: /setstock plan PRODUCT_ID PLAN_ID STOCK")
            return
        pid = context.args[1]
        plan_id = context.args[2]
        try:
            stock = int(context.args[3])
        except ValueError:
            await update.message.reply_text("Stock must be a number")
            return
        if store.update_plan_stock(pid, plan_id, stock):
            stock_text = "Unlimited" if stock == -1 else str(stock)
            await update.message.reply_text(f"Stock updated for plan! Stock: {stock_text}")
        else:
            await update.message.reply_text("Product or plan not found")

async def cmd_pause(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\nFor product: /pause product PRODUCT_ID\nFor plan: /pause plan PRODUCT_ID PLAN_ID"
        )
        return
    type_arg = context.args[0].lower()
    if type_arg == "product":
        pid = context.args[1]
        product = get_product(pid)
        if not product:
            await update.message.reply_text("Product not found")
            return
        current_paused = product.get("paused", False)
        new_paused = not current_paused
        if store.pause_product(pid, new_paused):
            status = "paused" if new_paused else "resumed"
            await update.message.reply_text(f"Product {status} successfully!")
    elif type_arg == "plan":
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /pause plan PRODUCT_ID PLAN_ID")
            return
        pid = context.args[1]
        plan_id = context.args[2]
        product = get_product(pid)
        if not product:
            await update.message.reply_text("Product not found")
            return
        plan = find_plan(product, plan_id)
        if not plan:
            await update.message.reply_text("Plan not found")
            return
        current_paused = plan.get("paused", False)
        new_paused = not current_paused
        if store.pause_plan(pid, plan_id, new_paused):
            status = "paused" if new_paused else "resumed"
            await update.message.reply_text(f"Plan {status} successfully!")

async def cmd_stock_status(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("This command is only for admins.")
        return
    if len(context.args) > 0:
        pid = context.args[0]
        product = get_product(pid)
        if not product:
            await update.message.reply_text("Product not found")
            return
        status_text = f"STOCK STATUS: {product['name']}\n\n"
        prod_paused = "PAUSED" if product.get("paused", False) else "ACTIVE"
        prod_stock = product.get("stock", -1)
        prod_stock_text = "Unlimited" if prod_stock == -1 else str(prod_stock)
        status_text += f"Product: {prod_paused} | Stock: {prod_stock_text}\n\n"
        if product.get("plans"):
            status_text += "Plans:\n"
            for plan in product["plans"]:
                plan_paused = "P" if plan.get("paused", False) else "A"
                plan_stock = plan.get("stock", -1)
                plan_stock_text = "U" if plan_stock == -1 else str(plan_stock)
                status_text += f"  {plan_paused} {plan['name']}: Stock {plan_stock_text}\n"
        await update.message.reply_text(status_text)
    else:
        products = load_products()["items"]
        status_text = "ALL PRODUCTS STOCK STATUS\n\n"
        for pid, product in products.items():
            prod_paused = "P" if product.get("paused", False) else "A"
            status_text += f"{prod_paused} {product['name']}\n"
            for plan in product.get("plans", []):
                plan_paused = "P" if plan.get("paused", False) else "A"
                plan_stock = plan.get("stock", -1)
                plan_stock_text = "U" if plan_stock == -1 else str(plan_stock)
                status_text += f"   {plan_paused} {plan['name']}: {plan_stock_text}\n"
            status_text += "\n"
        await update.message.reply_text(status_text)

# ========== customer screens ==========
def category_screen(cat_id, user_id):
    name = button_name(cat_id)
    if cat_id not in PRODUCT_CATEGORIES:
        text = "<b>" + html.escape(name) + "</b>" + NL + NL + "This section is coming soon."
        rows = [[{"text": "Back", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}]]
        return text, rows, None
    prods = products_in_category(cat_id)
    rows = []
    i = 0
    while i < len(prods):
        row = [{"text": prods[i][1]["name"], "callback_data": "prod:" + prods[i][0], "emoji_id": prods[i][1].get("emoji_id")}]
        if i + 1 < len(prods):
            row.append({"text": prods[i + 1][1]["name"], "callback_data": "prod:" + prods[i + 1][0], "emoji_id": prods[i + 1][1].get("emoji_id")})
        rows.append(row)
        i += 2
    if user_id == ADMIN_ID:
        rows.append([{"text": "Add Product", "callback_data": "addprod:" + cat_id, "emoji_id": None}])
        if prods:
            rows.append([{"text": "Manage Products", "callback_data": "mprod:" + cat_id, "emoji_id": None}])
        rows.append([{"text": "Edit Page Text", "callback_data": "catintro:" + cat_id, "emoji_id": None}])
        rows.append([{"text": "Set Page Image", "callback_data": "catimage:" + cat_id, "emoji_id": None}])
    rows.append([{"text": "Back", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}])
    cat_image = get_category_image(cat_id)
    if prods:
        text = "<b>" + html.escape(name) + "</b>" + NL + html.escape(get_category_intro(cat_id))
    elif user_id == ADMIN_ID:
        text = "<b>" + html.escape(name) + "</b>" + NL + "No products yet. Tap 'Add Product' to create one."
    else:
        text = "<b>" + html.escape(name) + "</b>" + NL + "No products available yet. Please check back soon."
    return text, rows, cat_image

def product_screen(pid, user_id=None):
    product = get_product(pid)
    if not product:
        return None
    available, reason = store.check_product_availability(product)
    if not available:
        caption = "<b>" + html.escape(product["name"]) + "</b>" + NL + NL
        if reason == "paused":
            caption += "<b>Sorry, this product is currently paused.</b>" + NL
        else:
            caption += "<b>Sorry, this product is currently out of stock.</b>" + NL
        caption += "Please check back later."
        rows = [[{"text": "Back", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}]]
        return caption, rows, None
    caption = "<b>" + html.escape(product["name"]) + "</b>"
    desc = html.escape(product.get("description", ""))
    if desc:
        caption += NL + NL + desc
    rows = []
    for plan in product.get("plans", []):
        plan_available, plan_reason = store.check_plan_availability(product, plan)
        if plan_available:
            rows.append([{"text": plan["name"] + " | " + plan["price"], "callback_data": "plan:" + pid + ":" + plan["id"], "emoji_id": plan.get("emoji_id")}])
        else:
            status_text = "PAUSED" if plan_reason == "plan_paused" else "OUT"
            rows.append([{"text": plan["name"] + " | " + plan["price"] + " [" + status_text + "]", "callback_data": "noop", "emoji_id": plan.get("emoji_id")}])
    if user_id == ADMIN_ID:
        rows.append([{"text": "Edit Product", "callback_data": "pm:" + pid, "emoji_id": None}])
    rows.append([{"text": "Back", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}])
    return caption, rows, product.get("image")

def plan_screen(pid, plan_id, qty=1):
    product = get_product(pid)
    if not product:
        return None
    plan = find_plan(product, plan_id)
    if not plan:
        return None
    available, reason = store.check_plan_availability(product, plan)
    if not available:
        caption = "<b>" + html.escape(product["name"]) + "</b>" + NL + NL
        if reason == "product_paused":
            caption += "<b>Sorry, this product is currently paused.</b>" + NL
        elif reason == "plan_paused":
            caption += "<b>Sorry, this plan is currently paused.</b>" + NL
        else:
            caption += "<b>Sorry, this product is currently out of stock.</b>" + NL
        caption += "Please check back later."
        rows = [[{"text": "Back", "callback_data": "prod:" + pid, "emoji_id": get_action_emoji("back_button")}]]
        return caption, rows, None
    if qty < 1:
        qty = 1
    available_stock = store.get_available_stock(product, plan)
    stock_text = ""
    if available_stock > 0:
        stock_text = f"\nStock available: {available_stock}"
        if qty > available_stock:
            qty = available_stock
    caption = (
        "<b>" + html.escape(product["name"]) + "</b>" + NL + NL
        + "<b>Plan: " + html.escape(plan["name"]) + "</b>" + NL
        + "<b>Price: " + html.escape(plan["price"]) + "</b>"
        + stock_text
    )
    base = pid + ":" + plan_id + ":" + str(qty)
    action_emojis = load_action_emojis()
    if available_stock != 1 and available_stock != 0:
        rows = [
            [
                {"text": "-", "callback_data": "pqd:" + base, "emoji_id": action_emojis.get("decrement")},
                {"text": "Qty: " + str(qty), "callback_data": "noop", "emoji_id": None},
                {"text": "+", "callback_data": "pqi:" + base, "emoji_id": action_emojis.get("increment")},
            ],
            [{"text": "Buy Now", "callback_data": "cart:buypq:" + base, "emoji_id": action_emojis.get("buy_now")}],
            [{"text": "Add to Cart", "callback_data": "cart:addpq:" + base, "emoji_id": action_emojis.get("add_to_cart")}],
            [{"text": "Back", "callback_data": "prod:" + pid, "emoji_id": action_emojis.get("back_button")}],
        ]
    else:
        rows = [
            [{"text": "Buy Now", "callback_data": "cart:buypq:" + base, "emoji_id": action_emojis.get("buy_now")}],
            [{"text": "Add to Cart", "callback_data": "cart:addpq:" + base, "emoji_id": action_emojis.get("add_to_cart")}],
            [{"text": "Back", "callback_data": "prod:" + pid, "emoji_id": action_emojis.get("back_button")}],
        ]
    return caption, rows, plan.get("image")

def tg_select_screen(user_id):
    tg = load_tg()
    text = "<b>" + html.escape(tg.get("select_text", "")) + "</b>"
    rows = []
    for pl in tg.get("plans", []):
        rows.append([{"text": pl["name"] + " | " + pl["price"], "callback_data": "tgplan:" + pl["id"], "emoji_id": pl.get("emoji_id")}])
    if user_id == ADMIN_ID:
        rows.append([{"text": "Manage Telegram Premium", "callback_data": "tgmanage", "emoji_id": None}])
    rows.append([{"text": "Back", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}])
    return text, rows, tg.get("select_image")

def tg_username_screen():
    tg = load_tg()
    text = "<b>" + html.escape(tg.get("username_text", "")) + "</b>"
    rows = [[{"text": "Back", "callback_data": "tgmenu", "emoji_id": get_action_emoji("back_button")}]]
    return text, rows, tg.get("username_image")

def tg_confirm_screen(plan, username):
    caption = (
        "<b>Plan: " + html.escape(plan["name"]) + " | " + html.escape(plan["price"]) + "</b>" + NL
        + "<b>User: @" + html.escape(username) + "</b>"
    )
    action_emojis = load_action_emojis()
    rows = [
        [{"text": "Buy Now", "callback_data": "cart:buytg", "emoji_id": action_emojis.get("buy_now")}],
        [{"text": "Add to Cart", "callback_data": "cart:addtg", "emoji_id": action_emojis.get("add_to_cart")}],
        [{"text": "Back", "callback_data": "tgmenu", "emoji_id": action_emojis.get("back_button")}],
    ]
    return caption, rows, plan.get("image")

# ========== admin panels ==========
def tg_manage_panel():
    tg = load_tg()
    text = (
        "MANAGE TELEGRAM PREMIUM" + NL
        + "Select text: " + tg.get("select_text", "") + NL
        + "Select image: " + ("Yes" if tg.get("select_image") else "No") + NL
        + "Username text: " + tg.get("username_text", "") + NL
        + "Username image: " + ("Yes" if tg.get("username_image") else "No") + NL
        + "Plans: " + str(len(tg.get("plans", [])))
    )
    kb = [
        [InlineKeyboardButton("Edit Select Text", callback_data="tg_seltext")],
        [InlineKeyboardButton("Change Select Image", callback_data="tg_selimg")],
        [InlineKeyboardButton("Edit Username Text", callback_data="tg_usrtext")],
        [InlineKeyboardButton("Change Username Image", callback_data="tg_usrimg")],
        [InlineKeyboardButton("Manage Plans", callback_data="tgmpl")],
        [InlineKeyboardButton("Back", callback_data="tgmenu")],
    ]
    return text, InlineKeyboardMarkup(kb)

def tg_manage_plans_panel():
    tg = load_tg()
    kb = []
    for pl in tg.get("plans", []):
        kb.append([
            InlineKeyboardButton(pl["name"] + " | " + pl["price"], callback_data="tgplm:" + pl["id"]),
            InlineKeyboardButton("Up", callback_data="tgplu:" + pl["id"]),
            InlineKeyboardButton("Down", callback_data="tgpld:" + pl["id"]),
        ])
    kb.append([InlineKeyboardButton("Add Plan", callback_data="tgpladd")])
    kb.append([InlineKeyboardButton("Back", callback_data="tgmanage")])
    return "MANAGE PLANS - Telegram Premium" + NL + "Tap a plan to edit it.", InlineKeyboardMarkup(kb)

def tg_plan_manage_menu(plan_id):
    plan = find_tg_plan(plan_id)
    if not plan:
        return None
    img = "Yes" if plan.get("image") else "No"
    text = "EDITING PLAN" + NL + "Name: " + plan["name"] + NL + "Price: " + plan["price"] + NL + "Image: " + img
    kb = [
        [InlineKeyboardButton("Edit Name", callback_data="tgplen:" + plan_id)],
        [InlineKeyboardButton("Edit Price", callback_data="tgplep:" + plan_id)],
        [InlineKeyboardButton("Change Image", callback_data="tgplei:" + plan_id)],
        [InlineKeyboardButton("Delete Plan", callback_data="tgpldel:" + plan_id)],
        [InlineKeyboardButton("Back", callback_data="tgmpl")],
    ]
    return text, InlineKeyboardMarkup(kb)

def edit_panel():
    text = "EDIT MENU" + NL + "Choose what you want to do:"
    kb = [
        [InlineKeyboardButton("Edit Welcome Text", callback_data="e_wtext")],
        [InlineKeyboardButton("Edit Welcome Image", callback_data="e_wimg")],
        [InlineKeyboardButton("Add Button", callback_data="e_add")],
        [InlineKeyboardButton("Rename Button", callback_data="e_rename")],
        [InlineKeyboardButton("Set Button Emoji", callback_data="e_setemoji")],
        [InlineKeyboardButton("Set Action Button Emojis", callback_data="e_setactionemoji")],
        [InlineKeyboardButton("Set Product Emoji", callback_data="e_setprodemoji")],
        [InlineKeyboardButton("Set Plan Emoji", callback_data="e_setplanemoji")],
        [InlineKeyboardButton("Set Wallet Button Emoji", callback_data="e_setwalletemoji")],
        [InlineKeyboardButton("Resize Button", callback_data="e_resize")],
        [InlineKeyboardButton("Reorder Buttons", callback_data="e_reorder")],
        [InlineKeyboardButton("Delete Button", callback_data="e_delete")],
        [InlineKeyboardButton("Crypto Payments", callback_data="pay:admin")],
        [InlineKeyboardButton("Close", callback_data="e_close")],
    ]
    return text, InlineKeyboardMarkup(kb)

def list_buttons_panel(title, action_prefix):
    buttons = load_buttons()
    kb = []
    for b in buttons:
        emoji_info = " [E]" if b.get("emoji_id") else ""
        kb.append([InlineKeyboardButton(b["text"] + "  (" + b["size"] + ")" + emoji_info, callback_data=action_prefix + b["id"])])
    kb.append([InlineKeyboardButton("Back", callback_data="e_back")])
    return title, InlineKeyboardMarkup(kb)

def reorder_panel():
    buttons = load_buttons()
    kb = []
    for i, b in enumerate(buttons):
        kb.append([
            InlineKeyboardButton(str(i + 1) + ". " + b["text"], callback_data="noop"),
            InlineKeyboardButton("Up", callback_data="mvu:" + b["id"]),
            InlineKeyboardButton("Down", callback_data="mvd:" + b["id"]),
        ])
    kb.append([InlineKeyboardButton("Back", callback_data="e_back")])
    return "REORDER BUTTONS" + NL + "Use Up/Down to move a button:", InlineKeyboardMarkup(kb)

def manage_products_panel(cat_id):
    name = button_name(cat_id)
    prods = products_in_category(cat_id)
    kb = []
    for pid, p in prods:
        stock_status = ""
        if p.get("paused", False):
            stock_status = " [PAUSED]"
        elif p.get("stock", -1) == 0:
            stock_status = " [OUT]"
        elif p.get("stock", -1) > 0:
            stock_status = f" [{p['stock']}]"
        kb.append([
            InlineKeyboardButton(p["name"] + stock_status, callback_data="pm:" + pid),
            InlineKeyboardButton("Up", callback_data="pmu:" + pid),
            InlineKeyboardButton("Down", callback_data="pmd:" + pid),
        ])
    kb.append([InlineKeyboardButton("Add Product", callback_data="addprod:" + cat_id)])
    kb.append([InlineKeyboardButton("Back", callback_data="cat:" + cat_id)])
    return "MANAGE PRODUCTS - " + name + NL + "Tap a product to edit.", InlineKeyboardMarkup(kb)

def product_manage_menu(pid):
    product = get_product(pid)
    if not product:
        return None
    cat = product["category"]
    img = "Yes" if product.get("image") else "No"
    stock = product.get("stock", -1)
    paused = product.get("paused", False)
    stock_text = "Unlimited" if stock == -1 else str(stock)
    status_text = "PAUSED" if paused else "ACTIVE"
    text = (
        "EDITING: " + product["name"] + NL + NL
        + "Description: " + (product.get("description") or "(none)") + NL
        + "Image: " + img + NL
        + "Product Stock: " + stock_text + NL
        + "Status: " + status_text + NL
        + "Plans: " + str(len(product.get("plans", []))) + NL + NL
        + "Note: Individual plans can have their own stock settings"
    )
    kb = [
        [InlineKeyboardButton("Edit Name", callback_data="pen:" + pid)],
        [InlineKeyboardButton("Edit Description", callback_data="ped:" + pid)],
        [InlineKeyboardButton("Change Image", callback_data="pei:" + pid)],
        [InlineKeyboardButton("Set Product Stock", callback_data="prod_stock:" + pid)],
        [InlineKeyboardButton("Pause/Resume Product", callback_data="prod_pause:" + pid)],
        [InlineKeyboardButton("Manage Plans", callback_data="mpl:" + pid)],
        [InlineKeyboardButton("Delete Product", callback_data="pdel:" + pid)],
        [InlineKeyboardButton("Back", callback_data="mprod:" + cat)],
    ]
    return text, InlineKeyboardMarkup(kb)

def manage_plans_panel(pid):
    product = get_product(pid)
    if not product:
        return None
    kb = []
    for pl in product.get("plans", []):
        stock_status = ""
        if pl.get("paused", False):
            stock_status = " [PAUSED]"
        elif pl.get("stock", -1) == 0:
            stock_status = " [OUT]"
        elif pl.get("stock", -1) > 0:
            stock_status = f" [{pl['stock']}]"
        kb.append([
            InlineKeyboardButton(pl["name"] + " | " + pl["price"] + stock_status, callback_data="plm:" + pid + ":" + pl["id"]),
            InlineKeyboardButton("Up", callback_data="plu:" + pid + ":" + pl["id"]),
            InlineKeyboardButton("Down", callback_data="pld:" + pid + ":" + pl["id"]),
        ])
    kb.append([InlineKeyboardButton("Add Plan", callback_data="pladd:" + pid)])
    kb.append([InlineKeyboardButton("Back", callback_data="pm:" + pid)])
    return "MANAGE PLANS - " + product["name"] + NL + "Tap a plan to edit.", InlineKeyboardMarkup(kb)

def plan_manage_menu(pid, plan_id):
    product = get_product(pid)
    if not product:
        return None
    plan = find_plan(product, plan_id)
    if not plan:
        return None
    img = "Yes" if plan.get("image") else "No"
    stock = plan.get("stock", -1)
    paused = plan.get("paused", False)
    stock_text = "Unlimited" if stock == -1 else str(stock)
    status_text = "PAUSED" if paused else "ACTIVE"
    product_stock = product.get("stock", -1)
    product_stock_text = "Unlimited" if product_stock == -1 else str(product_stock)
    text = (
        "EDITING PLAN" + NL + NL
        + "Plan: " + plan["name"] + NL
        + "Price: " + plan["price"] + NL
        + "Image: " + img + NL
        + "Plan Stock: " + stock_text + NL
        + "Status: " + status_text + NL + NL
        + f"Product Stock: {product_stock_text}" + NL
        + "Note: Plan stock overrides product stock"
    )
    kb = [
        [InlineKeyboardButton("Edit Name", callback_data="plen:" + pid + ":" + plan_id)],
        [InlineKeyboardButton("Edit Price", callback_data="plep:" + pid + ":" + plan_id)],
        [InlineKeyboardButton("Change Image", callback_data="plei:" + pid + ":" + plan_id)],
        [InlineKeyboardButton("Set Plan Stock", callback_data="plan_stock:" + pid + ":" + plan_id)],
        [InlineKeyboardButton("Pause/Resume Plan", callback_data="plan_pause:" + pid + ":" + plan_id)],
        [InlineKeyboardButton("Delete Plan", callback_data="pldel:" + pid + ":" + plan_id)],
        [InlineKeyboardButton("Back", callback_data="mpl:" + pid)],
    ]
    return text, InlineKeyboardMarkup(kb)

# ========== callbacks ==========
async def on_callback(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data == "home":
        context.user_data.clear()
        msg = query.message
        try:
            await msg.delete()
        except Exception:
            pass
        await send_home(context, msg.chat_id, user_id, query.from_user.first_name)
        await query.answer()
        return

    if data.startswith("open:"):
        cat_id = data[5:]
        if cat_id == "support":
            sup = load_support()
            first_name = query.from_user.first_name or "there"
            raw_text = sup.get("text") or DEFAULT_SUPPORT["text"]
            text = "<b>" + html.escape(raw_text.replace("{name}", first_name)) + "</b>"
            photo = sup.get("image")
            if user_id == ADMIN_ID:
                rows = [
                    [{"text": "Edit Text", "callback_data": "sup_text", "emoji_id": None}],
                    [{"text": "Edit Image", "callback_data": "sup_img", "emoji_id": None}],
                    [{"text": "Close", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}],
                ]
            else:
                rows = [[{"text": "Close", "callback_data": "close", "emoji_id": get_action_emoji("back_button")}]]
            await query.answer()
            if photo:
                await raw_send_photo(query.message.chat_id, photo, text, rows)
            else:
                await raw_send_message(query.message.chat_id, text, rows)
            return
        if cat_id == "tg":
            text, rows, photo = tg_select_screen(user_id)
            if photo:
                await raw_send_photo(query.message.chat_id, photo, text, rows)
            else:
                await raw_send_message(query.message.chat_id, text, rows)
            await query.answer()
            return
        if cat_id == "wallet":
            await payments.open_wallet(query, context)
            return
        text, rows, photo = category_screen(cat_id, user_id)
        if photo:
            await raw_send_photo(query.message.chat_id, photo, text, rows)
        else:
            await raw_send_message(query.message.chat_id, text, rows)
        await query.answer()
        return

    if data == "tgmenu":
        context.user_data.clear()
        text, rows, photo = tg_select_screen(user_id)
        try:
            await query.message.delete()
        except Exception:
            pass
        if photo:
            await raw_send_photo(query.message.chat_id, photo, text, rows)
        else:
            await raw_send_message(query.message.chat_id, text, rows)
        await query.answer()
        return

    if data.startswith("tgplan:"):
        plan_id = data[7:]
        plan = find_tg_plan(plan_id)
        if not plan:
            await query.answer("Plan not found", show_alert=True)
            return
        try:
            await query.message.delete()
        except Exception:
            pass
        text, rows, photo = tg_username_screen()
        if photo:
            await raw_send_photo(query.message.chat_id, photo, text, rows)
        else:
            await raw_send_message(query.message.chat_id, text, rows)
        context.user_data.clear()
        context.user_data["state"] = "tg_await_username"
        context.user_data["tg_plan"] = plan_id
        await query.answer()
        return

    if data.startswith("cat:"):
        cat_id = data[4:]
        if cat_id == "tg":
            text, rows, photo = tg_select_screen(user_id)
            try:
                await query.message.delete()
            except Exception:
                pass
            if photo:
                await raw_send_photo(query.message.chat_id, photo, text, rows)
            else:
                await raw_send_message(query.message.chat_id, text, rows)
            await query.answer()
            return
        text, rows, photo = category_screen(cat_id, user_id)
        if photo:
            await raw_edit_message_media(query.message.chat_id, query.message.message_id, photo, text, rows)
        else:
            await raw_edit_message_text(query.message.chat_id, query.message.message_id, text, rows)
        await query.answer()
        return

    if data.startswith("catimage:"):
        cat_id = data[9:]
        context.user_data.clear()
        context.user_data["state"] = "edit_cat_image"
        context.user_data["target_cat"] = cat_id
        current = get_category_image(cat_id) or "None"
        await safe_edit(query, context,
            "EDIT PAGE IMAGE - " + button_name(cat_id) + NL + NL
            + "Current image: " + ("Yes" if current != "None" else "No") + NL + NL
            + "Send a new image, or send 0 to remove it."
        )
        return

    if data.startswith("prod:"):
        pid = data[5:]
        screen = product_screen(pid, user_id)
        if not screen:
            await query.answer("Product not found", show_alert=True)
            return
        caption, rows, photo = screen
        if photo:
            await raw_edit_message_media(query.message.chat_id, query.message.message_id, photo, caption, rows)
        else:
            await raw_edit_message_text(query.message.chat_id, query.message.message_id, caption, rows)
        await query.answer()
        return

    if data.startswith("plan:"):
        pid, plan_id = data[5:].split(":", 1)
        screen = plan_screen(pid, plan_id, 1)
        if not screen:
            await query.answer("Plan not found", show_alert=True)
            return
        caption, rows, photo = screen
        if photo:
            await raw_edit_message_media(query.message.chat_id, query.message.message_id, photo, caption, rows)
        else:
            await raw_edit_message_text(query.message.chat_id, query.message.message_id, caption, rows)
        await query.answer()
        return

    if data.startswith("pqi:") or data.startswith("pqd:"):
        pid, plan_id, qty_str = data[4:].split(":", 2)
        try:
            qty = int(qty_str)
        except Exception:
            qty = 1
        qty = qty + 1 if data.startswith("pqi:") else qty - 1
        if qty < 1:
            qty = 1
        screen = plan_screen(pid, plan_id, qty)
        if not screen:
            await query.answer("Plan not found", show_alert=True)
            return
        caption, rows, photo = screen
        if photo:
            await raw_edit_message_media(query.message.chat_id, query.message.message_id, photo, caption, rows)
        else:
            await raw_edit_message_text(query.message.chat_id, query.message.message_id, caption, rows)
        await query.answer()
        return

    if data == "sup_text":
        if user_id != ADMIN_ID:
            await query.answer("Not allowed", show_alert=True)
            return
        context.user_data.clear()
        context.user_data["state"] = "edit_support_text"
        cur = load_support().get("text", "")
        await safe_edit(query, context, "EDIT SUPPORT TEXT" + NL + NL + "Current:" + NL + cur + NL + NL + "Use {name} for the customer's first name.")
        await query.answer()
        return

    if data == "sup_img":
        if user_id != ADMIN_ID:
            await query.answer("Not allowed", show_alert=True)
            return
        context.user_data.clear()
        context.user_data["state"] = "edit_support_image"
        await safe_edit(query, context, "Send the new SUPPORT IMAGE. (send 0 to remove it)")
        await query.answer()
        return

    if data == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        return

    if data == "noop":
        await query.answer()
        return

    if user_id != ADMIN_ID:
        await query.answer("Not allowed", show_alert=True)
        return

    if data == "tgmanage":
        context.user_data.clear()
        text, kb = tg_manage_panel()
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data == "tg_seltext":
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_select_text"
        await safe_edit(query, context, "Send the new SELECT-PLAN text:")
        return

    if data == "tg_selimg":
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_select_image"
        await safe_edit(query, context, "Send the new SELECT-PLAN image. (send 0 to remove)")
        return

    if data == "tg_usrtext":
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_user_text"
        await safe_edit(query, context, "Send the new USERNAME-PROMPT text:")
        return

    if data == "tg_usrimg":
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_user_image"
        await safe_edit(query, context, "Send the new USERNAME-PROMPT image. (send 0 to remove)")
        return

    if data == "tgmpl":
        text, kb = tg_manage_plans_panel()
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("tgplu:") or data.startswith("tgpld:"):
        plan_id = data[6:]
        reorder_tg_plan(plan_id, up=data.startswith("tgplu:"))
        text, kb = tg_manage_plans_panel()
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("tgplm:"):
        plan_id = data[6:]
        res = tg_plan_manage_menu(plan_id)
        if not res:
            await query.answer("Not found", show_alert=True)
            return
        text, kb = res
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("tgplen:"):
        plan_id = data[7:]
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_plan_name"
        context.user_data["target_tg_plan"] = plan_id
        await safe_edit(query, context, "Send the new PLAN NAME:")
        return

    if data.startswith("tgplep:"):
        plan_id = data[7:]
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_plan_price"
        context.user_data["target_tg_plan"] = plan_id
        await safe_edit(query, context, "Send the new PRICE (example: $30):")
        return

    if data.startswith("tgplei:"):
        plan_id = data[7:]
        context.user_data.clear()
        context.user_data["state"] = "edit_tg_plan_image"
        context.user_data["target_tg_plan"] = plan_id
        await safe_edit(query, context, "Send the new PLAN IMAGE. (send 0 to remove)")
        return

    if data.startswith("tgpldelok:"):
        plan_id = data[10:]
        delete_tg_plan(plan_id)
        text, kb = tg_manage_plans_panel()
        await safe_edit(query, context, "Plan deleted." + NL + NL + text, reply_markup=kb)
        return

    if data.startswith("tgpldel:"):
        plan_id = data[8:]
        plan = find_tg_plan(plan_id)
        nm = plan["name"] if plan else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete", callback_data="tgpldelok:" + plan_id)],
            [InlineKeyboardButton("No, go back", callback_data="tgplm:" + plan_id)],
        ])
        await safe_edit(query, context, "Delete plan '" + nm + "'?", reply_markup=kb)
        return

    if data == "tgpladd":
        context.user_data.clear()
        context.user_data["state"] = "addtgplan_name"
        await safe_edit(query, context, "Send the NEW PLAN NAME (example: 3 Months):")
        return

    if data.startswith("addprod:"):
        cat_id = data[8:]
        context.user_data.clear()
        context.user_data["state"] = "prod_image"
        context.user_data["draft"] = {"category": cat_id, "name": "", "description": "", "image": None, "plans": []}
        await query.message.reply_text(
            "ADD PRODUCT" + NL + NL + "Step 1: Send the PRODUCT IMAGE now." + NL
            + "(or send 0 to skip the image)"
        )
        await query.answer()
        return

    if data.startswith("mprod:"):
        cat_id = data[6:]
        text, kb = manage_products_panel(cat_id)
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("catintro:"):
        cat_id = data[9:]
        context.user_data.clear()
        context.user_data["state"] = "edit_cat_intro"
        context.user_data["target_cat"] = cat_id
        current = get_category_intro(cat_id)
        await safe_edit(query, context,
            "EDIT PAGE TEXT - " + button_name(cat_id) + NL + NL
            + "Current text:" + NL + current + NL + NL
            + "Send the new text."
        )
        return

    if data.startswith("pmu:") or data.startswith("pmd:"):
        pid = data[4:]
        reorder_product(pid, up=data.startswith("pmu:"))
        product = get_product(pid)
        cat_id = product["category"] if product else ""
        text, kb = manage_products_panel(cat_id)
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("pm:"):
        pid = data[3:]
        res = product_manage_menu(pid)
        if not res:
            await query.answer("Not found", show_alert=True)
            return
        text, kb = res
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("pen:"):
        pid = data[4:]
        context.user_data.clear()
        context.user_data["state"] = "edit_prod_name"
        context.user_data["target_pid"] = pid
        await safe_edit(query, context, "Send the new PRODUCT NAME:")
        return

    if data.startswith("ped:"):
        pid = data[4:]
        context.user_data.clear()
        context.user_data["state"] = "edit_prod_desc"
        context.user_data["target_pid"] = pid
        await safe_edit(query, context, "Send the new DESCRIPTION:")
        return

    if data.startswith("pei:"):
        pid = data[4:]
        context.user_data.clear()
        context.user_data["state"] = "edit_prod_image"
        context.user_data["target_pid"] = pid
        await safe_edit(query, context, "Send the new PRODUCT IMAGE. (send 0 to remove)")
        return

    if data.startswith("pdelok:"):
        pid = data[7:]
        d = load_products()
        product = d["items"].get(pid)
        cat_id = product["category"] if product else ""
        if pid in d["items"]:
            del d["items"][pid]
            save_products(d)
        text, kb = manage_products_panel(cat_id)
        await safe_edit(query, context, "Product deleted." + NL + NL + text, reply_markup=kb)
        return

    if data.startswith("pdel:"):
        pid = data[5:]
        product = get_product(pid)
        name = product["name"] if product else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete", callback_data="pdelok:" + pid)],
            [InlineKeyboardButton("No, go back", callback_data="pm:" + pid)],
        ])
        await safe_edit(query, context, "Delete product '" + name + "' and all its plans?", reply_markup=kb)
        return

    if data.startswith("mpl:"):
        pid = data[4:]
        res = manage_plans_panel(pid)
        if not res:
            await query.answer("Not found", show_alert=True)
            return
        text, kb = res
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("plu:") or data.startswith("pld:"):
        pid, plan_id = data[4:].split(":", 1)
        reorder_plan(pid, plan_id, up=data.startswith("plu:"))
        text, kb = manage_plans_panel(pid)
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("plm:"):
        pid, plan_id = data[4:].split(":", 1)
        res = plan_manage_menu(pid, plan_id)
        if not res:
            await query.answer("Not found", show_alert=True)
            return
        text, kb = res
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("plen:"):
        pid, plan_id = data[5:].split(":", 1)
        context.user_data.clear()
        context.user_data["state"] = "edit_plan_name"
        context.user_data["target_pid"] = pid
        context.user_data["target_plan"] = plan_id
        await safe_edit(query, context, "Send the new PLAN NAME:")
        return

    if data.startswith("plep:"):
        pid, plan_id = data[5:].split(":", 1)
        context.user_data.clear()
        context.user_data["state"] = "edit_plan_price"
        context.user_data["target_pid"] = pid
        context.user_data["target_plan"] = plan_id
        await safe_edit(query, context, "Send the new PRICE:")
        return

    if data.startswith("plei:"):
        pid, plan_id = data[5:].split(":", 1)
        context.user_data.clear()
        context.user_data["state"] = "edit_plan_image"
        context.user_data["target_pid"] = pid
        context.user_data["target_plan"] = plan_id
        await safe_edit(query, context, "Send the new PLAN IMAGE. (send 0 to remove)")
        return

    if data.startswith("pldelok:"):
        pid, plan_id = data[8:].split(":", 1)
        d = load_products()
        product = d["items"].get(pid)
        if product:
            product["plans"] = [pl for pl in product.get("plans", []) if pl["id"] != plan_id]
            save_products(d)
        text, kb = manage_plans_panel(pid)
        await safe_edit(query, context, "Plan deleted." + NL + NL + text, reply_markup=kb)
        return

    if data.startswith("pldel:"):
        pid, plan_id = data[6:].split(":", 1)
        product = get_product(pid)
        plan = find_plan(product, plan_id) if product else None
        nm = plan["name"] if plan else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete", callback_data="pldelok:" + pid + ":" + plan_id)],
            [InlineKeyboardButton("No, go back", callback_data="plm:" + pid + ":" + plan_id)],
        ])
        await safe_edit(query, context, "Delete plan '" + nm + "'?", reply_markup=kb)
        return

    if data.startswith("pladd:"):
        pid = data[6:]
        context.user_data.clear()
        context.user_data["state"] = "addplan_name"
        context.user_data["target_pid"] = pid
        await safe_edit(query, context, "Send the NEW PLAN NAME:")
        return

    if data.startswith("prod_stock:"):
        pid = data[11:]
        context.user_data.clear()
        context.user_data["state"] = "set_product_stock"
        context.user_data["target_pid"] = pid
        product = get_product(pid)
        current_stock = product.get("stock", -1) if product else -1
        await safe_edit(query, context,
            f"SET PRODUCT STOCK\n\nCurrent stock: {current_stock}\n\nSend a number:\n-1 = Unlimited stock\n0 = Out of stock\n1-999999 = Limited stock"
        )
        return

    if data.startswith("prod_pause:"):
        pid = data[11:]
        product = get_product(pid)
        if product:
            current = product.get("paused", False)
            new_status = not current
            if store.pause_product(pid, new_status):
                status_text = "PAUSED" if new_status else "ACTIVE"
                await query.answer(f"Product is now {status_text}")
        res = product_manage_menu(pid)
        if res:
            text, kb = res
            await safe_edit(query, context, text, reply_markup=kb)
        return

    if data.startswith("plan_stock:"):
        parts = data[11:].split(":", 1)
        pid = parts[0]
        plan_id = parts[1]
        context.user_data.clear()
        context.user_data["state"] = "set_plan_stock"
        context.user_data["target_pid"] = pid
        context.user_data["target_plan"] = plan_id
        product = get_product(pid)
        plan = find_plan(product, plan_id) if product else None
        current_stock = plan.get("stock", -1) if plan else -1
        await safe_edit(query, context,
            f"SET PLAN STOCK\n\nCurrent stock: {current_stock}\n\nSend a number:\n-1 = Unlimited stock\n0 = Out of stock\n1-999999 = Limited stock"
        )
        return

    if data.startswith("plan_pause:"):
        parts = data[11:].split(":", 1)
        pid = parts[0]
        plan_id = parts[1]
        product = get_product(pid)
        plan = find_plan(product, plan_id) if product else None
        if plan:
            current = plan.get("paused", False)
            new_status = not current
            if store.pause_plan(pid, plan_id, new_status):
                status_text = "PAUSED" if new_status else "ACTIVE"
                await query.answer(f"Plan is now {status_text}")
        res = plan_manage_menu(pid, plan_id)
        if res:
            text, kb = res
            await safe_edit(query, context, text, reply_markup=kb)
        return

    if data == "edit":
        context.user_data.clear()
        text, kb = edit_panel()
        await query.message.reply_text(text, reply_markup=kb)
        await query.answer()
        return

    if data == "e_back":
        context.user_data.clear()
        text, kb = edit_panel()
        await safe_edit(query, context, text, reply_markup=kb)
        return

    if data == "e_close":
        context.user_data.clear()
        await safe_edit(query, context, "Edit closed. Send /start to see the updated menu.")
        return

    if data == "e_wtext":
        context.user_data.clear()
        context.user_data["state"] = "edit_welcome_text"
        current = get_welcome_text()
        await safe_edit(query, context,
            "EDIT WELCOME TEXT" + NL + NL + "Current text:" + NL + current + NL + NL
            + "Send the new welcome text. Use {name} for the customer's name."
        )
        return

    if data == "e_wimg":
        context.user_data.clear()
        context.user_data["state"] = "edit_welcome_image"
        await safe_edit(query, context,
            "EDIT WELCOME IMAGE" + NL + NL + "Send the new welcome IMAGE now. (send 0 to remove)"
        )
        return

    if data == "e_add":
        context.user_data["state"] = "add_name"
        await safe_edit(query, context, "Send the text for the new button:")
        return

    if data in ("addsize:half", "addsize:full"):
        size = "half" if data.endswith("half") else "full"
        text = context.user_data.get("new_text")
        if text:
            buttons = load_buttons()
            buttons.append({"id": uuid.uuid4().hex[:6], "text": text, "size": size, "emoji_id": None})
            save_buttons(buttons)
        context.user_data.clear()
        panel_text, kb = edit_panel()
        await safe_edit(query, context, "Button added." + NL + NL + panel_text, reply_markup=kb)
        return

    if data == "e_rename":
        title, kb = list_buttons_panel("Pick a button to RENAME:", "rn:")
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data.startswith("rn:"):
        bid = data[3:]
        context.user_data["state"] = "rename"
        context.user_data["target"] = bid
        b = find_button(load_buttons(), bid)
        cur = b["text"] if b else ""
        await safe_edit(query, context, "Current name: " + cur + NL + "Send the new name:")
        return

    if data == "e_setemoji":
        title, kb = list_buttons_panel("Pick a button to set a custom emoji on:", "se:")
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data == "e_setactionemoji":
        action_emojis = load_action_emojis()
        text = "SET ACTION BUTTON EMOJIS\n\n"
        for key in action_emojis:
            status = "✅" if action_emojis[key] else "❌"
            text += f"{status} {key.replace('_', ' ').title()}\n"
        kb = [
            [InlineKeyboardButton("Buy Now", callback_data="setaction:buy_now")],
            [InlineKeyboardButton("Add to Cart", callback_data="setaction:add_to_cart")],
            [InlineKeyboardButton("Back Button", callback_data="setaction:back_button")],
            [InlineKeyboardButton("+ Increment", callback_data="setaction:increment")],
            [InlineKeyboardButton("- Decrement", callback_data="setaction:decrement")],
            [InlineKeyboardButton("Use Wallet", callback_data="setaction:use_wallet")],
            [InlineKeyboardButton("Back", callback_data="e_back")],
        ]
        await safe_edit(query, context, text, InlineKeyboardMarkup(kb))
        return

    if data.startswith("setaction:"):
        action_key = data[10:]
        context.user_data["state"] = "set_action_emoji"
        context.user_data["action_key"] = action_key
        await safe_edit(query, context,
            f"SET EMOJI FOR: {action_key.replace('_', ' ').upper()}\n\n"
            "Send a message with a custom animated emoji IN IT.\n"
            "Send 0 to REMOVE the current emoji.")
        return

    # ========== SET PRODUCT EMOJI (includes SMM services) ==========
    if data == "e_setprodemoji":
        all_products = load_products()["items"]
        kb = []
        # OTT / VPN products
        for pid, p in all_products.items():
            emoji_info = " [E]" if p.get("emoji_id") else ""
            kb.append([InlineKeyboardButton(p["name"] + emoji_info, callback_data="seprod:" + pid)])
        # SMM platforms (Instagram, TikTok etc.) — one button per platform
        smm_platforms = smm.load_platforms_for_emoji()
        for plat_id, plat_name, has_emoji in smm_platforms:
            emoji_info = " [E]" if has_emoji else ""
            kb.append([InlineKeyboardButton(plat_name + emoji_info + " [SMM]", callback_data="seprod_smm_plat:" + plat_id)])
        kb.append([InlineKeyboardButton("Back", callback_data="e_back")])
        await safe_edit(query, context, "Pick a product to set custom emoji:", InlineKeyboardMarkup(kb))
        return

    if data.startswith("seprod:"):
        pid = data[7:]
        product = get_product(pid)
        if not product:
            await query.answer("Product not found", show_alert=True)
            return
        cur_emoji = "ID: " + str(product.get("emoji_id")) if product.get("emoji_id") else "None"
        context.user_data.clear()
        context.user_data["state"] = "set_product_emoji_await"
        context.user_data["target_pid"] = pid
        await safe_edit(query, context,
            "SET CUSTOM EMOJI for product: " + product["name"] + NL + NL
            + "Current: " + cur_emoji + NL + NL
            + "Send a message with a custom animated emoji IN IT." + NL
            + "Send 0 to REMOVE the current emoji."
        )
        return

    # ========== SET EMOJI FOR SMM PLATFORM — show sub-menu ==========
    if data.startswith("seprod_smm_plat:"):
        plat_id = data[16:]
        plat_name, cur_emoji = smm.get_platform_emoji_info(plat_id)
        emoji_info = " [E]" if cur_emoji else ""
        # Build sub-menu: platform button emoji + per-service emojis
        kb = [[InlineKeyboardButton(plat_name + " Button Emoji" + emoji_info, callback_data="seprod_smm_btn:" + plat_id)]]
        # Add each service of this platform
        svcs = smm.load_services_for_emoji(plat_id)
        for sid, label, has_emoji in svcs:
            svc_emoji_info = " [E]" if has_emoji else ""
            kb.append([InlineKeyboardButton(label + svc_emoji_info, callback_data="seprod_smm_svc:" + plat_id + ":" + sid)])
        kb.append([InlineKeyboardButton("Back", callback_data="e_setprodemoji")])
        await safe_edit(query, context,
            "SET EMOJI — " + plat_name + NL + NL
            + "1. Tap '" + plat_name + " Button Emoji' to set emoji on the platform button." + NL
            + "2. Tap a service to set emoji on that service button.",
            InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith("seprod_smm_btn:"):
        plat_id = data[15:]
        plat_name, cur_emoji = smm.get_platform_emoji_info(plat_id)
        cur_text = "ID: " + str(cur_emoji) if cur_emoji else "None"
        context.user_data.clear()
        context.user_data["state"] = "set_smm_platform_emoji"
        context.user_data["target_smm_plat"] = plat_id
        await safe_edit(query, context,
            "SET EMOJI for button: " + plat_name + NL + NL
            + "Current: " + cur_text + NL + NL
            + "Send a message with a custom animated emoji IN IT." + NL
            + "Send 0 to REMOVE the current emoji."
        )
        return

    if data.startswith("seprod_smm_svc:"):
        rest = data[15:]
        plat_id, sid = rest.split(":", 1)
        label, cur_emoji = smm.get_service_emoji_info(sid)
        cur_text = "ID: " + str(cur_emoji) if cur_emoji else "None"
        context.user_data.clear()
        context.user_data["state"] = "set_smm_service_emoji"
        context.user_data["target_smm_sid"] = sid
        context.user_data["target_smm_plat"] = plat_id
        await safe_edit(query, context,
            "SET EMOJI for service: " + label + NL + NL
            + "Current: " + cur_text + NL + NL
            + "Send a message with a custom animated emoji IN IT." + NL
            + "Send 0 to REMOVE the current emoji."
        )
        return

    if data == "e_setplanemoji":
        all_products = load_products()["items"]
        kb = []
        for pid, p in all_products.items():
            if p.get("plans"):
                kb.append([InlineKeyboardButton(p["name"], callback_data="seplanprod:" + pid)])
        kb.append([InlineKeyboardButton("Back", callback_data="e_back")])
        await safe_edit(query, context, "Pick a product first:", InlineKeyboardMarkup(kb))
        return

    if data.startswith("seplanprod:"):
        pid = data[11:]
        product = get_product(pid)
        if not product or not product.get("plans"):
            await query.answer("No plans found", show_alert=True)
            return
        kb = []
        for pl in product["plans"]:
            emoji_info = " [E]" if pl.get("emoji_id") else ""
            kb.append([InlineKeyboardButton(pl["name"] + emoji_info, callback_data="seplan:" + pid + ":" + pl["id"])])
        kb.append([InlineKeyboardButton("Back", callback_data="e_setplanemoji")])
        await safe_edit(query, context, "Pick a plan for: " + product["name"], InlineKeyboardMarkup(kb))
        return

    if data.startswith("seplan:"):
        pid, plan_id = data[7:].split(":", 1)
        product = get_product(pid)
        plan = find_plan(product, plan_id) if product else None
        if not plan:
            await query.answer("Plan not found", show_alert=True)
            return
        cur_emoji = "ID: " + str(plan.get("emoji_id")) if plan.get("emoji_id") else "None"
        context.user_data.clear()
        context.user_data["state"] = "set_plan_emoji_await"
        context.user_data["target_pid"] = pid
        context.user_data["target_plan"] = plan_id
        await safe_edit(query, context,
            "SET CUSTOM EMOJI for plan: " + plan["name"] + NL + NL
            + "Current: " + cur_emoji + NL + NL
            + "Send a message with a custom animated emoji IN IT." + NL
            + "Send 0 to REMOVE the current emoji."
        )
        return

    if data == "e_setwalletemoji":
        context.user_data["state"] = "set_wallet_emoji"
        cur_emoji = get_action_emoji("use_wallet") or "None"
        await safe_edit(query, context,
            "SET EMOJI FOR USE WALLET BUTTON\n\n"
            f"Current: {cur_emoji}\n\n"
            "Send a message with a custom animated emoji IN IT.\n"
            "Send 0 to REMOVE the current emoji.")
        return

    if data.startswith("se:"):
        bid = data[3:]
        b = find_button(load_buttons(), bid)
        if not b:
            await query.answer("Button not found", show_alert=True)
            return
        cur_emoji = "ID: " + str(b.get("emoji_id")) if b.get("emoji_id") else "None"
        context.user_data.clear()
        context.user_data["state"] = "set_emoji_await"
        context.user_data["target"] = bid
        await safe_edit(query, context,
            "SET CUSTOM EMOJI for: " + b["text"] + NL + NL
            + "Current: " + cur_emoji + NL + NL
            + "Send a message with a custom animated emoji IN IT to apply it." + NL
            + "Send 0 to REMOVE the current emoji."
        )
        return

    if data == "e_resize":
        title, kb = list_buttons_panel("Tap a button to switch its size:", "rs:")
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data.startswith("rs:"):
        bid = data[3:]
        buttons = load_buttons()
        b = find_button(buttons, bid)
        if b:
            b["size"] = "full" if b["size"] == "half" else "half"
            save_buttons(buttons)
        title, kb = list_buttons_panel("Tap a button to switch its size:", "rs:")
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data == "e_reorder":
        title, kb = reorder_panel()
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data.startswith("mvu:") or data.startswith("mvd:"):
        bid = data[4:]
        buttons = load_buttons()
        idx = next((i for i, b in enumerate(buttons) if b["id"] == bid), None)
        if idx is not None:
            if data.startswith("mvu:") and idx > 0:
                buttons[idx - 1], buttons[idx] = buttons[idx], buttons[idx - 1]
            elif data.startswith("mvd:") and idx < len(buttons) - 1:
                buttons[idx + 1], buttons[idx] = buttons[idx], buttons[idx + 1]
            save_buttons(buttons)
        title, kb = reorder_panel()
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data == "e_delete":
        title, kb = list_buttons_panel("Pick a button to DELETE:", "del:")
        await safe_edit(query, context, title, reply_markup=kb)
        return

    if data.startswith("delok:"):
        bid = data[6:]
        buttons = [b for b in load_buttons() if b["id"] != bid]
        save_buttons(buttons)
        panel_text, kb = edit_panel()
        await safe_edit(query, context, "Button deleted." + NL + NL + panel_text, reply_markup=kb)
        return

    if data.startswith("del:"):
        bid = data[4:]
        b = find_button(load_buttons(), bid)
        name = b["text"] if b else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete", callback_data="delok:" + bid)],
            [InlineKeyboardButton("No, go back", callback_data="e_delete")],
        ])
        await safe_edit(query, context, "Delete '" + name + "' ?", reply_markup=kb)
        return

    await query.answer()

# ========== TG username step ==========
async def handle_tg_username(update, context):
    raw = (update.message.text or "").strip()
    username = raw.lstrip("@").strip()
    if not username or " " in username:
        await update.message.reply_text("Please type a single valid username (no spaces).")
        return
    plan_id = context.user_data.get("tg_plan")
    plan = find_tg_plan(plan_id)
    if not plan:
        await update.message.reply_text("Something went wrong. Please send /start and try again.")
        return
    context.user_data.clear()
    context.user_data["cart_pending"] = {
        "kind": "tg",
        "title": "Telegram Premium - " + plan["name"],
        "product": "Telegram Premium",
        "plan": plan["name"],
        "price": plan["price"],
        "username": username,
        "target_label": "Telegram Premium Username",
    }
    caption, rows, photo = tg_confirm_screen(plan, username)
    chat_id = update.effective_chat.id
    await raw_send_message(chat_id, caption, rows, photo)
    try:
        await update.message.delete()
    except Exception:
        pass

# ========== text handler ==========
async def on_text(update, context):
    state = context.user_data.get("state")

    if state == "tg_await_username":
        await handle_tg_username(update, context)
        return

    if update.effective_user.id != ADMIN_ID:
        return

    if not state:
        return

    text = update.message.text.strip()

    if state == "set_action_emoji":
        action_key = context.user_data.get("action_key")
        if text == "0":
            emojis = load_action_emojis()
            emojis[action_key] = None
            save_action_emojis(emojis)
            context.user_data.clear()
            panel_text, kb = edit_panel()
            await update.message.reply_text(f"Emoji removed from {action_key}.", reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                e = custom_emojis[0]
                emoji_id = e.custom_emoji_id
                emojis = load_action_emojis()
                emojis[action_key] = emoji_id
                save_action_emojis(emojis)
                context.user_data.clear()
                await update.message.reply_text(f"Custom emoji set for {action_key}! ID: {emoji_id}")
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    if state == "set_wallet_emoji":
        if text == "0":
            emojis = load_action_emojis()
            emojis["use_wallet"] = None
            save_action_emojis(emojis)
            context.user_data.clear()
            panel_text, kb = edit_panel()
            await update.message.reply_text("Wallet button emoji removed.", reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                e = custom_emojis[0]
                emoji_id = e.custom_emoji_id
                emojis = load_action_emojis()
                emojis["use_wallet"] = emoji_id
                save_action_emojis(emojis)
                context.user_data.clear()
                await update.message.reply_text(f"Custom emoji set for Use Wallet button! ID: {emoji_id}")
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    if state == "set_emoji_await":
        if text == "0":
            bid = context.user_data.get("target")
            buttons = load_buttons()
            b = find_button(buttons, bid)
            if b:
                b["emoji_id"] = None
                save_buttons(buttons)
            context.user_data.clear()
            panel_text, kb = edit_panel()
            await update.message.reply_text("Custom emoji removed." + NL + NL + panel_text, reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                e = custom_emojis[0]
                emoji_id = e.custom_emoji_id
                bid = context.user_data.get("target")
                buttons = load_buttons()
                b = find_button(buttons, bid)
                if b:
                    b["emoji_id"] = emoji_id
                    save_buttons(buttons)
                context.user_data.clear()
                await update.message.reply_text(
                    "Custom emoji set! ID: " + emoji_id + NL + NL
                    + "Send /start to see your updated menu."
                )
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    if state == "set_product_emoji_await":
        if text == "0":
            pid = context.user_data.get("target_pid")
            d = load_products()
            if pid in d["items"]:
                d["items"][pid]["emoji_id"] = None
                save_products(d)
            context.user_data.clear()
            panel_text, kb = edit_panel()
            await update.message.reply_text("Custom emoji removed from product." + NL + NL + panel_text, reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                e = custom_emojis[0]
                emoji_id = e.custom_emoji_id
                pid = context.user_data.get("target_pid")
                d = load_products()
                if pid in d["items"]:
                    d["items"][pid]["emoji_id"] = emoji_id
                    save_products(d)
                context.user_data.clear()
                await update.message.reply_text(
                    "Custom emoji set for product! ID: " + emoji_id + NL + NL
                    + "Send /start to see your updated menu."
                )
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    # ========== SET EMOJI FOR SMM PLATFORM (Instagram, TikTok etc.) ==========
    if state == "set_smm_platform_emoji":
        if text == "0":
            plat_id = context.user_data.get("target_smm_plat")
            smm.set_platform_emoji(plat_id, None)
            context.user_data.clear()
            panel_text, kb = edit_panel()
            await update.message.reply_text("Custom emoji removed from SMM platform.", reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                emoji_id = custom_emojis[0].custom_emoji_id
                plat_id = context.user_data.get("target_smm_plat")
                smm.set_platform_emoji(plat_id, emoji_id)
                context.user_data.clear()
                await update.message.reply_text(
                    "Custom emoji set! ID: " + emoji_id + NL + NL
                    + "Send /start to see your updated menu."
                )
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    # ========== SET EMOJI FOR SMM SERVICE ==========
    if state == "set_smm_service_emoji":
        sid = context.user_data.get("target_smm_sid")
        plat_id = context.user_data.get("target_smm_plat")
        if text == "0":
            smm.set_service_emoji(sid, None)
            context.user_data.clear()
            back_cb = "seprod_smm_plat:" + plat_id if plat_id else "e_setprodemoji"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=back_cb)]])
            await update.message.reply_text("Custom emoji removed from service.", reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                emoji_id = custom_emojis[0].custom_emoji_id
                smm.set_service_emoji(sid, emoji_id)
                context.user_data.clear()
                back_cb = "seprod_smm_plat:" + plat_id if plat_id else "e_setprodemoji"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=back_cb)]])
                await update.message.reply_text(
                    "Emoji set! ID: " + emoji_id + NL + "Send /start to see your updated menu.",
                    reply_markup=kb
                )
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    if state == "set_plan_emoji_await":
        if text == "0":
            pid = context.user_data.get("target_pid")
            plan_id = context.user_data.get("target_plan")
            _update_plan(pid, plan_id, "emoji_id", None)
            context.user_data.clear()
            panel_text, kb = edit_panel()
            await update.message.reply_text("Custom emoji removed from plan." + NL + NL + panel_text, reply_markup=kb)
        else:
            entities = update.message.entities or []
            custom_emojis = [e for e in entities if e.type == MessageEntity.CUSTOM_EMOJI]
            if custom_emojis:
                e = custom_emojis[0]
                emoji_id = e.custom_emoji_id
                pid = context.user_data.get("target_pid")
                plan_id = context.user_data.get("target_plan")
                _update_plan(pid, plan_id, "emoji_id", emoji_id)
                context.user_data.clear()
                await update.message.reply_text(
                    "Custom emoji set for plan! ID: " + emoji_id + NL + NL
                    + "Send /start to see your updated menu."
                )
            else:
                await update.message.reply_text(
                    "No custom emoji detected." + NL + NL
                    + "Send a message containing an animated custom emoji, or send 0 to cancel."
                )
        return

    if state == "edit_cat_image":
        cat_id = context.user_data.get("target_cat")
        if text == "0":
            set_category_image(cat_id, None)
            context.user_data.clear()
            await _done_back(update, "Page image removed.", "cat:" + cat_id)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove the image.")
        return

    if state == "edit_support_text":
        sup = load_support()
        sup["text"] = text
        save_support(sup)
        context.user_data.clear()
        await _done_back(update, "Support text updated.", "open:support")
        return

    if state == "edit_support_image":
        if text == "0":
            sup = load_support()
            sup["image"] = None
            save_support(sup)
            context.user_data.clear()
            await _done_back(update, "Support image removed.", "open:support")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove it.")
        return

    if state == "edit_tg_select_text":
        d = load_tg(); d["select_text"] = text; save_tg(d)
        context.user_data.clear()
        await _done_back(update, "Select text updated.", "tgmanage")
        return

    if state == "edit_tg_select_image":
        if text == "0":
            d = load_tg(); d["select_image"] = None; save_tg(d)
            context.user_data.clear()
            await _done_back(update, "Select image removed.", "tgmanage")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove the image.")
        return

    if state == "edit_tg_user_text":
        d = load_tg(); d["username_text"] = text; save_tg(d)
        context.user_data.clear()
        await _done_back(update, "Username text updated.", "tgmanage")
        return

    if state == "edit_tg_user_image":
        if text == "0":
            d = load_tg(); d["username_image"] = None; save_tg(d)
            context.user_data.clear()
            await _done_back(update, "Username image removed.", "tgmanage")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove the image.")
        return

    if state == "edit_tg_plan_name":
        plan_id = context.user_data.get("target_tg_plan")
        update_tg_plan(plan_id, "name", text)
        context.user_data.clear()
        await _done_back(update, "Plan name updated.", "tgplm:" + plan_id)
        return

    if state == "edit_tg_plan_price":
        plan_id = context.user_data.get("target_tg_plan")
        update_tg_plan(plan_id, "price", text)
        context.user_data.clear()
        await _done_back(update, "Plan price updated.", "tgplm:" + plan_id)
        return

    if state == "edit_tg_plan_image":
        if text == "0":
            plan_id = context.user_data.get("target_tg_plan")
            update_tg_plan(plan_id, "image", None)
            context.user_data.clear()
            await _done_back(update, "Plan image removed.", "tgplm:" + plan_id)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove the image.")
        return

    if state == "addtgplan_name":
        context.user_data["new_tg_plan"] = {"id": uuid.uuid4().hex[:6], "name": text, "price": "", "image": None}
        context.user_data["state"] = "addtgplan_price"
        await update.message.reply_text("Send the PRICE for '" + text + "' (example: $30):")
        return

    if state == "addtgplan_price":
        context.user_data["new_tg_plan"]["price"] = text
        context.user_data["state"] = "addtgplan_image"
        await update.message.reply_text("Send the IMAGE for this plan. (or send 0 to skip)")
        return

    if state == "addtgplan_image":
        if text == "0":
            add_tg_plan(context.user_data.get("new_tg_plan"))
            context.user_data.clear()
            await _done_back(update, "Plan added.", "tgmpl")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to skip.")
        return

    if state == "edit_welcome_text":
        settings = load_settings(); settings["welcome_text"] = text; save_settings(settings)
        context.user_data.clear()
        await _done_back(update, "Welcome text updated. Send /start to preview it.", "edit")
        return

    if state == "edit_welcome_image":
        if text == "0":
            settings = load_settings(); settings["welcome_image"] = None; save_settings(settings)
            context.user_data.clear()
            await _done_back(update, "Welcome image removed.", "edit")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove the image.")
        return

    if state == "edit_cat_intro":
        cat_id = context.user_data.get("target_cat")
        set_category_intro(cat_id, text)
        context.user_data.clear()
        await _done_back(update, "Page text updated.", "cat:" + cat_id)
        return

    if state == "add_name":
        context.user_data["new_text"] = text
        context.user_data["state"] = "add_size"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Half width", callback_data="addsize:half")],
            [InlineKeyboardButton("Full width", callback_data="addsize:full")],
        ])
        await update.message.reply_text("Choose the size for '" + text + "':", reply_markup=kb)
        return

    if state == "rename":
        bid = context.user_data.get("target")
        buttons = load_buttons()
        b = find_button(buttons, bid)
        if b:
            b["text"] = text
            save_buttons(buttons)
        context.user_data.clear()
        panel_text, kb = edit_panel()
        await update.message.reply_text("Renamed." + NL + NL + panel_text, reply_markup=kb)
        return

    if state == "prod_image":
        if text == "0":
            context.user_data["draft"]["image"] = None
            context.user_data["state"] = "prod_name"
            await update.message.reply_text("Step 2: Send the PRODUCT NAME:")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to skip.")
        return

    if state == "prod_name":
        context.user_data["draft"]["name"] = text
        context.user_data["state"] = "prod_desc"
        await update.message.reply_text("Step 3: Send the PRODUCT DESCRIPTION:")
        return

    if state == "prod_desc":
        context.user_data["draft"]["description"] = text
        context.user_data["state"] = "plan_name"
        await update.message.reply_text("Step 4: Send the PLAN NAME (or 0 when done):")
        return

    if state == "plan_name":
        if text == "0":
            await finish_product(update, context)
            return
        context.user_data["draft_plan"] = {"id": uuid.uuid4().hex[:6], "name": text, "price": "", "image": None}
        context.user_data["state"] = "plan_price"
        await update.message.reply_text("Send the PRICE for '" + text + "':")
        return

    if state == "plan_price":
        context.user_data["draft_plan"]["price"] = text
        context.user_data["state"] = "plan_image"
        await update.message.reply_text("Send the IMAGE for this plan. (or send 0 to skip)")
        return

    if state == "plan_image":
        if text == "0":
            context.user_data["draft_plan"]["image"] = None
            _commit_plan(context)
            context.user_data["state"] = "plan_name"
            await update.message.reply_text("Plan added. Send the NEXT plan name, or 0 to finish.")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to skip.")
        return

    if state == "edit_prod_name":
        pid = context.user_data.get("target_pid")
        d = load_products()
        if pid in d["items"]:
            d["items"][pid]["name"] = text
            save_products(d)
        context.user_data.clear()
        await _done_back(update, "Name updated.", "pm:" + pid)
        return

    if state == "edit_prod_desc":
        pid = context.user_data.get("target_pid")
        d = load_products()
        if pid in d["items"]:
            d["items"][pid]["description"] = text
            save_products(d)
        context.user_data.clear()
        await _done_back(update, "Description updated.", "pm:" + pid)
        return

    if state == "edit_prod_image":
        if text == "0":
            pid = context.user_data.get("target_pid")
            d = load_products()
            if pid in d["items"]:
                d["items"][pid]["image"] = None
                save_products(d)
            context.user_data.clear()
            await _done_back(update, "Image removed.", "pm:" + pid)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove.")
        return

    if state == "edit_plan_name":
        pid = context.user_data.get("target_pid")
        plan_id = context.user_data.get("target_plan")
        _update_plan(pid, plan_id, "name", text)
        context.user_data.clear()
        await _done_back(update, "Plan name updated.", "plm:" + pid + ":" + plan_id)
        return

    if state == "edit_plan_price":
        pid = context.user_data.get("target_pid")
        plan_id = context.user_data.get("target_plan")
        _update_plan(pid, plan_id, "price", text)
        context.user_data.clear()
        await _done_back(update, "Plan price updated.", "plm:" + pid + ":" + plan_id)
        return

    if state == "edit_plan_image":
        if text == "0":
            pid = context.user_data.get("target_pid")
            plan_id = context.user_data.get("target_plan")
            _update_plan(pid, plan_id, "image", None)
            context.user_data.clear()
            await _done_back(update, "Plan image removed.", "plm:" + pid + ":" + plan_id)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove.")
        return

    if state == "addplan_name":
        context.user_data["new_plan"] = {"id": uuid.uuid4().hex[:6], "name": text, "price": "", "image": None}
        context.user_data["state"] = "addplan_price"
        await update.message.reply_text("Send the PRICE for '" + text + "':")
        return

    if state == "addplan_price":
        context.user_data["new_plan"]["price"] = text
        context.user_data["state"] = "addplan_image"
        await update.message.reply_text("Send the IMAGE for this plan. (or send 0 to skip)")
        return

    if state == "addplan_image":
        if text == "0":
            _append_plan_to_product(context, None)
            pid = context.user_data.get("target_pid")
            context.user_data.clear()
            await _done_back(update, "Plan added.", "mpl:" + pid)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to skip.")
        return

    if state == "set_product_stock":
        try:
            stock = int(text.strip())
            pid = context.user_data.get("target_pid")
            if store.update_product_stock(pid, stock):
                stock_text = "Unlimited" if stock == -1 else str(stock)
                await update.message.reply_text(f"Stock updated! Stock: {stock_text}")
            else:
                await update.message.reply_text("Product not found")
        except ValueError:
            await update.message.reply_text("Invalid number! Send -1, 0, or positive number")
            return
        context.user_data.clear()
        res = product_manage_menu(pid)
        if res:
            text_msg, kb = res
            await update.message.reply_text(text_msg, reply_markup=kb)
        return

    if state == "set_plan_stock":
        try:
            stock = int(text.strip())
            pid = context.user_data.get("target_pid")
            plan_id = context.user_data.get("target_plan")
            if store.update_plan_stock(pid, plan_id, stock):
                stock_text = "Unlimited" if stock == -1 else str(stock)
                await update.message.reply_text(f"Plan stock updated! Stock: {stock_text}")
            else:
                await update.message.reply_text("Product or plan not found")
        except ValueError:
            await update.message.reply_text("Invalid number! Send -1, 0, or positive number")
            return
        context.user_data.clear()
        res = plan_manage_menu(pid, plan_id)
        if res:
            text_msg, kb = res
            await update.message.reply_text(text_msg, reply_markup=kb)
        return

# ========== photo handler ==========
async def on_photo(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    state = context.user_data.get("state")
    file_id = update.message.photo[-1].file_id

    if state == "edit_cat_image":
        cat_id = context.user_data.get("target_cat")
        set_category_image(cat_id, file_id)
        context.user_data.clear()
        await _done_back(update, "Page image updated.", "cat:" + cat_id)
        return

    if state == "edit_support_image":
        sup = load_support(); sup["image"] = file_id; save_support(sup)
        context.user_data.clear()
        await _done_back(update, "Support image updated.", "open:support")
        return

    if state == "edit_tg_select_image":
        d = load_tg(); d["select_image"] = file_id; save_tg(d)
        context.user_data.clear()
        await _done_back(update, "Select image updated.", "tgmanage")
        return

    if state == "edit_tg_user_image":
        d = load_tg(); d["username_image"] = file_id; save_tg(d)
        context.user_data.clear()
        await _done_back(update, "Username image updated.", "tgmanage")
        return

    if state == "edit_tg_plan_image":
        plan_id = context.user_data.get("target_tg_plan")
        update_tg_plan(plan_id, "image", file_id)
        context.user_data.clear()
        await _done_back(update, "Plan image updated.", "tgplm:" + plan_id)
        return

    if state == "addtgplan_image":
        plan = context.user_data.get("new_tg_plan")
        if plan:
            plan["image"] = file_id
            add_tg_plan(plan)
        context.user_data.clear()
        await _done_back(update, "Plan added.", "tgmpl")
        return

    if state == "edit_welcome_image":
        settings = load_settings(); settings["welcome_image"] = file_id; save_settings(settings)
        context.user_data.clear()
        await _done_back(update, "Welcome image updated. Send /start to preview it.", "edit")
        return

    if state == "prod_image":
        context.user_data["draft"]["image"] = file_id
        context.user_data["state"] = "prod_name"
        await update.message.reply_text("Image saved. Step 2: Send the PRODUCT NAME:")
        return

    if state == "plan_image":
        context.user_data["draft_plan"]["image"] = file_id
        _commit_plan(context)
        context.user_data["state"] = "plan_name"
        await update.message.reply_text("Plan image saved. Send the NEXT plan name, or 0 to finish.")
        return

    if state == "edit_prod_image":
        pid = context.user_data.get("target_pid")
        d = load_products()
        if pid in d["items"]:
            d["items"][pid]["image"] = file_id
            save_products(d)
        context.user_data.clear()
        await _done_back(update, "Image updated.", "pm:" + pid)
        return

    if state == "edit_plan_image":
        pid = context.user_data.get("target_pid")
        plan_id = context.user_data.get("target_plan")
        _update_plan(pid, plan_id, "image", file_id)
        context.user_data.clear()
        await _done_back(update, "Plan image updated.", "plm:" + pid + ":" + plan_id)
        return

    if state == "addplan_image":
        _append_plan_to_product(context, file_id)
        pid = context.user_data.get("target_pid")
        context.user_data.clear()
        await _done_back(update, "Plan added.", "mpl:" + pid)
        return

# ========== helpers ==========
async def _done_back(update, message, back_callback):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=back_callback)]])
    await update.message.reply_text(message, reply_markup=kb)

def _update_plan(pid, plan_id, field, value):
    d = load_products()
    product = d["items"].get(pid)
    if product:
        for pl in product.get("plans", []):
            if pl["id"] == plan_id:
                pl[field] = value
                break
        save_products(d)

def _append_plan_to_product(context, image):
    pid = context.user_data.get("target_pid")
    plan = context.user_data.get("new_plan")
    if not pid or not plan:
        return
    plan["image"] = image
    d = load_products()
    product = d["items"].get(pid)
    if product:
        product.setdefault("plans", []).append(plan)
        save_products(d)

def _commit_plan(context):
    plan = context.user_data.get("draft_plan")
    if plan:
        if "plans" not in context.user_data["draft"]:
            context.user_data["draft"]["plans"] = []
        context.user_data["draft"]["plans"].append(plan)
        context.user_data["draft_plan"] = None

async def finish_product(update, context):
    draft = context.user_data.get("draft")
    if not draft:
        context.user_data.clear()
        return
    if "plans" not in draft:
        draft["plans"] = []
    data = load_products()
    pid = uuid.uuid4().hex[:8]
    data["items"][pid] = draft
    save_products(data)
    plan_count = len(draft.get("plans", []))
    context.user_data.clear()
    await update.message.reply_text(
        "PRODUCT SAVED" + NL + NL + "Name: " + draft["name"] + NL
        + "Plans: " + str(plan_count) + NL + NL
        + "Send /start and open the category to see it."
    )

def main():
    print("Project folder:", BASE_DIR)
    s = load_settings()
    print("Welcome image set:", "yes" if s.get("welcome_image") else "no")

    ensure_viewcart_button()

    app = Application.builder().token(BOT_TOKEN).build()
    cart.setup(app, ADMIN_ID)
    smm.setup(app, ADMIN_ID, BOT_TOKEN)
    payments.setup(app, ADMIN_ID, BOT_TOKEN)
    orders.register_gate(app)
    orders.register_commands(app)
    orders.register_order_buttons(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getid", cmd_getid))
    app.add_handler(CommandHandler("commands", cmd_commands))
    app.add_handler(CommandHandler("wallet", cmd_wallet))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("active", cmd_active))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("setstock", cmd_set_stock))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("stockstatus", cmd_stock_status))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Bot running. /getid to capture emoji IDs.")
    app.run_polling()

if __name__ == "__main__":
    main()