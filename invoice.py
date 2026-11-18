"""
Premium Villa - invoice PDF (invoice.py)  -  the "printed pass" design.

A ticket that is printed out of a slot: big product name, red PAID stamp, on-chain payment
details (coin / address / TxID), a punch-card for the warranty and a stub with the total and a
QR code that opens the transaction on a block explorer.

Fonts (Inter + a mono face) live inside invoice_assets.py, so only 'reportlab' must be installed.

    from invoice import render_pdf
    render_pdf(fields, file_or_path)         # fields come from myorders.invoice_fields()
"""

import io
import random

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

import invoice_assets

PAGE_W, PAGE_H = 780.0, 677.04
U = 780.0 / 1084.0                      # layout is written in "design pixels" (1084 wide) and scaled

BLACK_F, XBOLD_F, BOLD_F, MED_F, MONO, MONOB = "PV-Black", "PV-ExtraBold", "PV-Bold", "PV-Medium", "PV-Mono", "PV-MonoBold"

BLUE = "#1d3dff"
PAPER = "#f3f2ed"
INK = "#0d0d12"
MUTE = "#666672"
RED = "#e5321b"
GREEN = "#12b76a"
SLOT = "#06061a"

_ready = False


def _setup():
    global _ready
    if _ready:
        return
    for name, weight in ((BLACK_F, "Black"), (XBOLD_F, "ExtraBold"), (BOLD_F, "Bold"), (MED_F, "Medium"),
                         (MONO, "Mono"), (MONOB, "MonoBold")):
        pdfmetrics.registerFont(TTFont(name, io.BytesIO(invoice_assets.font_bytes(weight))))
    _ready = True


def _ok(text, font):
    """True when every character exists in the font (else we fall back to something printable)."""
    try:
        cmap = pdfmetrics.getFont(font).face.charToGlyph
        return all((ord(ch) in cmap) or ch.isspace() for ch in text)
    except Exception:
        return True


def _w(s, font, size, spc=0.0):
    return stringWidth(s, font, size) + spc * len(s)


def _fit_size(s, font, size, max_w, spc=0.0, min_size=7.0):
    while size > min_size and _w(s, font, size, spc) > max_w:
        size -= 0.25
    return size


def _clip(s, font, size, max_w, spc=0.0):
    s = str(s)
    if _w(s, font, size, spc) <= max_w:
        return s
    while s and _w(s + "...", font, size, spc) > max_w:
        s = s[:-1]
    return s.rstrip() + "..."


def _hero_lines(name, max_w):
    """Largest Inter-Black size that fits: one line if possible, else two balanced lines."""
    name = name.upper()
    best = (_fit_size(name, BLACK_F, 107, max_w, -1.2, 40), [name])
    if best[0] >= 84 or " " not in name:
        return best
    words = name.split()
    cand = None
    for i in range(1, len(words)):
        l1, l2 = " ".join(words[:i]), " ".join(words[i:])
        size = min(_fit_size(l1, BLACK_F, 52, 470, -0.8, 24), _fit_size(l2, BLACK_F, 52, 470, -0.8, 24))
        if cand is None or size > cand[0]:
            cand = (size, [l1, l2])
    return cand if cand and cand[0] > best[0] * 0.62 else best


def _stamp_png(label, sub, px_w=1000):
    """Rough red ink stamp as a transparent PNG (speckled like a real rubber stamp)."""
    from PIL import Image, ImageDraw, ImageFont, ImageChops
    big = ImageFont.truetype(io.BytesIO(invoice_assets.font_bytes("Black")), 230)
    small = ImageFont.truetype(io.BytesIO(invoice_assets.font_bytes("MonoBold")), 34)
    W, H = px_w, 640
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    spc = 18
    tw = sum(d.textlength(ch, font=big) + spc for ch in label) - spc
    bx0, by0 = 70, 40
    bw, bh = int(tw + 150), 300
    d.rectangle([bx0, by0, bx0 + bw, by0 + bh], outline=255, width=14)
    d.rectangle([bx0 - 24, by0 - 24, bx0 + bw + 24, by0 + bh + 24], outline=255, width=7)
    x = bx0 + 75
    for ch in label:
        d.text((x, by0 + 14), ch, font=big, fill=255)
        x += d.textlength(ch, font=big) + spc
    sw = sum(d.textlength(ch, font=small) + 7 for ch in sub) - 7
    xs = bx0 + (bw - sw) / 2.0
    for ch in sub:
        d.text((xs, by0 + bh + 62), ch, font=small, fill=255)
        xs += d.textlength(ch, font=small) + 7
    # speckle: knock random bits out of the ink
    rnd = random.Random(7)
    noise = Image.effect_noise((W, H), 70)
    holes = noise.point(lambda v: 0 if v > 168 else 255)
    im = ImageChops.multiply(im, holes)
    for _ in range(900):
        cx, cy, r = rnd.randrange(W), rnd.randrange(H), rnd.choice((1, 1, 2, 3))
        ImageDraw.Draw(im).ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    r_, g_, b_ = (int(RED[i:i + 2], 16) for i in (1, 3, 5))
    out = Image.new("RGBA", (W, H), (r_, g_, b_, 0))
    out.putalpha(im.point(lambda v: int(v * 0.92)))
    return out, (bx0, by0, bw, bh)


def render_pdf(f, out):
    _setup()
    c = canvas.Canvas(out, pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Invoice #" + str(f.get("order_no", "")))
    c.setAuthor("Premium Villa")
    c.setSubject("Invoice")

    def X(px):
        return px * U

    def Y(py):
        return PAGE_H - py * U

    def fill(col, a=1.0):
        c.setFillColor(HexColor(col))
        c.setFillAlpha(a)

    def stroke(col, w=1.0, dash=None, a=1.0):
        c.setStrokeColor(HexColor(col))
        c.setStrokeAlpha(a)
        c.setLineWidth(w * U)
        c.setDash(*([[d * U for d in dash], 0] if dash else [[], 0]))

    def rect(x, y, w, h, col, r=0.0, a=1.0):
        fill(col, a)
        if r:
            c.roundRect(X(x), Y(y + h), w * U, h * U, r * U, stroke=0, fill=1)
        else:
            c.rect(X(x), Y(y + h), w * U, h * U, stroke=0, fill=1)
        c.setFillAlpha(1)

    def hline(x0, x1, y, col=INK, w=2.0, dash=None, a=1.0):
        stroke(col, w, dash, a)
        c.line(X(x0), Y(y), X(x1), Y(y))
        c.setDash([], 0)
        c.setStrokeAlpha(1)

    def text(x, y, s, font, size, col=INK, align="l", spc=0.0):
        """x, y in design px; y is the baseline."""
        s = str(s)
        fill(col)
        width = _w(s, font, size, spc)
        if align == "r":
            x -= width
        elif align == "c":
            x -= width / 2.0
        t = c.beginText(X(x), Y(y))
        t.setFont(font, size * U)
        t.setCharSpace(spc * U)
        t.textOut(s)
        c.drawText(t)

    def lab(x, y, s, col=MUTE, align="l"):
        text(x, y, s.upper(), MONO, 10.5, col, align, 2.3)

    # ----------------------------------------------------------------- background + slot + ticket
    rect(0, 0, 1084, 941, BLUE)
    for i, a in enumerate((0.05, 0.05, 0.05, 0.05, 0.05, 0.05)):      # soft drop shadow
        rect(31 - i * 2, 70 + 14 + i * 5, 1021 + i * 4, 760 + i * 2, "#00003c", 26 + i * 3, a * 0.8)
    rect(31, 62, 1021, 760, PAPER, 26)
    rect(14, 43, 1054, 25, SLOT, 13)
    rect(34, 61, 1014, 3, "#000000", 2)
    stroke("#ffffff", 1.2, a=0.16)
    c.line(X(30), Y(66.5), X(1052), Y(66.5))
    c.setStrokeAlpha(1)

    # stub divider + notches
    hline(744, 744, 0, w=0)       # no-op, keeps state tidy
    stroke("#0d0d12", 2.0, (6, 5), 0.4)
    c.line(X(744), Y(78), X(744), Y(806))
    c.setDash([], 0)
    c.setStrokeAlpha(1)
    fill(BLUE)
    c.circle(X(744), Y(822), 15 * U, stroke=0, fill=1)

    # ----------------------------------------------------------------- header
    rect(67, 88, 43, 44, INK, 6)
    text(88.5, 117.5, "PV", BLACK_F, 21, PAPER, "c", -0.8)
    text(122, 107, "PREMIUM VILLA", XBOLD_F, 15.5, INK, "l", 2.2)
    text(122, 127, "Premium services at exceptional value", MONO, 11, MUTE, "l", 0.3)
    rect(613, 89, 95, 23, INK, 11.5)
    text(661, 106, "INVOICE", MONOB, 11.5, PAPER, "c", 3.3)
    text(708, 131, "NO. " + str(f.get("order_no", "")), MONO, 12.5, INK, "r", 0.5)

    # ----------------------------------------------------------------- hero
    smm = f.get("kind") == "smm"
    lab(67, 174, "Item")
    name = str(f.get("product") or "Product")
    size, lines = _hero_lines(name, 641)
    if len(lines) == 1:
        text(67, 268, lines[0], BLACK_F, size, INK, "l", -1.2)
    else:
        text(67, 224, lines[0], BLACK_F, size, INK, "l", -0.8)
        text(67, 224 + size * 1.0, lines[1], BLACK_F, size, INK, "l", -0.8)

    tag = "SOCIAL MEDIA SERVICE" if smm else (str(f.get("plan") or "").upper() or "DIGITAL PRODUCT")
    tag_size = 15
    tag_w = _w(tag, XBOLD_F, tag_size, 1.8) + 26
    rect(67, 291, tag_w, 31, BLUE)
    text(80, 312, tag, XBOLD_F, tag_size, PAPER, "l", 1.8)
    if not smm:
        text(67 + tag_w + 13, 312, "QTY " + str(f.get("qty", "1")) + " × " + str(f.get("rate", "")), MONO, 12, INK, "l", 0.5)

    # stamp (rubber-stamp look, tilted)
    sub = (str(f.get("date_stamp", "")) + " · " + (f.get("coin") or "WALLET") + " · CONFIRMED").upper()
    img, (bx, by, bw, bh) = _stamp_png("PAID", sub)
    sc = 0.3 * 2.5 * U * 0.93 * 0.5 * 0.85          # pixels of the PNG -> points
    iw, ih = img.size
    cx, cy = X(600), Y(266)
    c.saveState()
    c.translate(cx, cy)
    c.rotate(9)
    c.drawImage(ImageReader(img), -iw * sc / 2.0, -ih * sc / 2.0 + 6, iw * sc, ih * sc, mask="auto")
    c.restoreState()

    # ----------------------------------------------------------------- facts row
    cols = (67, 231, 396, 560)
    for x in cols:
        hline(x, x + 148, 355, INK, 2.0)
    lab(cols[0], 382, "Date of purchase")
    text(cols[0], 409, f.get("date", ""), BOLD_F, 17, INK)

    lab(cols[1], 382, "Billed to")
    bill = str(f.get("bill_to") or "Customer")
    if not _ok(bill, BOLD_F):
        bill = "Customer"
    bill = bill.upper() if not bill.startswith("@") else bill
    text(cols[1], 409, _clip(bill, BOLD_F, 17, 140), BOLD_F, 17, INK)
    text(cols[1], 429, "Telegram " + str(f.get("userid", "")), MONO, 11, MUTE, "l", 0.1)

    lab(cols[2], 382, "Paid with")
    text(cols[2], 409, str(f.get("method", "")), BOLD_F, 17, INK)
    if f.get("coin_full"):
        sub2 = f["coin_full"] + " · " + f["coin"]
    else:
        sub2 = "Premium Villa wallet"
    text(cols[2], 429, _clip(sub2, MONO, 11, 146), MONO, 11, MUTE, "l", 0.1)

    lab(cols[3], 382, "Status")
    fill(GREEN)
    c.circle(X(cols[3] + 4.5), Y(403), 4.5 * U, stroke=0, fill=1)
    text(cols[3] + 18, 409, "Confirmed", BOLD_F, 17, INK)
    text(cols[3], 429, "Delivered on", MONO, 11, MUTE, "l", 0.1)
    text(cols[3], 443, "Telegram", MONO, 11, MUTE, "l", 0.1)

    # ----------------------------------------------------------------- payment ledger
    method_key = f.get("method_key") or "wallet"
    onchain = "crypto" in method_key
    lab(67, 486, "On-chain payment" if onchain else "Payment", INK)
    lab(708, 486, f.get("network") or "PREMIUM VILLA WALLET", MUTE, "r")
    hline(67, 708, 497, INK, 2.0)
    if onchain:
        rows = [("Coin", None), ("Address", f.get("address") or "-"), ("TxID", f.get("txid") or "-")]
    else:
        rows = [("Method", "Wallet balance"), ("Paid from", "Premium Villa wallet"), ("Reference", str(f.get("order_no", "")))]
    for i, (k, v) in enumerate(rows):
        yb = 497 + 44 * (i + 1)
        lab(67, yb - 20, k)
        if v is None:                                   # coin row
            nm = f.get("coin_full") or f.get("coin") or "Crypto"
            text(160, yb - 18, nm, BOLD_F, 16.5, INK)
            tw = _w(nm, BOLD_F, 16.5)
            rect(160 + tw + 9, yb - 33, _w(f.get("coin", ""), MONOB, 10, 1.4) + 14, 18, INK, 3)
            text(160 + tw + 16, yb - 20, f.get("coin", ""), MONOB, 10, PAPER, "l", 1.4)
        else:
            v = str(v)
            if not _ok(v, MONO):
                v = "-"
            sz = _fit_size(v, MONO, 13, 548)
            text(160, yb - 17, v, MONO, sz, INK)
        hline(67, 708, yb, INK, 1.2, (4, 4), 0.28)

    # ----------------------------------------------------------------- warranty punch-card / order details
    wm = int(f.get("warranty_months") or 0)
    if smm:
        lab(67, 668, "Order details", INK)
        lab(708, 668, "Social media service", MUTE, "r")
        hline(67, 708, 679, INK, 2.0)
        det = [(f.get("target_label") or "Details", f.get("target") or "-"),
               ("Quantity", name.split(" ", 1)[1] if " " in name else "-")]
        for i, (k, v) in enumerate(det):
            yb = 679 + 34 * (i + 1)
            lab(67, yb - 12, k)
            v = str(v)
            if not _ok(v, MONO):
                v = "-"
            text(230, yb - 11, v, MONO, _fit_size(v, MONO, 13, 478), INK)
            hline(67, 708, yb, INK, 1.2, (4, 4), 0.28)
    else:
        lab(67, 668, ("Warranty · " + (str(wm) + " month" + ("s" if wm != 1 else ""))) if wm else "Warranty", INK)
        lab(708, 668, ("Valid till " + str(f.get("valid_till", ""))) if wm else "No warranty", MUTE, "r")
        hline(67, 708, 679, INK, 2.0)
        labels = f.get("punch") or []
        n = len(labels)
        if n:
            spacing = 76.0 if n <= 6 else min(76.0, 618.0 / n)
            for i, lb in enumerate(labels):
                hx = 80.5 + spacing * i
                hy = 706
                fill("#000000", 0.0)
                stroke("#0d0d12", 1.5, a=0.22)
                c.circle(X(hx), Y(hy), 19.2 * U, stroke=1, fill=0)           # outer ring
                c.setStrokeAlpha(1)
                fill(PAPER)
                c.circle(X(hx), Y(hy), 17.5 * U, stroke=0, fill=1)
                fill(BLUE)
                c.circle(X(hx), Y(hy), 15 * U, stroke=0, fill=1)
                fill("#000000", 0.38)                                         # inner shadow (punched look)
                c.circle(X(hx), Y(hy - 1.2), 15 * U, stroke=0, fill=0)
                c.saveState()
                p = c.beginPath()
                p.circle(X(hx), Y(hy), 15 * U)
                c.clipPath(p, stroke=0, fill=0)
                fill("#000000", 0.32)
                c.ellipse(X(hx - 16), Y(hy - 12), X(hx + 16), Y(hy - 27), stroke=0, fill=1)
                c.restoreState()
                fill(BLUE)
                c.setFillAlpha(1)
                c.circle(X(hx), Y(hy + 1.5), 13 * U, stroke=0, fill=1)
                text(hx - 14, 744, lb, MONO, 9.5 if n <= 6 else 8.2, MUTE, "l", 1.2 if n <= 6 else 0.4)

    text_y = 778
    note = "DIGITAL SUBSCRIPTIONS, DELIVERED ON TELEGRAM. COMPUTER-GENERATED INVOICE, NO SIGNATURE REQUIRED."
    if smm:
        note = "SOCIAL MEDIA SERVICES, DELIVERED TO THE ACCOUNT ABOVE. COMPUTER-GENERATED INVOICE, NO SIGNATURE REQUIRED."
    words, line, lines_out = note.split(" "), "", []
    for wd in words:
        trial = (line + " " + wd).strip()
        if _w(trial, MONO, 10, 0.6) > 630 and line:
            lines_out.append(line)
            line = wd
        else:
            line = trial
    lines_out.append(line)
    for i, ln in enumerate(lines_out[:2]):
        text(67, text_y + 17 * i + (3 if smm else 0) - (6 if smm else 0), ln, MONO, 10, MUTE, "l", 0.6)

    # ----------------------------------------------------------------- stub
    lab(773, 96, "Total paid")
    total = str(f.get("total", "$0.00"))
    text(773, 158, total, BLACK_F, _fit_size(total, BLACK_F, 72, 252, -1.0, 40), INK, "l", -1.0)
    coin = f.get("coin") or ""
    if onchain and "wallet" in method_key:
        paid_lbl = "Paid by wallet + " + coin
    elif onchain:
        paid_lbl = "Paid in " + coin
    else:
        paid_lbl = "Paid by wallet"
    sum_rows = (("Subtotal", total, 205), ("" + paid_lbl, total, 238))
    for k, v, yb in sum_rows:
        text(773, yb, k, MONO, 12.5, INK, "l", 0.2)
        text(1025, yb, v, MONO, 12.5, INK, "r", 0.2)
        hline(773, 1025, yb + 12, INK, 1.2, (4, 4), 0.28)
    rect(773, 264, 252, 51, INK)
    text(787, 294, "BALANCE DUE", XBOLD_F, 14, PAPER, "l", 1.2)
    text(1009, 297, str(f.get("balance", "$0.00")), BLACK_F, 23, PAPER, "r", -0.3)

    # QR (only for on-chain payments: opens the transaction on a block explorer)
    if f.get("explorer_url"):
        lab(773, 576, "Scan to verify on-chain")
        rect(773, 589, 144, 144, "#ffffff")
        stroke(INK, 2.0)
        c.rect(X(774), Y(732), 142 * U, 142 * U, stroke=1, fill=0)
        try:
            from reportlab.graphics.barcode.qr import QrCodeWidget
            from reportlab.graphics import renderPDF
            from reportlab.graphics.shapes import Drawing
            qr = QrCodeWidget(f["explorer_url"], barLevel="M", barBorder=0)
            x0, y0, x1, y1 = qr.getBounds()
            side = 124 * U
            d = Drawing(side, side, transform=[side / (x1 - x0), 0, 0, side / (y1 - y0), 0, 0])
            d.add(qr)
            fill(INK)
            renderPDF.draw(d, c, X(783), Y(723))
        except Exception:
            pass
        tx = str(f.get("txid", ""))
        short = tx[:8] + "\u2026" + tx[-8:] if len(tx) > 18 else tx
        text(773, 755, str(f.get("explorer_host", "")) + " \u00b7 TX " + short, MONO, 10.5, INK, "l", 0.1)
    text(773, 789, "ORDER " + str(f.get("order_no", "")), MONO, 10.5, MUTE, "l", 0.5)

    c.showPage()
    c.save()
