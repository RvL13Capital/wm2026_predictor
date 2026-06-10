#!/usr/bin/env python3
"""Pre-registered prediction log (plan step S7).

Appends one JSONL record per generated prediction artifact to
predictions_log/2026.jsonl, committed BEFORE kickoff. This is the mechanism
that turns the 2026 tournament into scoreable evidence: tips and probabilities
are recorded with full provenance (artifact header + git state at log time +
content hash), so the post-tournament evaluation (plan step S21) cannot be
accused of hindsight.

Usage:
    python3 scripts/log_predictions.py --kind matchday --file data/matchday1_tips_v5.txt
    python3 scripts/log_predictions.py --kind bonusfragen --file data/resim_20260610_1200.txt

Idempotent: re-logging a file whose sha256 is already in the log is a no-op.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOG = os.path.join(REPO_ROOT, "predictions_log", "2026.jsonl")

HEADER_PATTERNS = {
    "timestamp": re.compile(r"📅 Timestamp:\s*(\S+)"),
    "seed": re.compile(r"🌱 Seed:\s*(\S+)"),
    "commit": re.compile(r"🔗 Commit:\s*(\S+(?:\s*\(dirty\))?)"),
    "cmd": re.compile(r"⚙️\s*Cmd:\s*(.+)"),
}

# matchday_tips.py output format (see data/matchday1_tips_v4.txt):
#   Match 1: Mexico vs South Africa [GROUP]
#     P(Home)=78.7%  P(Draw)=15.6%  P(Away)=5.7%
#     ★ Optimal tip: 2:0  (EV = 1.969 pts)
MATCH_RE = re.compile(r"^Match (\d+): (.+?) vs (.+?) \[(\w+)\]")
PROBS_RE = re.compile(r"P\(Home\)=([\d.]+)%\s+P\(Draw\)=([\d.]+)%\s+P\(Away\)=([\d.]+)%")
TIP_RE = re.compile(r"★ Optimal tip: (\d+):(\d+)\s+\(EV = ([\d.]+) pts\)")


def git_state():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, stderr=subprocess.STDOUT
        ).decode().strip()
        dirty = subprocess.call(["git", "diff", "--quiet"], cwd=REPO_ROOT) != 0
        return {"commit": commit, "dirty": dirty}
    except Exception:
        return {"commit": "unknown", "dirty": None}


def parse_header(content: str) -> dict:
    header = {}
    for key, pat in HEADER_PATTERNS.items():
        m = pat.search(content)
        if m:
            header[key] = m.group(1).strip()
    return header


def parse_matchday(content: str) -> list:
    """Parse per-match tips + 1X2 probabilities from a matchday_tips output."""
    matches = []
    current = None
    for line in content.splitlines():
        m = MATCH_RE.match(line.strip())
        if m:
            if current:
                matches.append(current)
            current = {
                "n": int(m.group(1)),
                "team_a": m.group(2).strip(),
                "team_b": m.group(3).strip(),
                "phase": m.group(4),
            }
            continue
        if current is None:
            continue
        p = PROBS_RE.search(line)
        if p:
            current["p_home"] = float(p.group(1)) / 100.0
            current["p_draw"] = float(p.group(2)) / 100.0
            current["p_away"] = float(p.group(3)) / 100.0
        t = TIP_RE.search(line)
        if t:
            current["tip"] = f"{t.group(1)}:{t.group(2)}"
            current["ev"] = float(t.group(3))
    if current:
        matches.append(current)
    return matches


def parse_bonusfragen(content: str) -> dict:
    """Light-touch extraction for bonusfragen outputs: champion tip line if present."""
    out = {}
    m = re.search(r"WELTMEISTER\s+(\w[\w\s]*)", content)
    if m:
        out["champion_tip"] = m.group(1).strip().split("\n")[0]
    return out


def main():
    ap = argparse.ArgumentParser(description="Append a prediction artifact to the pre-registered log")
    ap.add_argument("--file", required=True, help="Generated prediction output file")
    ap.add_argument("--kind", required=True, choices=["matchday", "bonusfragen", "ko"],
                    help="Artifact kind (controls the parser)")
    ap.add_argument("--log", default=DEFAULT_LOG, help="JSONL log path")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="Permit logging an artifact generated from a dirty tree (discouraged)")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        content = f.read()
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

    header = parse_header(content)
    missing = [k for k in ("timestamp", "seed", "commit") if k not in header]
    if missing:
        print(f"❌ refusing to log: provenance header incomplete (missing {missing}) in {args.file}",
              file=sys.stderr)
        sys.exit(1)
    if "(dirty)" in header.get("commit", "") and not args.allow_dirty:
        print("❌ refusing to log: artifact was generated from a DIRTY tree "
              "(phantom-history rule). Commit first, regenerate, then log. "
              "Override with --allow-dirty only if you must.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.log), exist_ok=True)

    # Idempotency: skip if this exact artifact is already logged.
    if os.path.exists(args.log):
        with open(args.log, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    if json.loads(line).get("sha256") == sha:
                        print(f"↩ already logged (sha256 {sha[:12]}…) — no-op")
                        return
                except json.JSONDecodeError:
                    continue

    entry = {
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": args.kind,
        "source_file": os.path.relpath(os.path.abspath(args.file), REPO_ROOT),
        "sha256": sha,
        "header": header,
        "git_at_log": git_state(),
    }
    if args.kind in ("matchday", "ko"):
        matches = parse_matchday(content)
        if not matches:
            print("❌ refusing to log: no matches parsed from a matchday/ko artifact", file=sys.stderr)
            sys.exit(1)
        entry["matches"] = matches
    else:
        entry["bonusfragen"] = parse_bonusfragen(content)

    with open(args.log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    n = len(entry.get("matches", [])) or "—"
    print(f"✅ logged {args.kind} artifact {entry['source_file']} "
          f"(sha256 {sha[:12]}…, matches: {n}) → {os.path.relpath(args.log, REPO_ROOT)}")


if __name__ == "__main__":
    main()
