#!/bin/bash
# Daily WM 2026 Re-Simulation Script
# Run with: bash resim.sh
# Fetches latest Polymarket odds and runs 100k sims with injury adjustments

set -e
cd "$(dirname "$0")"

DATE=$(date +%Y%m%d_%H%M)
echo "🔄 WM 2026 Re-Simulation — $DATE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run with injuries + Polymarket
echo ""
echo "📊 Running 100k simulation with injuries + Polymarket..."
python3 tournament_bonusfragen.py \
    --sims 100000 \
    --seed "$RANDOM" \
    --fetch-odds \
    --output "data/resim_${DATE}.txt" 2>&1

echo ""
echo "📊 Running 100k JSON output..."
python3 tournament_bonusfragen.py \
    --sims 100000 \
    --seed "$RANDOM" \
    --fetch-odds \
    --json \
    --output "data/resim_${DATE}.json" 2>&1

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Done! Results saved to data/resim_${DATE}.txt"
echo ""
echo "📋 Summary:"
cat "data/resim_${DATE}.txt" | tail -20
