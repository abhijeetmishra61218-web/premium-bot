"""
Root cause fix: cryptos.json had plain emoji characters (🪙, 🐶) stored
in emoji_id instead of numeric custom-emoji IDs. Telegram's API rejects
that with "must be a valid Number", crashing every screen with a crypto
button. This clears the bad values and makes the keyboard builder skip
non-numeric emoji_id values instead of crashing.
"""
import json

with open("cryptos.json", "r", encoding="utf-8") as f:
    data = json.load(f)

cleared = []
for c in data.get("cryptos", []):
    eid = c.get("emoji_id")
    if eid and not str(eid).isdigit():
        cleared.append((c.get("name"), eid))
        c["emoji_id"] = None

if cleared:
    with open("cryptos.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Cleared {len(cleared)} bad emoji_id value(s) from cryptos.json:")
    for name, eid in cleared:
        print(f"  - {name}: {eid!r} -> None")
else:
    print("No bad emoji_id values found in cryptos.json.")

with open("payments.py", "r", encoding="utf-8") as f:
    src = f.read()

old_p = '''            if btn.get("emoji_id"):
                raw_btn["icon_custom_emoji_id"] = btn["emoji_id"]'''
new_p = '''            eid = btn.get("emoji_id")
            if eid and str(eid).isdigit():
                raw_btn["icon_custom_emoji_id"] = eid'''

if new_p in src:
    print("payments.py already patched.")
elif old_p not in src:
    print("ERROR: payments.py marker not found, no changes made there.")
else:
    src = src.replace(old_p, new_p)
    with open("payments.py", "w", encoding="utf-8") as f:
        f.write(src)
    print("Patched payments.py (defensive emoji_id check).")

with open("bot.py", "r", encoding="utf-8") as f:
    src = f.read()

old_b = '''            if btn.get("emoji_id"):
                raw_btn["icon_custom_emoji_id"] = btn["emoji_id"]'''
new_b = '''            eid = btn.get("emoji_id")
            if eid and str(eid).isdigit():
                raw_btn["icon_custom_emoji_id"] = eid'''

if new_b in src:
    print("bot.py already patched.")
elif old_b not in src:
    print("ERROR: bot.py marker not found, no changes made there.")
else:
    src = src.replace(old_b, new_b)
    with open("bot.py", "w", encoding="utf-8") as f:
        f.write(src)
    print("Patched bot.py (defensive emoji_id check).")

print("Done. Restart the bot now.")
