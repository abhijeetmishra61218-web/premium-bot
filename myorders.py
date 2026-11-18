"""
Premium Villa - My Orders (myorders.py)

Customer-facing purchase history:
  main menu "My Orders" -> list (image + "My Orders" + one button per purchase)
  -> tap one -> detail screen (product image, order details, Download Invoice, Back)

Admin extras:  /addorder  /delorder <order id>  /userorders <id|@user>
Wire into bot.py with:  import myorders  and  myorders.setup(app, ADMIN_ID)
"""

import os
import re
import html
import time
import uuid
import calendar
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters, ApplicationHandlerStop

import store

NL = chr(10)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDERS_FILE = os.path.join(BASE_DIR, "my_orders.json")
ADMIN_ID = 0
GROUP = -4                      # own handler group (cart=-2, payments=-3, order cmds=-5)
PAGE_SIZE = 8
DISPLAY_TZ = timezone(timedelta(hours=5, minutes=30))   # dates are shown in IST

METHOD_LABEL = {"crypto": "Crypto", "wallet": "Wallet", "wallet+crypto": "Wallet + Crypto"}


# ============================== storage ==============================
def _load():
    d = store._load(ORDERS_FILE, {"orders": [], "image": None})
    if not isinstance(d, dict):
        d = {"orders": [], "image": None}
    d.setdefault("orders", [])
    d.setdefault("image", None)
    return d

def _save(d):
    store._save(ORDERS_FILE, d)

def get_image():
    return _load().get("image")

def set_image(file_id):
    d = _load()
    d["image"] = file_id
    _save(d)

def _exists(rec):
    for r in _load()["orders"]:
        if (str(r.get("order_id")) == str(rec.get("order_id")) and r.get("pid") == rec.get("pid")
                and r.get("plan_id") == rec.get("plan_id") and r.get("user_id") == rec.get("user_id")):
            return True
    return False

def add_record(rec):
    """Returns True if added, False if an identical record already exists."""
    if _exists(rec):
        return False
    d = _load()
    d["orders"].append(rec)
    _save(d)
    return True

def orders_for(user_id):
    mine = [r for r in _load()["orders"] if r.get("user_id") == user_id]
    mine.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return mine

def get_record(rid):
    for r in _load()["orders"]:
        if r.get("rid") == rid:
            return r
    return None

def remove_by_order_id(order_id):
    d = _load()
    keep = [r for r in d["orders"] if str(r.get("order_id")) != str(order_id)]
    removed = len(d["orders"]) - len(keep)
    if removed:
        d["orders"] = keep
        _save(d)
    return removed


# ============================== formatting helpers ==============================
def esc(x):
    return html.escape(str(x if x is not None else ""))

def money(v):
    try:
        v = float(v)
    except Exception:
        return "$0"
    if abs(v - round(v)) < 0.005:
        return "$" + str(int(round(v)))
    return "$" + ("%.2f" % v)

def fmt_months(n):
    return str(n) + (" Month" if n == 1 else " Months")

def plan_months(plan_name):
    """'6 Months' -> 6, '1 Year' -> 12, anything else -> None."""
    s = plan_name or ""
    m = re.search(r"(\d+)\s*(?:months?|mos?|m)\b", s, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:years?|yrs?|y)\b", s, re.I)
    if m:
        return int(m.group(1)) * 12
    return None

def short_plan(plan_name):
    """'6 Months' -> '6M', '1 Year' -> '1Y', '10 Days' -> '10D'; else unchanged."""
    s = (plan_name or "").strip()
    m = re.search(r"(\d+)\s*(?:months?|mos?|m)\b", s, re.I)
    if m:
        return m.group(1) + "M"
    m = re.search(r"(\d+)\s*(?:years?|yrs?|y)\b", s, re.I)
    if m:
        return m.group(1) + "Y"
    m = re.search(r"(\d+)\s*(?:days?|d)\b", s, re.I)
    if m:
        return m.group(1) + "D"
    return s

def add_months(dt, n):
    month_index = dt.month - 1 + n
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)

def _dt(ts):
    return datetime.fromtimestamp(ts, DISPLAY_TZ)

def date_short(ts):
    return _dt(ts).strftime("%d-%m-%y")

def date_long(dt):
    return dt.strftime("%d-%m-%Y")

def _warranty_value(plan, product):
    """Plan setting wins. Older products that still carry a product-level setting are the fallback."""
    if plan is not None and "warranty" in plan:
        return plan.get("warranty")
    return (product or {}).get("warranty")

def warranty_months(product, plan_name, plan=None):
    """Warranty promised for this plan: months (int) or None.
    Setting: absent/0 = none, N = N months, 'plan' = same as the plan length."""
    w = _warranty_value(plan, product)
    if isinstance(w, int) and w > 0:
        return w
    if w == "plan":
        return plan_months(plan_name)
    return None

def warranty_setting_text(plan, product=None):
    w = _warranty_value(plan, product)
    if isinstance(w, int) and w > 0:
        return fmt_months(w)
    if w == "plan":
        return "Same as plan length"
    return "No warranty"

def _plan_of(product, plan_id):
    for pl in (product or {}).get("plans", []):
        if pl.get("id") == plan_id:
            return pl
    return None

def smm_label(title, qty_text):
    """'Instagram High Quality Followers' + '1,000'  ->  'Instagram 1,000 Followers'."""
    try:
        import smm
        for p in smm._load().get("platforms", []):
            for sv in p.get("services", []):
                if (sv.get("title") or "") == (title or ""):
                    return (p.get("name") or "").strip() + " " + str(qty_text) + " " + (sv.get("unit") or "").strip()
    except Exception:
        pass
    return (title or "Service")


# ============================== building records ==============================
def _find_product_by_name(name):
    name = (name or "").strip().lower()
    if not name:
        return None, None
    for pid, p in store.load_products()["items"].items():
        if (p.get("name") or "").strip().lower() == name:
            return pid, p
    return None, None

def make_record(user_id, username, order_id, ts, product_name, plan_name, amount, method,
                pid=None, plan_id=None, qty=1, crypto=None, address=None, txid=None,
                warranty=None, kind="plan", target=None, target_label=None, source="auto"):
    return {
        "rid": uuid.uuid4().hex[:8],
        "order_id": str(order_id),
        "user_id": int(user_id),
        "username": username,
        "ts": float(ts),
        "pid": pid,
        "plan_id": plan_id,
        "product_name": product_name,
        "plan_name": plan_name,
        "qty": int(qty or 1),
        "amount": float(amount or 0),
        "method": method,
        "crypto": crypto,
        "address": address,
        "txid": txid,
        "warranty_months": warranty,
        "kind": kind,
        "target": target,
        "target_label": target_label,
        "source": source,
    }

def record_purchase(user_id, order_id, order):
    """Called by payments.py after a successful payment. Never raises."""
    try:
        import cart
        items = order.get("items") or []
        crypto_name = order.get("crypto_name")
        wallet_used = float(order.get("wallet_used", 0) or 0)
        if order.get("wallet_full") or not crypto_name:
            method = "wallet"
        elif wallet_used > 0:
            method = "wallet+crypto"
        else:
            method = "crypto"
        username = None
        try:
            username = store.get_username(user_id)
        except Exception:
            pass
        now = time.time()
        for it in items:
            kind = it.get("kind") or "plan"
            pid, plan_id, product = it.get("pid"), it.get("plan_id"), None
            if pid:
                product = store.get_product(pid)
            elif kind != "smm":
                pid, product = _find_product_by_name(it.get("product"))
            qty = int(it.get("qty", 1) or 1)
            smm_name = None
            if kind == "smm":
                product_name = it.get("title") or it.get("product") or "Service"
                plan_name = cart._fmt_int(qty)
                smm_name = smm_label(product_name, plan_name)
                qty_store = 1
                wm = None
            else:
                product_name = (product or {}).get("name") or it.get("product") or it.get("title") or "Product"
                plan_name = it.get("plan") or ""
                qty_store = qty
                wm = warranty_months(product, plan_name, _plan_of(product, plan_id))
            try:
                amount = cart._line_total(it)
            except Exception:
                amount = float(order.get("usd", 0) or 0)
            rec = make_record(
                user_id, username, order_id, now, product_name, plan_name, amount, method,
                pid=pid, plan_id=plan_id, qty=qty_store, crypto=crypto_name if "crypto" in method else None,
                address=order.get("address") if "crypto" in method else None,
                txid=order.get("hash") if "crypto" in method else None,
                warranty=wm, kind=kind, target=it.get("target"), target_label=it.get("target_label"),
                source="auto")
            if smm_name:
                rec["smm_name"] = smm_name
            add_record(rec)
    except Exception as e:
        print(f"[myorders] could not record purchase: {e}")


# ============================== screens ==============================
def _bot():
    import bot
    return bot

def _back_emoji():
    try:
        return _bot().get_action_emoji("back_button")
    except Exception:
        return None

def _live_product(rec):
    """The product as it is NOW (so renames/image changes show up in old orders)."""
    pid = rec.get("pid")
    if pid:
        try:
            return store.get_product(pid)
        except Exception:
            return None
    return None

def _is_smm(rec):
    return (rec.get("kind") == "smm")

def _smm_platform_emoji(rec):
    """Social media orders show the PLATFORM's emoji (Instagram, TikTok, ...), not a service/plan one."""
    try:
        import smm
        plats = smm._load().get("platforms", [])
        for p in plats:
            if p.get("id") == rec.get("pid"):
                return p.get("emoji_id")
        for p in plats:                                  # older records: find the platform by service title
            for sv in p.get("services", []):
                if (sv.get("title") or "") == (rec.get("product_name") or ""):
                    return p.get("emoji_id")
    except Exception:
        pass
    return None

def _row_emoji(rec):
    if _is_smm(rec):
        return _smm_platform_emoji(rec)
    return (_live_product(rec) or {}).get("emoji_id")

def _display_name(rec):
    if _is_smm(rec):
        return rec.get("smm_name") or smm_label(rec.get("product_name"), rec.get("plan_name"))
    p = _live_product(rec)
    return (p or {}).get("name") or rec.get("product_name") or "Product"

def list_screen(user_id, page=0):
    mine = orders_for(user_id)
    pages = max(1, (len(mine) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    chunk = mine[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = "<b>My Orders</b>"
    if not mine:
        text += NL + NL + "You haven't made any purchases yet."
    rows = []
    for rec in chunk:
        p = _live_product(rec)
        if _is_smm(rec):
            label = _display_name(rec) + " - " + date_short(rec.get("ts", 0))
        else:
            label = _display_name(rec) + " - " + short_plan(rec.get("plan_name")) + " - " + date_short(rec.get("ts", 0))
        rows.append([{"text": label, "callback_data": "mo:v:" + rec["rid"] + ":" + str(page),
                      "emoji_id": _row_emoji(rec)}])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append({"text": "◀ Prev", "callback_data": "mo:pg:" + str(page - 1), "emoji_id": None})
        if page < pages - 1:
            nav.append({"text": "Next ▶", "callback_data": "mo:pg:" + str(page + 1), "emoji_id": None})
        rows.append(nav)
    if user_id == ADMIN_ID:
        rows.append([{"text": "Set Page Image", "callback_data": "mo:img", "emoji_id": None}])
    rows.append([{"text": "Back", "callback_data": "close", "emoji_id": _back_emoji()}])
    return text, rows, get_image()

def detail_text(rec):
    lines = [
        "<b>Order ID :</b> " + esc(rec.get("order_id")),
        "<b>Product :</b> " + esc(_display_name(rec)),
    ]
    if not _is_smm(rec):
        lines.append("<b>Plan :</b> " + esc(rec.get("plan_name")))
    if int(rec.get("qty", 1) or 1) > 1:
        lines.append("<b>Quantity :</b> " + str(int(rec["qty"])))
    if rec.get("target"):
        lines.append("<b>" + esc(rec.get("target_label") or "Details") + " :</b> " + esc(rec["target"]))
    lines.append("<b>Amount :</b> " + money(rec.get("amount")))
    method = rec.get("method") or "wallet"
    lines.append("<b>Payment Method :</b> " + METHOD_LABEL.get(method, method.title()))
    if "crypto" in method:
        lines.append("<b>Crypto :</b> " + esc(rec.get("crypto")))
        lines.append("<b>Crypto Addy :</b> <code>" + esc(rec.get("address")) + "</code>")
        lines.append("<b>Transaction Hash :</b> <code>" + esc(rec.get("txid")) + "</code>")
    if _is_smm(rec):                       # social media services: nothing about warranty
        return NL.join(lines)
    wm = rec.get("warranty_months")
    if wm:
        till = add_months(_dt(rec.get("ts", 0)), int(wm))
        lines.append("<b>Warranty :</b> " + fmt_months(int(wm)) + " (<b>Till :</b> " + date_long(till) + ")")
    else:
        lines.append("<b>Warranty :</b> No Warranty")
    return NL.join(lines)

def detail_screen(rec, page=0):
    try:
        import bot
        dl_emoji = bot.get_action_emoji("download_invoice")
    except Exception:
        dl_emoji = None
    rows = [
        [{"text": "Download Invoice", "callback_data": "mo:inv:" + rec["rid"], "emoji_id": dl_emoji}],
        [{"text": "Back", "callback_data": "mo:pg:" + str(page), "emoji_id": _back_emoji()}],
    ]
    p = _live_product(rec)
    return detail_text(rec), rows, (p or {}).get("image")


# ============================== invoice ==============================
def _date_inv(dt):
    return dt.strftime("%b") + " " + str(dt.day) + ", " + str(dt.year)        # Sep 15, 2026

def _customer_name(rec):
    """Telegram first name if the customer has used the bot, else @username, else 'Customer'."""
    try:
        u = store.load_users().get(str(rec.get("user_id")), {})
        if (u.get("first_name") or "").strip():
            return u["first_name"].strip()
    except Exception:
        pass
    if rec.get("username"):
        return "@" + str(rec["username"]).lstrip("@")
    return "Customer"

CRYPTO_INFO = {      # name as shown in the bot -> (full name, ticker, network label, explorer link prefix)
    "BTC": ("Bitcoin", "BTC", "BITCOIN NETWORK", "https://mempool.space/tx/"),
    "LTC": ("Litecoin", "LTC", "LITECOIN NETWORK", "https://litecoinspace.org/tx/"),
    "SOL": ("Solana", "SOL", "SOLANA NETWORK", "https://solscan.io/tx/"),
    "ETH": ("Ethereum", "ETH", "ETHEREUM NETWORK", "https://etherscan.io/tx/"),
    "USDT(TRC20)": ("Tether", "USDT", "TRON NETWORK (TRC20)", "https://tronscan.org/#/transaction/"),
    "USDT(BEP20)": ("Tether", "USDT", "BNB CHAIN (BEP20)", "https://bscscan.com/tx/"),
    "USDC(ERC20)": ("USD Coin", "USDC", "ETHEREUM NETWORK (ERC20)", "https://etherscan.io/tx/"),
    "USDC(SOL)": ("USD Coin", "USDC", "SOLANA NETWORK", "https://solscan.io/tx/"),
}

def crypto_info(name):
    key = (name or "").replace(" ", "").upper()
    if key in CRYPTO_INFO:
        return CRYPTO_INFO[key]
    return (name or "Crypto", (name or "").split("(")[0].upper() or "CRYPTO", "ON-CHAIN", "")

def punch_labels(dt, wm):
    """Labels under the warranty punch-holes (one hole per month, or per quarter for long warranties)."""
    wm = int(wm)
    if wm <= 0:
        return []
    if wm <= 12:
        return [add_months(dt, i).strftime("%b").upper() for i in range(wm - 1)] + \
               [add_months(dt, wm).strftime("%d %b").upper()]
    n = min(12, (wm + 2) // 3)
    step = wm / float(n)
    return [add_months(dt, int(round(step * i))).strftime("%b %y").upper() for i in range(1, n + 1)]

def invoice_fields(rec):
    """Turns a saved order into the strings printed on the invoice (see invoice.py)."""
    dt = _dt(rec.get("ts", 0))
    method = rec.get("method") or "wallet"
    amount = float(rec.get("amount") or 0)
    qty = max(1, int(rec.get("qty", 1) or 1))
    smm = _is_smm(rec)
    plan = "" if smm else (rec.get("plan_name") or "").strip()
    name = _display_name(rec)
    wm = rec.get("warranty_months")
    wm = int(wm) if wm else 0
    full, ticker, network, explorer = crypto_info(rec.get("crypto")) if "crypto" in method else ("", "", "", "")
    txid = str(rec.get("txid") or "")
    return {
        "order_no": str(rec.get("order_id")),
        "kind": "smm" if smm else "plan",
        "product": name,
        "plan": plan,
        "date": dt.strftime("%d %b %Y"),
        "date_stamp": dt.strftime("%d.%m.%Y"),
        "method_key": method,
        "method": METHOD_LABEL.get(method, str(method).title()),
        "bill_to": _customer_name(rec),
        "userid": str(rec.get("user_id")),
        "qty": str(qty),
        "rate": "$%.2f" % (amount / qty),
        "amount": "$%.2f" % amount,
        "total": "$%.2f" % amount,
        "balance": "$0.00",
        "target": str(rec.get("target") or ""),
        "target_label": str(rec.get("target_label") or ""),
        "coin_full": full, "coin": ticker, "network": network,
        "address": str(rec.get("address") or ""),
        "txid": txid,
        "explorer_url": (explorer + txid) if (explorer and txid) else "",
        "explorer_host": explorer.split("/")[2] if explorer else "",
        "warranty_months": wm,
        "valid_till": date_long(add_months(dt, wm)) if wm else "",
        "punch": punch_labels(dt, wm) if wm else [],
    }

def build_invoice_bytes(rec):
    import io
    import invoice
    buf = io.BytesIO()
    invoice.render_pdf(invoice_fields(rec), buf)
    buf.seek(0)
    return buf


# ============================== callbacks ==============================
async def _on_callback(update, context):
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith("mo:"):
        return
    user_id = query.from_user.id
    parts = data.split(":")
    act = parts[1] if len(parts) > 1 else ""
    bot = _bot()

    if act == "list":                      # from the main menu -> new message
        text, rows, photo = list_screen(user_id, 0)
        await query.answer()
        await bot.raw_send_message(query.message.chat_id, text, rows, photo)
        raise ApplicationHandlerStop

    if act == "pg":                        # page / back from detail -> edit in place
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        text, rows, photo = list_screen(user_id, page)
        await query.answer()
        await bot._show_screen(query, text, rows, photo)
        raise ApplicationHandlerStop

    if act == "v":
        rid = parts[2] if len(parts) > 2 else ""
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        rec = get_record(rid)
        if not rec or rec.get("user_id") != user_id:
            await query.answer("Order not found", show_alert=True)
            raise ApplicationHandlerStop
        text, rows, photo = detail_screen(rec, page)
        await query.answer()
        await bot._show_screen(query, text, rows, photo)
        raise ApplicationHandlerStop

    if act == "inv":
        rid = parts[2] if len(parts) > 2 else ""
        rec = get_record(rid)
        if not rec or rec.get("user_id") != user_id:
            await query.answer("Order not found", show_alert=True)
            raise ApplicationHandlerStop
        try:
            import invoice  # noqa: F401  (needs the reportlab package)
        except ImportError:
            await query.answer("Invoices are not available right now. Please contact support.", show_alert=True)
            print("[myorders] invoice needs reportlab:  venv/bin/pip install reportlab")
            raise ApplicationHandlerStop
        await query.answer("Preparing your invoice...")
        try:
            import asyncio
            buf = await asyncio.to_thread(build_invoice_bytes, rec)
            safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(rec.get("order_id"))) or "order"
            await context.bot.send_document(query.message.chat_id, document=buf,
                                            filename="Invoice_" + safe_id + ".pdf")
        except Exception as e:
            print(f"[myorders] invoice failed: {e}")
            try:
                await context.bot.send_message(query.message.chat_id,
                                               "Sorry, the invoice could not be created right now. Please try again in a moment.")
            except Exception:
                pass
        raise ApplicationHandlerStop

    # ---------------- admin only below ----------------
    if user_id != ADMIN_ID:
        await query.answer("Not allowed", show_alert=True)
        raise ApplicationHandlerStop

    if act == "img":
        context.user_data["mo_flow"] = {"step": "img"}
        await query.answer()
        await context.bot.send_message(query.message.chat_id,
                                       "Send the image for the My Orders page. (send 0 to remove it)")
        raise ApplicationHandlerStop

    if act == "ac":
        context.user_data.pop("mo_flow", None)
        await query.answer("Cancelled")
        try:
            await query.message.edit_text("Cancelled. Nothing was saved.")
        except Exception:
            pass
        raise ApplicationHandlerStop

    flow = context.user_data.get("mo_flow")
    if not flow or not flow.get("step"):
        await query.answer("Session expired - send /addorder again", show_alert=True)
        raise ApplicationHandlerStop

    if act == "ap" and flow["step"] == "product":        # product chosen
        pid = parts[2]
        product = store.get_product(pid)
        if not product:
            await query.answer("Product not found", show_alert=True)
            raise ApplicationHandlerStop
        flow["pid"] = pid
        flow["step"] = "plan"
        rows = [[InlineKeyboardButton(pl["name"] + " | " + pl["price"], callback_data="mo:apl:" + pl["id"])]
                for pl in product.get("plans", [])]
        rows.append([InlineKeyboardButton("Cancel", callback_data="mo:ac")])
        await query.answer()
        await query.message.edit_text("Product: <b>" + esc(product["name"]) + "</b>" + NL + "Choose the plan:",
                                      reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
        raise ApplicationHandlerStop

    if act == "apl" and flow["step"] == "plan":          # plan chosen
        plan_id = parts[2]
        product = store.get_product(flow["pid"])
        plan = next((pl for pl in (product or {}).get("plans", []) if pl["id"] == plan_id), None)
        if not plan:
            await query.answer("Plan not found", show_alert=True)
            raise ApplicationHandlerStop
        flow["plan_id"] = plan_id
        flow["step"] = "date"
        await query.answer()
        await query.message.edit_text(
            "Plan: <b>" + esc(plan["name"]) + "</b>" + NL + NL
            + "Send the PURCHASE DATE as DD-MM-YYYY (example 15-09-2026), or send <b>today</b>.",
            parse_mode="HTML")
        raise ApplicationHandlerStop

    if act == "am" and flow["step"] == "method":         # payment method chosen
        flow["method"] = parts[2]
        await query.answer()
        if flow["method"] == "crypto":
            flow["step"] = "crypto"
            await query.message.edit_text("Payment method: <b>Crypto</b>" + NL + NL
                                          + "Send the CRYPTO name (example: BTC).", parse_mode="HTML")
        else:
            flow["step"] = "orderid"
            await query.message.edit_text("Payment method: <b>Wallet</b>" + NL + NL + _orderid_prompt(flow),
                                          parse_mode="HTML")
        raise ApplicationHandlerStop

    if act == "as" and flow["step"] == "confirm":        # save
        rec = _record_from_flow(flow)
        added = add_record(rec)
        context.user_data.pop("mo_flow", None)
        await query.answer("Saved" if added else "Already exists")
        msg = ("✅ Order saved for user <code>" + str(rec["user_id"]) + "</code>." if added
               else "⚠️ An identical order already exists - nothing added.")
        await query.message.edit_text(msg, parse_mode="HTML")
        raise ApplicationHandlerStop

    await query.answer()
    raise ApplicationHandlerStop


# ============================== admin: add order flow ==============================
def _parse_date(s):
    s = (s or "").strip()
    if s.lower() in ("today", "now"):
        return datetime.now(DISPLAY_TZ)
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).replace(hour=12, tzinfo=DISPLAY_TZ)
        except ValueError:
            continue
    return None

def _clean(s):
    """Accept text pasted as a markdown link or with backticks: [abc](http://..) -> abc"""
    s = (s or "").strip()
    m = re.match(r"^\[(.+?)\]\(.*\)$", s)
    if m:
        s = m.group(1)
    return s.strip().strip("`").strip()

def _orderid_prompt(flow):
    return ("Send the ORDER ID for this purchase, or send <b>auto</b> to generate the next one "
            "(customer id + order number).")

def _record_from_flow(flow):
    product = store.get_product(flow["pid"])
    plan = next(pl for pl in product.get("plans", []) if pl["id"] == flow["plan_id"])
    method = flow.get("method", "wallet")
    return make_record(
        flow["uid"], flow.get("username") or store.get_username(flow["uid"]), flow["order_id"], flow["ts"],
        product["name"], plan["name"], flow["amount"], method,
        pid=flow["pid"], plan_id=flow["plan_id"], qty=1,
        crypto=flow.get("crypto") if method == "crypto" else None,
        address=flow.get("address") if method == "crypto" else None,
        txid=flow.get("txid") if method == "crypto" else None,
        warranty=warranty_months(product, plan["name"], plan), kind="plan", source="manual")

def _summary(flow):
    product = store.get_product(flow["pid"])
    plan = next(pl for pl in product.get("plans", []) if pl["id"] == flow["plan_id"])
    rec = _record_from_flow(flow)
    return ("<b>Please check, then save:</b>" + NL + NL
            + "Customer: <code>" + str(rec["user_id"]) + "</code>"
            + ((" (@" + esc(rec["username"]) + ")") if rec.get("username") else "") + NL
            + "Date: " + date_long(_dt(rec["ts"])) + NL + NL
            + detail_text(rec))

async def cmd_addorder(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["mo_flow"] = {"step": "uid"}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="mo:ac")]])
    await update.message.reply_text(
        "➕ <b>Add an order for a customer</b>" + NL + NL
        + "Send the customer's Telegram USER ID (numbers) or @username.", reply_markup=kb, parse_mode="HTML")

async def cmd_delorder(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /delorder <order id>")
        return
    n = remove_by_order_id(context.args[0])
    await update.message.reply_text(("Removed " + str(n) + " record(s) for order " + context.args[0]) if n
                                    else "No order found with that ID.")

async def cmd_userorders(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /userorders <user id or @username>")
        return
    arg = context.args[0]
    uid = int(arg) if arg.isdigit() else store.get_uid_by_username(arg)
    if not uid:
        await update.message.reply_text("User not found.")
        return
    mine = orders_for(int(uid))
    if not mine:
        await update.message.reply_text("No saved orders for " + str(uid) + ".")
        return
    lines = ["<b>Orders for " + str(uid) + "</b>"]
    for r in mine:
        lines.append("<code>" + esc(r["order_id"]) + "</code> - " + esc(_display_name(r)) + " - "
                     + esc(short_plan(r.get("plan_name"))) + " - " + date_short(r.get("ts", 0))
                     + " - " + money(r.get("amount")) + " [" + esc(r.get("source", "auto")) + "]")
    await update.message.reply_text(NL.join(lines), parse_mode="HTML")

async def _on_text(update, context):
    flow = context.user_data.get("mo_flow")
    if not flow:
        return
    if update.effective_user.id != ADMIN_ID:
        context.user_data.pop("mo_flow", None)
        return
    text = (update.message.text or "").strip()
    step = flow.get("step")
    reply = update.message.reply_text

    if text.lower() == "cancel":
        context.user_data.pop("mo_flow", None)
        await reply("Cancelled. Nothing was saved.")
        raise ApplicationHandlerStop

    if step == "img":
        if text == "0":
            set_image(None)
            context.user_data.pop("mo_flow", None)
            await reply("My Orders image removed.")
        else:
            await reply("Please send a photo, or send 0 to remove it.")
        raise ApplicationHandlerStop

    if step == "uid":
        if text.isdigit():
            uid = int(text)
        else:
            uid = store.get_uid_by_username(text)
            if not uid:
                await reply("I don't know that username (the customer must have used the bot). "
                            "Send their numeric user ID instead.")
                raise ApplicationHandlerStop
            flow["username"] = text.lstrip("@")
        flow["uid"] = int(uid)
        if text.startswith("@"):
            flow["username"] = text.lstrip("@")
        flow["step"] = "product"
        items = sorted(store.load_products()["items"].items(), key=lambda kv: kv[1].get("name", "").lower())
        rows, row = [], []
        for pid, p in items:
            row.append(InlineKeyboardButton(p["name"], callback_data="mo:ap:" + pid))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([InlineKeyboardButton("Cancel", callback_data="mo:ac")])
        await reply("Customer: <code>" + str(uid) + "</code>" + NL + "Choose the product:",
                    reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
        raise ApplicationHandlerStop

    if step == "date":
        dt = _parse_date(text)
        if not dt:
            await reply("I couldn't read that date. Use DD-MM-YYYY, for example 15-09-2026.")
            raise ApplicationHandlerStop
        flow["ts"] = dt.timestamp()
        flow["step"] = "amount"
        await reply("Date: <b>" + date_long(dt) + "</b>" + NL + NL + "Send the AMOUNT paid in USD (example 25).",
                    parse_mode="HTML")
        raise ApplicationHandlerStop

    if step == "amount":
        m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
        if not m or float(m.group(0)) <= 0:
            await reply("Please send a number, for example 25.")
            raise ApplicationHandlerStop
        flow["amount"] = float(m.group(0))
        flow["step"] = "method"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Crypto", callback_data="mo:am:crypto"),
             InlineKeyboardButton("Wallet", callback_data="mo:am:wallet")],
            [InlineKeyboardButton("Cancel", callback_data="mo:ac")],
        ])
        await reply("Amount: <b>" + money(flow["amount"]) + "</b>" + NL + "How did the customer pay?",
                    reply_markup=kb, parse_mode="HTML")
        raise ApplicationHandlerStop

    if step == "crypto":
        flow["crypto"] = _clean(text)
        flow["step"] = "address"
        await reply("Send the CRYPTO ADDRESS the customer paid to.")
        raise ApplicationHandlerStop

    if step == "address":
        flow["address"] = _clean(text)
        flow["step"] = "txid"
        await reply("Send the TRANSACTION HASH (TXID).")
        raise ApplicationHandlerStop

    if step == "txid":
        flow["txid"] = _clean(text)
        flow["step"] = "orderid"
        await reply(_orderid_prompt(flow), parse_mode="HTML")
        raise ApplicationHandlerStop

    if step == "orderid":
        if text.lower() == "auto":
            try:
                import payments
                n = payments.increment_order_count(flow["uid"])
                flow["order_id"] = str(flow["uid"]) + str(n)
            except Exception as e:
                await reply("Could not generate an ID automatically (" + str(e) + "). Send one by hand.")
                raise ApplicationHandlerStop
        else:
            flow["order_id"] = text
        flow["step"] = "confirm"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Save", callback_data="mo:as"),
             InlineKeyboardButton("Cancel", callback_data="mo:ac")],
        ])
        await reply(_summary(flow), reply_markup=kb, parse_mode="HTML")
        raise ApplicationHandlerStop

    # waiting for a button press
    await reply("Please use the buttons above, or send <b>cancel</b>.", parse_mode="HTML")
    raise ApplicationHandlerStop

async def _on_photo(update, context):
    flow = context.user_data.get("mo_flow")
    if not flow or flow.get("step") != "img":
        return
    if update.effective_user.id != ADMIN_ID:
        return
    set_image(update.message.photo[-1].file_id)
    context.user_data.pop("mo_flow", None)
    await update.message.reply_text("My Orders image updated.")
    raise ApplicationHandlerStop


# ============================== setup ==============================
def setup(application, admin_id):
    global ADMIN_ID
    ADMIN_ID = admin_id
    application.add_handler(CallbackQueryHandler(_on_callback, pattern=r"^mo:"), group=GROUP)
    application.add_handler(MessageHandler(filters.PHOTO, _on_photo), group=GROUP)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text), group=GROUP)
    application.add_handler(CommandHandler("addorder", cmd_addorder), group=GROUP)
    application.add_handler(CommandHandler("delorder", cmd_delorder), group=GROUP)
    application.add_handler(CommandHandler("userorders", cmd_userorders), group=GROUP)
    print("My Orders module loaded.")
