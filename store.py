"""
Premium Villa - shared data store (store.py)

Single source of truth used by BOTH bots (main shop bot + orders bot) and by
the payments module. Plain JSON files in the project folder, no DB needed.
"""

import os
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

# ---- identities / tokens (edit here if they ever change) ----
OWNER_ID = 6684244590
MAIN_BOT_TOKEN = "8712977638:AAFyazkpU-69d-5aokGYN_vb3JHWk6u_GfE"
ORDERS_BOT_TOKEN = "8912944844:AAEs8bPTGQVZEpFCeYExoBcMJkAiN4OP_Ak"

# customer-type thresholds (by number of paid orders)
FREQUENT_MIN = 10
AVERAGE_MIN = 3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
BANS_FILE = os.path.join(BASE_DIR, "bans.json")
STATE_FILE = os.path.join(BASE_DIR, "botstate.json")
WALLET_FILE = os.path.join(BASE_DIR, "wallets.json")
ORDERS_LOG = os.path.join(BASE_DIR, "orders_log.json")
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")

# ========================= low-level json =========================
def _load(path, default):
    if not os.path.exists(path):
        return json.loads(json.dumps(default))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(default))

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========================= users =========================
def register_user(user_id, username=None, first_name=None):
    data = _load(USERS_FILE, {"users": {}})
    u = data["users"].get(str(user_id), {})
    if username is not None:
        u["username"] = (username or "").lstrip("@")
    if first_name is not None:
        u["first_name"] = first_name
    u.setdefault("ts", time.time())
    data["users"][str(user_id)] = u
    _save(USERS_FILE, data)

def all_user_ids():
    return [int(uid) for uid in _load(USERS_FILE, {"users": {}})["users"].keys()]

def get_username(user_id):
    u = _load(USERS_FILE, {"users": {}})["users"].get(str(user_id), {})
    return u.get("username")

def norm_username(name):
    return (name or "").strip().lstrip("@").lower()

def get_uid_by_username(username):
    target = norm_username(username)
    if not target:
        return None
    for uid, u in _load(USERS_FILE, {"users": {}})["users"].items():
        if (u.get("username") or "").lower() == target:
            return int(uid)
    return None

def load_users():
    """Load all users data"""
    return _load(USERS_FILE, {"users": {}})["users"]

# ========================= admins =========================
def list_admins():
    extra = _load(ADMINS_FILE, {"admins": []})["admins"]
    ids = [OWNER_ID] + [int(a) for a in extra]
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out

def is_admin(user_id):
    try:
        return int(user_id) in list_admins()
    except Exception:
        return False

def add_admin(user_id):
    data = _load(ADMINS_FILE, {"admins": []})
    if int(user_id) not in [int(a) for a in data["admins"]] and int(user_id) != OWNER_ID:
        data["admins"].append(int(user_id))
        _save(ADMINS_FILE, data)

def remove_admin(user_id):
    data = _load(ADMINS_FILE, {"admins": []})
    data["admins"] = [int(a) for a in data["admins"] if int(a) != int(user_id)]
    _save(ADMINS_FILE, data)

# ========================= bans =========================
def is_banned(user_id):
    return int(user_id) in [int(b) for b in _load(BANS_FILE, {"banned": []})["banned"]]

def ban(user_id):
    data = _load(BANS_FILE, {"banned": []})
    if int(user_id) not in [int(b) for b in data["banned"]]:
        data["banned"].append(int(user_id))
        _save(BANS_FILE, data)

def unban(user_id):
    data = _load(BANS_FILE, {"banned": []})
    data["banned"] = [int(b) for b in data["banned"] if int(b) != int(user_id)]
    _save(BANS_FILE, data)

# ========================= maintenance =========================
def is_maintenance():
    return bool(_load(STATE_FILE, {"maintenance": False}).get("maintenance"))

def set_maintenance(on):
    _save(STATE_FILE, {"maintenance": bool(on)})

# ========================= wallet =========================
def wallet_balance(user_id):
    return float(_load(WALLET_FILE, {}).get(str(user_id), 0) or 0)

def wallet_add(user_id, amount):
    data = _load(WALLET_FILE, {})
    data[str(user_id)] = round(float(data.get(str(user_id), 0) or 0) + float(amount), 2)
    _save(WALLET_FILE, data)
    return data[str(user_id)]

def wallet_deduct(user_id, amount):
    data = _load(WALLET_FILE, {})
    bal = float(data.get(str(user_id), 0) or 0)
    new = round(max(0.0, bal - float(amount)), 2)
    data[str(user_id)] = new
    _save(WALLET_FILE, data)
    return new

def load_wallet():
    """Load wallet data"""
    return _load(WALLET_FILE, {})

def save_wallet(wallet):
    """Save wallet data"""
    _save(WALLET_FILE, wallet)

def get_wallet_balance(user_id):
    """Get user's current wallet balance"""
    wallet = load_wallet()
    return wallet.get(str(user_id), 0)

def remove_from_wallet(user_id, amount):
    """Remove amount from user's wallet and return new balance"""
    wallet = load_wallet()
    user_id_str = str(user_id)
    
    current = wallet.get(user_id_str, 0)
    new_balance = max(0, current - amount)
    wallet[user_id_str] = new_balance
    
    save_wallet(wallet)
    return new_balance

def add_to_wallet(user_id, amount):
    """Add amount to user's wallet and return new balance"""
    wallet = load_wallet()
    user_id_str = str(user_id)
    
    current = wallet.get(user_id_str, 0)
    new_balance = current + amount
    wallet[user_id_str] = new_balance
    
    save_wallet(wallet)
    return new_balance

# ========================= products =========================
def load_products():
    """Load products data with default stock values"""
    data = _load(PRODUCTS_FILE, {"items": {}})
    # Add default stock values for products that don't have them
    for pid, product in data["items"].items():
        if "stock" not in product:
            product["stock"] = -1  # Default: unlimited
        if "paused" not in product:
            product["paused"] = False  # Default: active
        for plan in product.get("plans", []):
            if "stock" not in plan:
                plan["stock"] = -1  # Default: unlimited
            if "paused" not in plan:
                plan["paused"] = False  # Default: active
    return data

def save_products(data):
    """Save products data"""
    _save(PRODUCTS_FILE, data)

def get_product(pid):
    """Get a single product by ID"""
    product = load_products()["items"].get(pid)
    if product:
        # Ensure stock and paused fields exist
        if "stock" not in product:
            product["stock"] = -1
        if "paused" not in product:
            product["paused"] = False
        for plan in product.get("plans", []):
            if "stock" not in plan:
                plan["stock"] = -1
            if "paused" not in plan:
                plan["paused"] = False
    return product

# ========================= STOCK MANAGEMENT =========================

def update_product_stock(pid, stock):
    """Update product stock (-1 for unlimited, 0 for out of stock, positive for limited)"""
    data = load_products()
    if pid in data["items"]:
        data["items"][pid]["stock"] = stock
        save_products(data)
        return True
    return False

def update_plan_stock(pid, plan_id, stock):
    """Update plan stock (-1 for unlimited, 0 for out of stock, positive for limited)"""
    data = load_products()
    if pid in data["items"]:
        for plan in data["items"][pid].get("plans", []):
            if plan["id"] == plan_id:
                plan["stock"] = stock
                save_products(data)
                return True
    return False

def pause_product(pid, paused):
    """Pause/unpause a product (True = paused, False = active)"""
    data = load_products()
    if pid in data["items"]:
        data["items"][pid]["paused"] = paused
        save_products(data)
        return True
    return False

def pause_plan(pid, plan_id, paused):
    """Pause/unpause a plan (True = paused, False = active)"""
    data = load_products()
    if pid in data["items"]:
        for plan in data["items"][pid].get("plans", []):
            if plan["id"] == plan_id:
                plan["paused"] = paused
                save_products(data)
                return True
    return False

def check_product_availability(product):
    """Check if product is available for customers"""
    if product.get("paused", False):
        return False, "paused"
    
    stock = product.get("stock", -1)
    if stock == 0:
        return False, "out_of_stock"
    return True, "available"

def check_plan_availability(product, plan):
    """Check if plan is available 
    Priority: Plan pause > Product pause > Plan stock > Product stock
    """
    # First check if plan is paused
    if plan.get("paused", False):
        return False, "plan_paused"
    
    # Then check if product is paused
    if product.get("paused", False):
        return False, "product_paused"
    
    # Check plan stock first (if set)
    plan_stock = plan.get("stock", -1)
    if plan_stock == 0:
        return False, "out_of_stock"
    elif plan_stock > 0:
        return True, "available"
    
    # If plan stock is unlimited, check product stock
    product_stock = product.get("stock", -1)
    if product_stock == 0:
        return False, "out_of_stock"
    
    return True, "available"

def get_available_stock(product, plan):
    """Get available stock count for a plan"""
    # Check plan stock first
    plan_stock = plan.get("stock", -1)
    if plan_stock > 0:
        return plan_stock
    elif plan_stock == 0:
        return 0
    
    # If plan stock is unlimited, use product stock
    product_stock = product.get("stock", -1)
    if product_stock > 0:
        return product_stock
    
    return -1  # Unlimited

def deduct_stock(pid, plan_id, quantity=1):
    """Deduct stock from plan or product level"""
    data = load_products()
    if pid in data["items"]:
        product = data["items"][pid]
        for plan in product.get("plans", []):
            if plan["id"] == plan_id:
                # Try to deduct from plan stock first
                plan_stock = plan.get("stock", -1)
                if plan_stock > 0:
                    plan["stock"] = plan_stock - quantity
                    save_products(data)
                    return plan["stock"]
                elif plan_stock == 0:
                    return None
                
                # If plan stock is unlimited, deduct from product stock
                product_stock = product.get("stock", -1)
                if product_stock > 0:
                    product["stock"] = product_stock - quantity
                    save_products(data)
                    return product["stock"]
                
                return -1  # Unlimited
    return None

# ========================= orders =========================
def add_order(record):
    data = _load(ORDERS_LOG, {"orders": []})
    record.setdefault("ts", time.time())
    record.setdefault("status", "pending")
    data["orders"].append(record)
    _save(ORDERS_LOG, data)

def get_order(order_id):
    for o in _load(ORDERS_LOG, {"orders": []})["orders"]:
        if str(o.get("order_id")) == str(order_id):
            return o
    return None

def set_order_status(order_id, status):
    data = _load(ORDERS_LOG, {"orders": []})
    changed = False
    for o in data["orders"]:
        if str(o.get("order_id")) == str(order_id):
            o["status"] = status
            changed = True
            break
    if changed:
        _save(ORDERS_LOG, data)
    return changed

def count_user_orders(user_id):
    return sum(1 for o in _load(ORDERS_LOG, {"orders": []})["orders"]
               if str(o.get("user_id")) == str(user_id))

def _is_today(ts):
    try:
        a = time.localtime(ts)
        b = time.localtime()
        return (a.tm_year, a.tm_yday) == (b.tm_year, b.tm_yday)
    except Exception:
        return False

def global_stats():
    orders = _load(ORDERS_LOG, {"orders": []})["orders"]
    total = len(orders)
    today = sum(1 for o in orders if _is_today(o.get("ts", 0)))
    cancelled = sum(1 for o in orders if o.get("status") == "cancelled")
    revenue = sum(float(o.get("amount", 0) or 0) for o in orders if o.get("status") != "cancelled")
    today_rev = sum(float(o.get("amount", 0) or 0) for o in orders
                    if o.get("status") != "cancelled" and _is_today(o.get("ts", 0)))
    return {
        "total_orders": total, "today_orders": today,
        "total_revenue": revenue, "today_revenue": today_rev,
        "cancelled": cancelled,
    }

def customer_stats(user_id):
    orders = [o for o in _load(ORDERS_LOG, {"orders": []})["orders"]
              if str(o.get("user_id")) == str(user_id)]
    paid = [o for o in orders if o.get("status") != "cancelled"]
    total = len(paid)
    revenue = sum(float(o.get("amount", 0) or 0) for o in paid)
    if total >= FREQUENT_MIN:
        ctype = "Frequent"
    elif total >= AVERAGE_MIN:
        ctype = "Average"
    else:
        ctype = "Less Use"
    return {"total_orders": total, "total_revenue": revenue, "type": ctype}

# ========================= money parsing =========================
def parse_money(text):
    """'$10', '10', '10.5' -> 10.0 ; returns None if not a positive number."""
    if not text:
        return None
    m = re.search(r"[-+]?\d*\.?\d+", str(text).replace(",", "").replace("$", ""))
    if not m:
        return None
    try:
        v = float(m.group(0))
    except Exception:
        return None
    return v if v > 0 else None

def fmt_money(value):
    try:
        v = float(value)
    except Exception:
        return "$0"
    if abs(v - round(v)) < 0.005:
        return "$" + str(int(round(v)))
    return "$" + ("%.2f" % v)

# ========================= find user by username =========================
def find_user_by_username(username):
    """Find user by their Telegram username"""
    users = load_users()
    target_username = username.lower().lstrip('@')
    
    for user_id, user_data in users.items():
        stored_username = user_data.get('username', '').lower()
        if stored_username == target_username:
            return {
                'user_id': int(user_id),
                'username': user_data.get('username'),
                'first_name': user_data.get('first_name', 'Unknown')
            }
    return None

# ========================= direct Telegram API (cross-bot sends) =========================
def api_call(token, method, **params):
    """Blocking call to the Telegram Bot API. Returns parsed JSON dict or None."""
    url = "https://api.telegram.org/bot" + token + "/" + method
    data = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            data[k] = json.dumps(v)
        else:
            data[k] = v
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def send_message_as_main(chat_id, text, reply_markup=None):
    """DM a customer through the MAIN bot"""
    return api_call(MAIN_BOT_TOKEN, "sendMessage", chat_id=chat_id, text=text,
                    parse_mode="HTML", reply_markup=reply_markup)

def send_message_as_orders(chat_id, text, reply_markup=None):
    """Message an admin through the ORDERS bot"""
    return api_call(ORDERS_BOT_TOKEN, "sendMessage", chat_id=chat_id, text=text,
                    parse_mode="HTML", reply_markup=reply_markup)