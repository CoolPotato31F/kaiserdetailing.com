#!/bin/bash

set -e

APP_DIR="/home/fechnerkaiser1/kaiserdetailing.com"
# The database lives OUTSIDE the repo so git operations can never touch it.
DATA_DIR="${KAISER_DATA_DIR:-/home/fechnerkaiser1/kaiser-data}"
DB="$DATA_DIR/bookings.db"
VENV="$APP_DIR/venv"
SERVICE="kaiser"

echo "🚀 Kaiser's Detail Co. — Deploying..."
echo "──────────────────────────────────────"

mkdir -p "$DATA_DIR"
cd "$APP_DIR"

# ── Safety: the DB must not be inside the repo ───────────────────────────────
# If bookings.db is sitting in APP_DIR, the `git reset --hard` below can wipe
# it. Refuse to deploy until it's been migrated out.
if [ -f "$APP_DIR/bookings.db" ]; then
    echo "❌ Found bookings.db inside the repo at $APP_DIR."
    echo "   A deploy would risk overwriting it. Run ./migrate_db_out_of_repo.sh first."
    exit 1
fi

# Refuse to deploy if the DB is tracked by git — a reset would clobber it.
if git ls-files --error-unmatch bookings.db >/dev/null 2>&1; then
    echo "❌ bookings.db is tracked by git. Run ./migrate_db_out_of_repo.sh first."
    exit 1
fi

# ── Back up the database BEFORE touching git ─────────────────────────────────
echo "💾 Backing up database..."
mkdir -p "$DATA_DIR/backups"
if [ -f "$DB" ]; then
    BACKUP="$DATA_DIR/backups/bookings-$(date +%Y%m%d-%H%M%S).db"
    # Fold the WAL back into the main DB first. The app runs in WAL mode, so
    # recent writes live in bookings.db-wal until a checkpoint. Backing up the
    # main file alone would silently miss them.
    sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
    # .backup is safe on a live DB; a plain cp can catch a half-written WAL.
    sqlite3 "$DB" ".backup '$BACKUP'" 2>/dev/null || cp "$DB" "$BACKUP"

    # Verify the backup is readable before trusting it.
    if sqlite3 "$BACKUP" "PRAGMA integrity_check;" 2>/dev/null | grep -q "^ok$"; then
        ROWS=$(sqlite3 "$BACKUP" "SELECT COUNT(*) FROM bookings;" 2>/dev/null || echo "?")
        echo "   Saved $(basename "$BACKUP") ($ROWS bookings)"
    else
        echo "❌ Backup failed its integrity check. Aborting deploy."
        exit 1
    fi

    # Keep the 30 most recent, delete older ones.
    ls -1t "$DATA_DIR/backups"/bookings-*.db 2>/dev/null | tail -n +31 | xargs -r rm --
else
    echo "   No database yet — skipping (first deploy?)"
fi

# Pull latest from GitHub
echo "📥 Pulling latest code from GitHub..."
git fetch origin main
git reset --hard origin/main

# Install/update dependencies
echo "📦 Installing dependencies..."
$VENV/bin/pip install -r requirements.txt -q

# Apply any DB migrations (init_db is safe to run repeatedly)
echo "🗄️  Running DB migrations..."
KAISER_DATA_DIR="$DATA_DIR" $VENV/bin/python3 -c "from app import init_db; init_db(); print('   DB OK')"

# Restart the service
echo "🔄 Restarting $SERVICE service..."
sudo systemctl restart $SERVICE
sleep 3

# Reload nginx
echo "🌐 Reloading nginx..."
sudo systemctl reload nginx

# Verify everything is up
echo "──────────────────────────────────────"
STATUS=$(sudo systemctl is-active $SERVICE)
if [ "$STATUS" = "active" ]; then
    echo "✅ $SERVICE is running"
else
    echo "❌ $SERVICE failed to start — checking logs:"
    sudo journalctl -u $SERVICE -n 20 --no-pager
    exit 1
fi

# Quick health check
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
if [ "$HTTP" = "200" ]; then
    echo "✅ Site responding (HTTP $HTTP)"
else
    echo "⚠️  Site returned HTTP $HTTP"
fi

# Confirm data survived the deploy.
if [ -f "$DB" ]; then
    echo "✅ Bookings intact: $(sqlite3 "$DB" "SELECT COUNT(*) FROM bookings;" 2>/dev/null || echo "?")"
fi

echo "──────────────────────────────────────"
echo "✅ Deployment complete!"