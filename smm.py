"""
Premium Villa - Social Media Services module (smm.py)
Wire into bot.py with:  import smm   and   smm.setup(app, ADMIN_ID)
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
# RAPIDAPI INSTAGRAM CHECK  (reliable, free tier, auto key-rotation)
# Set PRIVATE_CHECK_ENABLED = True to turn detection on.
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
    import httpx  # noqa: F401
    HTTPX_AVAILABLE = True
except Exception:
    HTTPX_AVAILABLE = False

try:
    import instaloader  # noqa: F401
    IG_AVAILABLE = True
except Exception:
    IG_AVAILABLE = False

NL = chr(10)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SMM_FILE = os.path.join(BASE_DIR, "smmdata.json")

ADMIN_ID = 0
CAT_ID = "smm"

_IG_SEM = asyncio.Semaphore(3)
_IG_SLOT_WAIT = 2
_IG_TIMEOUT = 10

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

    acct_prompt = "Please Enter Your Instagram Profile Username or Link"
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
                    svc("igs", "Story Views", "Instagram High Quality Story Views",
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
        data = _default_data()
        changed = True
    if "platforms" not in data or not isinstance(data["platforms"], list):
        data["platforms"] = _default_data()["platforms"]
        changed = True
    if not data["platforms"]:
        data["platforms"] = _default_data()["platforms"]
        changed = True
    if "root" not in data or not isinstance(data.get("root"), dict):
        data["root"] = _default_data()["root"]
        changed = True
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
# render helpers
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
# customer screens
# =====================================================================
def _root_screen(user_id):
    data = _load()
    cfg = data.get("root", {})
    rows = []
    for p in data["platforms"]:
        rows.append([InlineKeyboardButton(p["name"], callback_data="smp:" + p["id"])])
    if user_id == ADMIN_ID:
        rows.append([InlineKeyboardButton("Manage Platforms", callback_data="smmp")])
        rows.append([InlineKeyboardButton("Edit This Page", callback_data="smroot")])
    rows.append([InlineKeyboardButton("Back", callback_data="smx")])
    title = html.escape(cfg.get("title") or "Social Media Services")
    desc = html.escape(cfg.get("desc") or "Choose a platform:")
    text = "<b>" + title + "</b>" + NL + NL + desc
    return text, InlineKeyboardMarkup(rows), cfg.get("image")

def _platform_screen(pid, user_id):
    data = _load()
    p = _platform(data, pid)
    if not p:
        return None
    services = p.get("services", [])
    rows = []
    i = 0
    while i < len(services):
        row = [InlineKeyboardButton(services[i]["label"], callback_data="sms:" + pid + ":" + services[i]["id"])]
        if i + 1 < len(services):
            row.append(InlineKeyboardButton(services[i + 1]["label"], callback_data="sms:" + pid + ":" + services[i + 1]["id"]))
        rows.append(row)
        i += 2
    if user_id == ADMIN_ID:
        rows.append([InlineKeyboardButton("+ Add Service", callback_data="smsa:" + pid)])
        if services:
            rows.append([InlineKeyboardButton("Manage Services", callback_data="smms:" + pid)])
    rows.append([InlineKeyboardButton("Back", callback_data="smr")])
    text = "<b>" + html.escape(p["name"]) + "</b>" + NL + NL + "Choose a service:"
    return text, InlineKeyboardMarkup(rows), p.get("image")

def _service_screen(pid, sid):
    data = _load()
    p = _platform(data, pid)
    s = _service(p, sid)
    if not s:
        return None
    caption = (
        "<b>" + html.escape(s["title"]) + "</b>" + NL + NL
        + html.escape(s["price_text"]) + NL + NL
        + html.escape(s["minimum_text"]) + NL + NL
        + "<b>" + html.escape(s["qty_prompt"]) + "</b>"
    )
    rows = [[InlineKeyboardButton("Back", callback_data="smp:" + pid)]]
    return caption, InlineKeyboardMarkup(rows), s.get("image")

def _target_screen(s, qty=None):
    lines = []
    if qty is not None:
        lines.append("<b>" + html.escape(s["unit"]) + " : " + _fmt_int(qty) + "</b>")
        lines.append("")
    lines.append("<b>" + html.escape(s["target_prompt"]) + "</b>")
    caption = NL.join(lines)
    rows = [[InlineKeyboardButton("Back", callback_data="smp:" + s["_pid"])]] if s.get("_pid") else None
    return caption, (InlineKeyboardMarkup(rows) if rows else None), s.get("target_image")

def _confirm_caption(s, qty, target):
    total = _calc_total(s["price_per_1k"], qty)
    lines = ["<b>Product : " + _fmt_int(qty) + " " + html.escape(s["title"]) + "</b>"]
    if s["target_type"] == "post":
        lines.append("<b>Post Link : " + html.escape(target) + "</b>")
    else:
        uname = _extract_ig_username(target)
        lines.append("<b>Instagram Username : @" + html.escape(uname) + "</b>")
    lines.append("<b>Total Price : " + _fmt_money(total) + "</b>")
    return NL.join(lines)

# =====================================================================
# admin panels
# =====================================================================
def _manage_platforms_panel():
    data = _load()
    kb = []
    for i, p in enumerate(data["platforms"]):
        kb.append([
            InlineKeyboardButton(p["name"], callback_data="smpr:" + p["id"]),
            InlineKeyboardButton("Up", callback_data="smpu:" + p["id"]),
            InlineKeyboardButton("Down", callback_data="smpd:" + p["id"]),
            InlineKeyboardButton("Del", callback_data="smpx:" + p["id"]),
        ])
    kb.append([InlineKeyboardButton("+ Add Platform", callback_data="smpa")])
    kb.append([InlineKeyboardButton("Back", callback_data="smr")])
    text = ("MANAGE PLATFORMS" + NL
            + "Tap a name to rename. Use Up/Down to reorder, Del to delete.")
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
    text = ("MANAGE SERVICES - " + p["name"] + NL
            + "Tap a service to edit it, or use Up/Down to reorder.")
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
        + "Target type: " + s["target_type"] + NL
        + "Private check (auto-detect): " + ("on" if s.get("private_check") else "off") + NL
        + "Always remind (reliable): " + ("on" if s.get("always_remind") else "off") + NL
        + "Service image: " + ("yes" if s.get("image") else "no") + NL
        + "Quantity image: " + ("yes" if s.get("qty_image") else "no") + NL
        + "Target image: " + ("yes" if s.get("target_image") else "no") + NL
        + "Confirm image: " + ("yes" if s.get("confirm_image") else "no")
    )
    base = pid + ":" + sid
    kb = [
        [InlineKeyboardButton("Edit Label", callback_data="smsf:label:" + base)],
        [InlineKeyboardButton("Edit Title", callback_data="smsf:title:" + base)],
        [InlineKeyboardButton("Edit Unit", callback_data="smsf:unit:" + base)],
        [InlineKeyboardButton("Edit Price per 1k", callback_data="smsf:price_per_1k:" + base)],
        [InlineKeyboardButton("Edit Price Text", callback_data="smsf:price_text:" + base)],
        [InlineKeyboardButton("Edit Minimum (number)", callback_data="smsf:minimum:" + base)],
        [InlineKeyboardButton("Edit Minimum Text", callback_data="smsf:minimum_text:" + base)],
        [InlineKeyboardButton("Edit Quantity Prompt", callback_data="smsf:qty_prompt:" + base)],
        [InlineKeyboardButton("Edit Target Prompt", callback_data="smsf:target_prompt:" + base)],
        [InlineKeyboardButton("Toggle Target (account/post)", callback_data="smtt:" + base)],
        [InlineKeyboardButton("Toggle Private Check (auto-detect)", callback_data="smtp:" + base)],
        [InlineKeyboardButton("Toggle Always Remind (reliable)", callback_data="smtr:" + base)],
        [InlineKeyboardButton("Edit Private Reminder", callback_data="smsf:private_reminder:" + base)],
        [InlineKeyboardButton("Change Service Image", callback_data="smsi:image:" + base)],
        [InlineKeyboardButton("Change Quantity Image", callback_data="smsi:qty_image:" + base)],
        [InlineKeyboardButton("Change Target Image", callback_data="smsi:target_image:" + base)],
        [InlineKeyboardButton("Change Confirm Image", callback_data="smsi:confirm_image:" + base)],
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

    if data == "open:smm":
        text, kb, photo = _root_screen(user_id)
        if photo:
            await query.message.reply_photo(photo=photo, caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
        await query.answer()
        raise ApplicationHandlerStop

    if data == "smr":
        context.user_data.pop("smm_flow", None)
        text, kb, photo = _root_screen(user_id)
        await _render(query, context, text, kb, photo)
        await query.answer()
        raise ApplicationHandlerStop

    if data == "smx":
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smp:"):
        pid = data[4:]
        context.user_data.pop("smm_flow", None)
        res = _platform_screen(pid, user_id)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        text, kb, photo = res
        await _render(query, context, text, kb, photo)
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("sms:"):
        rest = data[4:]
        pid, sid = rest.split(":", 1)
        res = _service_screen(pid, sid)
        if not res:
            await query.answer("Not found", show_alert=True)
            raise ApplicationHandlerStop
        caption, kb, photo = res
        result_msg = await _render(query, context, caption, kb, photo)
        context.user_data.pop("state", None)
        context.user_data["smm_flow"] = {
            "step": "qty", "pid": pid, "sid": sid,
            "chat_id": result_msg.chat_id if result_msg else query.message.chat_id,
            "msg_id": result_msg.message_id if result_msg else query.message.message_id,
            "has_photo": bool(result_msg.photo) if result_msg else False,
        }
        await query.answer()
        raise ApplicationHandlerStop

    if user_id != ADMIN_ID:
        await query.answer("Not allowed", show_alert=True)
        raise ApplicationHandlerStop

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
        text, kb = res if res else (("MANAGE SERVICES" + NL + "(none)"),
                                    InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="smp:" + pid)]]))
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
        await _safe_edit(query, context, "Send the new value for " + field + hint + ":" + NL + "(or /start to cancel)")
        await query.answer()
        raise ApplicationHandlerStop

    if data.startswith("smsi:"):
        rest = data[5:]
        field, pid, sid = rest.split(":", 2)
        context.user_data["smm_flow"] = {"step": "edit_image", "field": field, "pid": pid, "sid": sid}
        await _safe_edit(query, context, "Send the new image for " + field + "." + NL
                         + "(send 0 to remove it, or /start to cancel)")
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

    if step == "qty":
        d = _load()
        s = _service(_platform(d, flow["pid"]), flow["sid"])
        if not s:
            context.user_data.pop("smm_flow", None)
            await update.message.reply_text("Sorry, that service is no longer available. Send /start.")
            raise ApplicationHandlerStop
        qty = _parse_int(text)
        if qty is None:
            await _delete_user_msg(update)
            raise ApplicationHandlerStop
        if qty < int(s.get("minimum", 0)):
            await _delete_user_msg(update)
            raise ApplicationHandlerStop
        await _delete_user_msg(update)
        flow["qty"] = qty
        flow["step"] = "target"
        s_copy = dict(s)
        s_copy["_pid"] = flow["pid"]
        caption, kb, photo = _target_screen(s_copy, qty)
        await _render_to(context, flow["chat_id"], flow["msg_id"], flow["has_photo"], caption, kb, photo)
        flow["has_photo"] = photo is not None
        context.user_data["smm_flow"] = flow
        raise ApplicationHandlerStop

    if step == "target":
        d = _load()
        s = _service(_platform(d, flow["pid"]), flow["sid"])
        if not s:
            context.user_data.pop("smm_flow", None)
            await update.message.reply_text("Sorry, that service is no longer available. Send /start.")
            raise ApplicationHandlerStop
        target_raw = text
        if not target_raw or " " in target_raw.strip():
            await _delete_user_msg(update)
            raise ApplicationHandlerStop
        await _delete_user_msg(update)

        qty = flow.get("qty", 0)
        chat_id, msg_id, had_photo = flow["chat_id"], flow["msg_id"], flow["has_photo"]
        confirm_caption = _confirm_caption(s, qty, target_raw)
        if s["target_type"] == "post":
            _ctgt = target_raw
        else:
            _ctgt = "@" + _extract_ig_username(target_raw)
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
        confirm_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Buy Now", callback_data="cart:buysmm")],
            [InlineKeyboardButton("Add to Cart", callback_data="cart:addsmm")],
            [InlineKeyboardButton("Back", callback_data="smp:" + flow["pid"])],
        ])
        confirm_photo = s.get("confirm_image") or s.get("image")

        do_check = (s["target_type"] == "account") and bool(s.get("private_check"))
        is_private = None
        if do_check:
            username = _extract_ig_username(target_raw)
            is_private = await _check_private(username)

        force_remind = (s["target_type"] == "account") and bool(s.get("always_remind"))
        show_reminder = (is_private is True) or force_remind

        context.user_data.pop("smm_flow", None)
        # keep cart_pending (pop only clears smm_flow above? no - re-set it)
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

        if show_reminder:
            reminder = "<b>" + html.escape(s.get("private_reminder", "")) + "</b>"
            r_photo = s.get("target_image")
            await _render_to(context, chat_id, msg_id, had_photo, reminder, None, r_photo)
            await asyncio.sleep(5)
            await _render_to(context, chat_id, msg_id, r_photo is not None,
                             confirm_caption, confirm_kb, confirm_photo)
        else:
            await _render_to(context, chat_id, msg_id, had_photo,
                             confirm_caption, confirm_kb, confirm_photo)
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
        flow["step"] = "add_svc_type"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Account (username)", callback_data="smtype:account")],
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
    acct_prompt = "Please Enter Your Instagram Profile Username or Link"
    post_prompt = "Please Enter Your Instagram Post Link"
    svc = {
        "id": uuid.uuid4().hex[:6],
        "label": draft["label"],
        "title": draft["title"],
        "unit": unit,
        "price_per_1k": price,
        "price_text": "Price : " + _fmt_money(price) + " Per 1,000 " + unit,
        "minimum": minimum,
        "minimum_text": "Minimum : " + str(minimum) + " " + unit,
        "qty_prompt": "Please Enter The Number Of " + unit + " You want",
        "qty_image": None,
        "target_type": choice,
        "target_prompt": acct_prompt if choice == "account" else post_prompt,
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

def setup(application, admin_id):
    global ADMIN_ID
    ADMIN_ID = admin_id
    application.add_handler(CallbackQueryHandler(_on_callback_with_type), group=-1)
    application.add_handler(MessageHandler(filters.PHOTO, _on_photo), group=-1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text), group=-1)
    n_keys = len([k for k in RAPIDAPI_KEYS if k])
    print("Social Media module loaded.")
    print("  RapidAPI keys:", n_keys, "| httpx:", HTTPX_AVAILABLE, "| instaloader fallback:", IG_AVAILABLE)
    print("  Private-check active:", _check_enabled())
