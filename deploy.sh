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