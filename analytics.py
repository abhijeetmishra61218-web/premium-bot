"""
Premium Villa - sales analytics (analytics.py)

Keeps a 10-day log of what customers do (opened a product / plan, added to cart, reached the
payment page, picked a crypto, paid, let it expire, cancelled) and gives the admin reports so
prices can be judged:

    /aall [days]              everything, per product: who (username), date and time, what they did
    /a<productname> [days]    only that product, e.g. /aspotify or /aytpremium (name without spaces; the
                              first letters are enough). Shows who, date, time and what they did
    /funnel [days]            per product and plan: clicks -> cart -> payment page -> paid, sell rate, names
    /paypage [days]           everybody who reached the payment page and whether they paid
    /clicks [days]            full click log as a CSV file;  /clicks @user  = one customer's timeline
    /anotify                  turn the "new payment page opened" alert to you on/off
    /trackme                  turn tracking of your own (admin) clicks on/off - handy for testing

You also get a live alert whenever a customer opens a payment page; the same message is updated as they
pick a crypto and then pay, let it expire or cancel.

Wire into bot.py with:  import analytics  and  analytics.setup(app, ADMIN_ID)
Everything older than RETAIN_DAYS is deleted automatically. The admin's own clicks are ignored by default.
"""

import csv
import html
import io
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

from telegram.ext import CommandHandler, MessageHandler, filters

import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(BASE_DIR, "analytics_events.jsonl")
SETTINGS = os.path.join(BASE_DIR, "analytics_settings.json")
RETAIN_DAYS = 30
IST = timezone(timedelta(hours=5, minutes=30))
GROUP = -4
ADMIN_ID = 0
NL = "\n"

_last_prune = 0.0


# ============================== storage ==============================
def _settings():
    try:
        with open(SETTINGS, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_settings(d):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except Exception:
        pass


def _prune(force=False):
    global _last_prune
    now = time.time()
    if not force and now - _last_prune < 3600:
        return
    _last_prune = now
    cutoff = now - RETAIN_DAYS * 86400
    try:
        if not os.path.exists(FILE):
            return
        kept = []
        with open(FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    if json.loads(line).get("ts", 0) >= cutoff:
                        kept.append(line if line.endswith("\n") else line + "\n")
                except Exception:
                    continue
        tmp = FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(kept)
        os.replace(tmp, FILE)
    except Exception as e:
        print(f"[analytics] prune failed: {e}")


def track(uid, ev, **kw):
    """Record one event. Never raises - analytics must not be able to break the shop."""
    try:
        uid = int(uid)
        if uid == ADMIN_ID and not _settings().get("track_admin"):
            return
        rec = {"ts": round(time.time(), 1), "uid": uid, "ev": ev}
        for k, v in kw.items():
            if v is not None:
                rec[k] = v
        with open(FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _prune()
    except Exception as e:
        print(f"[analytics] could not record {ev}: {e}")


def load_events(days=RETAIN_DAYS):
    cutoff = time.time() - min(max(1, int(days)), RETAIN_DAYS) * 86400
    out = []
    try:
        with open(FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("ts", 0) >= cutoff:
                    out.append(r)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[analytics] read failed: {e}")
    return out


# ============================== helpers used by the hooks ==============================
def item_key(item):
    """(product name, plan name) of a cart item - social media services use their title."""
    if item.get("kind") == "smm":
        return (item.get("title") or item.get("product") or "Service", "")
    return (item.get("product") or item.get("title") or "Product", item.get("plan") or "")


def _line_price(item):
    try:
        import cart
        return round(float(cart._line_total(item)), 2)
    except Exception:
        return None


def track_cart_add(uid, item):
    p, pl = item_key(item)
    track(uid, "cart", product=p, plan=pl, price=_line_price(item), qty=item.get("qty"))


def track_pay_page(uid, aid, items, total, source):
    for it in items:
        p, pl = item_key(it)
        track(uid, "pay", aid=aid, product=p, plan=pl, price=_line_price(it), qty=it.get("qty"),
              total=round(float(total), 2), source=source)


# ============================== report helpers ==============================
def _name(uid, users):
    u = users.get(str(uid), {})
    un = (u.get("username") or "").strip()
    fn = (u.get("first_name") or "").strip()
    if un:
        return "@" + un
    return fn or ("id " + str(uid))


def _when(ts):
    return datetime.fromtimestamp(ts, IST).strftime("%d %b %H:%M")


def _money(v):
    try:
        v = float(v)
    except Exception:
        return str(v)
    return "$" + (str(int(v)) if abs(v - round(v)) < 0.005 else "%.2f" % v)


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _people(uids, users, limit=25):
    """Tappable names (opens the customer's chat): 'Jo, @kay, Sam' ... '+3 more'."""
    uids = sorted(uids)
    shown = [('<a href="tg://user?id=%d">%s</a>' % (u, _esc(_name(u, users)))) for u in uids[:limit]]
    more = len(uids) - limit
    return ", ".join(shown) + ((" +" + str(more) + " more") if more > 0 else "")


def _chunks(blocks, limit=3800):
    out, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 1 > limit:
            out.append(cur)
            cur = ""
        cur += (NL if cur else "") + b
    if cur:
        out.append(cur)
    return out


def _parse_days(tokens):
    days = RETAIN_DAYS
    rest = []
    for t in tokens:
        if t.isdigit() and 1 <= int(t) <= RETAIN_DAYS:
            days = int(t)
        else:
            rest.append(t)
    return days, rest


def _attempts(events):
    """Group payment-page visits by attempt id: {aid: {...}} with outcome."""
    att = {}
    for r in events:
        aid = r.get("aid")
        if not aid:
            continue
        a = att.setdefault(aid, {"aid": aid, "uid": r["uid"], "ts": r["ts"], "items": [], "total": 0,
                                 "crypto": None, "outcome": "none", "order_id": None, "source": None})
        ev = r["ev"]
        if ev == "pay":
            a["items"].append(r)
            a["ts"] = min(a["ts"], r["ts"])
            a["total"] = r.get("total", a["total"])
            a["source"] = r.get("source")
        elif ev == "crypto":
            a["crypto"] = r.get("crypto")
        elif ev == "paid":
            a["outcome"] = "paid"
            a["order_id"] = r.get("order_id")
            a["method"] = r.get("method")
        elif ev == "expired" and a["outcome"] != "paid":
            a["outcome"] = "expired"
        elif ev == "cancel" and a["outcome"] != "paid":
            a["outcome"] = "cancel"
    return {k: v for k, v in att.items() if v["items"] or v["outcome"] == "paid"}


OUTCOME = {"paid": "✅ PAID", "expired": "⌛ Expired (didn't pay)", "cancel": "✖ Cancelled",
           "none": "⏳ Left without paying"}


# ============================== /funnel ==============================
def funnel_text(days):
    ev = load_events(days)
    if not ev:
        return ["No activity recorded yet. The log starts from the moment this update went live."]
    att = _attempts(ev)
    paid_aids = {a["aid"] for a in att.values() if a["outcome"] == "paid"}
    users = store.load_users()

    stats = {}          # (product, plan) -> dict
    prod_views = {}     # product -> [clicks, set(users)]

    def S(key):
        return stats.setdefault(key, {"views": 0, "vu": set(), "cart": 0, "pay": 0, "pu": set(),
                                      "paid": 0, "paidu": set(), "price": None})

    people_any, people_pay, people_paid = set(), set(), set()
    revenue = 0.0
    for r in ev:
        e, uid = r["ev"], r["uid"]
        people_any.add(uid)
        if e == "view":
            pv = prod_views.setdefault(r.get("product", "?"), [0, set()])
            pv[0] += 1
            pv[1].add(uid)
        elif e in ("plan", "svc"):
            s = S((r.get("product", "?"), r.get("plan", "") if e == "plan" else ""))
            s["views"] += 1
            s["vu"].add(uid)
            if r.get("price") not in (None, ""):
                s["price"] = r.get("price")
        elif e == "cart":
            s = S((r.get("product", "?"), r.get("plan", "")))
            s["cart"] += 1
            if s["price"] is None and r.get("qty", 1) == 1:
                s["price"] = r.get("price")
        elif e == "pay":
            s = S((r.get("product", "?"), r.get("plan", "")))
            s["pay"] += 1
            s["pu"].add(uid)
            people_pay.add(uid)
            if r.get("aid") in paid_aids:
                s["paid"] += 1
                s["paidu"].add(uid)
        elif e == "paid":
            people_paid.add(uid)
            revenue += float(r.get("total") or 0)

    total_att = len(att)
    paid_att = len(paid_aids)
    head = ["<b>SALES FUNNEL - last " + str(days) + " day" + ("s" if days != 1 else "") + "</b>", "",
            "People who opened something: <b>" + str(len(people_any)) + "</b>",
            "Reached the payment page: <b>" + str(len(people_pay)) + "</b> (" + str(total_att) + " visits)",
            "Paid: <b>" + str(len(people_paid)) + "</b> people, " + str(paid_att) + " orders, " + _money(revenue),
            "Payment-page visits that did not pay: <b>" + str(total_att - paid_att) + "</b>"]
    if len(people_any):
        head.append("Overall sell rate: <b>%.0f%%</b> of visitors paid" % (100.0 * len(people_paid) / len(people_any)))
    head += ["", "Read each line as:  clicks (people) → cart → payment page → paid, then paid ÷ people", ""]

    groups = {}
    for (p, pl), s in stats.items():
        groups.setdefault(p, []).append((pl, s))
    for p in prod_views:
        groups.setdefault(p, [])

    def weight(p):
        return -(sum(s["views"] for _, s in groups[p]) + prod_views.get(p, [0])[0])

    blocks = ["\n".join(head)]
    for p in sorted(groups, key=weight):
        pvw = prod_views.get(p)
        title = "<b>" + _esc(p) + "</b>"
        if pvw:
            title += "  (page: " + str(pvw[0]) + " clicks, " + str(len(pvw[1])) + " people)"
        lines = [title]
        for pl, s in sorted(groups[p], key=lambda x: -x[1]["views"]):
            label = _esc(pl) if pl else "service"
            if s["price"] not in (None, ""):
                label += " (" + (_money(s["price"]) if not isinstance(s["price"], str) else _esc(s["price"])) + ")"
            ppl = len(s["vu"])
            rate = ("%.0f%%" % (100.0 * len(s["paidu"]) / ppl)) if ppl else "-"
            line = ("  • " + label + ": " + str(s["views"]) + " (" + str(ppl) + ") → 🛒 " + str(s["cart"])
                    + " → 💳 " + str(s["pay"]) + " → ✅ " + str(s["paid"]) + "  =  <b>" + rate + "</b>")
            if s["pay"] >= 3 and s["paid"] == 0:
                line += "  ⚠ reached payment, nobody paid"
            elif ppl >= 8 and s["paid"] == 0:
                line += "  ⚠ many clicks, no sales"
            lines.append(line)
            if s["vu"]:
                lines.append("      👁 clicked: " + _people(s["vu"], users))
            nopay = s["pu"] - s["paidu"]
            if nopay:
                lines.append("      💳 reached payment, didn't pay: " + _people(nopay, users))
            if s["paidu"]:
                lines.append("      ✅ paid: " + _people(s["paidu"], users))
        blocks.append("\n".join(lines))
    blocks.append("<i>Tip: a plan with many clicks but few payments is usually priced too high, or its page "
                  "isn't convincing. A plan where people reach payment but don't pay may be too expensive "
                  "once they see the crypto amount.</i>")
    return _chunks(blocks)


# ============================== /paypage ==============================
def paypage_text(days):
    ev = load_events(days)
    att = sorted(_attempts(ev).values(), key=lambda a: -a["ts"])
    if not att:
        return ["Nobody reached the payment page in the last " + str(days) + " day(s)."]
    users = store.load_users()
    paid = sum(1 for a in att if a["outcome"] == "paid")
    uniq = len({a["uid"] for a in att})
    head = ("<b>PAYMENT PAGE - last " + str(days) + " day" + ("s" if days != 1 else "") + "</b>" + NL + NL
            + "Visits: <b>" + str(len(att)) + "</b> by " + str(uniq) + " people" + NL
            + "Paid: <b>" + str(paid) + "</b>   Did not pay: <b>" + str(len(att) - paid) + "</b>")
    blocks = [head]
    for a in att[:80]:
        items = "; ".join(_esc(i.get("product", "?")) + (" - " + _esc(i["plan"]) if i.get("plan") else "")
                          for i in a["items"]) or "(order)"
        line = ("<b>" + _when(a["ts"]) + "</b> · " + _esc(_name(a["uid"], users)) + " <code>" + str(a["uid"]) + "</code>" + NL
                + "  " + items + NL
                + "  " + _money(a["total"]) + " · " + _esc(a["crypto"] or "no crypto picked") + " · " + OUTCOME[a["outcome"]])
        blocks.append(line)
    if len(att) > 80:
        blocks.append("<i>Showing the latest 80. Use /clicks for the full log.</i>")
    return _chunks(blocks)


# ============================== /clicks ==============================
EV_NAME = {"view": "Opened product", "plan": "Opened plan", "svc": "Opened social media service",
           "cart": "Added to cart", "pay": "Reached payment page", "crypto": "Picked crypto",
           "paid": "PAID", "expired": "Payment expired", "cancel": "Cancelled payment"}


def _resolve_user(token):
    t = token.strip()
    if t.startswith("@"):
        uid = store.get_uid_by_username(t)
        return uid
    if t.isdigit() and len(t) > 5:
        return int(t)
    return None


def timeline_text(uid, days):
    ev = [r for r in load_events(days) if r["uid"] == uid]
    users = store.load_users()
    if not ev:
        return ["No activity for that customer in the last " + str(days) + " day(s)."]
    lines = ["<b>" + _esc(_name(uid, users)) + "</b> <code>" + str(uid) + "</code> - last " + str(days) + " day(s)"]
    for r in sorted(ev, key=lambda x: x["ts"]):
        what = EV_NAME.get(r["ev"], r["ev"])
        detail = _esc(r.get("product", ""))
        if r.get("plan"):
            detail += " - " + _esc(r["plan"])
        if r["ev"] == "crypto":
            detail = _esc(r.get("crypto", ""))
        if r["ev"] in ("pay", "paid") and r.get("total") is not None:
            detail += " (" + _money(r["total"]) + ")"
        lines.append(_when(r["ts"]) + "  " + what + ("  " + detail if detail else ""))
    return _chunks(["\n".join(lines)])


def csv_bytes(days):
    ev = sorted(load_events(days), key=lambda r: r["ts"])
    users = store.load_users()
    att = _attempts(ev)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time (IST)", "user id", "username", "first name", "event", "product", "plan", "price",
                "qty", "crypto", "payment attempt", "attempt outcome", "order id", "order total", "source"])
    for r in ev:
        u = users.get(str(r["uid"]), {})
        a = att.get(r.get("aid"))
        w.writerow([datetime.fromtimestamp(r["ts"], IST).strftime("%Y-%m-%d %H:%M:%S"), r["uid"],
                    u.get("username", ""), u.get("first_name", ""), EV_NAME.get(r["ev"], r["ev"]),
                    r.get("product", ""), r.get("plan", ""), r.get("price", ""), r.get("qty", ""),
                    r.get("crypto", ""), r.get("aid", ""), OUTCOME[a["outcome"]] if a else "",
                    r.get("order_id", ""), r.get("total", ""), r.get("source", "")])
    return buf.getvalue().encode("utf-8-sig")


# ============================== owner alerts ==============================
_NOTES = {}        # attempt id -> {"msg_id": int, "data": {...}}


def _note_text(d):
    status = d.get("status", "🟡 Looking at the payment page")
    lines = ["🔔 <b>New payment page opened</b>", "",
             "<b>Product:</b> " + d.get("items", "?"),
             "<b>Amount:</b> " + _money(d.get("total", 0)),
             "<b>Buyer:</b> " + d.get("buyer", "?"),
             "<b>Crypto:</b> " + d.get("crypto", "not chosen yet"),
             "<b>Status:</b> " + status,
             "<b>Opened:</b> " + d.get("opened", "")]
    if d.get("order_id"):
        lines.append("<b>Order ID:</b> <code>" + _esc(d["order_id"]) + "</code>")
    return NL.join(lines)


async def notify(bot, aid, uid, stage, items=None, total=None, source=None, crypto=None,
                 crypto_amount=None, order_id=None):
    """Alert the owner about a payment page. One message per visit, edited as the visit progresses."""
    try:
        if not ADMIN_ID or not aid:
            return
        st = _settings()
        if st.get("notify") is False:
            return
        if int(uid) == ADMIN_ID and not st.get("track_admin"):
            return
        note = _NOTES.setdefault(aid, {"msg_id": None, "data": {}})
        d = note["data"]
        if stage == "open":
            users = store.load_users()
            parts = []
            for it in (items or []):
                p, pl = item_key(it)
                q = it.get("qty", 1)
                parts.append(_esc(p) + ((" - " + _esc(pl)) if pl else "")
                             + ((" x" + str(q)) if q and int(q) > 1 and it.get("kind") != "smm" else "")
                             + ((" (" + _esc(str(q)) + ")") if it.get("kind") == "smm" else ""))
            d["items"] = "; ".join(parts) or "?"
            d["total"] = total or 0
            d["buyer"] = ('<a href="tg://user?id=%d">%s</a>' % (int(uid), _esc(_name(uid, users)))
                          + " <code>" + str(uid) + "</code>")
            d["opened"] = datetime.now(IST).strftime("%d %b %Y, %H:%M:%S") + " IST"
            d["status"] = "🟡 Looking at the payment page"
        elif stage == "crypto":
            d["crypto"] = _esc(crypto or "?") + ((" - " + _esc(str(crypto_amount))) if crypto_amount else "")
            d["status"] = "🟠 Address shown, waiting for the payment"
        elif stage == "paid":
            d["status"] = "✅ PAID"
            d["order_id"] = order_id
        elif stage == "expired":
            d["status"] = "⌛ Expired - did not pay"
        elif stage == "cancel":
            d["status"] = "✖ Cancelled by the customer"
        text = _note_text(d)
        if note["msg_id"] is None:
            if stage != "open":
                return                      # we never announced this visit (e.g. bot restarted): skip
            m = await bot.send_message(ADMIN_ID, text, parse_mode="HTML", disable_web_page_preview=True)
            note["msg_id"] = m.message_id
        else:
            await bot.edit_message_text(text, chat_id=ADMIN_ID, message_id=note["msg_id"],
                                        parse_mode="HTML", disable_web_page_preview=True)
        if stage in ("paid", "expired", "cancel"):
            _NOTES.pop(aid, None)
        if len(_NOTES) > 300:
            for k in list(_NOTES)[:100]:
                _NOTES.pop(k, None)
    except Exception as e:
        print(f"[analytics] owner alert failed: {e}")


# ============================== per-product log (/aall, /a<product>) ==============================
def _slug(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _all_product_names(events):
    names = {}
    for r in events:
        if r.get("product"):
            names[r["product"]] = True
    try:
        for p in store.load_products()["items"].values():
            if p.get("name"):
                names[p["name"]] = True
    except Exception:
        pass
    return list(names)


def _match_products(typed, names):
    typed = _slug(typed)
    exact = [n for n in names if _slug(n) == typed]
    if exact:
        return exact
    return [n for n in names if _slug(n).startswith(typed)]


def _event_line(r, att, users):
    e = r["ev"]
    plan = (" " + _esc(r["plan"])) if r.get("plan") else ""
    price = r.get("price")
    ptxt = ""
    if price not in (None, ""):
        ptxt = " (" + (_esc(price) if isinstance(price, str) else _money(price)) + ")"
    who = '<a href="tg://user?id=%d">%s</a>' % (r["uid"], _esc(_name(r["uid"], users)))
    if e == "view":
        what = "opened the product page"
    elif e == "plan":
        what = "opened plan" + plan + ptxt
    elif e == "svc":
        what = "opened the service" + ptxt
    elif e == "cart":
        what = "added to cart" + plan + ptxt
    elif e == "pay":
        a = att.get(r.get("aid"), {})
        what = ("💳 reached the payment page" + plan + ptxt + " · " + _esc(a.get("crypto") or "no crypto picked")
                + " · " + OUTCOME.get(a.get("outcome", "none"), ""))
    else:
        return None
    return "<b>" + _when(r["ts"]) + "</b> · " + who + " — " + what


def product_log(names, days, cap):
    ev = load_events(days)
    att = _attempts(ev)
    users = store.load_users()
    by_prod = {}
    for r in ev:
        if r.get("product") in names:
            by_prod.setdefault(r["product"], []).append(r)
    blocks = []
    for p in sorted(by_prod, key=lambda x: -max(r["ts"] for r in by_prod[x])):
        rows = sorted(by_prod[p], key=lambda r: -r["ts"])
        people = {r["uid"] for r in rows}
        visits = [r for r in rows if r["ev"] == "pay"]
        paid = sum(1 for r in visits if att.get(r.get("aid"), {}).get("outcome") == "paid")
        lines = ["<b>" + _esc(p) + "</b>  ·  " + str(len(people)) + " people, " + str(len(visits))
                 + " payment-page visits, " + str(paid) + " paid"]
        shown = 0
        for r in rows:
            ln = _event_line(r, att, users)
            if not ln:
                continue
            lines.append(ln)
            shown += 1
            if shown >= cap:
                break
        rest = sum(1 for r in rows if r["ev"] in ("view", "plan", "svc", "cart", "pay")) - shown
        if rest > 0:
            lines.append("<i>+" + str(rest) + " older. Use /a" + _slug(p)[:12] + " or /clicks for everything.</i>")
        blocks.append("\n".join(lines))
    return blocks


# ============================== commands ==============================
async def _reply_all(update, parts):
    for p in parts:
        await update.message.reply_text(p, parse_mode="HTML", disable_web_page_preview=True)


def _admin_only(fn):
    async def wrapper(update, context):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("This command is only for admins.")
            return
        await fn(update, context)
    return wrapper


RESERVED = {"active", "add", "addorder", "admin", "ad", "aall", "anotify", "ban", "userorders"}


@_admin_only
async def cmd_aall(update, context):
    days, _ = _parse_days(context.args or [])
    ev = load_events(days)
    names = _all_product_names(ev)
    blocks = product_log(set(names), days, cap=40)
    if not blocks:
        await update.message.reply_text("No activity in the last %d day(s)." % days)
        return
    head = "<b>ALL PRODUCTS - last %d day%s</b>  (newest first, times are IST)" % (days, "" if days == 1 else "s")
    await _reply_all(update, _chunks([head] + blocks))


async def cmd_product_log(update, context):
    """Handles /a<productname>, e.g. /aspotify or /aytpremium."""
    if update.effective_user.id != ADMIN_ID:
        return
    text = (update.message.text or "").split()[0][1:].split("@")[0]
    if text.lower() in RESERVED or not text.lower().startswith("a") or len(text) < 3:
        return
    typed = text[1:]
    days, _ = _parse_days((update.message.text or "").split()[1:])
    ev = load_events(days)
    names = _match_products(typed, _all_product_names(ev))
    if not names:
        await update.message.reply_text("No product matches /" + text + ". Try /aall, or the product name "
                                        "without spaces, e.g. /aspotify.")
        return
    blocks = product_log(set(names), days, cap=150)
    if not blocks:
        await update.message.reply_text("Nobody has clicked " + ", ".join(names) + " in the last %d day(s)." % days)
        return
    head = "<b>/%s - last %d day%s</b>  (newest first, times are IST)" % (_esc(text), days, "" if days == 1 else "s")
    await _reply_all(update, _chunks([head] + blocks))


@_admin_only
async def cmd_anotify(update, context):
    s = _settings()
    s["notify"] = not (s.get("notify") is not False)
    _save_settings(s)
    await update.message.reply_text("Payment-page alerts are now " + ("ON." if s["notify"] else "OFF."))


@_admin_only
async def cmd_funnel(update, context):
    days, _ = _parse_days(context.args or [])
    await _reply_all(update, funnel_text(days))


@_admin_only
async def cmd_paypage(update, context):
    days, _ = _parse_days(context.args or [])
    await _reply_all(update, paypage_text(days))


@_admin_only
async def cmd_clicks(update, context):
    days, rest = _parse_days(context.args or [])
    if rest:
        uid = _resolve_user(rest[0])
        if uid is None:
            await update.message.reply_text("Usage: /clicks [days]   or   /clicks @username|id [days]")
            return
        await _reply_all(update, timeline_text(uid, days))
        return
    data = csv_bytes(days)
    buf = io.BytesIO(data)
    buf.name = "premium_villa_clicks_%dd.csv" % days
    await update.message.reply_document(buf, caption="Click log, last %d day(s). Times are IST. "
                                        "Open it in Excel or Google Sheets." % days)


@_admin_only
async def cmd_trackme(update, context):
    s = _settings()
    s["track_admin"] = not s.get("track_admin")
    _save_settings(s)
    await update.message.reply_text("Tracking of your own clicks is now " + ("ON (for testing)." if s["track_admin"] else "OFF."))


def setup(application, admin_id):
    global ADMIN_ID
    ADMIN_ID = admin_id
    _prune(force=True)
    application.add_handler(CommandHandler("aall", cmd_aall), group=GROUP)
    application.add_handler(CommandHandler("anotify", cmd_anotify), group=GROUP)
    application.add_handler(MessageHandler(filters.COMMAND & filters.Regex(r"^/a[A-Za-z0-9_]{2,}"), cmd_product_log), group=GROUP)
    application.add_handler(CommandHandler("funnel", cmd_funnel), group=GROUP)
    application.add_handler(CommandHandler("paypage", cmd_paypage), group=GROUP)
    application.add_handler(CommandHandler("clicks", cmd_clicks), group=GROUP)
    application.add_handler(CommandHandler("trackme", cmd_trackme), group=GROUP)
    print("Analytics module loaded (keeps %d days)." % RETAIN_DAYS)
