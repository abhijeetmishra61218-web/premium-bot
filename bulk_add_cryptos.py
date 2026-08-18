"""
One-time bulk crypto adder for premium-villa-bot.
Run with: venv/bin/python bulk_add_cryptos.py
"""

import asyncio
import json
import os
import uuid

import httpx

CRYPTOS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptos.json")
API_URL = "https://api.oxapay.com/v1/common/currencies"

REQUESTED = [
    "BTC", "ETH", "USDT", "USDC", "LTC", "SOL", "POL", "TRX", "XMR",
    "GRAM", "BNB", "DOGE", "NOT", "DOGS", "SHIB", "XRP",
]

ALIASES = {
    "POL": ["POL", "MATIC"],
    "GRAM": ["GRAM", "TON"],
}

NETWORK_SHORT = {
    "TRON": "TRX", "TRC20": "TRX",
    "ETHEREUM": "ETH", "ERC20": "ETH",
    "SOLANA": "SOL",
    "BSC": "BSC", "BEP20": "BSC", "BINANCE SMART CHAIN": "BSC",
    "POLYGON": "POL",
    "BITCOIN": "BTC",
    "LITECOIN": "LTC",
    "DOGECOIN": "DOGE",
    "TON": "TON",
    "XRP LEDGER": "XRP", "RIPPLE": "XRP",
    "MONERO": "XMR",
}


def short_label(net_key, net_info):
    raw = (net_info.get("name") or net_key or "").upper()
    return NETWORK_SHORT.get(raw, NETWORK_SHORT.get(net_key.upper(), net_key))


def new_id():
    return uuid.uuid4().hex[:8]


async def main():
    print("Fetching live currency list from OxaPay...")
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(API_URL)
    payload = resp.json()
    data = payload.get("data") or {}
    if not data:
        print("Got an empty/unexpected response from OxaPay:")
        print(json.dumps(payload, indent=2)[:1000])
        return

    with open(CRYPTOS_FILE, "r", encoding="utf-8") as f:
        store = json.load(f)
    store.setdefault("cryptos", [])
    existing = store["cryptos"]

    def already_have(symbol, network_key):
        for c in existing:
            if c.get("oxapay_currency", "").upper() == symbol.upper() and (
                c.get("oxapay_network") == network_key
            ):
                return True
        return False

    added, skipped, not_found = [], [], []

    for requested_symbol in REQUESTED:
        candidates = ALIASES.get(requested_symbol, [requested_symbol])
        match_key, match_info = None, None
        for cand in candidates:
            for k, v in data.items():
                if k.upper() == cand.upper() and v.get("status", True):
                    match_key, match_info = k, v
                    break
            if match_key:
                break

        if not match_key:
            not_found.append(requested_symbol)
            continue

        networks = match_info.get("networks") or {}
        if not networks:
            not_found.append(requested_symbol + " (no active networks)")
            continue

        if len(networks) == 1:
            net_key = next(iter(networks.keys()))
            if already_have(match_key, net_key):
                skipped.append(f"{match_key}")
                continue
            existing.append({
                "id": new_id(),
                "name": match_key,
                "enabled": True,
                "oxapay_currency": match_key,
                "oxapay_network": net_key,
                "emoji_id": None,
            })
            added.append(f"{match_key}")
        else:
            for net_key, net_info in networks.items():
                if already_have(match_key, net_key):
                    skipped.append(f"{match_key} ({short_label(net_key, net_info)})")
                    continue
                label = f"{match_key} ({short_label(net_key, net_info)})"
                existing.append({
                    "id": new_id(),
                    "name": label,
                    "enabled": True,
                    "oxapay_currency": match_key,
                    "oxapay_network": net_key,
                    "emoji_id": None,
                })
                added.append(label)

    with open(CRYPTOS_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)

    print()
    print(f"Added {len(added)}:")
    for a in added:
        print("  +", a)
    if skipped:
        print(f"\nSkipped {len(skipped)} (already present):")
        for s in skipped:
            print("  =", s)
    if not_found:
        print(f"\nNot found on OxaPay {len(not_found)}:")
        for n in not_found:
            print("  ?", n)
    print("\nDone. Restart the bot to pick up the changes.")


if __name__ == "__main__":
    asyncio.run(main())
