#!/bin/bash
# Daily WM 2026 Re-Simulation Script
# Run with: bash resim.sh            (or: SEED=12345 bash resim.sh)
# Fetches Polymarket odds ONCE, then runs the txt and json outputs as ONE
# simulation pair: same seed, same odds snapshot. (Previously each run drew
# its own $RANDOM seed and re-fetched odds, so the "same" daily txt/json
# pair came from two different simulations.)

set -e
cd "$(dirname "$0")"

DATE=$(date +%Y%m%d_%H%M)
SEED=${SEED:-$RANDOM}
echo "🔄 WM 2026 Re-Simulation — $DATE"
echo "🌱 Seed: $SEED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Marker so we only trust a snapshot created by THIS run (a stale snapshot
# would silently diverge from the txt run if today's fetch failed).
MARKER=$(mktemp)

# Run 1 (txt): live fetch — auto-saves data/polymarket_snapshot_*.json
echo ""
echo "📊 Running 100k simulation with injuries + Polymarket (txt)..."
python3 tournament_bonusfragen.py \
    --sims 100000 \
    --seed "$SEED" \
    --fetch-odds \
    --output "data/resim_${DATE}.txt" 2>&1

SNAP=$(find data -name 'polymarket_snapshot_*.json' -newer "$MARKER" | sort | tail -1)
rm -f "$MARKER"

# Run 2 (json): SAME seed, SAME snapshot (no second fetch)
echo ""
echo "📊 Running 100k JSON output (same seed + snapshot)..."
if [ -n "$SNAP" ]; then
    echo "   📎 Reusing snapshot: $SNAP"
    python3 tournament_bonusfragen.py \
        --sims 100000 \
        --seed "$SEED" \
        --odds-snapshot "$SNAP" \
        --json \
        --output "data/resim_${DATE}.json" 2>&1
else
    echo "   ⚠ No fresh snapshot from run 1 (fetch failed?) — json run is Elo-only, matching the txt run."
    python3 tournament_bonusfragen.py \
        --sims 100000 \
        --seed "$SEED" \
        --json \
        --output "data/resim_${DATE}.json" 2>&1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Done! Results saved to data/resim_${DATE}.txt / .json (seed $SEED)"
echo ""
echo "📋 Summary:"
tail -20 "data/resim_${DATE}.txt"
