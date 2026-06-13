"""
Kaiser's Detail Co. — Printable Flyer Generator
Letter size (8.5 x 11 in), black & white, print-ready.

Services, pricing, durations and add-on mappings are kept in lock-step with the
online booking tool on kaiserdetailing.com (index.html). In that tool:
  • Quick Wash is an ADD-ON ($20), not a standalone service.
  • Each service lists only the add-ons the booking tool allows for it.

Run:   python flyer.py
Out:   kaisers_detail_flyer_bw.pdf
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white
import os, io, qrcode
from PIL import Image as PILImage

# ── PALETTE (black & white) ────────────────────────────────────────────────────
GOLD       = HexColor('#000000')   # was gold → black
GOLD_LIGHT = HexColor('#f2f2f2')   # was gold tint → light grey
GOLD_BD    = HexColor('#999999')   # was gold border → mid grey
CHARCOAL   = HexColor('#18181a')   # unchanged — already near-black
INK        = HexColor('#2e2d2b')   # unchanged
MUTED      = HexColor("#000000")   # unchanged
CREAM      = HexColor('#f7f7f7')   # was warm cream → neutral light grey
RULE       = HexColor("#000000")   # was warm rule → neutral grey
WHITE      = white

W, H   = letter          # 612 × 792
MARGIN = 34
INNER  = W - 2 * MARGIN  # 544 pt
GAP    = 9
COL    = (INNER - GAP) / 2  # ~267 pt per column

LOGO    = 'favicon.png'
QR_URL  = 'https://kaiserdetailing.com'
OUT     = 'kaisers_detail_flyer_bw.pdf'

# ── CANONICAL ADD-ON PRICES (match booking tool ADDONS) ────────────────────────
#   tire_shine $10 · carpet_shampoo $30 · wax $30 · clay $45 · rainx $10 · quick_wash $20
ADDON_PRICE = {
    'Quick Wash':      '+$20',
    'Tire Shine':      '+$10',
    'Carpet Shampoo':  '+$30',
    'Wax':             '+$30',
    'Clay Service':    '+$45',
    'RainX':           '+$10',
}

# ── SERVICE DATA — mirrors index.html SERVICES + SERVICE_ADDONS ─────────────────
# Order matches the booking tool's "All" tab. Quick Wash is intentionally NOT a
# service here — it is an add-on offered on the services the tool allows.
def ao(*names):
    return [(n, ADDON_PRICE[n]) for n in names]

SERVICES = [
    {
        'name': 'Interior Detail',
        'dur': '1 hr 30 min', 'price': '$100',
        'desc': 'Deep vacuum, panels, glass & odor',
        'addons': ao('Carpet Shampoo'),
    },
    {
        'name': 'Professional Detail',
        'dur': '3 hrs', 'price': '$150',
        'desc': 'Full interior + exterior package',
        'addons': ao('Carpet Shampoo', 'Clay Service', 'RainX'),
    },
    {
        'name': 'Showroom Detail',
        'dur': '4 hrs', 'price': '$225',
        'desc': 'Top-to-bottom showroom-quality finish',
        'addons': ao('Clay Service', 'RainX'),
    },
    {
        'name': 'Exterior Detail',
        'dur': '1 hr 30 min', 'price': '$75',
        'desc': 'Hand wash, wheels, windows & jambs',
        'addons': ao('Wax', 'Clay Service', 'RainX'),
    },
    {
        'name': 'Quick Interior Cleaning',
        'dur': '30 min', 'price': '$35',
        'desc': 'Vacuum, wipe-down & freshen up',
        'addons': ao('Carpet Shampoo', 'Quick Wash'),
    },
    {
        'name': 'Quick Detail',
        'dur': '1 hr', 'price': '$55',
        'desc': 'Interior vacuum + exterior wash',
        'addons': ao('Tire Shine'),
    },
    {
        'name': 'Engine Bay Cleaning',
        'dur': '30 min', 'price': '$35',
        'desc': 'Degreased & detailed under the hood',
        'addons': ao('Quick Wash'),
    },
    {
        'name': 'Headlight Restoration',
        'dur': '40 min', 'price': '$40',
        'desc': 'Restores cloudy lenses to like-new clarity',
        'addons': ao('Quick Wash'),
    },
    {
        'name': 'Sticker / Decal Removal',
        'dur': '15 min', 'price': '$15',
        'desc': 'Clean removal without damaging paint',
        'addons': ao('Quick Wash'),
    },
]

# Add-ons summarized in their own strip (mirrors the tool's Add-Ons & Extras tab)
EXTRAS = [
    ('Quick Wash',     '30 min', '+$20', 'Fast exterior hand wash — add to many services'),
    ('Tire Shine',     '30 min', '+$10', 'Rich, lasting shine on tires'),
    ('Carpet Shampoo', '30 min', '+$30', 'Deep-clean carpets & mats'),
    ('Wax',            '45 min', '+$30', 'Hand wax for gloss & protection'),
    ('Clay Service',   '35 min', '+$45', 'Removes bonded contaminants'),
    ('RainX',          '15 min', '+$10', 'Water-beading glass treatment'),
]

# ── SIZING CONSTANTS ──────────────────────────────────────────────────────────
SAFE       = 18    # non-printable edge inset — header/footer pulled in from top/bottom
HEADER_H   = 120
FOOTER_H   = 60
EYEBROW_H  = 16
EXTRA_H    = 34
CARD_GAP   = 6
ADDON_H    = 14
ADDON_GAP  = 3
CARD_PAD   = 8

def card_height(svc):
    n = len(svc['addons'])
    rows = (n + 1) // 2
    base = 50
    if n == 0:
        return base
    return base + 8 + rows * (ADDON_H + ADDON_GAP)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def rr(c, x, y, w, h, r=5, fc=None, sc=None, lw=0.5):
    if fc: c.setFillColor(fc)
    if sc: c.setStrokeColor(sc); c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r,
                fill=1 if fc else 0,
                stroke=1 if sc else 0)

def txt(c, s, x, y, font='Helvetica', sz=8, color=MUTED, align='left'):
    c.setFont(font, sz)
    c.setFillColor(color)
    if align == 'center': c.drawCentredString(x, y, s)
    elif align == 'right': c.drawRightString(x, y, s)
    else: c.drawString(x, y, s)

def hline(c, y, x0=MARGIN, x1=None, color=RULE, lw=0.5):
    x1 = x1 or W - MARGIN
    c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x0, y, x1, y)

def make_qr_image(url, size=200):
    """Return a PIL Image of the QR code (white modules = transparent)."""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    img = img.resize((size, size), PILImage.NEAREST)
    return img

def draw_qr(c, url, x, y, size):
    """Draw QR code image onto canvas at (x, y) bottom-left, given size in pts."""
    img = make_qr_image(url, size=int(size * 3))   # oversample for sharpness
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(buf), x, y, width=size, height=size)

# ── SECTIONS ─────────────────────────────────────────────────────────────────

def draw_header(c):
    top = H - SAFE
    band_bottom = top - HEADER_H
    c.setFillColor(CHARCOAL)
    c.rect(0, band_bottom, W, 200, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, H, W, 3, fill=1, stroke=0)

    ls = 46
    lx = W / 2 - ls / 2
    ly = band_bottom + 70
    if os.path.exists(LOGO):
        c.drawImage(LOGO, lx, ly, width=ls, height=ls,
                    mask='auto', preserveAspectRatio=True)
    else:
        c.setFillColor(GOLD); c.circle(W/2, ly + ls/2, ls/2, fill=1, stroke=0)

    txt(c, "Kaiser's Detail Co.", W/2, ly - 16, 'Times-Bold', 24, WHITE, 'center')
    txt(c, 'AUTO DETAILING  ·  PLAINFIELD, IL', W/2, ly - 31, 'Helvetica', 8.5, HexColor('#cccccc'), 'center')
    txt(c, '"Your Car, Spotless."', W/2, ly - 48, 'Times-BoldItalic', 12,
        HexColor('#f2f2f2'), 'center')

    # QR code — top-right corner of header band
    qr_size = 72
    qr_x = W - MARGIN - qr_size
    qr_y = band_bottom + (HEADER_H - qr_size) / 2   # vertically centred in band
    draw_qr(c, QR_URL, qr_x, qr_y, qr_size)
    txt(c, 'SCAN TO BOOK', qr_x + qr_size / 2, qr_y - 11,
        'Helvetica-Bold', 5.5, HexColor('#aaaaaa'), 'center')

    return band_bottom


def eyebrow(c, text, y):
    txt(c, text, MARGIN, y, 'Helvetica-Bold', 6.5, GOLD)
    hline(c, y - 4, color=GOLD_BD, lw=0.6)
    return y - EYEBROW_H


def draw_card(c, svc, x, y, w):
    ch = card_height(svc)

    rr(c, x, y - ch, w, ch, r=5, fc=CREAM, sc=RULE, lw=0.5)

    hh = 34
    c.setFillColor(WHITE)
    c.roundRect(x, y - hh, w, hh, 5, fill=1, stroke=0)
    c.rect(x, y - hh, w, 5, fill=1, stroke=0)
    hline(c, y - hh, x, x + w, RULE, 0.4)

    txt(c, svc['name'], x + CARD_PAD, y - 13, 'Helvetica-Bold', 9.5, CHARCOAL)
    txt(c, svc['price'], x + w - CARD_PAD, y - 13,
        'Times-Bold', 13, GOLD, 'right')
    dur_desc = f"{svc['dur']}  ·  {svc['desc']}"
    txt(c, dur_desc, x + CARD_PAD, y - 25, 'Helvetica', 6.8, MUTED)

    n = len(svc['addons'])
    if n:
        ao_y = y - hh - 8
        txt(c, 'ADD-ONS:', x + CARD_PAD, ao_y, 'Helvetica-Bold', 5.5, GOLD)

        pill_gap = 3
        pill_w = (w - 2*CARD_PAD - pill_gap) / 2

        for i, (aname, aprice) in enumerate(svc['addons']):
            col_i = i % 2
            row_i = i // 2
            px = x + CARD_PAD + col_i * (pill_w + pill_gap)
            py = ao_y - 5 - row_i * (ADDON_H + ADDON_GAP) - ADDON_H

            rr(c, px, py, pill_w, ADDON_H, r=3, fc=GOLD_LIGHT, sc=GOLD_BD, lw=0.3)
            txt(c, aname, px + 4, py + 4, 'Helvetica', 6, INK)
            txt(c, aprice, px + pill_w - 4, py + 4, 'Helvetica-Bold', 6.5, GOLD, 'right')

    return y - ch


def draw_extras(c, y):
    y = eyebrow(c, 'ADD-ONS — MIX INTO ANY ELIGIBLE SERVICE', y)
    cw = (INNER - 2 * GAP) / 3
    for i, (name, dur, price, desc) in enumerate(EXTRAS):
        col = i % 3
        row = i // 3
        x = MARGIN + col * (cw + GAP)
        ey = y - row * (EXTRA_H + 5)
        rr(c, x, ey - EXTRA_H, cw, EXTRA_H, r=5, fc=CREAM, sc=RULE, lw=0.5)
        txt(c, name, x + CARD_PAD, ey - 13, 'Helvetica-Bold', 8.5, CHARCOAL)
        txt(c, price, x + cw - CARD_PAD, ey - 13, 'Times-Bold', 11.5, GOLD, 'right')
        txt(c, dur, x + CARD_PAD, ey - 24, 'Helvetica-Bold', 6, GOLD)
        txt(c, desc, x + CARD_PAD + 34, ey - 24, 'Helvetica', 6, MUTED)
    rows = (len(EXTRAS) + 2) // 3
    return y - rows * EXTRA_H - (rows - 1) * 5


def draw_footer(c):
    base = SAFE
    c.setFillColor(CHARCOAL)
    c.rect(0, base + FOOTER_H - 100, W, 100, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, base + FOOTER_H - 100, W, 100, fill=1, stroke=0)

    mid = base + (FOOTER_H - 3) / 2
    txt(c, 'Book in 60 seconds — visit or scan:', W/2, mid + 12,
        'Helvetica-Bold', 12, WHITE, 'center')
    txt(c, 'kaiserdetailing.com  ·  815-823-9485  ·  KaoFechner@outlook.com',
        W/2, mid - 4, 'Helvetica', 8, HexColor('#cccccc'), 'center')
    txt(c, 'Plainfield, IL & surrounding areas',
        W/2, mid - 17, 'Helvetica', 7.5, WHITE, 'center')


# ── BACK PAGE (top-third fold panel) ─────────────────────────────────────────

PANEL_H = H / 3   # 264 pt — the visible top-third when folded

# Mini strip mirrors the booking tool's headline services & prices
HERO_SVCS = [
    ('Quick Detail',     '$55',  '1 hr'),
    ('Exterior Detail',  '$75',  '1h 30m'),
    ('Interior Detail',  '$100', '1h 30m'),
    ('Pro Detail',       '$150', '3 hrs'),
]

def draw_back_page(c):
    # ── white background for whole page ──────────────────────────────────────
    c.setFillColor(WHITE)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── fold guide: dashed line at 2/3 from top (= 1/3 from bottom of panel) ─
    fold_y = H - PANEL_H
    c.setStrokeColor(HexColor('#bbbbbb'))
    c.setLineWidth(0.5)
    c.setDash(4, 4)
    c.line(MARGIN, fold_y, W - MARGIN, fold_y)
    c.setDash()   # reset
    txt(c, 'FOLD HERE', W - MARGIN, fold_y + 3, 'Helvetica', 5, HexColor('#bbbbbb'), 'right')

    # ── solid black panel fill ────────────────────────────────────────────────
    c.setFillColor(CHARCOAL)
    c.rect(0, fold_y, W, PANEL_H, fill=1, stroke=0)

    # thin top rule
    c.setFillColor(GOLD)
    c.rect(0, H - 3, W, 3, fill=1, stroke=0)

    # ── layout: left text block, right QR ────────────────────────────────────
    QR_SIZE  = 90
    QR_X     = W - MARGIN - QR_SIZE
    QR_Y     = fold_y + (PANEL_H - QR_SIZE) / 2 - 8
    TEXT_W   = QR_X - MARGIN - 18   # text column width

    # ── Logo + brand name (top-left) ─────────────────────────────────────────
    ls = 30
    logo_y = H - MARGIN - ls
    logo_x = MARGIN
    if os.path.exists(LOGO):
        c.drawImage(LOGO, logo_x, logo_y, width=ls, height=ls,
                    mask='auto', preserveAspectRatio=True)
    lbl_x = logo_x + ls + 8
    txt(c, "Kaiser's Detail Co.", lbl_x, logo_y + 10, 'Times-Bold', 15, WHITE)
    txt(c, 'AUTO DETAILING  ·  PLAINFIELD, IL', lbl_x, logo_y - 2, 'Helvetica', 7, HexColor('#aaaaaa'))

    # ── Big tagline ───────────────────────────────────────────────────────────
    tag_y = logo_y - 30
    txt(c, 'Your Car,', MARGIN, tag_y, 'Times-Bold', 28, WHITE)
    txt(c, 'Spotless.', MARGIN, tag_y - 30, 'Times-BoldItalic', 28, HexColor('#dddddd'))

    # ── Sub line ──────────────────────────────────────────────────────────────
    mis_y = tag_y - 58
    c.setStrokeColor(HexColor('#555555'))
    c.setLineWidth(0.5)
    c.line(MARGIN, mis_y + 14, MARGIN + TEXT_W * 0.55, mis_y + 14)
    txt(c, 'Professional auto detailing,', MARGIN, mis_y + 2, 'Helvetica-Bold', 8.5, HexColor('#eeeeee'))
    txt(c, 'done right at your door.', MARGIN, mis_y - 12, 'Helvetica', 8, HexColor('#aaaaaa'))

    # ── Mini service strip ────────────────────────────────────────────────────
    strip_y  = fold_y + 28
    svc_w    = TEXT_W / len(HERO_SVCS)
    for i, (name, price, dur) in enumerate(HERO_SVCS):
        sx = MARGIN + i * svc_w
        # subtle divider between items
        if i > 0:
            c.setStrokeColor(HexColor('#444444'))
            c.setLineWidth(0.5)
            c.line(sx, strip_y - 2, sx, strip_y + 36)
        txt(c, price, sx + 6, strip_y + 22, 'Times-Bold', 13, WHITE)
        txt(c, name, sx + 6, strip_y + 10, 'Helvetica-Bold', 6.5, HexColor('#cccccc'))
        txt(c, dur,  sx + 6, strip_y,      'Helvetica', 6,   HexColor('#888888'))

    # ── QR code ───────────────────────────────────────────────────────────────
    # white rounded square background
    pad = 6
    rr(c, QR_X - pad, QR_Y - pad, QR_SIZE + pad*2, QR_SIZE + pad*2,
       r=8, fc=WHITE, sc=None)
    draw_qr(c, QR_URL, QR_X, QR_Y, QR_SIZE)
    txt(c, 'SCAN TO BOOK', QR_X + QR_SIZE / 2, QR_Y - pad - 10,
        'Helvetica-Bold', 6, HexColor('#aaaaaa'), 'center')
    txt(c, 'kaiserdetailing.com', QR_X + QR_SIZE / 2, QR_Y - pad - 21,
        'Helvetica', 5.5, HexColor('#777777'), 'center')


# ── BUILD ─────────────────────────────────────────────────────────────────────

def build():
    cv = canvas.Canvas(OUT, pagesize=letter)
    cv.setTitle("Kaiser's Detail Co. — Flyer")

    cv.setFillColor(WHITE)
    cv.rect(0, 0, W, H, fill=1, stroke=0)

    y = draw_header(cv)
    y -= 18
    y = eyebrow(cv, 'SERVICES & PRICING', y)

    # Split the 9 services across two columns, balanced by height
    half = (len(SERVICES) + 1) // 2
    left_svcs  = SERVICES[:half]
    right_svcs = SERVICES[half:]
    ly = ry = y

    for svc in left_svcs:
        ly = draw_card(cv, svc, MARGIN, ly, COL)
        ly -= CARD_GAP

    for svc in right_svcs:
        ry = draw_card(cv, svc, MARGIN + COL + GAP, ry, COL)
        ry -= CARD_GAP

    cur_y = min(ly, ry) - 8
    cur_y = draw_extras(cv, cur_y)
    cur_y -= 4

    draw_footer(cv)

    margin_above_footer = cur_y - (SAFE + FOOTER_H)
    if margin_above_footer < 0:
        print(f"Warning: Overflow by {-margin_above_footer:.1f}pt — tighten spacing.")
    else:
        print(f"Fit OK — {margin_above_footer:.1f}pt above footer.")

    # ── PAGE 2: back of flyer ─────────────────────────────────────────────────
    cv.showPage()
    draw_back_page(cv)

    cv.save()
    print(f"Saved -> {OUT}")


if __name__ == '__main__':
    build()