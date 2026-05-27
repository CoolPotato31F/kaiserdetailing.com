"""
Kaiser's Detail Co. — Door-to-Door Appointment Form
Simple, functional, fits on one page.
Run: python generate_form.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

W, H   = letter
M      = 0.5 * inch   # margin
CW     = W - 2 * M    # content width
LH     = 20           # standard line height

def cb(c, x, y, size=8):
    """Checkbox centered on text baseline y."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.7)
    c.rect(x, y - 1, size, size, fill=0, stroke=1)

def line(c, x, y, w):
    """Fill-in underline."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.5)
    c.line(x, y - 2, x + w, y - 2)

def hdr(c, x, y, text, w):
    """Section header — dark bar, white text."""
    c.setFillColor(colors.black)
    c.rect(x, y - 12, w, 13, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 4, y - 9, text.upper())
    return y - 12 - 10   # 10pt gap after bar

def label_field(c, x, y, label, lw, fw):
    """Label + underline on same row."""
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(x, y, label)
    line(c, x + lw, y, fw)

def build(out="kaiser_appointment_form.pdf"):
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle("Kaiser's Detail Co. — Appointment Form")
    y = H - M - 6

    # ── HEADER ──────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.black)
    c.drawString(M, y, "Kaiser's Detail Co. — Appointment Form")
    c.setFont("Helvetica", 7.5)
    c.drawRightString(M + CW, y, "kaiserdetailing.com  |  KaoFechner@outlook.com")
    y -= 14

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.line(M, y, M + CW, y)
    y -= 10

    # ── CUSTOMER INFO ────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Customer Info", CW) - 6

    half = CW / 2 - 4
    label_field(c, M,           y, "Name:",    36, half - 40)
    label_field(c, M+half+8,    y, "Phone:",   38, half - 42)
    y -= LH
    label_field(c, M,           y, "Email:",   36, CW - 40)
    y -= LH
    label_field(c, M,           y, "Address:", 48, CW - 52)
    y -= LH
    label_field(c, M,           y, "City/ZIP:", 50, half - 54)
    label_field(c, M+half+8,    y, "Best time to call:", 104, half - 108)
    y -= 13

    # ── VEHICLE INFO ─────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Vehicle Info", CW) - 6

    t = CW / 3 - 2
    label_field(c, M,         y, "Year:",  28, t - 32)
    label_field(c, M+t+4,     y, "Make:",  30, t - 34)
    label_field(c, M+2*(t+4), y, "Model:", 34, t - 38)
    y -= LH
    label_field(c, M,     y, "Color:",     34, t - 38)
    label_field(c, M+t+4, y, "Condition:", 54, t - 58)

    # Type checkboxes
    tx = M + 2*(t+4)
    c.setFont("Helvetica", 8); c.setFillColor(colors.black)
    c.drawString(tx, y, "Type:")
    for label, ox in [("Car",30),("Truck",58),("SUV",100)]:
        cb(c, tx+ox, y)
        c.drawString(tx+ox+11, y, label)
    y -= 6

    # ── APPOINTMENT ──────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Appointment", CW) -6

    label_field(c, M,        y, "Date:", 28, half - 32)
    label_field(c, M+half+8, y, "Time:", 28, half - 32)
    y -= 6

    # ── SERVICES ─────────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Services + Add-Ons  (check what applies, circle add-ons)", CW) - 6

    # Two columns
    L = M
    R = M + CW/2 + 6
    SW = CW/2 - 8   # service col width

    # helper: service row with checkbox, name/price, optional truck note
    def svc(cy, col, name, price, truck=None):
        cb(c, col, cy)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.black)
        c.drawString(col+11, cy, name)
        c.setFont("Helvetica", 8)
        c.drawRightString(col+SW, cy, price)
        cy -= 11
        if truck:
            # Indented truck/SUV checkbox row
            c.setStrokeColor(colors.black)
            c.setLineWidth(0.6)
            c.rect(col+10, cy - 1, 7, 7, fill=0, stroke=1)
            c.setFont("Helvetica-Oblique", 7)
            c.setFillColor(colors.black)
            c.drawString(col+20, cy, f"Truck / SUV add-on  {truck}")
            cy -= 10
        return cy

    # helper: addon line (indented, no checkbox — circle it)
    def addon(cy, col, name, price):
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.6)
        c.rect(col+10, cy - 1, 7, 7, fill=0, stroke=1)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.black)
        c.drawString(col+20, cy, name)
        c.drawRightString(col+SW, cy, price)
        return cy - 10

    ly = y
    ry = y

    # LEFT COLUMN
    ly = svc(ly, L, "Interior Detail", "$100", truck="+$25")
    ly = addon(ly, L, "Trunk Cleaning", "+$30")
    ly = addon(ly, L, "Carpet Shampoo", "+$30")
    ly -= 3

    ly = svc(ly, L, "Professional Detail", "$150", truck="+$25")
    ly = addon(ly, L, "Clay Service", "+$45")
    ly -= 3

    ly = svc(ly, L, "Quick Wash", "$20")
    ly = addon(ly, L, "Tire Shine", "+$10")
    ly = addon(ly, L, "RainX", "+$10")
    ly = addon(ly, L, "Wax", "+$30")
    ly -= 3

    ly = svc(ly, L, "Quick Detail", "$55")
    ly = addon(ly, L, "Tire Shine", "+$10")
    ly = addon(ly, L, "RainX", "+$10")
    ly = addon(ly, L, "Wax", "+$30")
    ly = addon(ly, L, "Carpet Shampoo", "+$30")
    ly -= 3

    ly = svc(ly, L, "Engine Bay Cleaning", "$35")
    ly -= 3

    # RIGHT COLUMN
    ry = svc(ry, R, "Exterior Detail", "$75")
    ry = addon(ry, R, "Clay Service", "+$45")
    ry = addon(ry, R, "RainX", "+$10")
    ry = addon(ry, R, "Tire Shine", "+$10")
    ry = addon(ry, R, "Wax", "+$30")
    ry = addon(ry, R, "Sticker/Decal Removal", "+$15")
    ry = addon(ry, R, "Engine Bay Cleaning", "+$35")
    ry -= 3

    ry = svc(ry, R, "Showroom Detail", "$225", truck="+$25")
    ry -= 3

    ry = svc(ry, R, "Quick Interior Cleaning", "$35", truck="+$10")
    ry = addon(ry, R, "Carpet Shampoo", "+$30")
    ry -= 3

    ry = svc(ry, R, "Headlight Restoration", "$40")
    ry -= 3

    ry = svc(ry, R, "Sticker/Decal Removal", "$15")
    ry -= 3

    y = min(ly, ry) - 8

    # vertical divider between columns
    c.setStrokeColor(colors.HexColor("#cccccc"))
    c.setLineWidth(0.5)
    c.line(M + CW/2 + 2, y + 8, M + CW/2 + 2, y + 8 + max(ly,ry) - y - 8)
    # just draw a short divider in the service area
    c.line(M + CW/2 + 2, min(ly,ry) - 2, M + CW/2 + 2, y + 200)

    # ── TOTALS ───────────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Totals", CW) - 6

    label_field(c, M,        y, "Services:", 52, half - 56)
    label_field(c, M+half+8, y, "Add-Ons:", 50, half - 54)
    y -= LH
    label_field(c, M,        y, "Truck/SUV upcharge:", 110, half - 114)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M+half+8, y, "GRAND TOTAL:  $")
    line(c, M+half+8+94, y, half - 98)
    y -= 6

    # ── NOTES ────────────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Notes", CW) - 6

    for _ in range(3):
        line(c, M, y, CW)
        y -= LH
    y -= 6

    # ── SIGNATURE ────────────────────────────────────────────────────────────
    y = hdr(c, M, y, "Agreement", CW)

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawString(M, y, "Customer agrees to selected services and pricing above.")
    y -= LH +6
    label_field(c, M,        y, "Signature:", 54, half - 58)
    label_field(c, M+half+8, y, "Date:",      28, half - 32)
    y -= LH
    label_field(c, M,        y, "Print Name:", 58, half - 62)
    y -= LH + 4

    # ── FOOTER ───────────────────────────────────────────────────────────────
    c.setFillColor(colors.black)
    c.rect(M, M, CW, 16, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 6.5)
    c.drawString(M+5, M+5, "Kaiser's Detail Co.  ·  kaiserdetailing.com  ·  KaoFechner@outlook.com")
    c.setFont("Helvetica-Bold", 6.5)
    c.drawRightString(M+CW-5, M+5, "Supporting a local student through college")

    c.save()
    print(f"✅ Saved: {out}")

if __name__ == "__main__":
    build()