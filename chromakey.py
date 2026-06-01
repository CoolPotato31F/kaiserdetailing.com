"""
Chroma Key Tool
--------------
• Open any image
• Eyedropper: click the canvas to sample the key color
• Sliders: Threshold (%), Smoothness (edge feather), Radius (color range)
• Export transparent PNG
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk, ImageFilter
import threading
import os

# ── Theme colors ──────────────────────────────────────────────────────────────
BG       = "#1a1a1f"
PANEL    = "#24242b"
CARD     = "#2d2d36"
ACCENT   = "#6c63ff"
ACCENT2  = "#a89cff"
TEXT     = "#f0eeff"
MUTED    = "#8888aa"
SUCCESS  = "#4caf82"
BORDER   = "#3a3a48"
SLIDER_T = "#6c63ff"

class ChromaKeyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chroma Key Tool")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(960, 640)

        # State
        self.source_img   = None   # original PIL Image (RGBA)
        self.result_img   = None   # keyed PIL Image (RGBA)
        self.display_img  = None   # PhotoImage for canvas
        self.key_color    = None   # (R, G, B) sampled color
        self.eyedrop_mode = False
        self.preview_bg   = "checker"  # "checker" | "black" | "white"
        self._debounce_id = None

        # Canvas zoom / pan
        self.zoom_factor  = 1.0
        self.pan_x        = 0
        self.pan_y        = 0
        self._drag_start  = None

        self._build_ui()
        self._apply_styles()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top toolbar ──────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=PANEL, height=52)
        toolbar.pack(side="top", fill="x")
        toolbar.pack_propagate(False)

        def tb_btn(parent, text, cmd, accent=False):
            bg_ = ACCENT if accent else CARD
            fg_ = TEXT
            b = tk.Button(parent, text=text, command=cmd,
                          bg=bg_, fg=fg_, activebackground=ACCENT2,
                          activeforeground=TEXT, relief="flat",
                          padx=14, pady=6, font=("Segoe UI", 9, "bold"),
                          cursor="hand2", bd=0)
            b.pack(side="left", padx=4, pady=8)
            return b

        tb_btn(toolbar, "📂  Open Image",  self._open_image)
        tb_btn(toolbar, "💾  Export PNG",  self._export, accent=True)

        self.eyedrop_btn = tk.Button(
            toolbar, text="🎯  Eyedropper",
            command=self._toggle_eyedrop,
            bg=CARD, fg=TEXT, activebackground=ACCENT,
            activeforeground=TEXT, relief="flat",
            padx=14, pady=6, font=("Segoe UI", 9, "bold"),
            cursor="hand2", bd=0)
        self.eyedrop_btn.pack(side="left", padx=4, pady=8)

        # Color swatch
        self.swatch_frame = tk.Frame(toolbar, bg=PANEL)
        self.swatch_frame.pack(side="left", padx=12, pady=10)
        tk.Label(self.swatch_frame, text="Key Color", bg=PANEL,
                 fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=(0,6))
        self.swatch = tk.Canvas(self.swatch_frame, width=32, height=28,
                                bg="#00ff00", highlightthickness=1,
                                highlightbackground=BORDER)
        self.swatch.pack(side="left")
        self.swatch_hex = tk.Label(self.swatch_frame, text="#00ff00",
                                   bg=PANEL, fg=MUTED, font=("Consolas", 8))
        self.swatch_hex.pack(side="left", padx=6)

        # Preview bg toggle
        tk.Label(toolbar, text="Preview:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(20, 4))
        self.bg_var = tk.StringVar(value="checker")
        for val, lbl in [("checker","Grid"), ("black","Black"), ("white","White")]:
            rb = tk.Radiobutton(toolbar, text=lbl, variable=self.bg_var,
                                value=val, command=self._refresh_canvas,
                                bg=PANEL, fg=MUTED, selectcolor=CARD,
                                activebackground=PANEL, activeforeground=TEXT,
                                font=("Segoe UI", 8), cursor="hand2")
            rb.pack(side="left", padx=2)

        # Status label
        self.status_lbl = tk.Label(toolbar, text="Open an image to begin",
                                   bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.status_lbl.pack(side="right", padx=16)

        # ── Main area: canvas + right panel ──────────────────────────────────
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)

        # Canvas area
        canvas_frame = tk.Frame(main, bg=BG)
        canvas_frame.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self.canvas = tk.Canvas(canvas_frame, bg="#111116",
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>",   self._canvas_click)
        self.canvas.bind("<ButtonPress-3>",   self._pan_start)
        self.canvas.bind("<B3-Motion>",        self._pan_move)
        self.canvas.bind("<MouseWheel>",       self._zoom)
        self.canvas.bind("<Button-4>",         self._zoom)  # Linux scroll up
        self.canvas.bind("<Button-5>",         self._zoom)  # Linux scroll down

        # Zoom controls
        zbar = tk.Frame(canvas_frame, bg=BG)
        zbar.pack(fill="x", pady=(2,0))
        tk.Button(zbar, text="−", command=lambda: self._zoom_step(-1),
                  bg=CARD, fg=TEXT, relief="flat", width=3,
                  font=("Segoe UI", 10, "bold"), cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(zbar, text="+", command=lambda: self._zoom_step(1),
                  bg=CARD, fg=TEXT, relief="flat", width=3,
                  font=("Segoe UI", 10, "bold"), cursor="hand2"
                  ).pack(side="left", padx=2)
        tk.Button(zbar, text="Fit", command=self._fit_zoom,
                  bg=CARD, fg=TEXT, relief="flat", padx=8,
                  font=("Segoe UI", 8), cursor="hand2"
                  ).pack(side="left", padx=2)
        self.zoom_lbl = tk.Label(zbar, text="100%", bg=BG, fg=MUTED,
                                 font=("Segoe UI", 8))
        self.zoom_lbl.pack(side="left", padx=8)

        # ── Right panel ───────────────────────────────────────────────────────
        right = tk.Frame(main, bg=PANEL, width=270)
        right.pack(side="right", fill="y", padx=(0,0))
        right.pack_propagate(False)

        def section(parent, title):
            f = tk.Frame(parent, bg=PANEL)
            f.pack(fill="x", padx=14, pady=(14, 4))
            tk.Label(f, text=title.upper(), bg=PANEL, fg=ACCENT2,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w")
            sep = tk.Frame(parent, bg=BORDER, height=1)
            sep.pack(fill="x", padx=14, pady=(0, 10))
            return parent

        def slider_row(parent, label, from_, to, default, fmt, var_name):
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", padx=14, pady=3)
            top = tk.Frame(row, bg=PANEL)
            top.pack(fill="x")
            tk.Label(top, text=label, bg=PANEL, fg=TEXT,
                     font=("Segoe UI", 9)).pack(side="left")
            val_lbl = tk.Label(top, text=fmt.format(default),
                               bg=PANEL, fg=ACCENT2,
                               font=("Consolas", 9, "bold"))
            val_lbl.pack(side="right")
            var = tk.DoubleVar(value=default)
            def on_change(v, lbl=val_lbl, f=fmt, dv=default):
                lbl.config(text=f.format(float(v)))
                self._schedule_update()
            sl = ttk.Scale(row, from_=from_, to=to, variable=var,
                           orient="horizontal", command=on_change,
                           style="Custom.Horizontal.TScale")
            sl.pack(fill="x", pady=(2,0))
            setattr(self, var_name, var)
            return var

        section(right, "Key Color")
        # Manual hex entry
        hex_row = tk.Frame(right, bg=PANEL)
        hex_row.pack(fill="x", padx=14, pady=(0,8))
        tk.Label(hex_row, text="Hex:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.hex_entry = tk.Entry(hex_row, width=9, bg=CARD, fg=TEXT,
                                  insertbackground=TEXT,
                                  font=("Consolas", 9), relief="flat",
                                  highlightthickness=1,
                                  highlightbackground=BORDER)
        self.hex_entry.insert(0, "#00ff00")
        self.hex_entry.pack(side="left", padx=6)
        tk.Button(hex_row, text="Set", command=self._set_color_from_hex,
                  bg=ACCENT, fg=TEXT, relief="flat", padx=8,
                  font=("Segoe UI", 8), cursor="hand2").pack(side="left")

        # Common color presets
        preset_row = tk.Frame(right, bg=PANEL)
        preset_row.pack(fill="x", padx=14, pady=(0,12))
        tk.Label(preset_row, text="Presets:", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0,6))
        for name, hex_ in [("Green","#00b140"), ("Blue","#0047ab"), ("Red","#cc0000")]:
            def make_cmd(h=hex_):
                return lambda: self._set_key_color_hex(h)
            tk.Button(preset_row, text=name, command=make_cmd(),
                      bg=CARD, fg=TEXT, relief="flat", padx=8, pady=2,
                      font=("Segoe UI", 8), cursor="hand2"
                      ).pack(side="left", padx=2)

        section(right, "Chroma Settings")
        slider_row(right, "Threshold  (similarity %)", 0, 100, 30, "{:.0f}%", "thresh_var")
        slider_row(right, "Radius  (color spread)",    0, 100, 20, "{:.0f}",  "radius_var")

        section(right, "Edge Refinement")
        slider_row(right, "Smoothness  (feather px)",  0, 20,  2,  "{:.1f}", "smooth_var")
        slider_row(right, "Spill Suppress  (%)",       0, 100, 30, "{:.0f}%","spill_var")

        section(right, "Export")
        tk.Button(right, text="💾  Save Transparent PNG",
                  command=self._export,
                  bg=ACCENT, fg=TEXT, activebackground=ACCENT2,
                  activeforeground=TEXT, relief="flat",
                  padx=14, pady=10,
                  font=("Segoe UI", 10, "bold"), cursor="hand2"
                  ).pack(fill="x", padx=14, pady=4)

        # Image info
        self.info_lbl = tk.Label(right, text="No image loaded",
                                 bg=PANEL, fg=MUTED,
                                 font=("Segoe UI", 7), wraplength=230)
        self.info_lbl.pack(padx=14, pady=8)

    def _apply_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Custom.Horizontal.TScale",
                    background=PANEL,
                    troughcolor=CARD,
                    sliderthickness=16,
                    sliderrelief="flat")
        s.map("Custom.Horizontal.TScale",
              background=[("active", PANEL)],
              foreground=[("active", ACCENT)])

    # ── Image loading ─────────────────────────────────────────────────────────

    def _open_image(self):
        path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"), ("All", "*.*")])
        if not path:
            return
        img = Image.open(path).convert("RGBA")
        self.source_img  = img
        self.result_img  = img.copy()
        fname = os.path.basename(path)
        w, h  = img.size
        self.info_lbl.config(text=f"{fname}\n{w} × {h} px")
        self.status_lbl.config(text=f"Loaded: {fname}")
        self._fit_zoom()
        self._refresh_canvas()
        if self.key_color:
            self._run_key()

    # ── Eyedropper ────────────────────────────────────────────────────────────

    def _toggle_eyedrop(self):
        self.eyedrop_mode = not self.eyedrop_mode
        if self.eyedrop_mode:
            self.eyedrop_btn.config(bg=ACCENT, text="🎯  Pick Color  (click canvas)")
            self.canvas.config(cursor="crosshair")
        else:
            self.eyedrop_btn.config(bg=CARD, text="🎯  Eyedropper")
            self.canvas.config(cursor="crosshair")

    def _canvas_click(self, event):
        if not self.source_img:
            return
        if self.eyedrop_mode:
            # Convert canvas coords → image coords
            cx = (event.x - self.pan_x) / self.zoom_factor
            cy = (event.y - self.pan_y) / self.zoom_factor
            iw, ih = self.source_img.size
            cx = max(0, min(int(cx), iw - 1))
            cy = max(0, min(int(cy), ih - 1))
            r, g, b, a = self.source_img.getpixel((cx, cy))
            self._set_key_color((r, g, b))
            self._toggle_eyedrop()  # auto-exit eyedrop mode
            self._run_key()

    def _set_key_color(self, rgb):
        self.key_color = rgb
        hex_ = "#{:02x}{:02x}{:02x}".format(*rgb)
        self.swatch.config(bg=hex_)
        self.swatch_hex.config(text=hex_)
        self.hex_entry.delete(0, "end")
        self.hex_entry.insert(0, hex_)

    def _set_key_color_hex(self, hex_):
        hex_ = hex_.strip().lstrip("#")
        try:
            r = int(hex_[0:2], 16)
            g = int(hex_[2:4], 16)
            b = int(hex_[4:6], 16)
            self._set_key_color((r, g, b))
            self._run_key()
        except Exception:
            pass

    def _set_color_from_hex(self):
        self._set_key_color_hex(self.hex_entry.get())

    # ── Chroma key algorithm ──────────────────────────────────────────────────

    def _schedule_update(self):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(80, self._run_key)

    def _run_key(self):
        if not self.source_img or not self.key_color:
            return
        self.status_lbl.config(text="Processing…")
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        src    = np.array(self.source_img, dtype=np.float32)
        kr, kg, kb = [c / 255.0 for c in self.key_color]

        thresh  = self.thresh_var.get() / 100.0   # 0–1
        radius  = self.radius_var.get() / 100.0   # 0–1
        smooth  = self.smooth_var.get()            # px
        spill   = self.spill_var.get() / 100.0    # 0–1

        r = src[:,:,0] / 255.0
        g = src[:,:,1] / 255.0
        b = src[:,:,2] / 255.0

        # Distance in RGB space from key color, weighted by radius
        dist = np.sqrt(
            ((r - kr) ** 2 +
             (g - kg) ** 2 +
             (b - kb) ** 2) / 3.0
        )

        # Adjust effective threshold with radius (radius expands the key range)
        effective_thresh = thresh * (1.0 + radius * 1.5)

        # Alpha: 0 where dist < thresh, ramp to 1 beyond
        alpha = np.clip((dist - thresh * 0.6) / max(effective_thresh * 0.4 + 1e-6, 0.01), 0, 1)

        # Spill suppression — reduce green channel where nearly keyed
        if spill > 0:
            spill_mask = 1.0 - alpha  # 1 = fully keyed pixels
            suppress   = spill_mask * spill
            if kg > max(kr, kb):          # green screen
                g = np.clip(g - suppress * g, 0, 1)
            elif kb > max(kr, kg):        # blue screen
                b = np.clip(b - suppress * b, 0, 1)
            elif kr > max(kg, kb):        # red screen
                r = np.clip(r - suppress * r, 0, 1)

        out = np.stack([r, g, b, alpha], axis=-1)
        out = np.clip(out * 255, 0, 255).astype(np.uint8)
        result = Image.fromarray(out, "RGBA")

        # Edge smoothing — feather the alpha channel
        if smooth > 0:
            a_img = Image.fromarray(out[:,:,3], "L")
            a_img = a_img.filter(ImageFilter.GaussianBlur(radius=smooth))
            result.putalpha(a_img)

        self.result_img = result
        self.after(0, self._refresh_canvas)
        self.after(0, lambda: self.status_lbl.config(text="Done ✓  —  Export when ready"))

    # ── Canvas rendering ──────────────────────────────────────────────────────

    def _refresh_canvas(self):
        if not self.result_img:
            return
        img = self.result_img.copy()

        bg_mode = self.bg_var.get()
        if bg_mode == "checker":
            bg = self._make_checker(img.size)
        elif bg_mode == "black":
            bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        else:
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))

        composed = Image.alpha_composite(bg, img)

        # Apply zoom
        w = int(composed.width  * self.zoom_factor)
        h = int(composed.height * self.zoom_factor)
        if w < 1 or h < 1:
            return
        composed = composed.resize((w, h), Image.LANCZOS)

        self.display_img = ImageTk.PhotoImage(composed)
        self.canvas.delete("all")
        self.canvas.create_image(self.pan_x, self.pan_y,
                                 anchor="nw", image=self.display_img)

    def _make_checker(self, size, sq=16):
        w, h = size
        arr  = np.zeros((h, w, 4), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                if (x // sq + y // sq) % 2 == 0:
                    arr[y,x] = [200, 200, 200, 255]
                else:
                    arr[y,x] = [150, 150, 150, 255]
        return Image.fromarray(arr, "RGBA")

    # ── Zoom / Pan ────────────────────────────────────────────────────────────

    def _fit_zoom(self):
        if not self.source_img:
            return
        cw = self.canvas.winfo_width()  or 700
        ch = self.canvas.winfo_height() or 500
        iw, ih = self.source_img.size
        self.zoom_factor = min(cw / iw, ch / ih, 1.0)
        self.pan_x = (cw - iw * self.zoom_factor) / 2
        self.pan_y = (ch - ih * self.zoom_factor) / 2
        self.zoom_lbl.config(text=f"{int(self.zoom_factor*100)}%")
        self._refresh_canvas()

    def _zoom_step(self, direction):
        self.zoom_factor = max(0.05, min(8.0, self.zoom_factor * (1.2 ** direction)))
        self.zoom_lbl.config(text=f"{int(self.zoom_factor*100)}%")
        self._refresh_canvas()

    def _zoom(self, event):
        delta = 0
        if event.num == 4 or event.delta > 0:
            delta = 1
        elif event.num == 5 or event.delta < 0:
            delta = -1
        self._zoom_step(delta)

    def _pan_start(self, event):
        self._drag_start = (event.x - self.pan_x, event.y - self.pan_y)

    def _pan_move(self, event):
        if self._drag_start:
            self.pan_x = event.x - self._drag_start[0]
            self.pan_y = event.y - self._drag_start[1]
            self._refresh_canvas()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self.result_img:
            messagebox.showwarning("No image", "Open and key an image first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save Transparent PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")])
        if path:
            self.result_img.save(path)
            self.status_lbl.config(text=f"Saved → {os.path.basename(path)}")
            messagebox.showinfo("Saved", f"Exported:\n{path}")


if __name__ == "__main__":
    app = ChromaKeyApp()
    app.geometry("1200x760")
    app.mainloop()