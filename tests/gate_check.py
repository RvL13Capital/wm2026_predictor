import sys
import os
import re
import json

def parse_header(filepath):
    meta = {}
    with open(filepath, 'r') as f:
        content = f.read()
    
    seed_match = re.search(r'🌱 Seed:\s*(\d+)', content)
    if seed_match:
        meta['seed'] = seed_match.group(1)
        
    sims_match = re.search(r'Basierend auf ([\d,]+) Monte-Carlo', content)
    if sims_match:
        meta['sims'] = sims_match.group(1).replace(',', '')
        
    commit_match = re.search(r'🔗 Commit:\s*([a-f0-9]+)', content)
    if commit_match:
        meta['commit'] = commit_match.group(1)
        
    return meta, content

def parse_champion_probs(content):
    probs = {}
    # Extract champion section
    match = re.search(r'WELTMEISTER \w+\n\s*├.*?\n(.*?)\n\s*└', content, re.DOTALL)
    if not match:
        return probs
    
    lines = match.group(1).strip().split('\n')
    for line in lines:
        if '%' in line:
            parts = line.split()
            # team is usually parts[1] if there is a star, otherwise parts[0]
            team_match = re.search(r'([A-Za-z\s]+)\s+\d+\.\d+%', line)
            if team_match:
                team = team_match.group(1).replace('★', '').replace('◀ TIP', '').strip()
                prob_str = re.search(r'(\d+\.\d+)%', line).group(1)
                probs[team] = float(prob_str)
    return probs

def check_gate(bonus_file, matchday_file, snapshot_file=None):
    errors = []
    
    print(f"🔍 Gate Check: Validating {bonus_file} and {matchday_file}...")
    
    # 1. Metadata check
    bonus_meta, bonus_content = parse_header(bonus_file)
    md_meta, md_content = parse_header(matchday_file)
    
    for key in ['seed', 'commit']:
        if key not in bonus_meta:
            errors.append(f"Missing {key} in {bonus_file}")
        if key not in md_meta:
            errors.append(f"Missing {key} in {matchday_file}")
            
    if 'sims' not in bonus_meta:
        errors.append(f"Missing sims count in {bonus_file}")
        
    # 2. Snapshot divergence check (c)
    if snapshot_file and os.path.exists(snapshot_file):
        with open(snapshot_file, 'r') as f:
            snap = json.load(f)
            
        mkt_probs = snap.get("probabilities", {})
        bonus_probs = parse_champion_probs(bonus_content)
        
        # Check Top 5 in snapshot
        top5_mkt = sorted(mkt_probs.items(), key=lambda x: x[1], reverse=True)[:5]
        for team, m_prob in top5_mkt:
            m_pct = m_prob * 100
            if team in bonus_probs:
                b_pct = bonus_probs[team]
                diff = abs(m_pct - b_pct)
                if diff > 5.0:
                    errors.append(f"Divergence > 5pp for {team}: Market {m_pct:.1f}% vs Bonus {b_pct:.1f}%")
            else:
                errors.append(f"Top market team {team} not found in bonus champion output")
                
    if errors:
        print("❌ GATE CHECK FAILED:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    else:
        print("✅ GATE CHECK PASSED: All consistencies verified.")
        sys.exit(0)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bonus", required=True)
    parser.add_argument("--matchday", required=True)
    parser.add_argument("--snapshot", default=None)
    args = parser.parse_args()
    
    check_gate(args.bonus, args.matchday, args.snapshot)
