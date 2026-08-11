"""
Kaiser's Detail Co. — Printable Flyer Generator
Letter size (8.5 x 11 in), black & white, print-ready.

Run:   python flyer_bw.py
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

# ── SERVICE DATA ──────────────────────────────────────────────────────────────
SERVICES = [
    {
        'name': 'Quick Wash',
        'dur': '30 min', 'price': '$20',
        'desc': 'Fast exterior rinse & hand wash',
        'addons': [('Tire Shine', '+$10'), ('Wax', '+$30'), ('RainX', '+$10')],
    },
    {
        'name': 'Interior Detail',
        'dur': '4 hr 30 min', 'price': '$100',
        'desc': 'Deep vacuum, panels, glass & odor',
        'addons': [('Carpet Shampoo', '+$30')],
    },
    {
        'name': 'Exterior Detail',
        'dur': '2 hr 30 min', 'price': '$75',
        'desc': 'Hand wash, wheels, windows & jambs',
        'addons': [
            ('Wax', '+$30'), ('Clay Service', '+$45'), ('RainX', '+$10'),
        ],
    },
    {
        'name': 'Professional Detail',
        'dur': '4 hrs', 'price': '$150',
        'desc': 'Full interior + exterior package',
        'addons': [
            ('Carpet Shampoo', '+$30'), ('Clay Service', '+$45'), ('RainX', '+$10'),
        ],
    },
    {
        'name': 'Engine Bay Cleaning',
        'dur': '30 min', 'price': '$55',
        'desc': 'Degreased & detailed under the hood',
        'addons': [],
    },
]

EXTRAS = [
    ('Sticker / Decal Removal', '15 min', '$15', 'Clean removal without damaging paint'),
]

# ── SIZING CONSTANTS ──────────────────────────────────────────────────────────
HEADER_H   = 130
COLLEGE_H  = 48
FOOTER_H   = 72
EYEBROW_H  = 18
EXTRA_H    = 42
CARD_GAP   = 5
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
    c.setFillColor(CHARCOAL)
    c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, H - 3, W, 3, fill=1, stroke=0)

    ls = 46
    lx = W / 2 - ls / 2
    ly = H - HEADER_H + 75
    if os.path.exists(LOGO):
        c.drawImage(LOGO, lx, ly, width=ls, height=ls,
                    mask='auto', preserveAspectRatio=True)
    else:
        c.setFillColor(GOLD); c.circle(W/2, ly + ls/2, ls/2, fill=1, stroke=0)

    txt(c, "Kaiser's Detail Co.", W/2, ly - 16, 'Times-Bold', 24, WHITE, 'center')
    txt(c, 'AUTO DETAILING  ·  GREENCASTLE, IN', W/2, ly - 30, 'Helvetica', 8.5, HexColor('#cccccc'), 'center')
    txt(c, '"Your Car, Spotless."', W/2, ly - 46, 'Times-BoldItalic', 12,
        HexColor('#f2f2f2'), 'center')
    txt(c, 'Greencastle, IN & within 25 miles', W/2, ly - 60,
        'Helvetica', 7.5, HexColor('#aaaaaa'), 'center')

    # QR code — top-right corner of header band
    qr_size = 72
    qr_x = W - MARGIN - qr_size
    qr_y = H - HEADER_H + (HEADER_H - qr_size) / 2   # vertically centred in band
    draw_qr(c, QR_URL, qr_x, qr_y, qr_size)
    txt(c, 'SCAN TO BOOK', qr_x + qr_size / 2, qr_y - 11,
        'Helvetica-Bold', 5.5, HexColor('#aaaaaa'), 'center')

    return H - HEADER_H


def draw_college_strip(c, y):
    by = y - COLLEGE_H - 6
    rr(c, MARGIN, by, INNER, COLLEGE_H, r=6, fc=GOLD_LIGHT, sc=GOLD_BD, lw=0.75)
    txt(c, 'Local, mobile & meticulous.',
        MARGIN + CARD_PAD, by + COLLEGE_H - 17, 'Helvetica-Bold', 9.5, CHARCOAL)
    txt(c, 'Kaiser\u2019s Detail Co. comes to you in Greencastle and within 25 miles with professional-grade tools.',
        MARGIN + CARD_PAD, by + COLLEGE_H - 31, 'Helvetica', 7.5, MUTED)
    txt(c, 'One booking a day means your car gets full, undivided attention.',
        MARGIN + CARD_PAD, by + COLLEGE_H - 43, 'Helvetica', 7.5, MUTED)
    return by - 6


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
    y = eyebrow(c, 'ADDITIONAL SERVICES', y)
    cw = (INNER - GAP) / 2
    for i, (name, dur, price, desc) in enumerate(EXTRAS):
        x = MARGIN + i * (cw + GAP)
        rr(c, x, y - EXTRA_H, cw, EXTRA_H, r=5, fc=CREAM, sc=RULE, lw=0.5)
        txt(c, name, x + CARD_PAD, y - 14, 'Helvetica-Bold', 9.5, CHARCOAL)
        txt(c, price, x + cw - CARD_PAD, y - 14, 'Times-Bold', 13, GOLD, 'right')
        txt(c, f'{dur}  ·  {desc}', x + CARD_PAD, y - 27, 'Helvetica', 7, MUTED)
    return y - EXTRA_H


def draw_footer(c):
    c.setFillColor(CHARCOAL)
    c.rect(0, FOOTER_H - 3, W, 3, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, 0, W, FOOTER_H - 3, fill=1, stroke=0)

    mid = (FOOTER_H - 3) / 2
    txt(c, 'Book in 60 seconds — visit or scan:', W/2, mid + 18,
        'Helvetica-Bold', 12, WHITE, 'center')
    txt(c, 'kaiserdetailing.com  ·  815-823-9485  ·  KaoFechner@outlook.com',
        W/2, mid + 3, 'Helvetica', 8, HexColor('#cccccc'), 'center')
    txt(c, 'Greencastle, IN & within 25 miles  ·  One booking a day — full attention on your car',
        W/2, mid - 12, 'Helvetica', 7.5, WHITE, 'center')


# ── BACK PAGE (top-third fold panel) ─────────────────────────────────────────

PANEL_H = H / 3   # 264 pt — the visible top-third when folded

HERO_SVCS = [
    ('Quick Wash',       '$20',  '30 min'),
    ('Exterior Detail',  '$75',  '2h 30m'),
    ('Interior Detail',  '$100', '4h 30m'),
    ('Full Detail',      '$150', '4 hrs'),
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
    txt(c, 'AUTO DETAILING  ·  GREENCASTLE, IN', lbl_x, logo_y - 2, 'Helvetica', 7, HexColor('#aaaaaa'))

    # ── Big tagline ───────────────────────────────────────────────────────────
    tag_y = logo_y - 26
    txt(c, 'Your Car,', MARGIN, tag_y, 'Times-Bold', 28, WHITE)
    txt(c, 'Spotless.', MARGIN, tag_y - 30, 'Times-BoldItalic', 28, HexColor('#dddddd'))

    # ── Mission line ──────────────────────────────────────────────────────────
    mis_y = tag_y - 56
    c.setStrokeColor(HexColor('#555555'))
    c.setLineWidth(0.5)
    c.line(MARGIN, mis_y + 14, MARGIN + TEXT_W * 0.55, mis_y + 14)
    txt(c, 'Local, mobile & meticulous.', MARGIN, mis_y + 2, 'Helvetica-Bold', 8.5, HexColor('#eeeeee'))
    txt(c, 'One booking a day — full attention on your car.', MARGIN, mis_y - 12, 'Helvetica', 8, HexColor('#aaaaaa'))

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
    y = draw_college_strip(cv, y)
    y -= 15
    y = eyebrow(cv, 'SERVICES & PRICING', y)

    left_svcs  = SERVICES[:4]
    right_svcs = SERVICES[4:]
    ly = ry = y

    for svc in left_svcs:
        ly = draw_card(cv, svc, MARGIN, ly, COL)
        ly -= CARD_GAP

    for svc in right_svcs:
        ry = draw_card(cv, svc, MARGIN + COL + GAP, ry, COL)
        ry -= CARD_GAP

    cur_y = min(ly, ry) - 6
    cur_y = draw_extras(cv, cur_y)
    cur_y -= 4

    draw_footer(cv)

    margin_above_footer = cur_y - FOOTER_H
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