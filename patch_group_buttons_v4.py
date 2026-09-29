"""
Sets the requested crypto button layout, regardless of which prior
version of _build_crypto_buttons_raw is currently on disk:
  - BTC: alone on its own row (full width)
  - USDT (TRC20) through USDC (SOL): packed 2-per-row (double width),
    in their existing/original order - no reordering.
  - LTC onward: unchanged, default 3-per-row packing (exactly as before).
"""
import re

with open("payments.py", "r", encoding="utf-8") as f:
    src = f.read()

if "tail_started" in src:
    print("Already patched (v4), nothing to do.")
    raise SystemExit(0)

pattern = re.compile(
    r"def _build_crypto_buttons_raw\(cryptos\):.*?\n(?=def _picker_screen_raw)",
    re.S,
)

if not pattern.search(src):
    print("ERROR: could not locate _build_crypto_buttons_raw / _picker_screen_raw boundary.")
    print("Paste the output of: grep -n 'def _build_crypto_buttons_raw\\|def _picker_screen_raw' payments.py")
    raise SystemExit(1)

new_func = '''def _build_crypto_buttons_raw(cryptos):
    # BTC gets its own full-width row; USDT (TRC20) through USDC (SOL)
    # pack 2-per-row (double width) in their existing order; everything
    # from LTC onward keeps the original default 3-per-row packing.
    rows = []
    current_row = []
    current_cap = None
    tail_started = False

    def flush():
        nonlocal current_row
        if current_row:
            rows.append(current_row)
            current_row = []

    for c in cryptos:
        currency = c.get("oxapay_currency", "")
        if not tail_started and currency == "LTC":
            tail_started = True
        if tail_started:
            cap = 3
        elif currency == "BTC":
            cap = 1
        else:
            cap = 2
        if cap != current_cap or len(current_row) >= cap:
            flush()
            current_cap = cap
        button = {"text": c["name"], "callback_data": "pay:pick:" + c["id"]}
        if c.get("emoji_id"):
            button["emoji_id"] = c["emoji_id"]
        current_row.append(button)
    flush()
    return rows

'''

src = pattern.sub(new_func, src, count=1)
with open("payments.py", "w", encoding="utf-8") as f:
    f.write(src)
print("Patched payments.py: BTC solo row, USDT-USDC block 2/row, LTC onward unchanged.")
