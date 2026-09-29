"""
Premium Villa - Shopping Cart module (cart.py)
Wire into bot.py with:  import cart   and   cart.setup(app, ADMIN_ID)
"""

import os
import re
import json
import uuid
import time
import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CallbackQueryHandler, MessageHandler, filters, ApplicationHandlerStop

NL = chr(10)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CART_FILE = os.path.join(BASE_DIR, "carts.json")
CART_CFG_FILE = os.path.join(BASE_DIR, "cart_config.json")
ADMIN_ID = 0

# ----- cart page config (admin-editable heading text + image) -----
def _load_cfg():
    if not os.path.exists(CART_CFG_FILE):
        return {}
    try:
        with open(CART_CFG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cfg(d):
    with open(CART_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def get_cart_text():
    return _load_cfg().get("text") or "Your Cart"

def set_cart_text(t):
    d = _load_cfg()
    d["text"] = t
    _save_cfg(d)

def get_cart_image():
    return _load_cfg().get("image")

def set_cart_image(file_id):
    d = _load_cfg()
    d["image"] = file_id
    _save_cfg(d)

def _load_all():
    if not os.path.exists(CART_FILE):
        return {}
    try:
        with open(CART_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_all(data):
    tmp = CART_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CART_FILE)   # atomic write -> no half-written/stale reads

# carts auto-expire after this many seconds of no activity
CART_TTL_SECONDS = 12 * 60 * 60   # 12 hours

def _entry(user_id, data=None):
    """Return the per-user record {items, ts}, upgrading the old list format."""
    if data is None:
        data = _load_all()
    rec = data.get(str(user_id))
    if rec is None:
        return {"items": [], "ts": 0}
    if isinstance(rec, list):            # legacy format (bare list of items)
        return {"items": rec, "ts": time.time()}
    return {"items": rec.get("items", []), "ts": rec.get("ts", 0)}

def _get_cart(user_id):
    data = _load_all()
    rec = _entry(user_id, data)
    # expire stale carts (12h no activity)
    if rec["items"] and rec.get("ts") and (time.time() - rec["ts"] > CART_TTL_SECONDS):
        data[str(user_id)] = {"items": [], "ts": time.time()}
        _save_all(data)
        return []
    return rec["items"]

def _set_cart(user_id, items):
    data = _load_all()
    data[str(user_id)] = {"items": list(items), "ts": time.time()}
    _save_all(data)

def _add_item(user_id, item):
    items = _get_cart(user_id)
    item["cid"] = uuid.uuid4().hex[:8]
    items.append(item)
    _set_cart(user_id, items)

def _money(value):
    try:
        v = float(value)
    except Exception:
        return "$0"
    if abs(v - round(v)) < 0.005:
        return "$" + str(int(round(v)))
    return "$" + ("%.2f" % v)

def _fmt_int(n):
    try:
        return "{:,}".format(int(n))
    except Exception:
        return str(n)

def _price_to_float(price_str):
    m = re.search(r"[-+]?\d*\.?\d+", str(price_str).replace(",", ""))
    return float(m.group(0)) if m else 0.0

def _line_total(item):
    if item.get("kind") == "smm":
        return _price_to_float(item["price_per_1k"]) * float(item["qty"]) / 1000.0
    return _price_to_float(item["unit_price"]) * float(item["qty"])

def _cart_total(items):
    return sum(_line_total(it) for it in items)

def _added_screen(back_cb):
    """Screen shown right after an item is added to the cart."""
    text = "<b>Item Added To Cart Successfully</b>"
    kb = [
        [InlineKeyboardButton("Checkout More Products", callback_data="home")],
        [InlineKeyboardButton("View Cart", callback_data="cart:open")],
        [InlineKeyboardButton("Back", callback_data=back_cb)],
    ]
    return text, InlineKeyboardMarkup(kb)

def _cart_screen(user_id, is_admin=False):
    items = _get_cart(user_id)
    heading = "<b>" + html.escape(get_cart_text()) + "</b>"
    photo = get_cart_image()
    if not items:
        text = heading + NL + NL + "Your cart is empty." + NL + "Browse the menu and tap 'Add to Cart'."
        kb = []
        if is_admin:
            kb.append([
                InlineKeyboardButton("Edit Cart Text", callback_data="cart:ctext"),
                InlineKeyboardButton("Change Cart Image", callback_data="cart:cimg"),
            ])
        kb.append([InlineKeyboardButton("Back", callback_data="cart:close")])
        return text, InlineKeyboardMarkup(kb), photo

    lines = [heading, ""]
    kb = []
    for i, it in enumerate(items, start=1):
        lt = _line_total(it)
        if it.get("kind") == "smm":
            desc = _fmt_int(it["qty"]) + " " + it["title"]
        else:
            desc = it["title"] + "  x" + str(it["qty"])
        if it.get("target"):
            desc += "  (" + it["target"] + ")"
        lines.append("<b>" + str(i) + ".</b> " + desc + " - <b>" + _money(lt) + "</b>")
        if it.get("kind") == "smm":
            minus_lbl = "\u2796 less"
            plus_lbl = "\u2795 more"
        else:
            minus_lbl = "\u2796 1"
            plus_lbl = "\u2795 1"
        kb.append([
            InlineKeyboardButton(minus_lbl, callback_data="cart:dec:" + it["cid"]),
            InlineKeyboardButton("\U0001F5D1 Remove #" + str(i), callback_data="cart:del:" + it["cid"]),
            InlineKeyboardButton(plus_lbl, callback_data="cart:inc:" + it["cid"]),
        ])

    lines.append("")
    lines.append("<b>Total : " + _money(_cart_total(items)) + "</b>")
    kb.append([InlineKeyboardButton("Checkout", callback_data="cart:checkout")])
    kb.append([InlineKeyboardButton("Clear Cart", callback_data="cart:clear")])
    if is_admin:
        kb.append([
            InlineKeyboardButton("Edit Cart Text", callback_data="cart:ctext"),
            InlineKeyboardButton("Change Cart Image", callback_data="cart:cimg"),
        ])
    kb.append([InlineKeyboardButton("Back", callback_data="cart:close")])
    return NL.join(lines), InlineKeyboardMarkup(kb), photo

def _checkout_screen(user_id):
    items = _get_cart(user_id)
    if not items:
        text = "<b>Checkout</b>" + NL + NL + "Your cart is empty."
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="cart:open")]])
    lines = ["<b>Order Summary</b>", ""]
    for i, it in enumerate(items, start=1):
        lt = _line_total(it)
        if it.get("kind") == "smm":
            desc = _fmt_int(it["qty"]) + " " + it["title"]
        else:
            desc = it["title"] + "  x" + str(it["qty"])
        if it.get("target"):
            desc += "  (" + it["target"] + ")"
        lines.append("<b>" + str(i) + ".</b> " + desc + " - <b>" + _money(lt) + "</b>")
    lines.append("")
    lines.append("<b>Total To Pay : " + _money(_cart_total(items)) + "</b>")
    lines.append("")
    lines.append("Payment is the next step we will add (crypto wallet).")
    kb = [[InlineKeyboardButton("Back to Cart", callback_data="cart:open")]]
    return NL.join(lines), InlineKeyboardMarkup(kb)

async def _show(query, context, text, kb):
    msg = query.message
    if msg.photo:
        try:
            await msg.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=kb, parse_mode="HTML")
        return
    try:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

async def _render_cart(query, context, text, kb, photo):
    """Edit the current message into the cart (supports an optional image)."""
    msg = query.message
    has_photo = bool(msg.photo)
    want_photo = photo is not None
    if want_photo and has_photo:
        try:
            return await msg.edit_media(
                media=InputMediaPhoto(media=photo, caption=text, parse_mode="HTML"), reply_markup=kb)
        except Exception:
            pass
    elif (not want_photo) and (not has_photo):
        try:
            return await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
    try:
        await msg.delete()
    except Exception:
        pass
    if want_photo:
        return await context.bot.send_photo(chat_id=msg.chat_id, photo=photo, caption=text,
                                            reply_markup=kb, parse_mode="HTML")
    return await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=kb, parse_mode="HTML")

def _item_from_product(pid, plan_id, qty=1):
    """OTT / VPN plan -> a cart item. Reads live data from bot.py."""
    try:
        import bot
        product = bot.get_product(pid)
        if not product:
            return None
        plan = None
        for pl in product.get("plans", []):
            if pl["id"] == plan_id:
                plan = pl
                break
        if not plan:
            return None
        return {
            "kind": "plan",
            "title": product["name"] + " - " + plan["name"],
            "product": product["name"],
            "plan": plan["name"],
            "unit_price": plan.get("price", "$0"),
            "qty": max(1, int(qty)),
            "target": None,
        }
    except Exception:
        return None

async def _on_callback(update, context):
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith("cart:"):
        return
    user_id = query.from_user.id
    action = data[5:]

    if action == "open":
        context.user_data.pop("cart_pending", None)
        is_admin = (user_id == ADMIN_ID)
        text, kb, photo = _cart_screen(user_id, is_admin)
        if query.message.photo or query.message.text is None:
            if photo:
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo,
                                             caption=text, reply_markup=kb, parse_mode="HTML")
            else:
                await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await _render_cart(query, context, text, kb, photo)
        await query.answer()
        raise ApplicationHandlerStop

    if action == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        raise ApplicationHandlerStop

    # ----- owner-only: edit the cart page text / image -----
    if action == "ctext":
        if user_id != ADMIN_ID:
            await query.answer("Not allowed", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["cart_flow"] = {"step": "edit_cart_text"}
        await _show(query, context,
                    "Send the new CART PAGE heading text:" + NL + "(or /start to cancel)",
                    InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="cart:open")]]))
        await query.answer()
        raise ApplicationHandlerStop

    if action == "cimg":
        if user_id != ADMIN_ID:
            await query.answer("Not allowed", show_alert=True)
            raise ApplicationHandlerStop
        context.user_data["cart_flow"] = {"step": "edit_cart_image"}
        await _show(query, context,
                    "Send the new CART PAGE image." + NL + "(send 0 to remove it, or /start to cancel)",
                    InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="cart:open")]]))
        await query.answer()
        raise ApplicationHandlerStop

    # ----- add an OTT/VPN plan -----
    if action.startswith("addp:"):
        rest = action[5:]
        pid, plan_id = rest.split(":", 1)
        item = _item_from_product(pid, plan_id)
        if item:
            _add_item(user_id, item)
            await query.answer("Added to cart")
            text, kb = _added_screen("prod:" + pid)
            await _show(query, context, text, kb)
        else:
            await query.answer("Could not add item", show_alert=True)
        raise ApplicationHandlerStop

    # ----- add an OTT/VPN plan WITH quantity (from the plan stepper) -----
    if action.startswith("addpq:"):
        pid, plan_id, qty_str = action[6:].split(":", 2)
        try:
            qty = int(qty_str)
        except Exception:
            qty = 1
        item = _item_from_product(pid, plan_id, qty)
        if item:
            _add_item(user_id, item)
            await query.answer("Added to cart")
            text, kb = _added_screen("prod:" + pid)
            await _show(query, context, text, kb)
        else:
            await query.answer("Could not add item", show_alert=True)
        raise ApplicationHandlerStop

    # ----- BUY NOW an OTT/VPN plan: pay for this item ONLY (separate from cart) -----
    if action.startswith("buypq:"):
        pid, plan_id, qty_str = action[6:].split(":", 2)
        try:
            qty = int(qty_str)
        except Exception:
            qty = 1
        item = _item_from_product(pid, plan_id, qty)
        if not item:
            await query.answer("Could not buy item", show_alert=True)
            raise ApplicationHandlerStop
        await query.answer()
        import payments
        await payments.begin_payment_buynow(query, context, item)
        raise ApplicationHandlerStop

    # ----- add a Telegram Premium item (uses pending data) -----
    if action == "addtg":
        pend = context.user_data.get("cart_pending")
        if pend and pend.get("kind") == "tg":
            _add_item(user_id, {
                "kind": "plan",
                "title": pend["title"],
                "product": pend.get("product", "Telegram Premium"),
                "plan": pend.get("plan", ""),
                "unit_price": pend["price"],
                "qty": 1,
                "target": "@" + pend["username"] if pend.get("username") else None,
                "target_label": pend.get("target_label", "Telegram Premium Username"),
            })
            context.user_data.pop("cart_pending", None)
            await query.answer("Added to cart")
            text, kb = _added_screen("tgmenu")
            await _show(query, context, text, kb)
        else:
            await query.answer("Could not add item", show_alert=True)
        raise ApplicationHandlerStop

    # ----- add a Social Media item (uses pending data) -----
    if action == "addsmm":
        pend = context.user_data.get("cart_pending")
        if pend and pend.get("kind") == "smm":
            _add_item(user_id, {
                "kind": "smm",
                "title": pend["title"],
                "product": pend.get("product", pend["title"]),
                "plan": pend.get("plan", ""),
                "price_per_1k": pend["price_per_1k"],
                "qty": int(pend["qty"]),
                "min": int(pend.get("min", 1)),
                "step": int(pend.get("step", 100)),
                "target": pend.get("target"),
                "target_label": pend.get("target_label", "Detail"),
            })
            back_cb = "smp:" + pend["pid"] if pend.get("pid") else "smr"
            context.user_data.pop("cart_pending", None)
            await query.answer("Added to cart")
            text, kb = _added_screen(back_cb)
            await _show(query, context, text, kb)
        else:
            await query.answer("Could not add item", show_alert=True)
        raise ApplicationHandlerStop

    # ----- BUY NOW Telegram Premium (pending) -> pay for this item ONLY -----
    if action == "buytg":
        pend = context.user_data.get("cart_pending")
        if pend and pend.get("kind") == "tg":
            item = {
                "kind": "plan",
                "title": pend["title"],
                "product": pend.get("product", "Telegram Premium"),
                "plan": pend.get("plan", ""),
                "unit_price": pend["price"],
                "qty": 1,
                "target": "@" + pend["username"] if pend.get("username") else None,
                "target_label": pend.get("target_label", "Telegram Premium Username"),
            }
            context.user_data.pop("cart_pending", None)
            await query.answer()
            import payments
            await payments.begin_payment_buynow(query, context, item)
        else:
            await query.answer("Could not buy item", show_alert=True)
        raise ApplicationHandlerStop

    # ----- BUY NOW Social Media (pending) -> pay for this item ONLY -----
    if action == "buysmm":
        pend = context.user_data.get("cart_pending")
        if pend and pend.get("kind") == "smm":
            item = {
                "kind": "smm",
                "title": pend["title"],
                "product": pend.get("product", pend["title"]),
                "plan": pend.get("plan", ""),
                "price_per_1k": pend["price_per_1k"],
                "qty": int(pend["qty"]),
                "min": int(pend.get("min", 1)),
                "step": int(pend.get("step", 100)),
                "target": pend.get("target"),
                "target_label": pend.get("target_label", "Detail"),
            }
            context.user_data.pop("cart_pending", None)
            await query.answer()
            import payments
            await payments.begin_payment_buynow(query, context, item)
        else:
            await query.answer("Could not buy item", show_alert=True)
        raise ApplicationHandlerStop

    # ----- increase / decrease quantity -----
    if action.startswith("inc:") or action.startswith("dec:"):
        cid = action[4:]
        up = action.startswith("inc:")
        items = _get_cart(user_id)
        for it in items:
            if it.get("cid") == cid:
                if it.get("kind") == "smm":
                    step = int(it.get("step", 100))
                    mn = int(it.get("min", step))
                    it["qty"] = max(mn, int(it["qty"]) + (step if up else -step))
                else:
                    it["qty"] = max(1, int(it["qty"]) + (1 if up else -1))
                break
        _set_cart(user_id, items)
        text, kb, photo = _cart_screen(user_id, user_id == ADMIN_ID)
        await _render_cart(query, context, text, kb, photo)
        await query.answer()
        raise ApplicationHandlerStop

    # ----- remove an item -----
    if action.startswith("del:"):
        cid = action[4:]
        items = [it for it in _get_cart(user_id) if it.get("cid") != cid]
        _set_cart(user_id, items)
        text, kb, photo = _cart_screen(user_id, user_id == ADMIN_ID)
        await _render_cart(query, context, text, kb, photo)
        await query.answer("Removed")
        raise ApplicationHandlerStop

    # ----- clear -----
    if action == "clear":
        _set_cart(user_id, [])                 # force-empty + bump activity ts
        await query.answer("Cart cleared")
        text, kb, photo = _cart_screen(user_id, user_id == ADMIN_ID)
        try:
            await _render_cart(query, context, text, kb, photo)
        except Exception:
            try:
                await query.message.delete()
            except Exception:
                pass
            await context.bot.send_message(chat_id=query.message.chat_id, text=text,
                                           reply_markup=kb, parse_mode="HTML")
        raise ApplicationHandlerStop

    # ----- checkout -> crypto payment -----
    if action == "checkout":
        await query.answer()
        import payments
        await payments.begin_payment_from_cart(query, context)
        raise ApplicationHandlerStop

    await query.answer()
    raise ApplicationHandlerStop

async def _on_text(update, context):
    flow = context.user_data.get("cart_flow")
    if not flow:
        return
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("cart_flow", None)
        return
    step = flow.get("step")
    text = (update.message.text or "").strip()
    if step == "edit_cart_text":
        set_cart_text(text)
        context.user_data.pop("cart_flow", None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("View Cart", callback_data="cart:open")]])
        await update.message.reply_text("Cart page text updated.", reply_markup=kb)
        raise ApplicationHandlerStop
    if step == "edit_cart_image":
        if text == "0":
            set_cart_image(None)
            context.user_data.pop("cart_flow", None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("View Cart", callback_data="cart:open")]])
            await update.message.reply_text("Cart image removed.", reply_markup=kb)
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove it.")
        raise ApplicationHandlerStop
    return

async def _on_photo(update, context):
    flow = context.user_data.get("cart_flow")
    if not flow or flow.get("step") != "edit_cart_image":
        return
    if update.effective_user.id != ADMIN_ID:
        return
    file_id = update.message.photo[-1].file_id
    set_cart_image(file_id)
    context.user_data.pop("cart_flow", None)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("View Cart", callback_data="cart:open")]])
    await update.message.reply_text("Cart image updated.", reply_markup=kb)
    raise ApplicationHandlerStop

def cart_count(user_id):
    return len(_get_cart(user_id))

def setup(application, admin_id):
    global ADMIN_ID
    ADMIN_ID = admin_id
    application.add_handler(CallbackQueryHandler(_on_callback), group=-2)
    application.add_handler(MessageHandler(filters.PHOTO, _on_photo), group=-2)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text), group=-2)
    print("Cart module loaded.")
