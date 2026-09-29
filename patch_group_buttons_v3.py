"""
Sets the exact crypto button layout requested:

  BTC
  SOL | LTC | POL
  USDT (TRC20) | USDT (BSC)
  USDT (ETH)   | USDT (SOL)
  ETH (ETH)    | USDC (ETH)
  USDC (BSC)   | USDC (SOL)
  TRX | XMR | GRAM
  BNB | DOGE | DOGS
  SHIB (ETH)   | SHIB (BSC)

Uses an explicit group order (rather than automatic sorting) so the
layout is exact and stable. Any future coin not covered by
GROUP_ORDER is appended at the end automatically (not dropped).
"""

with open("payments.py", "r", encoding="utf-8") as f:
    src = f.read()

marker_fixed = "GROUP_ORDER = ["
if marker_fixed in src:
    print("Already patched (v3), nothing to do.")
    raise SystemExit(0)

old = '''def _build_crypto_buttons_raw(cryptos):
    # Group same-coin chain variants together (all USDT chains together,
    # all ETH chains together, all USDC chains together, SOL together),
    # BTC first, everything else keeps its existing relative order after.
    PRIORITY = {"BTC": 0, "USDT": 1, "ETH": 2, "USDC": 3, "SOL": 4}
    ordered = sorted(cryptos, key=lambda c: PRIORITY.get(c.get("oxapay_currency", ""), 5))

    rows = []
    current_row = []
    current_cap = None  # 2 = big/chain-labeled row, 3 = small/plain row

    def flush():
        nonlocal current_row
        if current_row:
            rows.append(current_row)
            current_row = []

    for c in ordered:
        has_chain = "(" in c.get("name", "")
        cap = 2 if has_chain else 3  # chain-labeled buttons get double-size (2/row)
        if cap != current_cap or len(current_row) >= cap:
            flush()
            current_cap = cap
        button = {"text": c["name"], "callback_data": "pay:pick:" + c["id"]}
        if c.get("emoji_id"):
            button["emoji_id"] = c["emoji_id"]
        current_row.append(button)
    flush()
    return rows'''

new = '''def _build_crypto_buttons_raw(cryptos):
    # Explicit row grouping per admin's exact requested layout:
    #   BTC
    #   SOL | LTC | POL
    #   USDT chains (2/row)
    #   ETH + USDC chains (2/row)
    #   TRX | XMR | GRAM / BNB | DOGE | DOGS
    #   SHIB chains (2/row)
    GROUP_ORDER = [
        ["BTC"],
        ["SOL", "LTC", "POL"],
        ["USDT"],
        ["ETH", "USDC"],
        ["TRX", "XMR", "GRAM", "BNB", "DOGE", "DOGS"],
        ["SHIB"],
    ]

    rows = []
    used_ids = set()

    def pack(items):
        row = []
        cap = None
        for c in items:
            has_chain = "(" in c.get("name", "")
            item_cap = 2 if has_chain else 3  # chain-labeled = 2/row (double size), plain = 3/row
            if cap is None:
                cap = item_cap
            if item_cap != cap or len(row) >= cap:
                if row:
                    rows.append(row)
                row = []
                cap = item_cap
            button = {"text": c["name"], "callback_data": "pay:pick:" + c["id"]}
            if c.get("emoji_id"):
                button["emoji_id"] = c["emoji_id"]
            row.append(button)
        if row:
            rows.append(row)

    for group_syms in GROUP_ORDER:
        group_items = [c for c in cryptos if c.get("oxapay_currency", "") in group_syms]
        group_items.sort(key=lambda c: group_syms.index(c.get("oxapay_currency", "")))
        for c in group_items:
            used_ids.add(c.get("id"))
        pack(group_items)

    # Any coin not covered by GROUP_ORDER (e.g. newly added) keeps original order at the end.
    leftover = [c for c in cryptos if c.get("id") not in used_ids]
    if leftover:
        pack(leftover)

    return rows'''

if old not in src:
    print("ERROR: could not find the expected (v2) function. No changes made.")
    print("If patch_group_buttons_v2.py was never applied, run that one first.")
    raise SystemExit(1)

src = src.replace(old, new)
with open("payments.py", "w", encoding="utf-8") as f:
    f.write(src)
print("Patched payments.py: exact requested layout is now live.")
