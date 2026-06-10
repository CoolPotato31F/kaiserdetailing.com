#!/bin/bash

set -e

APP_DIR="/home/fechnerkaiser1/kaiserdetailing.com"
VENV_DIR="$APP_DIR/venv"

echo "🚀 Starting deployment..."

cd $APP_DIR

echo "📥 Pulling latest code..."
git pull origin main

echo "🐍 Activating virtual environment..."
source $VENV_DIR/bin/activate

echo "📦 Installing requirements..."
pip install -r requirements.txt

echo "🔄 Restarting Gunicorn (systemd)..."
sudo systemctl restart gunicorn

echo "🌐 Reloading Nginx..."
sudo systemctl reload nginx

echo "✅ Deployment complete!"
