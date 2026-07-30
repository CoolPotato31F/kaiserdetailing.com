#!/bin/bash

echo "🚗 Kaiser's Detail Co. — Push to GitHub"
echo "------------------------------------"

# Navigate to the project folder (adjust to wherever you keep it)
cd "$(dirname "$0")"

# Safety: make sure the live database and secrets are NEVER committed.
# If any of them got tracked before .gitignore existed, untrack them now
# (removes from git index only — the local files stay put).
for f in bookings.db bookings.db-wal bookings.db-shm .flask_secret; do
    if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        echo "⚠️  Untracking $f (should never be in git)"
        git rm --cached "$f" -q
    fi
done

# Add all changes (bookings.db etc. are now excluded by .gitignore)
git add .

# Abort if the database somehow still got staged — better to stop than to
# push live data and have it overwrite the server on the next deploy.
if git diff --cached --name-only | grep -qE '(^|/)(bookings\.db|data/)'; then
    echo "❌ Refusing to push: a database file is staged. Check .gitignore."
    exit 1
fi

# Commit with a timestamp message (skip cleanly if nothing changed)
git commit -m "update $(date '+%Y-%m-%d %H:%M:%S')" || echo "ℹ️  Nothing to commit."

# Push to GitHub (no --force; force-push can erase remote history)
git push origin main

echo "------------------------------------"
echo "✅ Done! Changes pushed to GitHub."
echo "On the VM, run:  git pull && sudo systemctl restart kaiser"