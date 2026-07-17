#!/bin/bash

echo "🚗 Kaiser's Detail Co. — Push to GitHub"
echo "------------------------------------"

# Navigate to the project folder (adjust to wherever you keep it)
cd "$(dirname "$0")"

# Never let a database file reach the repo. If one gets committed, the deploy's
# `git reset --hard` will overwrite the live DB on the VM and destroy real
# bookings and finances. .gitignore covers this, but check anyway.
if git ls-files --error-unmatch bookings.db >/dev/null 2>&1; then
    echo "⚠️  bookings.db is tracked by git — untracking it now."
    git rm --cached bookings.db -q
fi

# Stage everything, then defensively unstage any DB files that slipped through.
git add .
git reset -q -- '*.db' '*.db-wal' '*.db-shm' backups/ 2>/dev/null || true

if git diff --cached --name-only | grep -qE '\.db($|-wal|-shm)'; then
    echo "❌ A database file is still staged. Aborting push."
    exit 1
fi

if git diff --cached --quiet; then
    echo "ℹ️  Nothing to commit."
    exit 0
fi

# Commit with a timestamp message
git commit -m "update $(date '+%Y-%m-%d %H:%M:%S')"

# Push to GitHub (no --force; force-push can erase remote history)
git push origin main

echo "------------------------------------"
echo "✅ Done! Changes pushed to GitHub."
echo "On the VM, run:  ./deploy.sh"