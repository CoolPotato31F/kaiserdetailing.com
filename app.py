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
from werkzeug.middleware.proxy_fix import ProxyFix

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
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "a6gtcbyyxj924ihs22gtej3gb3p2z7")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Session cookie settings — required for login to work over HTTPS via nginx
app.config.update(
    SESSION_COOKIE_SECURE=True,       # only send cookie over HTTPS
    SESSION_COOKIE_HTTPONLY=True,     # JS can't read the cookie
    SESSION_COOKIE_SAMESITE="Lax",    # cookie survives normal navigation
)

# ──────────────────────────────────────────────────────────────────────────────
# Service / add-on catalog (server-side source of truth for prices)
# Prices are validated server-side so a tampered client can't change totals.
# ──────────────────────────────────────────────────────────────────────────────
# DEFAULT_SERVICES seeds the `packages` table the first time the DB is created.
# After that, the ADMIN PANEL is the source of truth — prices, durations,
# names, and visibility all live in the database and are edited from /admin.
# The "order" field controls the display order (lower = shown first).
DEFAULT_SERVICES = {
    "showroom_detail":     {"name": "Showroom Detail",         "price": 225, "dur": "5h",     "visible": 1, "order": 1},
    "professional_detail": {"name": "Professional Detail",     "price": 150, "dur": "4h",     "visible": 1, "order": 2},
    "interior_detail":     {"name": "Interior Detail",         "price": 100, "dur": "4h 30m", "visible": 1, "order": 3},
    "exterior_detail":     {"name": "Exterior Detail",         "price": 75,  "dur": "2h 30m", "visible": 1, "order": 4},
    "engine_bay":          {"name": "Engine Bay Cleaning",     "price": 55,  "dur": "30m",    "visible": 1, "order": 5},
    "decal_removal":       {"name": "Sticker / Decal Removal", "price": 15,  "dur": "15m",    "visible": 1, "order": 6},
}


def load_services(visible_only=False):
    """
    Load the service catalog from the database (the admin panel is the source
    of truth). Returns an ordered dict keyed by service_key, each value holding
    name / price / dur / visible / order. Falls back to DEFAULT_SERVICES if the
    table isn't ready yet (e.g. during very first init).
    """
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM packages"
            + (" WHERE visible = 1" if visible_only else "")
            + " ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        conn.close()
    except Exception:
        rows = []

    if not rows:
        # Fallback so the site never breaks if the table is momentarily missing
        out = {}
        for k, v in sorted(DEFAULT_SERVICES.items(), key=lambda kv: kv[1]["order"]):
            if visible_only and not v.get("visible", 1):
                continue
            out[k] = {"name": v["name"], "price": v["price"], "dur": v["dur"],
                      "visible": v.get("visible", 1), "order": v["order"]}
        return out

    out = {}
    for r in rows:
        out[r["service_key"]] = {
            "name":    r["name"],
            "price":   r["price"],
            "dur":     r["duration"],
            "visible": r["visible"],
            "order":   r["sort_order"],
        }
    return out


# Backwards-compatible module-level catalog. Kept in sync at request time by
# refresh_services() so existing references to SERVICES keep working, but the
# database is always authoritative. Do NOT rely on this being static.
# Seed with defaults at import time; the real values are loaded from the DB
# after init_db() runs (get_db isn't defined yet at this point in the module).
SERVICES = {
    k: {"name": v["name"], "price": v["price"], "dur": v["dur"],
        "visible": v.get("visible", 1), "order": v["order"]}
    for k, v in sorted(DEFAULT_SERVICES.items(), key=lambda kv: kv[1]["order"])
}


def refresh_services():
    """Reload SERVICES from the DB. Called at the start of price-sensitive requests."""
    global SERVICES
    SERVICES = load_services()
    return SERVICES

ADDONS = {
    "carpet_shampoo": {"name": "Carpet Shampoo", "price": 30, "dur": "30m"},
    "wax":            {"name": "Wax",            "price": 30, "dur": "45m"},
    "clay":           {"name": "Clay Service",   "price": 45, "dur": "35m"},
    "rainx":          {"name": "RainX",          "price": 10, "dur": "15m"},
}

# Which add-ons are valid for each service (server-side validation)
SERVICE_ADDONS = {
    "interior_detail":     ["carpet_shampoo"],
    "exterior_detail":     ["wax", "clay", "rainx"],
    "professional_detail": ["carpet_shampoo", "clay", "rainx"],
    "showroom_detail":     ["clay", "rainx"],
    "engine_bay":          [],
    "decal_removal":       [],
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
    if booking.get("vehicle_type") in LARGE_VEHICLES:
        vehicle_line += f" (+${LARGE_VEHICLE_SURCHARGE} large vehicle)"
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("status") != 1:
                app.logger.error(f"Pushover error: {result}")
                return False, str(result)
            else:
                app.logger.info("Pushover notification sent.")
                return True, None
    except Exception as e:
        # Never let a notification failure crash the booking response
        app.logger.error(f"Pushover failed: {e}")
        return False, str(e)


def notify_review(review):
    """
    Fire a Pushover push notification for a new customer review.
    Never lets a notification failure break the review submission response.

    review is a dict with keys: service, website_ease, quality, communication,
    value_rating, recommend, favorite, improve, customer_name, email.
    """
    if not PUSHOVER_TOKEN:
        app.logger.warning("Pushover: PUSHOVER_TOKEN not set — skipping notification.")
        return

    stars = "★" * review["quality"] + "☆" * (5 - review["quality"])
    name = review.get("customer_name") or "Anonymous"

    lines = [
        f"{name} — {review['service']}",
        f"{stars}  (quality {review['quality']}/5)",
        f"Website ease: {review['website_ease']}/5",
    ]
    if review.get("communication"):
        lines.append(f"Communication: {review['communication']}/5")
    if review.get("recommend"):
        lines.append(f"Would recommend: {review['recommend']}/5")
    if review.get("value_rating"):
        lines.append(f"Good value: {review['value_rating']}")
    if review.get("favorite"):
        lines.append(f"Liked: {review['favorite']}")
    if review.get("improve"):
        lines.append(f"Improve: {review['improve']}")

    payload = urllib.parse.urlencode({
        "token":   PUSHOVER_TOKEN,
        "user":    PUSHOVER_USER,
        "title":   "⭐ New Customer Review",
        "message": "\n".join(lines),
        "sound":   "magic",
        "priority": "0",
    }).encode()

    try:
        req = urllib.request.Request(
            "https://api.pushover.net/1/messages.json",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("status") != 1:
                app.logger.error(f"Pushover error: {result}")
                return False, str(result)
            else:
                app.logger.info("Pushover review notification sent.")
                return True, None
    except Exception as e:
        app.logger.error(f"Pushover review notification failed: {e}")
        return False, str(e)


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
            booking_date  TEXT NOT NULL,          -- one ACTIVE booking per day (see partial index)
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
            created_at    TEXT NOT NULL,
            deleted       INTEGER NOT NULL DEFAULT 0   -- soft-delete: 1 = hidden, never lost
        );
    """)
    conn.commit()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocked_times (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            block_date   TEXT NOT NULL,          -- range START date (YYYY-MM-DD)
            block_type   TEXT NOT NULL,           -- 'range' (legacy: 'full_day'/'before'/'after')
            before_time  TEXT DEFAULT NULL,       -- legacy: block all slots before this time
            after_time   TEXT DEFAULT NULL,       -- legacy: block all slots after this time
            end_date     TEXT DEFAULT NULL,       -- range END date (YYYY-MM-DD)
            start_time   TEXT DEFAULT NULL,       -- range START time (e.g. "9:00 AM")
            end_time     TEXT DEFAULT NULL,       -- range END time (e.g. "2:00 PM")
            note         TEXT DEFAULT '',         -- admin note e.g. "Family trip"
            created_at   TEXT NOT NULL
        );
    """)
    conn.commit()
    # Migration: add range columns to existing databases without losing data
    for _col in ("end_date", "start_time", "end_time"):
        try:
            conn.execute(f"ALTER TABLE blocked_times ADD COLUMN {_col} TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            pass  # column already exists — safe to ignore
    # Migration: add vehicle_type column to existing databases without losing data
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # column already exists — safe to ignore

    # Migration: add a soft-delete flag. Deleting a booking sets deleted=1 so the
    # record is NEVER lost from the file — it's just hidden from the admin view.
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # column already exists — safe to ignore

    # Enforce "one ACTIVE booking per day" at the DB level while still allowing a
    # freed-up (soft-deleted) date to be booked again. The old table-level UNIQUE
    # constraint on booking_date blocked that, so we use a partial unique index
    # that only applies to non-deleted rows.
    #
    # Older databases were created with `booking_date TEXT NOT NULL UNIQUE`, which
    # can't be dropped without rebuilding the table. Detect that and rebuild once.
    cols = conn.execute("PRAGMA index_list('bookings')").fetchall()
    has_table_unique = any(
        (row[3] if len(row) > 3 else "") == "u"  # origin 'u' = created by a UNIQUE constraint
        for row in cols
    )
    if has_table_unique:
        conn.executescript("""
            PRAGMA foreign_keys=off;
            BEGIN TRANSACTION;
            ALTER TABLE bookings RENAME TO bookings_old;
            CREATE TABLE bookings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_date  TEXT NOT NULL,
                arrival_time  TEXT NOT NULL,
                service_key   TEXT NOT NULL,
                service_name  TEXT NOT NULL,
                addons_json   TEXT NOT NULL DEFAULT '[]',
                total_price   INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                contact_type  TEXT NOT NULL,
                contact_value TEXT NOT NULL,
                vehicle_type  TEXT NOT NULL DEFAULT '',
                street        TEXT NOT NULL,
                city          TEXT NOT NULL,
                state         TEXT NOT NULL,
                notes         TEXT DEFAULT '',
                agreed_terms  INTEGER NOT NULL DEFAULT 0,
                source        TEXT NOT NULL DEFAULT 'web',
                created_at    TEXT NOT NULL,
                deleted       INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO bookings
                (id, booking_date, arrival_time, service_key, service_name,
                 addons_json, total_price, customer_name, contact_type, contact_value,
                 vehicle_type, street, city, state, notes, agreed_terms, source,
                 created_at, deleted)
            SELECT
                 id, booking_date, arrival_time, service_key, service_name,
                 addons_json, total_price, customer_name, contact_type, contact_value,
                 vehicle_type, street, city, state, notes, agreed_terms, source,
                 created_at, COALESCE(deleted, 0)
            FROM bookings_old;
            DROP TABLE bookings_old;
            COMMIT;
            PRAGMA foreign_keys=on;
        """)
        conn.commit()

    # Partial unique index: at most one non-deleted booking per date.
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_active_date
        ON bookings (booking_date) WHERE deleted = 0
    """)
    conn.commit()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            service        TEXT NOT NULL,
            website_ease   INTEGER NOT NULL,       -- 1-5
            quality        INTEGER NOT NULL,       -- 1-5
            communication  INTEGER,                -- 1-5
            value_rating   TEXT,                   -- 'Yes' / 'Somewhat' / 'No'
            recommend      INTEGER,                -- 1-5
            favorite       TEXT DEFAULT '',
            improve        TEXT DEFAULT '',
            customer_name  TEXT DEFAULT '',
            email          TEXT DEFAULT '',
            created_at     TEXT NOT NULL
        );
    """)
    conn.commit()

    # ── Packages (editable service catalog) ────────────────────────────────
    # Prices, durations, names, and visibility all live here so the admin can
    # change them from the dashboard and have them persist. Seeded once from
    # DEFAULT_SERVICES; after that the admin panel owns this table.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            service_key  TEXT NOT NULL UNIQUE,    -- stable id used in bookings/URLs
            name         TEXT NOT NULL,
            price        INTEGER NOT NULL,
            duration     TEXT NOT NULL DEFAULT '',
            visible      INTEGER NOT NULL DEFAULT 1,  -- 1 = shown on site, 0 = hidden
            sort_order   INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()

    # ── Site stats (persistent counters) ───────────────────────────────────
    # A simple key/value counter table that survives server restarts. Used to
    # track things like how many visitors arrived from Facebook (fbclid). The
    # counters live in the same SQLite file as everything else, so they persist
    # across restarts and deploys just like bookings do.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_stats (
            stat_key    TEXT PRIMARY KEY,
            count       INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT
        );
    """)
    conn.commit()

    # Seed defaults only if the table is empty (first run). We never overwrite
    # existing rows, so admin edits are preserved across restarts/deploys.
    existing = conn.execute("SELECT COUNT(*) AS c FROM packages").fetchone()["c"]
    if existing == 0:
        for key, v in DEFAULT_SERVICES.items():
            conn.execute(
                "INSERT INTO packages (service_key, name, price, duration, visible, sort_order) "
                "VALUES (?,?,?,?,?,?)",
                (key, v["name"], v["price"], v["dur"], v.get("visible", 1), v["order"]),
            )
        conn.commit()

    conn.close()

    # Now that the table exists and is seeded, load the real catalog into the
    # module-level SERVICES so price validation uses the admin's values.
    refresh_services()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
LARGE_VEHICLES = {"Minivan", "SUV"}
LARGE_VEHICLE_SURCHARGE = 25
# Only services that involve interior work qualify for the large-vehicle surcharge
LARGE_VEHICLE_SERVICES = {
    "interior_detail", "professional_detail", "showroom_detail",
}


def compute_total(service_key, addon_keys, vehicle_type=""):
    """Server-side price calc. Raises ValueError on invalid input."""
    if service_key not in SERVICES:
        raise ValueError("Unknown service.")
    total = SERVICES[service_key]["price"]
    # Large vehicle surcharge — only on services involving interior work
    if vehicle_type in LARGE_VEHICLES and service_key in LARGE_VEHICLE_SERVICES:
        total += LARGE_VEHICLE_SURCHARGE
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


def bump_stat(key, amount=1):
    """
    Increment a persistent counter in the site_stats table by `amount`.
    Creates the row if it doesn't exist yet. Any failure is swallowed so a
    tracking hiccup never breaks the page the visitor is trying to load.
    """
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO site_stats (stat_key, count, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(stat_key) DO UPDATE SET "
            "count = count + excluded.count, updated_at = excluded.updated_at",
            (key, amount, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.warning("bump_stat(%s) failed: %s", key, e)


def get_stat(key):
    """Read a persistent counter. Returns 0 if it doesn't exist."""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT count FROM site_stats WHERE stat_key = ?", (key,)
        ).fetchone()
        conn.close()
        return row["count"] if row else 0
    except Exception:
        return 0


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
    # Facebook click tracking. When someone taps the link from a Facebook post,
    # Facebook appends a ?fbclid=... parameter to the URL. We count each such
    # visit in the persistent site_stats table so it survives server restarts.
    # We only count once per browser session (via a session flag) so a single
    # visitor refreshing the page doesn't inflate the number.
    if request.args.get("fbclid") and not session.get("counted_fb"):
        bump_stat("fb_visits")
        session["counted_fb"] = True
    return render_template("index.html")


@app.route("/review")
def review():
    return render_template("review.html")


@app.route("/api/review", methods=["POST"])
def submit_review():
    data = request.get_json(silent=True) or {}

    service = (data.get("service") or "").strip()
    favorite = (data.get("favorite") or "").strip()
    improve = (data.get("improve") or "").strip()
    value_rating = (data.get("value") or "").strip()
    customer_name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()

    if not service:
        return jsonify({"ok": False, "error": "Please select which service you had."}), 400

    def _to_int_1_5(v):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        return n if 1 <= n <= 5 else None

    website_ease = _to_int_1_5(data.get("website_ease"))
    quality = _to_int_1_5(data.get("quality"))
    communication = _to_int_1_5(data.get("communication"))
    recommend = _to_int_1_5(data.get("recommend"))

    if website_ease is None or quality is None:
        return jsonify({"ok": False, "error": "Please answer the required rating questions."}), 400

    conn = get_db()
    conn.execute("""
        INSERT INTO reviews
        (service, website_ease, quality, communication, value_rating, recommend,
         favorite, improve, customer_name, email, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        service, website_ease, quality, communication, value_rating, recommend,
        favorite, improve, customer_name, email,
        datetime.now().isoformat(timespec="seconds"),
    ))
    conn.commit()
    conn.close()

    notify_review({
        "service": service,
        "website_ease": website_ease,
        "quality": quality,
        "communication": communication,
        "value_rating": value_rating,
        "recommend": recommend,
        "favorite": favorite,
        "improve": improve,
        "customer_name": customer_name,
    })

    return jsonify({"ok": True})


@app.route("/api/availability")
def availability():
    """Return taken dates and the earliest bookable date (tomorrow)."""
    refresh_services()
    earliest = (date.today() + timedelta(days=1)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT booking_date FROM bookings WHERE booking_date >= ? AND deleted = 0",
        (earliest,)
    ).fetchall()
    taken = [r["booking_date"] for r in rows]

    # Blocked times — include any block that is still relevant today or later.
    # For range blocks the relevant end is end_date; legacy rows only have block_date.
    block_rows = conn.execute(
        "SELECT * FROM blocked_times WHERE COALESCE(end_date, block_date) >= ?",
        (earliest,)
    ).fetchall()
    conn.close()

    blocks = []
    for b in block_rows:
        row = dict(b)
        blocks.append({
            "id":          row["id"],
            "date":        row["block_date"],       # start date (or the only date for legacy)
            "type":        row["block_type"],
            "before_time": row["before_time"],       # legacy
            "after_time":  row["after_time"],        # legacy
            "end_date":    row.get("end_date"),
            "start_time":  row.get("start_time"),
            "end_time":    row.get("end_time"),
            "note":        row["note"],
        })

    # Visible packages, in display order, so the public site can hide disabled
    # ones and apply admin-set price/duration/name overrides.
    packages = [
        {"key": k, "name": v["name"], "price": v["price"],
         "dur": v["dur"], "order": v["order"]}
        for k, v in load_services(visible_only=True).items()
    ]

    return jsonify({
        "taken": taken,
        "earliest": earliest,
        "time_slots": TIME_SLOTS,
        "large_vehicles": list(LARGE_VEHICLES),
        "large_vehicle_surcharge": LARGE_VEHICLE_SURCHARGE,
        "large_vehicle_services": list(LARGE_VEHICLE_SERVICES),
        "blocks": blocks,
        "packages": packages,
    })


@app.route("/api/book", methods=["POST"])
def book():
    refresh_services()
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
        total, clean_addons = compute_total(service_key, addon_keys, vehicle_type)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # Check if the requested date/time is blocked (ranges + legacy blocks)
    conn = get_db()
    block_rows = conn.execute(
        "SELECT * FROM blocked_times "
        "WHERE block_date = ? OR (block_date <= ? AND COALESCE(end_date, block_date) >= ?)",
        (booking_date, booking_date, booking_date)
    ).fetchall()
    conn.close()
    slot_idx = TIME_SLOTS.index(arrival_time)
    unavailable = jsonify({"ok": False, "error": "Sorry — that time is not available for booking."}), 400
    for b in block_rows:
        if b["block_type"] == "range":
            start_date = b["block_date"]
            end_date   = b["end_date"] or b["block_date"]
            if not (start_date <= booking_date <= end_date):
                continue
            # Lower bound: honor start_time only on the start day
            first = TIME_SLOTS.index(b["start_time"]) if (booking_date == start_date and b["start_time"]) else 0
            # Upper bound: honor end_time only on the end day
            last  = TIME_SLOTS.index(b["end_time"])   if (booking_date == end_date   and b["end_time"])   else len(TIME_SLOTS) - 1
            if first <= slot_idx <= last:
                return unavailable
            continue
        # legacy blocks (only apply on the exact date)
        if b["block_date"] != booking_date:
            continue
        if b["block_type"] == "full_day":
            return jsonify({"ok": False, "error": "Sorry — that day is not available for booking."}), 400
        if b["block_type"] == "before" and b["before_time"]:
            if slot_idx < TIME_SLOTS.index(b["before_time"]):
                return jsonify({"ok": False, "error": f"Sorry — arrivals before {b['before_time']} are not available that day."}), 400
        if b["block_type"] == "after" and b["after_time"]:
            if slot_idx > TIME_SLOTS.index(b["after_time"]):
                return jsonify({"ok": False, "error": f"Sorry — arrivals after {b['after_time']} are not available that day."}), 400

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
    refresh_services()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM bookings WHERE deleted = 0 ORDER BY booking_date ASC, arrival_time ASC"
    ).fetchall()

    bookings = []
    for r in rows:
        b = dict(r)
        addon_names = [ADDONS[a]["name"] for a in json.loads(b["addons_json"]) if a in ADDONS]
        b["addon_names"] = addon_names
        b["is_past"] = b["booking_date"] < date.today().isoformat()
        bookings.append(b)

    # Blocked times — query before closing connection
    block_rows = conn.execute(
        "SELECT * FROM blocked_times ORDER BY block_date ASC"
    ).fetchall()

    review_rows = conn.execute(
        "SELECT * FROM reviews ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    # Full package catalog (including hidden ones) for the editable board
    conn2 = get_db()
    package_rows = conn2.execute(
        "SELECT * FROM packages ORDER BY sort_order ASC, id ASC"
    ).fetchall()
    conn2.close()
    packages = [dict(p) for p in package_rows]

    blocks = [dict(b) for b in block_rows]
    reviews = [dict(r) for r in review_rows]
    avg_quality = round(sum(r["quality"] for r in reviews) / len(reviews), 1) if reviews else None

    return render_template(
        "admin.html",
        bookings=bookings,
        blocks=blocks,
        reviews=reviews,
        avg_quality=avg_quality,
        services=SERVICES,
        packages=packages,
        addons=ADDONS,
        service_addons=SERVICE_ADDONS,
        time_slots=TIME_SLOTS,
        today=(date.today() + timedelta(days=1)).isoformat(),
        fb_visits=get_stat("fb_visits"),
    )


@app.route("/admin/create", methods=["POST"])
@login_required
def admin_create():
    refresh_services()
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
        total, clean_addons = compute_total(service_key, addon_keys, vehicle_type)
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


@app.route("/admin/packages", methods=["POST"])
@login_required
def admin_save_packages():
    """
    Save the whole package board in one shot. For each package we accept:
      visible_<key>   — checkbox ("on" if checked, absent if not)
      name_<key>      — display name
      price_<key>     — integer dollars
      duration_<key>  — free-text duration e.g. "4h 30m"
      order_<key>     — integer sort order
    Only keys that already exist in the packages table are updated.
    """
    f = request.form
    conn = get_db()
    rows = conn.execute("SELECT service_key FROM packages").fetchall()
    keys = [r["service_key"] for r in rows]

    errors = []
    for key in keys:
        name = (f.get(f"name_{key}") or "").strip()
        price_raw = (f.get(f"price_{key}") or "").strip()
        duration = (f.get(f"duration_{key}") or "").strip()
        order_raw = (f.get(f"order_{key}") or "").strip()
        visible = 1 if f.get(f"visible_{key}") else 0

        if not name:
            errors.append(f"{key}: name can't be empty")
            continue
        try:
            price = int(round(float(price_raw)))
            if price < 0:
                raise ValueError
        except ValueError:
            errors.append(f"{name}: invalid price")
            continue
        try:
            order = int(order_raw) if order_raw != "" else 0
        except ValueError:
            order = 0

        conn.execute(
            "UPDATE packages SET name=?, price=?, duration=?, visible=?, sort_order=? "
            "WHERE service_key=?",
            (name, price, duration, visible, order, key),
        )
    conn.commit()
    conn.close()
    refresh_services()

    if errors:
        return _admin_redirect("Saved with issues: " + "; ".join(errors))
    return _admin_redirect("Packages saved.", ok=True)


@app.route("/admin/block", methods=["POST"])
@login_required
def admin_add_block():
    f = request.form
    start_date = (f.get("start_date") or "").strip()
    end_date   = (f.get("end_date") or "").strip()
    start_time = (f.get("start_time") or "").strip() or None
    end_time   = (f.get("end_time") or "").strip() or None
    note       = (f.get("note") or "").strip()

    if not start_date or not end_date:
        return _admin_redirect("Please select a start and end date.")
    try:
        from datetime import datetime as _dt
        sd = _dt.strptime(start_date, "%Y-%m-%d").date()
        ed = _dt.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return _admin_redirect("Invalid date.")
    if ed < sd:
        return _admin_redirect("End date can't be before the start date.")

    # Validate times against the offered slots (a blank means the whole day edge)
    if start_time and start_time not in TIME_SLOTS:
        return _admin_redirect("Invalid start time.")
    if end_time and end_time not in TIME_SLOTS:
        return _admin_redirect("Invalid end time.")
    # On a single-day block, end time must not be before start time
    if sd == ed and start_time and end_time and \
       TIME_SLOTS.index(end_time) < TIME_SLOTS.index(start_time):
        return _admin_redirect("End time can't be before the start time.")

    conn = get_db()
    conn.execute("""
        INSERT INTO blocked_times
        (block_date, block_type, before_time, after_time,
         end_date, start_time, end_time, note, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (start_date, "range", None, None,
          end_date, start_time, end_time, note,
          datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()
    return _admin_redirect("Time period blocked.", ok=True)


@app.route("/admin/block/delete/<int:block_id>", methods=["POST"])
@login_required
def admin_delete_block(block_id):
    conn = get_db()
    conn.execute("DELETE FROM blocked_times WHERE id = ?", (block_id,))
    conn.commit()
    conn.close()
    return _admin_redirect("Block removed.", ok=True)


@app.route("/admin/test-notification", methods=["POST"])
@login_required
def admin_test_notification():
    if not PUSHOVER_TOKEN:
        return jsonify({"ok": False, "error": "PUSHOVER_TOKEN not set."})
    ok, err = notify({
        "customer_name": "Test — Kaiser's Detail Co.",
        "service_name":  "Test Notification",
        "addon_names":   [],
        "booking_date":  date.today().isoformat(),
        "arrival_time":  "Now",
        "total_price":   0,
        "contact_type":  "phone",
        "contact_value": "815-823-9485",
        "vehicle_type":  "Sedan",
        "street": "123 Main St", "city": "Plainfield", "state": "IL",
        "notes":  "This is a test notification from the admin panel.",
        "source": "admin",
    })
    if ok:
        return jsonify({"ok": True})
    else:
        return jsonify({"ok": False, "error": err or "Pushover request failed"})


@app.route("/admin/delete/<int:booking_id>", methods=["POST"])
@login_required
def admin_delete(booking_id):
    # Soft delete: hide it from the admin view but keep the record on file forever.
    conn = get_db()
    conn.execute("UPDATE bookings SET deleted = 1 WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return _admin_redirect("Booking removed from the list (kept on file).", ok=True)


@app.route("/admin/review/delete/<int:review_id>", methods=["POST"])
@login_required
def admin_delete_review(review_id):
    conn = get_db()
    conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    return _admin_redirect("Review deleted.", ok=True)


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