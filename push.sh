#!/bin/bash

echo "🚗 Kaiser's Detail Co. — Auto Push"
echo "------------------------------------"

# Navigate to the project folder
cd /Users/kaiser/Documents/KaiserWebDesign/Client\ Websites/kaiserdetailing.com

# Add all changes
git add .

# Commit with a timestamp message
git commit -m "update $(date '+%Y-%m-%d %H:%M:%S')"

# Push to GitHub
git push origin main

echo "------------------------------------"
echo "✅ Done! Changes pushed to GitHub."