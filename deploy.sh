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

# Back up the live database BEFORE touching git.
# `git reset --hard` overwrites every tracked file, so if bookings.db was ever
# committed, this reset would clobber real bookings with an old snapshot. We
# stash the live DB aside, do the reset, then restore it — the server's data
# always wins over anything in the repo.
echo "💾 Backing up live database..."
DB_BACKUP=""
if [ -f "$APP_DIR/bookings.db" ]; then
    DB_BACKUP="$APP_DIR/bookings.db.deploy-backup"
    cp -f "$APP_DIR/bookings.db" "$DB_BACKUP"
    # Copy WAL side-files too, if present, so no committed writes are lost.
    [ -f "$APP_DIR/bookings.db-wal" ] && cp -f "$APP_DIR/bookings.db-wal" "$DB_BACKUP-wal"
    [ -f "$APP_DIR/bookings.db-shm" ] && cp -f "$APP_DIR/bookings.db-shm" "$DB_BACKUP-shm"
    echo "   Backed up $(du -h "$APP_DIR/bookings.db" | cut -f1) database"
fi

# Pull latest from GitHub
echo "📥 Pulling latest code from GitHub..."
git fetch origin main
# Stop tracking the DB in case an older commit still has it (belt and braces).
git rm --cached --ignore-unmatch bookings.db bookings.db-wal bookings.db-shm bookings.db-journal >/dev/null 2>&1 || true
git reset --hard origin/main

# Restore the live database that we stashed before the reset.
if [ -n "$DB_BACKUP" ] && [ -f "$DB_BACKUP" ]; then
    echo "♻️  Restoring live database..."
    mv -f "$DB_BACKUP" "$APP_DIR/bookings.db"
    [ -f "$DB_BACKUP-wal" ] && mv -f "$DB_BACKUP-wal" "$APP_DIR/bookings.db-wal"
    [ -f "$DB_BACKUP-shm" ] && mv -f "$DB_BACKUP-shm" "$APP_DIR/bookings.db-shm"
    echo "   Database restored — existing bookings preserved"
fi

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