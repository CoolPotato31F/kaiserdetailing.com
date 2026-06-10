#!/bin/bash

echo "🚗 Kaiser's Detail Co. — Push to GitHub"
echo "------------------------------------"

# Navigate to the project folder (adjust to wherever you keep it)
cd "$(dirname "$0")"

# Add all changes
git add .

# Commit with a timestamp message
git commit -m "update $(date '+%Y-%m-%d %H:%M:%S')"

# Push to GitHub (no --force; force-push can erase remote history)
git push origin main

echo "------------------------------------"
echo "✅ Done! Changes pushed to GitHub."
echo "On the VM, run:  git pull && sudo systemctl restart kaiser"
