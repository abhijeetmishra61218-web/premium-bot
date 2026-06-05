"""
Premium Villa - Social Media Services module (smm.py)
Wire into bot.py with:  import smm   and   smm.setup(app, ADMIN_ID)

CHANGES vs original:
  - Dedicated question screen (like TG Premium) shown after qty entry
  - qty_image now displayed on the quantity prompt screen
  - Custom emoji support on all SMM buttons via raw Telegram API
"""

import os
import html
import json
import uuid
import re
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ApplicationHandlerStop,
)

# =====================================================================
# RAPIDAPI INSTAGRAM CHECK
# =====================================================================
RAPIDAPI_KEYS = [
    "7b5d6b21c0msh57cf99440508089p1f9896jsn06a96f563bea",
    "49ee681ee5mshb39475bb04885e3p1ef2eejsn9f78c3506669",
    "657c008a11msh8294f330571da54p1efc9ajsned28faf444c0",
    "b40ea1582emsh574c62ad3110edfp1e8b68jsnec5ea593117b",
    "255d3ec2edmsh1d81a4f495523b5p10bd57jsn153528938a06",
    "209f50abc4msh6b70651a0f761eep1b494djsn9aff99cb4999",
    "bdf9253dfemshd092f90ed59935ep13aed9jsnb76056b453a9",
    "b91093e300msh875a0bc845da25dp1ec0d3jsnae33f962d5cc",
    "7e19c9ffeamshb46c475f576b191p1ad3acjsnd1f7d13e6f46",
    "b265f928a3msha20d2ad0154dba0p12bc3bjsn2ac4c4359ef7",
    "516874bdc7mshd51d8ad74a3ec08p162e84jsn58bf4db842d2",
    "26adaf8bddmsh198f922f15f94f3p10590cjsnefdbfa36a99d",
    "2aff64308bmsh51a7b957e6e10afp1f6d67jsn796d29de4eff",
    "7ed62b4085mshbeb8913763d8316p1c98b6jsn0f455b0569d3",
    "f18e2cb361msh965fce3b3002b2ap1e5421jsn095d8fca1717",
    "e2757d1f01mshc2a32936973859ap12a9e0jsn137d2fc15197",
    "a29186f629msh00e0a8d21dddc7fp1c63f6jsnd37dda4bcb96",
    "6165bf44dmshab908e2de5071f2p1a80cdjsnb2a49deb6562",
    "d52dc29e64mshe7a2f0378c0aa09p1cf29bjsn9d5b48767cf4",
]
RAPIDAPI_HOST = "instagram-scraper-stable-api.p.rapidapi.com"
RAPIDAPI_URL = "https://instagram-scraper-stable-api.p.rapidapi.com/ig_get_fb_profile.php?username_or_url={username}"

_KEY_INDEX = 0
PRIVATE_CHECK_ENABLED = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except Exception:
    HTTPX_AVAILABLE = False

try:
    import instaloader
    IG_AVAILABLE = True
except Exception:
    IG_AVAILABLE = False

NL = chr(10)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SMM_FILE = os.path.join(BASE_DIR, "smmdata.json")

ADMIN_ID = 0
CAT_ID = "smm"
BOT_TOKEN = ""  # set in setup()

_IG_SEM = asyncio.Semaphore(3)
_IG_SLOT_WAIT = 2
_IG_TIMEOUT = 10

TG_API_BASE = ""  # set in setup()

# =====================================================================
# HELPER: convert raw rows to standard InlineKeyboardMarkup
# =====================================================================
def _rows_to_kb(rows):
    """Convert raw rows (list of list of dicts) to InlineKeyboardMarkup."""
    kb_rows = []
    for row in rows:
        kb_row = []
        for btn in row:
            kb_row.append(InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]))
        kb_rows.append(kb_row)
    return InlineKeyboardMarkup(kb_rows)

# =====================================================================
# RAW API HELPERS (enables custom emoji on buttons)
# =====================================================================
def _build_raw_keyboard(rows_spec):
    """rows_spec: list of list of dicts with keys: text, callback_data, emoji_id (optional)"""
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

async def _raw_send_message(chat_id, text, keyboard_rows, photo=None, parse_mode="HTML"):
    if photo:
        return await _raw_send_photo(chat_id, photo, text, keyboard_rows, parse_mode)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API_BASE}/sendMessage", json=payload)
    return r.json()

async def _raw_send_photo(chat_id, photo, caption, keyboard_rows, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API_BASE}/sendPhoto", json=payload)
    return r.json()

async def _raw_edit_message_text(chat_id, message_id, text, keyboard_rows, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API_BASE}/editMessageText", json=payload)
    return r.json()

async def _raw_edit_message_media(chat_id, message_id, photo, caption, keyboard_rows, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "media": {"type": "photo", "media": photo, "caption": caption, "parse_mode": parse_mode},
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{TG_API_BASE}/editMessageMedia", json=payload)
    return r.json()

# =====================================================================
# DEFAULT DATA
# =====================================================================
def _default_data():
    def svc(sid, label, title, unit, price, minimum, target_type, target_prompt, private_check):
        return {
            "id": sid,
            "label": label,
            "title": title,
            "unit": unit,
            "price_per_1k": price,
            "price_text": "Price : " + _fmt_money(price) + " Per 1,000 " + unit,
            "minimum": minimum,
            "minimum_text": "Minimum : " + str(minimum) + " " + unit,
            "qty_prompt": "Please Enter The Number Of " + unit + " You want",
            "qty_image": None,
            "target_type": target_type,
            "target_prompt": target_prompt,
            "target_image": None,
            "image": None,
            "confirm_image": None,
            "private_check": private_check,
            "always_remind": False,
            "private_reminder": (
                "Your account is private. Please make it Public after placing the order. "
                "Once You Receive The Order, You can make it Private Again."
            ),
        }

    acct_prompt = "Please Enter Your Instagram Username or Profile Link"
    post_prompt = "Please Enter Your Instagram Post Link"
    return {
        "root": {
            "title": "Social Media Services",
            "desc": "Choose a platform:",
            "image": None,
        },
        "platforms": [
            {
                "id": "ig",
                "name": "Instagram",
                "services": [
                    svc("igf", "Followers | $12 Per 1k", "Instagram High Quality Followers",
                        "Followers", 12.0, 500, "account", acct_prompt, True),
                    svc("igl", "Post Likes", "Instagram High Quality Likes",
                        "Likes", 4.0, 100, "post", post_prompt, False),
                    svc("igv", "Post Views", "Instagram High Quality Views",
                        "Views", 2.0, 500, "post", post_prompt, False),
                    svc("igc", "Post Comments", "Instagram High Quality Comments",
                        "Comments", 20.0, 20, "post", post_prompt, False),
                    svc("igs", "Story Views", "Instagram Story Views",
                        "Story Views", 3.0, 100, "account", acct_prompt, True),
                ],
            }
        ],
    }

# =====================================================================
# storage (with self-heal)
# =====================================================================
def _load():
    if not os.path.exists(SMM_FILE):
        _save(_default_data())
    with open(SMM_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    changed = False
    if not isinstance(data, dict):
        data = _default_data(); changed = True
    if "platforms" not in data or not isinstance(data["platforms"], list):
        data["platforms"] = _default_data()["platforms"]; changed = True
    if not data["platforms"]:
        data["platforms"] = _default_data()["platforms"]; changed = True
    if "root" not in data or not isinstance(data.get("root"), dict):
        data["root"] = _default_data()["root"]; changed = True
    if changed:
        _save(data)
    return data

def _root_cfg():
    return _load().get("root", {"title": "Social Media Services", "desc": "Choose a platform:", "image": None})

def _save(data):
    with open(SMM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _platform(data, pid):
    for p in data["platforms"]:
        if p["id"] == pid:
            return p
    return None

def _service(platform, sid):
    if not platform:
        return None
    for s in platform.get("services", []):
        if s["id"] == sid:
            return s
    return None

# =====================================================================
# helpers
# =====================================================================
def _fmt_money(value):
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

def _parse_int(text):
    cleaned = re.sub(r"[,\s]", "", text or "")
    if not cleaned.isdigit():
        return None
    n = int(cleaned)
    return n if n > 0 else None

def _calc_total(price_per_1k, qty):
    try:
        return float(price_per_1k) * float(qty) / 1000.0
    except Exception:
        return 0.0

def _extract_ig_username(text):
    t = (text or "").strip().split("?")[0]
    m = re.search(r"instagram\.com/([^/\s]+)", t, re.IGNORECASE)
    if m:
        return m.group(1).lstrip("@").strip()
    return t.lstrip("@").strip()

# =====================================================================
# private check
# =====================================================================
def _find_is_private(obj):
    if isinstance(obj, dict):
        for key in ("is_private", "private", "isPrivate"):
            if key in obj and isinstance(obj[key], bool):
                return obj[key]
            if key in obj and isinstance(obj[key], (int, str)):
                val = str(obj[key]).strip().lower()
                if val in ("true", "1", "yes"):
                    return True
                if val in ("false", "0", "no"):
                    return False
        for v in obj.values():
            r = _find_is_private(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_is_private(v)
            if r is not None:
                return r
    return None

def _check_private_rapidapi_blocking(username):
    global _KEY_INDEX
    if not RAPIDAPI_KEYS:
        return None
    url = RAPIDAPI_URL.replace("{username}", username)
    n = len(RAPIDAPI_KEYS)
    start = _KEY_INDEX
    for offset in range(n):
        idx = (start + offset) % n
        key = RAPIDAPI_KEYS[idx]
        if not key:
            continue
        try:
            headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": RAPIDAPI_HOST}
            resp = httpx.get(url, headers=headers, timeout=_IG_TIMEOUT)
            if resp.status_code == 200:
                _KEY_INDEX = idx
                return _find_is_private(resp.json())
            if resp.status_code in (401, 403, 429):
                continue
            return None
        except Exception:
            continue
    return None

def _check_private_instaloader_blocking(username):
    try:
        loader = instaloader.Instaloader(
            quiet=True, download_pictures=False, download_videos=False,
            download_video_thumbnails=False, download_comments=False,
            save_metadata=False, compress_json=False, max_connection_attempts=1,
        )
        profile = instaloader.Profile.from_username(loader.context, username)
        return bool(profile.is_private)
    except Exception:
        return None

def _check_private_blocking(username):
    if RAPIDAPI_KEYS and HTTPX_AVAILABLE:
        result = _check_private_rapidapi_blocking(username)
        if result is not None:
            return result
    if IG_AVAILABLE:
        return _check_private_instaloader_blocking(username)
    return None

def _check_enabled():
    if not PRIVATE_CHECK_ENABLED:
        return False
    return bool(any(RAPIDAPI_KEYS) and HTTPX_AVAILABLE) or IG_AVAILABLE

async def _check_private(username):
    if not _check_enabled() or not username:
        return None
    try:
        await asyncio.wait_for(_IG_SEM.acquire(), timeout=_IG_SLOT_WAIT)
    except Exception:
        return None
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_check_private_blocking, username), timeout=_IG_TIMEOUT + 2
        )
    except Exception:
        return None
    finally:
        try:
            _IG_SEM.release()
        except Exception:
            pass

# =====================================================================
# render helpers (standard python-telegram-bot)
# =====================================================================
async def _render(query, context, caption, keyboard, photo=None):
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

async def _render_to(context, chat_id, msg_id, had_photo, caption, keyboard, photo=None):
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

async def _safe_edit(query, context, text, reply_markup=None):
    msg = query.message
    if msg.photo:
        try:
            await msg.delete()
        except Exception:
            pass
        await context.bot.send_message(chat_id=msg.chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        pass

# =====================================================================
# RAW render helpers (support custom emoji on buttons)
# =====================================================================
async def _raw_render_to(context, chat_id, msg_id, had_photo, caption, rows, photo=None):
    """Like _render_to but accepts raw rows (list of list of dicts) for emoji support."""
    want_photo = photo is not None
    if msg_id is not None:
        try:
            if want_photo and had_photo:
                await _raw_edit_message_media(chat_id, msg_id, photo, caption)
                return
            if (not want_photo) and (not had_photo):
                await _raw_edit_message_text(chat_id, msg_id, caption, rows)
                return
        except Exception:
            pass
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    if want_photo:
        await _raw_send_photo(chat_id, photo, caption, rows)
    else:
        await _raw_send_message(chat_id, caption, rows)

# =====================================================================
# customer screens
# =====================================================================
def _root_screen_rows(user_id):
    """Returns (caption, raw_rows, photo) — raw_rows support custom emoji."""
    data = _load()
    cfg = data.get("root", {})
    rows = []
    for p in data["platforms"]:
        rows.append([{"text": p["name"], "callback_data": "smp:" + p["id"], "emoji_id": p.get("emoji_id")}])
    if user_id == ADMIN_ID:
        rows.append([{"text": "Manage Platforms", "callback_data": "smmp", "emoji_id": None}])
        rows.append([{"text": "Edit This Page", "callback_data": "smroot", "emoji_id": None}])
    rows.append([{"text": "Back", "callback_data": "smx", "emoji_id": None}])
    title = html.escape(cfg.get("title") or "Social Media Services")
    desc = html.escape(cfg.get("desc") or "Choose a platform:")
    text = "<b>" + title + "</b>" + NL + NL + desc
    return text, rows, cfg.get("image")

def _platform_screen_rows(pid, user_id):
    """Returns (caption, raw_rows, photo)."""
    data = _load()
    p = _platform(data, pid)
    if not p:
        return None
    services = p.get("services", [])
    rows = []
    i = 0
    while i < len(services):
        row = [{"text": services[i]["label"], "callback_data": "sms:" + pid + ":" + services[i]["id"], "emoji_id": services[i].get("emoji_id")}]
        if i + 1 < len(services):
            row.append({"text": services[i + 1]["label"], "callback_data": "sms:" + pid + ":" + services[i + 1]["id"], "emoji_id": services[i + 1].get("emoji_id")})
        rows.append(row)
        i += 2
    if user_id == ADMIN_ID:
        rows.append([{"text": "+ Add Service", "callback_data": "smsa:" + pid, "emoji_id": None}])
        if services:
            rows.append([{"text": "Manage Services", "callback_data": "smms:" + pid, "emoji_id": None}])
            rows.append([{"text": "🎨 Set Service Emojis", "callback_data": "smemoji:" + pid, "emoji_id": None}])
    rows.append([{"text": "Back", "callback_data": "smr", "emoji_id": None}])
    text = "<b>" + html.escape(p["name"]) + "</b>" + NL + NL + "Choose a service:"
    return text, rows, p.get("image")

def _qty_screen_rows(pid, sid, s):
    """Quantity entry screen — shows qty_prompt + qty_image. Returns (caption, raw_rows, photo)."""
    caption = (
        "<b>" + html.escape(s["title"]) + "</b>" + NL + NL
        + html.escape(s["price_text"]) + NL + NL
        + html.escape(s["minimum_text"]) + NL + NL
        + "<b>" + html.escape(s["qty_prompt"]) + "</b>"
    )
    rows = [[{"text": "Back", "callback_data": "smp:" + pid, "emoji_id": None}]]
    photo = s.get("qty_image") or s.get("image")
    return caption, rows, photo

def _question_screen_rows(pid, s, qty):
    """
    Dedicated question screen shown after qty — like TG Premium username screen.
    Shows target_prompt + target_image. Returns (caption, raw_rows, photo).
    """
    caption = (
        "<b>" + html.escape(s["unit"]) + " : " + _fmt_int(qty) + "</b>" + NL + NL
        + "<b>" + html.escape(s["target_prompt"]) + "</b>"
    )
    rows = [[{"text": "Back", "callback_data": "sms:" + pid + ":" + s["id"], "emoji_id": None}]]
    photo = s.get("target_image")
    return caption, rows, photo

def _confirm_rows(pid, s, qty, target):
    """Confirmation screen. Returns (caption, raw_rows, photo)."""
    total = _calc_total(s["price_per_1k"], qty)
    lines = ["<b>Product : " + _fmt_int(qty) + " " + html.escape(s["title"]) + "</b>"]
    if s["target_type"] == "post":
        lines.append("<b>Post Link : " + html.escape(target) + "</b>")
    else:
        uname = _extract_ig_username(target)
        lines.append("<b>Instagram Username : @" + html.escape(uname) + "</b>")
    lines.append("<b>Total Price : " + _fmt_money(total) + "</b>")
    caption = NL.join(lines)
    rows = [
        [{"text": "Buy Now", "callback_data": "cart:buysmm", "emoji_id": None}],
        [{"text": "Add to Cart", "callback_data": "cart:addsmm", "emoji_id": None}],
        [{"text": "Back", "callback_data": "smp:" + pid, "emoji_id": None}],
    ]
    photo = s.get("confirm_image") or s.get("image")
    return caption, rows, photo

# =====================================================================
# admin panels (unchanged structure, standard keyboard fine for admin)
# =====================================================================
def _manage_platforms_panel():
    data = _load()
    kb = []
    for p in data["platforms"]:
        kb.append([
            InlineKeyboardButton(p["name"], callback_data="smpr:" + p["id"]),
            InlineKeyboardButton("Up", callback_data="smpu:" + p["id"]),
            InlineKeyboardButton("Down", callback_data="smpd:" + p["id"]),
            InlineKeyboardButton("Del", callback_data="smpx:" + p["id"]),
        ])
    kb.append([InlineKeyboardButton("+ Add Platform", callback_data="smpa")])
    kb.append([InlineKeyboardButton("Back", callback_data="smr")])
    text = "MANAGE PLATFORMS" + NL + "Tap a name to rename. Use Up/Down to reorder, Del to delete."
    return text, InlineKeyboardMarkup(kb)

def _manage_services_panel(pid):
    data = _load()
    p = _platform(data, pid)
    if not p:
        return None
    kb = []
    for s in p.get("services", []):
        kb.append([
            InlineKeyboardButton(s["label"], callback_data="smse:" + pid + ":" + s["id"]),
            InlineKeyboardButton("Up", callback_data="smsu:" + pid + ":" + s["id"]),
            InlineKeyboardButton("Down", callback_data="smsd:" + pid + ":" + s["id"]),
        ])
    kb.append([InlineKeyboardButton("+ Add Service", callback_data="smsa:" + pid)])
    kb.append([InlineKeyboardButton("Back", callback_data="smp:" + pid)])
    text = "MANAGE SERVICES - " + p["name"] + NL + "Tap a service to edit it, or use Up/Down to reorder."
    return text, InlineKeyboardMarkup(kb)

def _emoji_panel(pid):
    """Panel listing all services in a platform so admin can set emoji per service."""
    data = _load()
    p = _platform(data, pid)
    if not p:
        return None
    kb = []
    for s in p.get("services", []):
        emoji_info = " 2705" if s.get("emoji_id") else " 274c"
        kb.append([InlineKeyboardButton(s["label"] + emoji_info, callback_data="smemojis:" + pid + ":" + s["id"])])
    kb.append([InlineKeyboardButton("Back", callback_data="smp:" + pid)])
    text = (
        "SET SERVICE EMOJIS - " + p["name"] + NL + NL
        + "2705 = emoji set   274c = no emoji" + NL
        + "Tap a service to set or remove its emoji."
    )
    return text, InlineKeyboardMarkup(kb)

def _service_edit_panel(pid, sid):
    data = _load()
    p = _platform(data, pid)
    s = _service(p, sid)
    if not s:
        return None
    text = (
        "EDITING SERVICE" + NL
        + "Label: " + s["label"] + NL
        + "Title: " + s["title"] + NL
        + "Unit: " + s["unit"] + NL
        + "Price per 1k: " + _fmt_money(s["price_per_1k"]) + NL
        + "Price text: " + s["price_text"] + NL
        + "Minimum: " + str(s["minimum"]) + NL
        + "Minimum text: " + s["minimum_text"] + NL
        + "Qty prompt: " + s["qty_prompt"] + NL
        + "Question prompt: " + s["target_prompt"] + NL
        + "Target type: " + s["target_type"] + NL
        + "Private check (auto-detect): " + ("on" if s.get("private_check") else "off") + NL
        + "Always remind (reliable): " + ("on" if s.get("always_remind") else "off") + NL
        + "Service image (qty screen): " + ("yes" if s.get("image") else "no") + NL
        + "Qty screen image: " + ("yes" if s.get("qty_image") else "no") + NL
        + "Question screen image: " + ("yes" if s.get("target_image") else "no") + NL
        + "Confirm screen image: " + ("yes" if s.get("confirm_image") else "no")
    )
    base = pid + ":" + sid
    kb = [
        [InlineKeyboardButton("Edit Button Label", callback_data="smsf:label:" + base)],
        [InlineKeyboardButton("Edit Title", callback_data="smsf:title:" + base)],
        [InlineKeyboardButton("Edit Unit", callback_data="smsf:unit:" + base)],
        [InlineKeyboardButton("Edit Price per 1k", callback_data="smsf:price_per_1k:" + base)],
        [InlineKeyboardButton("Edit Price Text", callback_data="smsf:price_text:" + base)],
        [InlineKeyboardButton("Edit Minimum (number)", callback_data="smsf:minimum:" + base)],
        [InlineKeyboardButton("Edit Minimum Text", callback_data="smsf:minimum_text:" + base)],
        [InlineKeyboardButton("Edit Quantity Prompt", callback_data="smsf:qty_prompt:" + base)],
        [InlineKeyboardButton("Edit Question Text", callback_data="smsf:target_prompt:" + base)],
        [InlineKeyboardButton("Toggle Target (account/post)", callback_data="smtt:" + base)],
        [InlineKeyboardButton("Toggle Private Check", callback_data="smtp:" + base)],
        [InlineKeyboardButton("Toggle Always Remind", callback_data="smtr:" + base)],
        [InlineKeyboardButton("Edit Private Reminder", callback_data="smsf:private_reminder:" + base)],
        [InlineKeyboardButton("Change Qty Screen Image", callback_data="smsi:qty_image:" + base)],
        [InlineKeyboardButton("Change Question Screen Image", callback_data="smsi:target_image:" + base)],
        [InlineKeyboardButton("Change Confirm Screen Image", callback_data="smsi:confirm_image:" + base)],
        [InlineKeyboardButton("Delete Service", callback_data="smsx:" + base)],
        [InlineKeyboardButton("Back", callback_data="smms:" + pid)],
    ]
    return text, InlineKeyboardMarkup(kb)

# =====================================================================
# CALLBACK HANDLER (group -1)
# =====================================================================
async def _on_callback(update, context):
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not (data == "open:smm" or data.startswith("sm")):
        return
    user_id = query.from_user.id

    # ---- root SMM screen ----
    if data == "open:smm":
        caption, rows, photo = _root_screen_rows(user_id)
        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        had_photo = bool(query.message.photo)
        await query.answer()
        # Use standard render (no raw API needed here — no custom emoji on root screen buttons)
        kb = _rows_to_kb(rows)
        try:
            if photo and had_photo:
                await query.message.edit_media(
                    media=__import__("telegram").InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                    reply_markup=kb,
                )
            elif not photo and not had_photo:
                await query.message.edit_text(caption, reply_markup=kb, parse_mode="HTML")
            else:
                raise Exception("need new message")
        except Exception:
            try:
                await query.message.delete()
            except Exception:
                pass
            if photo:
                await query.get_bot().send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=kb, parse_mode="HTML")
            else:
                await query.get_bot().send_message(chat_id=chat_id, text=caption, reply_markup=kb, parse_mode="HTML")
        raise ApplicationHandlerStop

    if data == "smr":
        context.user_data.pop("smm_flow", None)
        caption, rows, photo = _root_screen_rows(user_id)
        chat_id = query.message.chat_id
        try:
            await query.message.delete()
        except Exception:
            pass
        await _raw_send_message(chat_id, caption, rows, photo)
        await query.answer()
        raise ApplicationHandlerStop

    if data == "smx":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        raise ApplicationHandlerStop

    # ---- platform screen ----
    if data.startswith("smp:"):
        pid = data[4:]
        context.user_data.pop("smm_flow", None)
        res = _platform_screen_rows(pid, user_id)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        caption, rows, photo = res
        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        had_photo = bool(query.message.photo)
        await _raw_render_to(context, chat_id, msg_id, had_photo, caption, rows, photo)
        await query.answer()
        raise ApplicationHandlerStop

    # ---- service selected → qty screen ----
    if data.startswith("sms:"):
        rest = data[4:]
        pid, sid = rest.split(":", 1)
        d = _load()
        s = _service(_platform(d, pid), sid)
        if not s:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        caption, rows, photo = _qty_screen_rows(pid, sid, s)
        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        had_photo = bool(query.message.photo)
        await _raw_render_to(context, chat_id, msg_id, had_photo, caption, rows, photo)
        context.user_data.pop("state", None)
        context.user_data["smm_flow"] = {
            "step": "qty",
            "pid": pid,
            "sid": sid,
            "chat_id": chat_id,
            "msg_id": msg_id,
            "has_photo": photo is not None,
        }
        await query.answer()
        raise ApplicationHandlerStop

    if user_id != ADMIN_ID:
        await query.answer("Not allowed", show_alert=True)
        raise ApplicationHandlerStop

    # ---- admin: manage platforms ----
    if data == "smmp":
        context.user_data.pop("smm_flow", None)
        text, kb = _manage_platforms_panel()
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data == "smroot":
        context.user_data.pop("smm_flow", None)
        cfg = _root_cfg()
        text = (
            "EDIT SOCIAL MEDIA PAGE" + NL
            + "Title: " + (cfg.get("title") or "") + NL
            + "Description: " + (cfg.get("desc") or "") + NL
            + "Image: " + ("yes" if cfg.get("image") else "no")
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Edit Title", callback_data="smrt:title")],
            [InlineKeyboardButton("Edit Description", callback_data="smrt:desc")],
            [InlineKeyboardButton("Change Image", callback_data="smri")],
            [InlineKeyboardButton("Back", callback_data="smr")],
        ])
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smrt:"):
        field = data[5:]
        context.user_data["smm_flow"] = {"step": "edit_root_field", "field": field}
        label = "TITLE" if field == "title" else "DESCRIPTION"
        await _safe_edit(query, context, "Send the new " + label + " for the Social Media page:" + NL + "(or /start to cancel)")
        await query.answer()
        raise ApplicationHandlerStop

    if data == "smri":
        context.user_data["smm_flow"] = {"step": "edit_root_image"}
        await _safe_edit(query, context, "Send the new IMAGE for the Social Media page." + NL
                         + "(send 0 to remove it, or /start to cancel)")
        await query.answer()
        raise ApplicationHandlerStop

    if data == "smpa":
        context.user_data["smm_flow"] = {"step": "add_platform"}
        await _safe_edit(query, context, "Send the new PLATFORM NAME (example: TikTok):" + NL + "(or /start to cancel)")
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smpr:"):
        pid = data[5:]
        context.user_data["smm_flow"] = {"step": "rename_platform", "pid": pid}
        await _safe_edit(query, context, "Send the new name for this platform:" + NL + "(or /start to cancel)")
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smpxok:"):
        pid = data[7:]
        d = _load()
        d["platforms"] = [p for p in d["platforms"] if p["id"] != pid]
        _save(d)
        text, kb = _manage_platforms_panel()
        await _safe_edit(query, context, "Platform deleted." + NL + NL + text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smpx:"):
        pid = data[5:]
        d = _load()
        p = _platform(d, pid)
        nm = p["name"] if p else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete", callback_data="smpxok:" + pid)],
            [InlineKeyboardButton("No, go back", callback_data="smmp")],
        ])
        await _safe_edit(query, context, "Delete platform '" + nm + "' and all its services?", kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smpu:") or data.startswith("smpd:"):
        pid = data[5:]
        d = _load()
        plats = d["platforms"]
        idx = next((i for i, p in enumerate(plats) if p["id"] == pid), None)
        if idx is not None:
            if data.startswith("smpu:") and idx > 0:
                plats[idx - 1], plats[idx] = plats[idx], plats[idx - 1]
            elif data.startswith("smpd:") and idx < len(plats) - 1:
                plats[idx + 1], plats[idx] = plats[idx], plats[idx + 1]
            _save(d)
        text, kb = _manage_platforms_panel()
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smms:"):
        pid = data[5:]
        res = _manage_services_panel(pid)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        text, kb = res
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smemoji:"):
        pid = data[8:]
        res = _emoji_panel(pid)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        text, kb = res
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smemojis:"):
        rest = data[9:]
        pid, sid = rest.split(":", 1)
        data2 = _load()
        s = _service(_platform(data2, pid), sid)
        if not s:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        cur = "ID: " + str(s.get("emoji_id")) if s.get("emoji_id") else "None"
        context.user_data["smm_flow"] = {"step": "set_svc_emoji", "pid": pid, "sid": sid}
        await _safe_edit(query, context,
            "SET EMOJI for: " + s["label"] + NL + NL
            + "Current: " + cur + NL + NL
            + "Send a message with a custom animated emoji IN IT." + NL
            + "Send 0 to REMOVE the current emoji." + NL
            + "(or /start to cancel)"
        )
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsa:"):
        pid = data[5:]
        context.user_data["smm_flow"] = {"step": "add_svc_label", "pid": pid, "draft": {}}
        await _safe_edit(query, context, "ADD SERVICE" + NL + NL
                         + "Send the BUTTON LABEL (example: Followers | $12 Per 1k):" + NL
                         + "(or /start to cancel)")
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smse:"):
        rest = data[5:]
        pid, sid = rest.split(":", 1)
        res = _service_edit_panel(pid, sid)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        text, kb = res
        await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsu:") or data.startswith("smsd:"):
        rest = data[5:]
        pid, sid = rest.split(":", 1)
        d = _load()
        p = _platform(d, pid)
        if p:
            svcs = p.get("services", [])
            idx = next((i for i, s in enumerate(svcs) if s["id"] == sid), None)
            if idx is not None:
                if data.startswith("smsu:") and idx > 0:
                    svcs[idx - 1], svcs[idx] = svcs[idx], svcs[idx - 1]
                elif data.startswith("smsd:") and idx < len(svcs) - 1:
                    svcs[idx + 1], svcs[idx] = svcs[idx], svcs[idx + 1]
                _save(d)
        res = _manage_services_panel(pid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsxok:"):
        rest = data[7:]
        pid, sid = rest.split(":", 1)
        d = _load()
        p = _platform(d, pid)
        if p:
            p["services"] = [s for s in p.get("services", []) if s["id"] != sid]
            _save(d)
        res = _manage_services_panel(pid)
        text, kb = res if res else (
            "MANAGE SERVICES" + NL + "(none)",
            InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="smp:" + pid)]])
        )
        await _safe_edit(query, context, "Service deleted." + NL + NL + text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsx:"):
        rest = data[5:]
        pid, sid = rest.split(":", 1)
        d = _load()
        s = _service(_platform(d, pid), sid)
        nm = s["label"] if s else "?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete", callback_data="smsxok:" + pid + ":" + sid)],
            [InlineKeyboardButton("No, go back", callback_data="smse:" + pid + ":" + sid)],
        ])
        await _safe_edit(query, context, "Delete service '" + nm + "'?", kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smtt:"):
        rest = data[5:]
        pid, sid = rest.split(":", 1)
        d = _load()
        s = _service(_platform(d, pid), sid)
        if s:
            s["target_type"] = "post" if s["target_type"] == "account" else "account"
            _save(d)
        res = _service_edit_panel(pid, sid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smtp:"):
        rest = data[5:]
        pid, sid = rest.split(":", 1)
        d = _load()
        s = _service(_platform(d, pid), sid)
        if s:
            s["private_check"] = not bool(s.get("private_check"))
            _save(d)
        res = _service_edit_panel(pid, sid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smtr:"):
        rest = data[5:]
        pid, sid = rest.split(":", 1)
        d = _load()
        s = _service(_platform(d, pid), sid)
        if s:
            s["always_remind"] = not bool(s.get("always_remind"))
            _save(d)
        res = _service_edit_panel(pid, sid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsf:"):
        rest = data[5:]
        field, pid, sid = rest.split(":", 2)
        context.user_data["smm_flow"] = {"step": "edit_field", "field": field, "pid": pid, "sid": sid}
        numeric = field in ("price_per_1k", "minimum")
        hint = " (numbers only)" if numeric else ""
        label_map = {
            "label": "Button Label",
            "title": "Title",
            "unit": "Unit word",
            "price_per_1k": "Price per 1,000",
            "price_text": "Price Text",
            "minimum": "Minimum quantity",
            "minimum_text": "Minimum Text",
            "qty_prompt": "Quantity Prompt (shown on quantity screen)",
            "target_prompt": "Question Text (shown on question screen)",
            "private_reminder": "Private Account Reminder",
        }
        label = label_map.get(field, field)
        await _safe_edit(query, context, "Send the new value for <b>" + label + "</b>" + hint + ":" + NL + "(or /start to cancel)", None)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsi:"):
        rest = data[5:]
        field, pid, sid = rest.split(":", 2)
        context.user_data["smm_flow"] = {"step": "edit_image", "field": field, "pid": pid, "sid": sid}
        label_map = {
            "qty_image": "Quantity Screen Image",
            "target_image": "Question Screen Image",
            "confirm_image": "Confirm Screen Image",
            "image": "Service Image",
        }
        label = label_map.get(field, field)
        await _safe_edit(query, context, "Send the new image for <b>" + label + "</b>." + NL
                         + "(send 0 to remove it, or /start to cancel)", None)
        await query.answer()
        raise ApplicationHandlerStop

    await query.answer()
    raise ApplicationHandlerStop

# =====================================================================
# TEXT HANDLER (group -1)
# =====================================================================
async def _on_text(update, context):
    flow = context.user_data.get("smm_flow")
    if not flow:
        return
    step = flow.get("step")
    text = (update.message.text or "").strip()
    uid = update.effective_user.id

    # ---- STEP 1: qty entry ----
    if step == "qty":
        d = _load()
        s = _service(_platform(d, flow["pid"]), flow["sid"])
        if not s:
            context.user_data.pop("smm_flow", None)
            await update.message.reply_text("Sorry, that service is no longer available. Send /start.")
            raise ApplicationHandlerStop
        qty = _parse_int(text)
        if qty is None or qty < int(s.get("minimum", 0)):
            await _delete_user_msg(update)
            raise ApplicationHandlerStop
        await _delete_user_msg(update)
        flow["qty"] = qty
        flow["step"] = "target"

        # Show the dedicated question screen
        caption, rows, photo = _question_screen_rows(flow["pid"], s, qty)
        result = await _raw_render_to(
            context, flow["chat_id"], flow["msg_id"], flow["has_photo"],
            caption, rows, photo
        )
        flow["has_photo"] = photo is not None
        # Update msg_id if a new message was sent
        if result and hasattr(result, "message_id"):
            flow["msg_id"] = result.message_id
        elif result and isinstance(result, dict) and result.get("result", {}).get("message_id"):
            flow["msg_id"] = result["result"]["message_id"]
        context.user_data["smm_flow"] = flow
        raise ApplicationHandlerStop

    # ---- STEP 2: target / question answer ----
    if step == "target":
        d = _load()
        s = _service(_platform(d, flow["pid"]), flow["sid"])
        if not s:
            context.user_data.pop("smm_flow", None)
            await update.message.reply_text("Sorry, that service is no longer available. Send /start.")
            raise ApplicationHandlerStop

        target_raw = text
        # For account type: basic username validation (no spaces, not empty)
        if s["target_type"] == "account":
            if not target_raw or " " in target_raw.strip():
                await _delete_user_msg(update)
                raise ApplicationHandlerStop
        # For post type: must look like a link or at least no spaces
        else:
            if not target_raw or " " in target_raw.strip():
                await _delete_user_msg(update)
                raise ApplicationHandlerStop

        await _delete_user_msg(update)

        qty = flow.get("qty", 0)
        chat_id, msg_id, had_photo = flow["chat_id"], flow["msg_id"], flow["has_photo"]

        if s["target_type"] == "post":
            _ctgt = target_raw
        else:
            _ctgt = "@" + _extract_ig_username(target_raw)

        # Private account check
        do_check = (s["target_type"] == "account") and bool(s.get("private_check"))
        is_private = None
        if do_check:
            username = _extract_ig_username(target_raw)
            is_private = await _check_private(username)

        force_remind = (s["target_type"] == "account") and bool(s.get("always_remind"))
        show_reminder = (is_private is True) or force_remind

        # Save cart pending
        context.user_data.pop("smm_flow", None)
        context.user_data["cart_pending"] = {
            "kind": "smm",
            "title": s["title"],
            "price_per_1k": s["price_per_1k"],
            "qty": int(qty),
            "min": int(s.get("minimum", 1)),
            "step": int(s.get("minimum", 1)) if int(s.get("minimum", 1)) > 0 else 100,
            "target": _ctgt,
            "pid": flow["pid"],
        }

        confirm_caption, confirm_rows, confirm_photo = _confirm_rows(flow["pid"], s, qty, _ctgt)

        if show_reminder:
            reminder = "<b>" + html.escape(s.get("private_reminder", "")) + "</b>"
            r_photo = s.get("target_image")
            # Show reminder without buttons
            await _raw_render_to(context, chat_id, msg_id, had_photo, reminder, [], r_photo)
            await asyncio.sleep(5)
            await _raw_send_message(chat_id, confirm_caption, confirm_rows, confirm_photo)
        else:
            await _raw_render_to(context, chat_id, msg_id, had_photo,
                                 confirm_caption, confirm_rows, confirm_photo)
        raise ApplicationHandlerStop

    # ---- Admin flows ----
    if step == "set_svc_emoji":
        if uid != ADMIN_ID:
            context.user_data.pop("smm_flow", None)
            return
        pid = flow.get("pid")
        sid = flow.get("sid")
        if text == "0":
            d = _load()
            s = _service(_platform(d, pid), sid)
            if s:
                s["emoji_id"] = None
                _save(d)
            context.user_data.pop("smm_flow", None)
            res = _emoji_panel(pid)
            if res:
                t, kb = res
                await _reply_back(update, "Emoji removed." + NL + NL + t, "smemoji:" + pid)
            raise ApplicationHandlerStop
        from telegram import MessageEntity as ME
        entities = update.message.entities or []
        custom_emojis = [e for e in entities if e.type == ME.CUSTOM_EMOJI]
        if custom_emojis:
            emoji_id = custom_emojis[0].custom_emoji_id
            d = _load()
            s = _service(_platform(d, pid), sid)
            if s:
                s["emoji_id"] = emoji_id
                _save(d)
            context.user_data.pop("smm_flow", None)
            await _reply_back(update, "Emoji set! ID: " + emoji_id, "smemoji:" + pid)
        else:
            await update.message.reply_text(
                "No custom emoji detected. Send a message with an animated emoji, or send 0 to remove."
            )
        raise ApplicationHandlerStop

    if step == "edit_root_field":
        if uid != ADMIN_ID:
            context.user_data.pop("smm_flow", None)
            return
        d = _load()
        d.setdefault("root", {})[flow["field"]] = text
        _save(d)
        context.user_data.pop("smm_flow", None)
        await _reply_back(update, "Updated. Open Social Media Services to see it.", "smr")
        raise ApplicationHandlerStop

    if step == "edit_root_image":
        if uid != ADMIN_ID:
            context.user_data.pop("smm_flow", None)
            return
        if text == "0":
            d = _load()
            d.setdefault("root", {})["image"] = None
            _save(d)
            context.user_data.pop("smm_flow", None)
            await _reply_back(update, "Image removed.", "smr")
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove the image.")
        raise ApplicationHandlerStop

    if step == "add_platform":
        if uid != ADMIN_ID:
            context.user_data.pop("smm_flow", None)
            return
        d = _load()
        d["platforms"].append({"id": uuid.uuid4().hex[:6], "name": text, "services": []})
        _save(d)
        context.user_data.pop("smm_flow", None)
        await _reply_back(update, "Platform added.", "smmp")
        raise ApplicationHandlerStop

    if step == "rename_platform":
        if uid != ADMIN_ID:
            context.user_data.pop("smm_flow", None)
            return
        d = _load()
        p = _platform(d, flow["pid"])
        if p:
            p["name"] = text
            _save(d)
        context.user_data.pop("smm_flow", None)
        await _reply_back(update, "Platform renamed.", "smmp")
        raise ApplicationHandlerStop

    if step == "add_svc_label":
        if uid != ADMIN_ID:
            return
        flow["draft"]["label"] = text
        flow["step"] = "add_svc_title"
        await update.message.reply_text("Send the TITLE (example: Instagram High Quality Followers):")
        raise ApplicationHandlerStop

    if step == "add_svc_title":
        flow["draft"]["title"] = text
        flow["step"] = "add_svc_unit"
        await update.message.reply_text("Send the UNIT word (example: Followers, Likes, Views):")
        raise ApplicationHandlerStop

    if step == "add_svc_unit":
        flow["draft"]["unit"] = text
        flow["step"] = "add_svc_price"
        await update.message.reply_text("Send the PRICE per 1,000 (numbers only, example: 12):")
        raise ApplicationHandlerStop

    if step == "add_svc_price":
        try:
            price = float(re.sub(r"[,\s$]", "", text))
        except Exception:
            await update.message.reply_text("Please send a number (example: 12).")
            raise ApplicationHandlerStop
        flow["draft"]["price"] = price
        flow["step"] = "add_svc_min"
        await update.message.reply_text("Send the MINIMUM quantity (numbers only, example: 500):")
        raise ApplicationHandlerStop

    if step == "add_svc_min":
        mn = _parse_int(text)
        if mn is None:
            await update.message.reply_text("Please send a whole number (example: 500).")
            raise ApplicationHandlerStop
        flow["draft"]["minimum"] = mn
        flow["step"] = "add_svc_qty_prompt"
        await update.message.reply_text(
            "Send the QUANTITY PROMPT text shown on the quantity screen:" + NL
            + "(example: Please Enter The Number Of Followers You Want)"
        )
        raise ApplicationHandlerStop

    if step == "add_svc_qty_prompt":
        flow["draft"]["qty_prompt"] = text
        flow["step"] = "add_svc_target_prompt"
        await update.message.reply_text(
            "Send the QUESTION TEXT shown on the question screen:" + NL
            + "(example: Please Enter Your Instagram Username or Profile Link)"
        )
        raise ApplicationHandlerStop

    if step == "add_svc_target_prompt":
        flow["draft"]["target_prompt"] = text
        flow["step"] = "add_svc_type"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Account (username/profile)", callback_data="smtype:account")],
            [InlineKeyboardButton("Post (link)", callback_data="smtype:post")],
        ])
        await update.message.reply_text("Does this service target an ACCOUNT or a POST?", reply_markup=kb)
        raise ApplicationHandlerStop

    if step == "edit_field":
        if uid != ADMIN_ID:
            return
        d = _load()
        s = _service(_platform(d, flow["pid"]), flow["sid"])
        if s:
            field = flow["field"]
            if field == "price_per_1k":
                try:
                    s[field] = float(re.sub(r"[,\s$]", "", text))
                except Exception:
                    await update.message.reply_text("Please send a number (example: 12).")
                    raise ApplicationHandlerStop
            elif field == "minimum":
                mn = _parse_int(text)
                if mn is None:
                    await update.message.reply_text("Please send a whole number (example: 500).")
                    raise ApplicationHandlerStop
                s[field] = mn
            else:
                s[field] = text
            _save(d)
        context.user_data.pop("smm_flow", None)
        await _reply_back(update, "Updated.", "smse:" + flow["pid"] + ":" + flow["sid"])
        raise ApplicationHandlerStop

    if step == "edit_image":
        if uid != ADMIN_ID:
            return
        if text == "0":
            d = _load()
            s = _service(_platform(d, flow["pid"]), flow["sid"])
            if s:
                s[flow["field"]] = None
                _save(d)
            context.user_data.pop("smm_flow", None)
            await _reply_back(update, "Image removed.", "smse:" + flow["pid"] + ":" + flow["sid"])
        else:
            await update.message.reply_text("Please send a photo, or send 0 to remove it.")
        raise ApplicationHandlerStop

    return

# =====================================================================
# type choice callback (add service flow)
# =====================================================================
async def _handle_type_choice(query, context, choice):
    flow = context.user_data.get("smm_flow")
    if not flow or flow.get("step") != "add_svc_type":
        await query.answer()
        return
    draft = flow["draft"]
    pid = flow["pid"]
    unit = draft["unit"]
    price = draft["price"]
    minimum = draft["minimum"]
    qty_prompt = draft.get("qty_prompt", "Please Enter The Number Of " + unit + " You want")
    target_prompt = draft.get("target_prompt",
        "Please Enter Your Instagram Profile Username or Link" if choice == "account"
        else "Please Enter Your Instagram Post Link"
    )
    svc = {
        "id": uuid.uuid4().hex[:6],
        "label": draft["label"],
        "title": draft["title"],
        "unit": unit,
        "price_per_1k": price,
        "price_text": "Price : " + _fmt_money(price) + " Per 1,000 " + unit,
        "minimum": minimum,
        "minimum_text": "Minimum : " + str(minimum) + " " + unit,
        "qty_prompt": qty_prompt,
        "qty_image": None,
        "target_type": choice,
        "target_prompt": target_prompt,
        "target_image": None,
        "image": None,
        "confirm_image": None,
        "private_check": (choice == "account"),
        "always_remind": False,
        "private_reminder": (
            "Your account is private. Please make it Public after placing the order. "
            "Once You Receive The Order, You can make it Private Again."
        ),
    }
    d = _load()
    p = _platform(d, pid)
    if p:
        p.setdefault("services", []).append(svc)
        _save(d)
    context.user_data.pop("smm_flow", None)
    res = _manage_services_panel(pid)
    if res:
        text, kb = res
        await _safe_edit(query, context, "Service added." + NL + NL + text, kb)
    await query.answer()

# =====================================================================
# PHOTO HANDLER (group -1)
# =====================================================================
async def _on_photo(update, context):
    flow = context.user_data.get("smm_flow")
    if not flow or flow.get("step") not in ("edit_image", "edit_root_image"):
        return
    if update.effective_user.id != ADMIN_ID:
        return
    file_id = update.message.photo[-1].file_id

    if flow.get("step") == "edit_root_image":
        d = _load()
        d.setdefault("root", {})["image"] = file_id
        _save(d)
        context.user_data.pop("smm_flow", None)
        await _reply_back(update, "Image updated. Open Social Media Services to see it.", "smr")
        raise ApplicationHandlerStop

    d = _load()
    s = _service(_platform(d, flow["pid"]), flow["sid"])
    if s:
        s[flow["field"]] = file_id
        _save(d)
    pid, sid = flow["pid"], flow["sid"]
    context.user_data.pop("smm_flow", None)
    await _reply_back(update, "Image updated.", "smse:" + pid + ":" + sid)
    raise ApplicationHandlerStop

# =====================================================================
# helpers
# =====================================================================
async def _reply_back(update, message, back_callback):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=back_callback)]])
    await update.message.reply_text(message, reply_markup=kb)

async def _delete_user_msg(update):
    try:
        await update.message.delete()
    except Exception:
        pass

_original_on_callback = _on_callback

async def _on_callback_with_type(update, context):
    query = update.callback_query
    data = query.data if query else ""
    if data and data.startswith("smtype:"):
        await _handle_type_choice(query, context, data.split(":", 1)[1])
        raise ApplicationHandlerStop
    await _original_on_callback(update, context)

# =====================================================================
# SETUP
# =====================================================================
def setup(application, admin_id, bot_token=None):
    global ADMIN_ID, BOT_TOKEN, TG_API_BASE
    ADMIN_ID = admin_id
    if bot_token:
        BOT_TOKEN = bot_token
    else:
        # Try to read from bot.py's global if available
        try:
            import bot as _bot
            BOT_TOKEN = _bot.BOT_TOKEN
        except Exception:
            pass
    TG_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

    application.add_handler(CallbackQueryHandler(_on_callback_with_type), group=-1)
    application.add_handler(MessageHandler(filters.PHOTO, _on_photo), group=-1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text), group=-1)

    n_keys = len([k for k in RAPIDAPI_KEYS if k])
    print("Social Media module loaded.")
    print("  RapidAPI keys:", n_keys, "| httpx:", HTTPX_AVAILABLE, "| instaloader fallback:", IG_AVAILABLE)
    print("  Private-check active:", _check_enabled())
    print("  Custom emoji support: ON (raw API)")

# =====================================================================
# EMOJI HELPERS (called by bot.py for the global Set Product Emoji panel)
# =====================================================================
def load_for_emoji():
    """Returns list of (service_id, label, has_emoji) for all services across all platforms."""
    data = _load()
    result = []
    for p in data["platforms"]:
        for s in p.get("services", []):
            result.append((s["id"], s["label"], bool(s.get("emoji_id"))))
    return result

def get_service_emoji_info(sid):
    """Returns (label, current_emoji_id) for a service by id."""
    data = _load()
    for p in data["platforms"]:
        for s in p.get("services", []):
            if s["id"] == sid:
                return s["label"], s.get("emoji_id")
    return sid, None

def set_service_emoji(sid, emoji_id):
    """Set or clear emoji_id on a service by id."""
    data = _load()
    for p in data["platforms"]:
        for s in p.get("services", []):
            if s["id"] == sid:
                s["emoji_id"] = emoji_id
                _save(data)
                return

def load_platforms_for_emoji():
    """Returns list of (platform_id, platform_name, has_emoji) for all platforms."""
    data = _load()
    result = []
    for p in data["platforms"]:
        result.append((p["id"], p["name"], bool(p.get("emoji_id"))))
    return result

def get_platform_emoji_info(plat_id):
    """Returns (name, current_emoji_id) for a platform by id."""
    data = _load()
    for p in data["platforms"]:
        if p["id"] == plat_id:
            return p["name"], p.get("emoji_id")
    return plat_id, None

def set_platform_emoji(plat_id, emoji_id):
    """Set or clear emoji_id on a platform by id."""
    data = _load()
    for p in data["platforms"]:
        if p["id"] == plat_id:
            p["emoji_id"] = emoji_id
            _save(data)
            return

def load_services_for_emoji(plat_id):
    """Returns list of (service_id, label, has_emoji) for all services in a platform."""
    data = _load()
    p = _platform(data, plat_id)
    if not p:
        return []
    return [(s["id"], s["label"], bool(s.get("emoji_id"))) for s in p.get("services", [])]