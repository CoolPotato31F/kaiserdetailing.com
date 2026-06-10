"""
Kaiser's Detail Co. — Booking Server
Flask app that serves the public site, handles bookings (one per day),
and serves a password-protected admin panel.

Run locally:   python app.py
Production:     gunicorn -w 1 -b 0.0.0.0:8000 app:app
"""

import os
import sqlite3
import secrets
import json
import urllib.request
import urllib.parse
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, abort
)

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bookings.db")

# Admin password. Override with the ADMIN_PASSWORD env var in production.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Kaiser556!?!")

# Secret key for sessions.
# If FLASK_SECRET is set in the environment, use it (recommended for production).
# Otherwise, generate one once and write it to a file so all gunicorn workers
# and server restarts share the same key. Without a stable key, sessions are
# invalidated on every restart or across multiple workers, breaking admin login.
_secret_file = os.path.join(BASE_DIR, ".flask_secret")
if os.environ.get("FLASK_SECRET"):
    SECRET_KEY = os.environ["FLASK_SECRET"]
elif os.path.exists(_secret_file):
    with open(_secret_file) as _f:
        SECRET_KEY = _f.read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(_secret_file, "w") as _f:
        _f.write(SECRET_KEY)

# ── Pushover ──────────────────────────────────────────────────────────────────
# PUSHOVER_USER  — your user key (the one from your dashboard)
# PUSHOVER_TOKEN — the application token you register at pushover.net/apps/build
#                  It's free. Name it "Kaiser Detail Co." and copy the token here.
# Set both as environment variables in deploy/kaiser.service, or paste them below.
PUSHOVER_USER  = os.environ.get("PUSHOVER_USER",  "ubaux1odxuxcxsf43sa65f8uics4xz")
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "a6gtcbyyxj924ihs22gtej3gb3p2z7")   # ← paste your app token here

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY

# ──────────────────────────────────────────────────────────────────────────────
# Service / add-on catalog (server-side source of truth for prices)
# Prices are validated server-side so a tampered client can't change totals.
# ──────────────────────────────────────────────────────────────────────────────
SERVICES = {
    "interior_detail":     {"name": "Interior Detail",        "price": 100, "dur": "1h 30m"},
    "exterior_detail":     {"name": "Exterior Detail",        "price": 75,  "dur": "1h 30m"},
    "professional_detail": {"name": "Professional Detail",    "price": 150, "dur": "3h"},
    "showroom_detail":     {"name": "Showroom Detail",        "price": 225, "dur": "4h"},
    "engine_bay":          {"name": "Engine Bay Cleaning",    "price": 35,  "dur": "30m"},
    "quick_interior":      {"name": "Quick Interior Cleaning","price": 35,  "dur": "30m"},
    "quick_detail":        {"name": "Quick Detail",           "price": 55,  "dur": "1h"},
    "headlight":           {"name": "Headlight Restoration",  "price": 40,  "dur": "40m"},
    "decal_removal":       {"name": "Sticker / Decal Removal","price": 15,  "dur": "15m"},
}

ADDONS = {
    "tire_shine":     {"name": "Tire Shine",     "price": 10},
    "carpet_shampoo": {"name": "Carpet Shampoo", "price": 30},
    "wax":            {"name": "Wax",            "price": 30},
    "clay":           {"name": "Clay Service",   "price": 45},
    "rainx":          {"name": "RainX",          "price": 10},
    "quick_wash":     {"name": "Quick Wash",     "price": 20},
}

# Which add-ons are valid for each service (server-side validation)
SERVICE_ADDONS = {
    "interior_detail":     ["carpet_shampoo"],
    "exterior_detail":     ["wax", "clay", "rainx"],
    "professional_detail": ["carpet_shampoo", "clay", "rainx"],
    "showroom_detail":     ["clay", "rainx"],
    "engine_bay":          ["quick_wash"],
    "quick_interior":      ["carpet_shampoo", "quick_wash"],
    "quick_detail":        ["tire_shine"],
    "headlight":           ["quick_wash"],
    "decal_removal":       ["quick_wash"],
}

# Available arrival time slots offered to customers
TIME_SLOTS = [
    "9:00 AM", "10:00 AM", "11:00 AM",
    "12:00 PM", "1:00 PM", "2:00 PM",
]


# ──────────────────────────────────────────────────────────────────────────────
# Pushover notifications
# ──────────────────────────────────────────────────────────────────────────────
def notify(booking):
    """
    Fire a Pushover push notification for a new booking.
    Runs in the same thread — fast enough (Pushover responds in ~200ms).
    Silently logs and continues if it fails; a notification error must never
    break the booking confirmation the customer is waiting for.

    booking is a dict with keys: customer_name, service_name, addon_names,
    booking_date, arrival_time, total_price, contact_type, contact_value,
    street, city, state, notes, source.
    """
    if not PUSHOVER_TOKEN:
        app.logger.warning("Pushover: PUSHOVER_TOKEN not set — skipping notification.")
        return

    # Format date nicely: "2026-06-14" → "Sat Jun 14"
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(booking["booking_date"], "%Y-%m-%d")
        pretty_date = d.strftime("%a %b %-d")
    except Exception:
        pretty_date = booking["booking_date"]

    addons_line = ""
    if booking.get("addon_names"):
        addons_line = "\n+ " + ", ".join(booking["addon_names"])

    contact_label = "📞" if booking.get("contact_type") == "phone" else "✉️"
    vehicle_line = f"\n🚗 {booking['vehicle_type']}" if booking.get("vehicle_type") else ""
    notes_line = f"\nNotes: {booking['notes']}" if booking.get("notes") else ""
    source_tag = " [admin]" if booking.get("source") == "admin" else ""

    title   = f"📅 New Booking{source_tag} — {booking['service_name']}"
    message = (
        f"{booking['customer_name']}\n"
        f"{booking['service_name']}{addons_line}\n"
        f"{pretty_date} at {booking['arrival_time']} · ${booking['total_price']}\n"
        f"{booking['street']}, {booking['city']} {booking['state']}\n"
        f"{contact_label} {booking['contact_value']}"
        f"{vehicle_line}"
        f"{notes_line}"
    )

    payload = urllib.parse.urlencode({
        "token":   PUSHOVER_TOKEN,
        "user":    PUSHOVER_USER,
        "title":   title,
        "message": message,
        "sound":   "cashregister",   # satisfying sound for a new booking
        "priority": "0",             # normal priority
    }).encode()

    try:
        req = urllib.request.Request(
            "https://api.pushover.net/1/messages.json",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            if result.get("status") != 1:
                app.logger.error(f"Pushover error: {result}")
            else:
                app.logger.info("Pushover notification sent.")
    except Exception as e:
        # Never let a notification failure crash the booking response
        app.logger.error(f"Pushover failed: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_date  TEXT NOT NULL UNIQUE,   -- one booking per day (YYYY-MM-DD)
            arrival_time  TEXT NOT NULL,
            service_key   TEXT NOT NULL,
            service_name  TEXT NOT NULL,
            addons_json   TEXT NOT NULL DEFAULT '[]',
            total_price   INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            contact_type  TEXT NOT NULL,          -- 'phone' or 'email'
            contact_value TEXT NOT NULL,
            vehicle_type  TEXT NOT NULL DEFAULT '',
            street        TEXT NOT NULL,
            city          TEXT NOT NULL,
            state         TEXT NOT NULL,
            notes         TEXT DEFAULT '',
            agreed_terms  INTEGER NOT NULL DEFAULT 0,
            source        TEXT NOT NULL DEFAULT 'web', -- 'web' or 'admin'
            created_at    TEXT NOT NULL
        );
    """)
    conn.commit()
    # Migration: add vehicle_type column to existing databases without losing data
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # column already exists — safe to ignore
    conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def compute_total(service_key, addon_keys):
    """Server-side price calc. Raises ValueError on invalid input."""
    if service_key not in SERVICES:
        raise ValueError("Unknown service.")
    total = SERVICES[service_key]["price"]
    allowed = set(SERVICE_ADDONS.get(service_key, []))
    clean_addons = []
    for a in addon_keys:
        if a not in ADDONS:
            raise ValueError(f"Unknown add-on: {a}")
        if a not in allowed:
            raise ValueError(f"Add-on '{ADDONS[a]['name']}' is not available for this service.")
        total += ADDONS[a]["price"]
        clean_addons.append(a)
    return total, clean_addons


def valid_future_date(d_str):
    """Date must be valid YYYY-MM-DD and tomorrow or later (no same-day booking)."""
    try:
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
    except ValueError:
        return False
    return d > date.today()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────────────────────────────────────────
# Public site
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/availability")
def availability():
    """Return taken dates and the earliest bookable date (tomorrow)."""
    earliest = (date.today() + timedelta(days=1)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT booking_date FROM bookings WHERE booking_date >= ?",
        (earliest,)
    ).fetchall()
    conn.close()
    taken = [r["booking_date"] for r in rows]
    return jsonify({
        "taken": taken,
        "earliest": earliest,
        "time_slots": TIME_SLOTS,
    })


@app.route("/api/book", methods=["POST"])
def book():
    data = request.get_json(silent=True) or {}

    # Required fields
    booking_date = (data.get("date") or "").strip()
    arrival_time = (data.get("time") or "").strip()
    service_key  = (data.get("service") or "").strip()
    addon_keys   = data.get("addons") or []
    name         = (data.get("name") or "").strip()
    contact_type = (data.get("contact_type") or "").strip()
    contact_val  = (data.get("contact_value") or "").strip()
    street       = (data.get("street") or "").strip()
    city         = (data.get("city") or "").strip()
    state        = (data.get("state") or "").strip()
    vehicle_type = (data.get("vehicle_type") or "").strip()
    notes        = (data.get("notes") or "").strip()
    agreed       = bool(data.get("agreed_terms"))

    # Validation
    if not valid_future_date(booking_date):
        return jsonify({"ok": False, "error": "Please choose a valid date (today or later)."}), 400
    if arrival_time not in TIME_SLOTS:
        return jsonify({"ok": False, "error": "Please choose a valid arrival time."}), 400
    if not name:
        return jsonify({"ok": False, "error": "Name is required."}), 400
    if contact_type not in ("phone", "email"):
        return jsonify({"ok": False, "error": "Invalid contact type."}), 400
    if not contact_val:
        return jsonify({"ok": False, "error": "A phone number or email is required."}), 400
    if contact_type == "email" and "@" not in contact_val:
        return jsonify({"ok": False, "error": "Please enter a valid email."}), 400
    if contact_type == "phone" and sum(c.isdigit() for c in contact_val) < 10:
        return jsonify({"ok": False, "error": "Please enter a valid phone number."}), 400
    if not (street and city and state):
        return jsonify({"ok": False, "error": "Full address (street, city, state) is required."}), 400
    if not vehicle_type:
        return jsonify({"ok": False, "error": "Please select a vehicle type."}), 400
    if not agreed:
        return jsonify({"ok": False, "error": "You must agree to the terms to book."}), 400

    try:
        total, clean_addons = compute_total(service_key, addon_keys)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    service_name = SERVICES[service_key]["name"]

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO bookings
            (booking_date, arrival_time, service_key, service_name, addons_json,
             total_price, customer_name, contact_type, contact_value,
             vehicle_type, street, city, state, notes, agreed_terms, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            booking_date, arrival_time, service_key, service_name,
            json.dumps(clean_addons), total, name, contact_type, contact_val,
            vehicle_type, street, city, state, notes, 1, "web",
            datetime.now().isoformat(timespec="seconds"),
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Sorry — that day was just booked. Please pick another date."
        }), 409
    conn.close()

    # Fire push notification (non-blocking on failure)
    addon_names = [ADDONS[a]["name"] for a in clean_addons if a in ADDONS]
    notify({
        "customer_name": name,
        "service_name":  service_name,
        "addon_names":   addon_names,
        "booking_date":  booking_date,
        "arrival_time":  arrival_time,
        "total_price":   total,
        "contact_type":  contact_type,
        "contact_value": contact_val,
        "vehicle_type":  vehicle_type,
        "street": street, "city": city, "state": state,
        "notes":  notes,
        "source": "web",
    })

    return jsonify({
        "ok": True,
        "message": "Booking confirmed!",
        "total": total,
        "service": service_name,
        "date": booking_date,
        "time": arrival_time,
    })


# ──────────────────────────────────────────────────────────────────────────────
# Admin
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Incorrect password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY booking_date ASC, arrival_time ASC"
    ).fetchall()
    conn.close()

    bookings = []
    for r in rows:
        b = dict(r)
        addon_names = [ADDONS[a]["name"] for a in json.loads(b["addons_json"]) if a in ADDONS]
        b["addon_names"] = addon_names
        b["is_past"] = b["booking_date"] < date.today().isoformat()
        bookings.append(b)

    return render_template(
        "admin.html",
        bookings=bookings,
        services=SERVICES,
        addons=ADDONS,
        service_addons=SERVICE_ADDONS,
        time_slots=TIME_SLOTS,
        today=(date.today() + timedelta(days=1)).isoformat(),
    )


@app.route("/admin/create", methods=["POST"])
@login_required
def admin_create():
    f = request.form
    booking_date = (f.get("date") or "").strip()
    arrival_time = (f.get("time") or "").strip()
    service_key  = (f.get("service") or "").strip()
    addon_keys   = f.getlist("addons")
    name         = (f.get("name") or "").strip()
    contact_type = (f.get("contact_type") or "phone").strip()
    contact_val  = (f.get("contact_value") or "").strip()
    street       = (f.get("street") or "").strip()
    city         = (f.get("city") or "").strip()
    state        = (f.get("state") or "").strip()
    vehicle_type = (f.get("vehicle_type") or "").strip()
    notes        = (f.get("notes") or "").strip()

    if not valid_future_date(booking_date):
        return _admin_redirect("Invalid date.")
    if arrival_time not in TIME_SLOTS:
        return _admin_redirect("Invalid time.")
    if not name or not contact_val or not (street and city and state):
        return _admin_redirect("Name, contact, and full address are required.")
    if not vehicle_type:
        return _admin_redirect("Vehicle type is required.")
    try:
        total, clean_addons = compute_total(service_key, addon_keys)
    except ValueError as e:
        return _admin_redirect(str(e))

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO bookings
            (booking_date, arrival_time, service_key, service_name, addons_json,
             total_price, customer_name, contact_type, contact_value,
             vehicle_type, street, city, state, notes, agreed_terms, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            booking_date, arrival_time, service_key, SERVICES[service_key]["name"],
            json.dumps(clean_addons), total, name, contact_type, contact_val,
            vehicle_type, street, city, state, notes, 1, "admin",
            datetime.now().isoformat(timespec="seconds"),
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return _admin_redirect("That date already has a booking.")
    conn.close()

    # Fire push notification (non-blocking on failure)
    addon_names = [ADDONS[a]["name"] for a in clean_addons if a in ADDONS]
    notify({
        "customer_name": name,
        "service_name":  SERVICES[service_key]["name"],
        "addon_names":   addon_names,
        "booking_date":  booking_date,
        "arrival_time":  arrival_time,
        "total_price":   total,
        "contact_type":  contact_type,
        "contact_value": contact_val,
        "vehicle_type":  vehicle_type,
        "street": street, "city": city, "state": state,
        "notes":  notes,
        "source": "admin",
    })

    return _admin_redirect("Booking created.", ok=True)


@app.route("/admin/delete/<int:booking_id>", methods=["POST"])
@login_required
def admin_delete(booking_id):
    conn = get_db()
    conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return _admin_redirect("Booking deleted.", ok=True)


def _admin_redirect(msg, ok=False):
    session["flash"] = {"msg": msg, "ok": ok}
    return redirect(url_for("admin_dashboard"))


@app.context_processor
def inject_flash():
    flash = session.pop("flash", None)
    return {"flash": flash}


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000, debug=False)