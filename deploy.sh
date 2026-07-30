#!/bin/bash

set -e

APP_DIR="/home/fechnerkaiser1/kaiserdetailing.com"
VENV="$APP_DIR/venv"
SERVICE="kaiser"

echo "🚀 Kaiser's Detail Co. — Deploying..."
echo "──────────────────────────────────────"

cd $APP_DIR

# Kill anything holding port 8000 before we do anything
echo "🔌 Clearing port 8000..."
sudo fuser -k 8000/tcp 2>/dev/null || true
sleep 1

# ── Database location ────────────────────────────────────────────────────────
# The DB now lives in $APP_DIR/data, OUTSIDE anything git tracks, so
# `git reset --hard` below can never touch it. (app.py auto-migrates a legacy
# $APP_DIR/bookings.db into data/ on first run.)
DATA_DIR="$APP_DIR/data"
DB_FILE="$DATA_DIR/bookings.db"
mkdir -p "$DATA_DIR"

# One-time move: if an old DB is still sitting in the app root, relocate it now
# (before git reset, in case it was ever committed) so no bookings are lost.
if [ -f "$APP_DIR/bookings.db" ] && [ ! -f "$DB_FILE" ]; then
    echo "📦 Migrating legacy bookings.db -> data/bookings.db"
    mv "$APP_DIR/bookings.db"      "$DB_FILE"        2>/dev/null || true
    mv "$APP_DIR/bookings.db-wal"  "$DB_FILE-wal"    2>/dev/null || true
    mv "$APP_DIR/bookings.db-shm"  "$DB_FILE-shm"    2>/dev/null || true
fi

# ── Back up the database BEFORE touching git ─────────────────────────────────
echo "💾 Backing up database..."
mkdir -p "$APP_DIR/backups"
if [ -f "$DB_FILE" ]; then
    BACKUP="$APP_DIR/backups/bookings-$(date +%Y%m%d-%H%M%S).db"
    # .backup is safe on a live DB; a plain cp can catch a half-written WAL.
    sqlite3 "$DB_FILE" ".backup '$BACKUP'" 2>/dev/null \
        || cp "$DB_FILE" "$BACKUP"
    echo "   Saved $(basename $BACKUP)"
    # Keep the 30 most recent, delete older ones.
    ls -1t "$APP_DIR/backups"/bookings-*.db 2>/dev/null | tail -n +31 | xargs -r rm --
else
    echo "   No database yet — skipping (first deploy?)"
fi

# Safety net: if the DB (or its sidecars) was ever committed, untrack it so
# future resets can't clobber it. Removes from git's index only; disk untouched.
for f in bookings.db bookings.db-wal bookings.db-shm; do
    if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        echo "⚠️  $f is tracked by git — untracking it now."
        git rm --cached "$f" -q
    fi
done

# Pull latest from GitHub
echo "📥 Pulling latest code from GitHub..."
git fetch origin main
git reset --hard origin/main

# Install/update dependencies
echo "📦 Installing dependencies..."
$VENV/bin/pip install -r requirements.txt -q

# Apply any DB migrations (init_db is safe to run repeatedly)
echo "🗄️  Running DB migrations..."
$VENV/bin/python3 -c "from app import init_db; init_db(); print('   DB OK')"

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

echo "──────────────────────────────────────"
echo "✅ Deployment complete!"