#!/bin/bash

set -e

APP_DIR="/home/fechnerkaiser1/kaiserdetailing.com"
VENV_DIR="$APP_DIR/venv"

echo "🚀 Starting deployment..."

cd $APP_DIR

echo "📥 Pulling latest code..."
git pull origin main

echo "📦 Installing requirements..."
$VENV_DIR/bin/pip install -r requirements.txt

echo "🔄 Restarting kaiser service..."
sudo systemctl restart kaiser

echo "🌐 Reloading Nginx..."
sudo systemctl reload nginx

echo "✅ Deployment complete!"
echo "   Status: $(sudo systemctl is-active kaiser)"