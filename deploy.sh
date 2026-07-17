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
 
# ── Back up the database BEFORE touching git ─────────────────────────────────
# `git reset --hard` below will overwrite any tracked file. If bookings.db ever
# got committed, that reset would wipe live data. Back up first, always.
echo "💾 Backing up database..."
mkdir -p "$APP_DIR/backups"
if [ -f "$APP_DIR/bookings.db" ]; then
    BACKUP="$APP_DIR/backups/bookings-$(date +%Y%m%d-%H%M%S).db"
    # .backup is safe on a live DB; a plain cp can catch a half-written WAL.
    sqlite3 "$APP_DIR/bookings.db" ".backup '$BACKUP'" 2>/dev/null \
        || cp "$APP_DIR/bookings.db" "$BACKUP"
    echo "   Saved $(basename $BACKUP)"
    # Keep the 30 most recent, delete older ones.
    ls -1t "$APP_DIR/backups"/bookings-*.db 2>/dev/null | tail -n +31 | xargs -r rm --
else
    echo "   No database yet — skipping (first deploy?)"
fi
 
# If the DB was ever committed, stop tracking it so future resets can't clobber
# it. This removes it from git's index only — the file on disk is untouched.
if git ls-files --error-unmatch bookings.db >/dev/null 2>&1; then
    echo "⚠️  bookings.db is tracked by git — untracking it now."
    git rm --cached bookings.db -q
    echo "   Commit this change and push, or it'll warn again next deploy."
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