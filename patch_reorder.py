with open("payments.py", "r", encoding="utf-8") as f:
    src = f.read()

old_helper = '''def _save_crypto(updated):
    data = load_cryptos()
    for i, c in enumerate(data["cryptos"]):
        if c["id"] == updated["id"]:
            data["cryptos"][i] = updated
            break
    save_cryptos(data)'''
new_helper = '''def _save_crypto(updated):
    data = load_cryptos()
    for i, c in enumerate(data["cryptos"]):
        if c["id"] == updated["id"]:
            data["cryptos"][i] = updated
            break
    save_cryptos(data)

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
    return True'''
assert old_helper in src, "anchor 1 (_save_crypto) not found - aborting, NO changes made"
src = src.replace(old_helper, new_helper, 1)

old_kb = '''    toggle = "Disable" if c.get("enabled") else "Enable"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Set Animated Emoji", callback_data="pay:emoji:" + cid)],
        [InlineKeyboardButton("🔘 " + toggle, callback_data="pay:tgl:" + cid)],
        [InlineKeyboardButton("🗑️ Remove", callback_data="pay:rm:" + cid)],
        [InlineKeyboardButton("🔙 Back", callback_data="pay:admin")],
    ])'''
new_kb = '''    toggle = "Disable" if c.get("enabled") else "Enable"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Set Animated Emoji", callback_data="pay:emoji:" + cid)],
        [InlineKeyboardButton("⬆️ Move Up", callback_data="pay:up:" + cid),
         InlineKeyboardButton("⬇️ Move Down", callback_data="pay:dn:" + cid)],
        [InlineKeyboardButton("🔘 " + toggle, callback_data="pay:tgl:" + cid)],
        [InlineKeyboardButton("🗑️ Remove", callback_data="pay:rm:" + cid)],
        [InlineKeyboardButton("🔙 Back", callback_data="pay:admin")],
    ])'''
assert old_kb in src, "anchor 2 (crypto_panel keyboard) not found - aborting, NO changes made"
src = src.replace(old_kb, new_kb, 1)

old_handler = '''    if action.startswith("tgl:"):'''
new_handler = '''    if action.startswith("up:") or action.startswith("dn:"):
        direction = -1 if action.startswith("up:") else 1
        cid = action.split(":", 1)[1]
        moved = _move_crypto(cid, direction)
        res = crypto_panel(cid)
        if res:
            text, kb = res
            await _safe_edit(query, context, text, kb)
        await query.answer("Moved" if moved else "Already at that end")
        raise ApplicationHandlerStop

    if action.startswith("tgl:"):'''
assert src.count(old_handler) == 1, "anchor 3 (tgl handler) not found or not unique - aborting, NO changes made"
src = src.replace(old_handler, new_handler, 1)

with open("payments.py", "w", encoding="utf-8") as f:
    f.write(src)

print("payments.py patched OK: Move Up / Move Down added to crypto admin panel")
