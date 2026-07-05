#!/bin/bash

echo "🚗 Kaiser's Detail Co. — Push to GitHub"
echo "------------------------------------"

# Navigate to the project folder (adjust to wherever you keep it)
cd "$(dirname "$0")"

# Make sure the database is NOT tracked. If it was ever committed, remove it
# from the repo (this does NOT delete your local file — only untracks it).
# Keeping it out of git is what stops deploys from resurrecting old bookings.
git rm --cached --ignore-unmatch bookings.db bookings.db-wal bookings.db-shm bookings.db-journal >/dev/null 2>&1 || true

# Add all changes (the .gitignore keeps the DB and local files out).
git add .

# Commit with a timestamp message
git commit -m "update $(date '+%Y-%m-%d %H:%M:%S')"

# Push to GitHub (no --force; force-push can erase remote history)
git push origin main

echo "------------------------------------"
echo "✅ Done! Changes pushed to GitHub."
echo "On the VM, run:  git pull && sudo systemctl restart kaiser"