"""
Kaiser's Detail Co. — Before / After Image Maker
Load a BEFORE and an AFTER photo, choose side-by-side or top/bottom,
and save a labeled composite with the website footer.

Run:   python before_after.py
Requires: Pillow   ->  pip install pillow
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk

# ── BRAND ─────────────────────────────────────────────────────────────────────
WEBSITE   = "kaiserdetailing.com"
CHARCOAL  = (24, 24, 26)
GOLD      = (198, 162, 92)
WHITE     = (255, 255, 255)

PANEL     = 1000     # size of each photo's square cell (px) — fixes label/footer scale
FOOTER_H  = 140      # website footer band height
GAP       = 8        # divider between the two photos

# Bubble label — fixed pixel sizes so labels never scale with photo size
BUBBLE_FONT   = 72
BUBBLE_PADX   = 38
BUBBLE_PADY   = 22
BUBBLE_MARGIN = 34   # distance from the photo corner
BUBBLE_RADIUS = 24


def load_font(size, bold=True):
    """Load a TrueType font at the requested size, trying common locations on
    Windows, macOS, and Linux. Falls back to a size-aware default if needed."""
    if bold:
        candidates = [
            r"C:\Windows\Fonts\arialbd.ttf",      # Windows
            r"C:\Windows\Fonts\segoeuib.ttf",     # Windows (Segoe UI Bold)
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
            "/Library/Fonts/Arial Bold.ttf",      # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
            "DejaVuSans-Bold.ttf",
            "arialbd.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans.ttf",
            "arial.ttf",
        ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    # Last resort: newer Pillow lets load_default take a size; older ignores it.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit_cover(img, w, h):
    """Resize+crop an image to exactly fill w×h (center crop)."""
    img = img.convert("RGB")
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:          # too wide -> match height, crop width
        nh = h
        nw = round(h * src_ratio)
    else:                              # too tall -> match width, crop height
        nw = w
        nh = round(w / src_ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def draw_bubble(cell, text, corner):
    """Draw a rounded gold text bubble in the given corner ('tl' or 'tr')."""
    d = ImageDraw.Draw(cell, "RGBA")
    font = load_font(BUBBLE_FONT)

    l, t, r, b = d.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t

    bw = tw + BUBBLE_PADX * 2
    bh = th + BUBBLE_PADY * 2

    if corner == "tr":
        bx0 = PANEL - BUBBLE_MARGIN - bw
    else:  # 'tl'
        bx0 = BUBBLE_MARGIN
    by0 = BUBBLE_MARGIN
    bx1, by1 = bx0 + bw, by0 + bh

    # solid charcoal bubble with a thin gold border
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=BUBBLE_RADIUS,
                        fill=CHARCOAL + (235,), outline=GOLD + (255,), width=3)
    # text (account for the font's own top offset `t`)
    tx = bx0 + BUBBLE_PADX - l
    ty = by0 + BUBBLE_PADY - t
    d.text((tx, ty), text, font=font, fill=GOLD)


def labeled_cell(img, text, corner):
    """Return a square PANEL×PANEL photo cell with a bubble label overlaid."""
    cell = fit_cover(img, PANEL, PANEL)
    draw_bubble(cell, text, corner)
    return cell


def build_composite(before_img, after_img, layout):
    before_cell = labeled_cell(before_img, "BEFORE", "tr")
    after_cell = labeled_cell(after_img, "AFTER", "tl")

    cw, ch = before_cell.size  # PANEL × PANEL

    if layout == "side":
        body_w = cw * 2 + GAP
        body_h = ch
        canvas = Image.new("RGB", (body_w, body_h + FOOTER_H), CHARCOAL)
        canvas.paste(before_cell, (0, 0))
        canvas.paste(after_cell, (cw + GAP, 0))
    else:  # stacked
        body_w = cw
        body_h = ch * 2 + GAP
        canvas = Image.new("RGB", (body_w, body_h + FOOTER_H), CHARCOAL)
        canvas.paste(before_cell, (0, 0))
        canvas.paste(after_cell, (0, ch + GAP))

    # footer band with website
    draw = ImageDraw.Draw(canvas)
    fy = canvas.height - FOOTER_H
    draw.rectangle([0, fy, canvas.width, canvas.height], fill=CHARCOAL)
    draw.rectangle([0, fy, canvas.width, fy + 6], fill=GOLD)

    brand_font = load_font(60)
    site_font = load_font(54, bold=False)
    brand = "Kaiser's Detail Co."
    gap = 44
    bl, bt, br_, bb = draw.textbbox((0, 0), brand, font=brand_font)
    sl, st, sr, sb = draw.textbbox((0, 0), WEBSITE, font=site_font)
    bw, bh = br_ - bl, bb - bt
    sw, sh = sr - sl, sb - st
    total = bw + gap + sw
    x0 = (canvas.width - total) // 2
    band_mid = fy + 6 + (FOOTER_H - 6) // 2
    draw.text((x0 - bl, band_mid - bh // 2 - bt), brand, font=brand_font, fill=WHITE)
    draw.text((x0 + bw + gap - sl, band_mid - sh // 2 - st), WEBSITE, font=site_font, fill=GOLD)

    return canvas


# ── GUI ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        root.title("Kaiser's Detail Co. — Before / After Maker")
        root.configure(bg="#18181a")
        root.geometry("760x560")

        self.before_path = None
        self.after_path = None
        self.before_img = None
        self.after_img = None
        self.layout = tk.StringVar(value="side")
        self.preview_imgtk = None

        # header
        tk.Label(root, text="Before / After Maker", bg="#18181a", fg="#c6a25c",
                 font=("Helvetica", 20, "bold")).pack(pady=(16, 2))
        tk.Label(root, text="kaiserdetailing.com", bg="#18181a", fg="#cccccc",
                 font=("Helvetica", 11)).pack(pady=(0, 12))

        btns = tk.Frame(root, bg="#18181a")
        btns.pack()

        self.before_btn = tk.Button(btns, text="① Load BEFORE photo", width=22,
                                     command=self.load_before, bg="#2e2d2b", fg="white",
                                     relief="flat", font=("Helvetica", 11, "bold"))
        self.before_btn.grid(row=0, column=0, padx=8, pady=6)

        self.after_btn = tk.Button(btns, text="② Load AFTER photo", width=22,
                                    command=self.load_after, bg="#2e2d2b", fg="white",
                                    relief="flat", font=("Helvetica", 11, "bold"))
        self.after_btn.grid(row=0, column=1, padx=8, pady=6)

        # layout choice
        lf = tk.Frame(root, bg="#18181a")
        lf.pack(pady=10)
        tk.Label(lf, text="Layout:", bg="#18181a", fg="white",
                 font=("Helvetica", 11)).grid(row=0, column=0, padx=(0, 10))
        tk.Radiobutton(lf, text="Side by side", variable=self.layout, value="side",
                       bg="#18181a", fg="white", selectcolor="#2e2d2b",
                       activebackground="#18181a", activeforeground="#c6a25c",
                       command=self.refresh_preview).grid(row=0, column=1, padx=6)
        tk.Radiobutton(lf, text="Top / bottom", variable=self.layout, value="stacked",
                       bg="#18181a", fg="white", selectcolor="#2e2d2b",
                       activebackground="#18181a", activeforeground="#c6a25c",
                       command=self.refresh_preview).grid(row=0, column=2, padx=6)

        # save  — packed at the BOTTOM first so it is always visible
        self.save_btn = tk.Button(root, text="💾  Save Image", command=self.save,
                                  bg="#c6a25c", fg="#18181a", relief="flat",
                                  font=("Helvetica", 13, "bold"), state="disabled")
        self.save_btn.pack(side="bottom", fill="x", padx=20, pady=(8, 16))

        self.hint = tk.Label(root, text="Load both photos to enable saving",
                             bg="#18181a", fg="#888", font=("Helvetica", 9))
        self.hint.pack(side="bottom", pady=(0, 2))

        # preview  — fills remaining space above the save button
        self.preview = tk.Label(root, bg="#0f0f10", width=46, height=14,
                                text="Preview will appear here", fg="#666")
        self.preview.pack(pady=12, fill="both", expand=True, padx=20)

    def _pick(self):
        return filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp"), ("All files", "*.*")])

    def load_before(self):
        p = self._pick()
        if not p:
            return
        try:
            self.before_img = Image.open(p)
            self.before_path = p
            self.before_btn.config(text="✓ BEFORE loaded")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")
            return
        self.refresh_preview()

    def load_after(self):
        p = self._pick()
        if not p:
            return
        try:
            self.after_img = Image.open(p)
            self.after_path = p
            self.after_btn.config(text="✓ AFTER loaded")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")
            return
        self.refresh_preview()

    def refresh_preview(self):
        if not (self.before_img and self.after_img):
            return
        comp = build_composite(self.before_img, self.after_img, self.layout.get())
        self._composite = comp
        prev = comp.copy()
        prev.thumbnail((640, 360), Image.LANCZOS)
        self.preview_imgtk = ImageTk.PhotoImage(prev)
        self.preview.config(image=self.preview_imgtk, text="", width=prev.width, height=prev.height)
        self.save_btn.config(state="normal")
        self.hint.config(text="Ready — click Save Image", fg="#c6a25c")

    def save(self):
        if not (self.before_img and self.after_img):
            messagebox.showwarning("Missing", "Load both photos first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save composite",
            defaultextension=".jpg",
            initialfile="kaisers_before_after.jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")])
        if not path:
            return
        comp = build_composite(self.before_img, self.after_img, self.layout.get())
        try:
            if path.lower().endswith(".png"):
                comp.save(path)
            else:
                comp.save(path, quality=92)
            messagebox.showinfo("Saved", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()