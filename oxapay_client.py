"""
Premium Villa - OxaPay merchant API client (oxapay_client.py)

Thin async wrapper around OxaPay's v1 Merchant API. Uses the "White Label"
endpoint so we get back a raw address/amount/expiry for THIS order only -
no redirect to oxapay.com, everything stays inside the bot.

Docs: https://docs.oxapay.com/api-reference/payment/generate-white-label
      https://docs.oxapay.com/api-reference/payment/payment-information
      https://docs.oxapay.com/api-reference/common/supported-currencies
"""

import hashlib
import hmac
import json
import os
import time

import httpx

API_BASE = "https://api.oxapay.com/v1"

# You can set the key via environment variable (preferred, keeps it out of
# the JSON file) or it will fall back to whatever is saved in cryptos.json
# through the admin panel (see payments.py: get_merchant_key/set_merchant_key).
ENV_KEY_NAME = "OXAPAY_MERCHANT_API_KEY"

DEFAULT_TIMEOUT = 20.0


class OxaPayError(Exception):
    def __init__(self, message, status=None, raw=None):
        super().__init__(message)
        self.status = status
        self.raw = raw


def get_env_key():
    return os.environ.get(ENV_KEY_NAME) or None


async def _request(method, path, merchant_key, json_body=None, params=None):
    if not merchant_key:
        raise OxaPayError("No OxaPay merchant API key configured.")
    url = API_BASE + path
    headers = {
        "merchant_api_key": merchant_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.request(method, url, headers=headers, json=json_body, params=params)
    try:
        data = resp.json()
    except Exception:
        raise OxaPayError(f"Non-JSON response (HTTP {resp.status_code})", status=resp.status_code)

    # OxaPay wraps everything in {"data": ..., "message": ..., "error": ..., "status": ...}
    status = data.get("status", resp.status_code)
    if resp.status_code >= 400 or (isinstance(status, int) and status >= 400):
        err = data.get("error") or {}
        msg = err.get("message") or data.get("message") or f"OxaPay error (HTTP {resp.status_code})"
        raise OxaPayError(msg, status=status, raw=data)
    return data.get("data") or {}


async def create_white_label(merchant_key, amount_usd, pay_currency, network=None,
                              order_id=None, lifetime_minutes=60, description=None,
                              callback_url=None, under_paid_coverage=None):
    """
    Create a one-time payment address for a single order.
    amount_usd is charged in USD (currency field omitted -> amount is USD).
    pay_currency is the coin the buyer will actually send (e.g. "BTC", "USDT").
    network is the OxaPay network key for that coin (e.g. "TRC20", "Bitcoin") -
    get valid values from get_supported_currencies().
    Returns dict with: track_id, address, memo, pay_amount, pay_currency,
    network, expired_at (unix ts), qr_code, rate, ...
    """
    body = {
        "amount": float(amount_usd),
        "pay_currency": pay_currency,
        "lifetime": max(15, min(2880, int(lifetime_minutes))),
    }
    if network:
        body["network"] = network
    if order_id:
        body["order_id"] = str(order_id)[:100]
    if description:
        body["description"] = str(description)[:250]
    if callback_url:
        body["callback_url"] = callback_url
    if under_paid_coverage is not None:
        body["under_paid_coverage"] = under_paid_coverage
    return await _request("POST", "/payment/white-label", merchant_key, json_body=body)


async def get_payment(merchant_key, track_id):
    """Poll the status of a payment created via create_white_label (or invoice)."""
    return await _request("GET", f"/payment/{track_id}", merchant_key)


async def get_accepted_currencies(merchant_key):
    """Currencies this merchant account has enabled on the OxaPay dashboard."""
    data = await _request("GET", "/payment/accepted-currencies", merchant_key)
    return data.get("list") or []


async def get_supported_currencies():
    """
    Full public catalogue of coins + valid network keys. No auth required.
    Returns: {"BTC": {"symbol": "BTC", "name": "Bitcoin", "status": true,
                        "networks": {"Bitcoin": {"network": "Bitcoin", ...}}}, ...}
    """
    url = API_BASE + "/common/currencies"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(url)
    data = resp.json()
    return (data.get("data") or {})


def verify_webhook_hmac(raw_body: bytes, hmac_header: str, secret: str) -> bool:
    """
    OxaPay signs webhook bodies with HMAC-SHA512 using your merchant API key
    as the secret. Only relevant if you later expose a public callback_url -
    the bot's default flow uses polling instead, so this isn't required.
    """
    if not hmac_header or not secret:
        return False
    calculated = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(calculated, hmac_header)
