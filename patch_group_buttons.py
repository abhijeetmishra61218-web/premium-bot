"""
Groups the crypto picker buttons by coin family (all USDT chains together,
all ETH chains together, all USDC chains together, SOL together, BTC
first), and gives buttons that show a chain/network in their name
(e.g. "USDT (TRC20)") 2-per-row instead of 3-per-row, so they render
noticeably wider ("double size"). Plain single-chain coins (BTC, LTC,
TRX, XMR, GRAM, BNB, DOGE, DOGS, native SOL) keep the original
3-per-row layout.
"""

with open("payments.py", "r", encoding="utf-8") as f:
    src = f.read()

marker = "def _build_crypto_buttons_raw(cryptos):\n    PRIORITY ="
if marker in src:
    print("Already patched, nothing to do.")
    raise SystemExit(0)

old = '''def _build_crypto_buttons_raw(cryptos):
    rows = []
    current_row = []
    for c in cryptos:
        button = {"text": c["name"], "callback_data": "pay:pick:" + c["id"]}
        if c.get("emoji_id"):
            button["emoji_id"] = c["emoji_id"]
        current_row.append(button)
        if len(current_row) >= 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    return rows'''

new = '''def _build_crypto_buttons_raw(cryptos):
    # Group same-coin chain variants together (all USDT chains together,
    # all ETH chains together, all USDC chains together, SOL together),
    # BTC first, everything else keeps its existing relative order after.
    PRIORITY = {"BTC": 0, "USDT": 1, "ETH": 2, "USDC": 3, "SOL": 4}
    ordered = sorted(cryptos, key=lambda c: PRIORITY.get(c.get("oxapay_currency", ""), 5))

    rows = []
    current_row = []
    current_group = None

    def flush():
        nonlocal current_row
        if current_row:
            rows.append(current_row)
            current_row = []

    for c in ordered:
        group = c.get("oxapay_currency", "")
        has_chain = "(" in c.get("name", "")
        cap = 2 if has_chain else 3  # chain-labeled buttons get double-size (2/row)
        if group != current_group:
            flush()
            current_group = group
        elif len(current_row) >= cap:
            flush()
        button = {"text": c["name"], "callback_data": "pay:pick:" + c["id"]}
        if c.get("emoji_id"):
            button["emoji_id"] = c["emoji_id"]
        current_row.append(button)
    flush()
    return rows'''

if old not in src:
    print("ERROR: could not find the expected original function. No changes made.")
    raise SystemExit(1)

src = src.replace(old, new)
with open("payments.py", "w", encoding="utf-8") as f:
    f.write(src)
print("Patched payments.py: crypto buttons now grouped by coin family, chain-labeled buttons are double-size.")
