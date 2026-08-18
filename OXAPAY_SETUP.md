# OxaPay integration - what changed & how to go live

## What changed

- **`oxapay_client.py`** (new) - thin client for OxaPay's v1 Merchant API
  (White Label endpoint = per-order address, no redirect page).
- **`payments.py`** (rewritten) - same buyer/admin UI shell as before
  (animated-emoji picker, wallet, deposit flow, admin panel), but the
  payment engine underneath is now OxaPay instead of your own
  blockchain scanning code.
- **`cryptos.json`** (reset) - new schema, see below. Your old
  addresses are gone because OxaPay now issues a fresh address per
  order, so a fixed address per coin no longer means anything.
- **`orders.py`** - one label changed from "Transaction Hash" to
  "OxaPay Track ID" (that's what actually gets stored now).

### Gone for good (this was the whole point)
- Manually pasting the transaction hash after paying.
- The "2 people paying the same amount at once" collision logic
  (`_pending_key`, `used_hashes.json`, "please send the hash" prompts).
- All the direct Esplora/Solana RPC/Tronscan/BscScan calls and your
  hardcoded `BSCSCAN_API_KEY`.
- The buyer ever seeing oxapay.com. The "White Label" endpoint returns
  raw JSON (address, amount, memo, expiry) - your bot renders it in
  its own message, exactly like before.

## 1. Get a Merchant API key

1. Sign up / log in at oxapay.com.
2. Go to **Merchant Service** in the dashboard, fill in the form
   (underpaid coverage %, who pays the fee, etc.) and generate a
   **Merchant API key**.
3. Enable whichever coins/networks you want to accept there too -
   the bot's "Accepted Currencies" list on your dashboard is what OxaPay
   will actually let you invoice against.

## 2. Give the bot the key

Two options, pick one:

**Environment variable (recommended - keeps the key out of the JSON file
that lives on disk):**
```bash
export OXAPAY_MERCHANT_API_KEY="your_key_here"
```
Put that in whatever starts your bot (systemd unit's `Environment=`,
a `.env` loaded before `python3 bot.py`, etc.) on the VM.

**Or via Telegram, as admin:**
Send `/payments` to the bot → **🔑 Merchant API Key** → paste it.
(This writes it into `cryptos.json`. The env var always wins if both
are set.)

## 3. Add your coins

Send `/payments` → **➕ Add Crypto** → type a symbol OxaPay supports
(e.g. `BTC`, `USDT`, `LTC`, `SOL`, `TRX`). The bot fetches OxaPay's
*live* currency/network list (`GET /v1/common/currencies` - public,
no key needed) so you're never guessing at network names like
`TRC20` vs `BEP20` vs `BSC` - you tap the exact one OxaPay returns.
Give it a display name (e.g. `USDT (TRC20)`) and it's live immediately.

Repeat for each coin. Toggle on/off, set an animated emoji, or remove
from each coin's panel exactly like before.

## 4. How a payment now works

1. Buyer picks a coin → bot calls OxaPay's White Label endpoint with
   the USD amount → gets back a **fresh address + exact coin amount +
   expiry** for that order only.
2. Bot shows it in the same message style as before, timer included
   (default 60 minutes, matches what you asked for - configurable via
   `DEFAULT_LIFETIME_MINUTES` at the top of `payments.py`).
3. Every ~12 seconds the bot asks OxaPay "has track_id X been paid?"
   (`GET /v1/payment/{track_id}`) and updates the message once it's
   `paid` - no polling of blockchain explorers, no tx hash typed by
   the buyer, no shared address so no cross-buyer collisions.
4. If it expires, buyer sees the same "order expired" message as
   before.

This is **polling**, not a webhook - deliberately, since your VM is on
a free trial with (presumably) no public domain/TLS cert yet. It works
fine at your scale; the only cost is up to ~12s of detection lag vs an
instant webhook push. If you later put the bot behind a real domain
(Cloudflare Tunnel, a $5 VPS with a reverse proxy, etc.) I can wire up
`oxapay_client.verify_webhook_hmac()` to a real callback endpoint for
instant, push-based confirmation instead - the client function is
already there, just unused for now.

## 5. Admin extras

- **🔍 Lookup Payment (Track ID)** in `/payments` - paste any
  `track_id` and see OxaPay's raw status for support/debugging.
- Merchant key is shown masked (`****1234`) everywhere in the admin UI.

## Cleanup on your VM (optional)

These files/values are no longer read by anything and can be deleted
whenever convenient: `used_hashes.json`, the `BSCSCAN_API_KEY` string
that used to live in `payments.py`.
