"""
Adds real error visibility to payments.py's raw Telegram API calls.
"""

with open("payments.py", "r", encoding="utf-8") as f:
    src = f.read()

marker = "class TelegramRawError(Exception):"
if marker in src:
    print("Already patched, nothing to do.")
    raise SystemExit(0)

old = '''async def raw_send_message(chat_id, text, keyboard_rows, photo=None, parse_mode="HTML"):
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
        return r.json()
    payload = {
        "chat_id": chat_id, "text": text, "parse_mode": parse_mode,
        "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{TG_API}/sendMessage", json=payload)
    return r.json()

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
        return r.json()
    payload = {
        "chat_id": chat_id, "message_id": message_id, "text": text,
        "parse_mode": parse_mode, "reply_markup": _build_raw_keyboard(keyboard_rows),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{TG_API}/editMessageText", json=payload)
    return r.json()'''

new = '''class TelegramRawError(Exception):
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
    return _raw_check(r.json(), "editMessageText")'''

if old not in src:
    print("ERROR: could not find the expected original code block. No changes made.")
    raise SystemExit(1)

src = src.replace(old, new)
with open("payments.py", "w", encoding="utf-8") as f:
    f.write(src)
print("Patched payments.py successfully. Restart the bot to pick it up.")
