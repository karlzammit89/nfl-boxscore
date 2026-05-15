#!/usr/bin/env python3
"""
Run this locally: python3 diagnose_periods.py
It prints EVERY period field ESPN sends so we know exactly what to read.
"""
import sys, json
sys.path.insert(0, '.')
from nfl.api import get_game_summary

game_id = "401772949"
summary = get_game_summary(game_id)
if not summary:
    print("ERROR: No data")
    sys.exit(1)

drives = summary.get("drives", {})
prev   = drives.get("previous", [])
curr   = drives.get("current")
all_drives = prev + ([curr] if curr else [])
print(f"Drives: {len(all_drives)}\n")

for di, drive in enumerate(all_drives[:5]):   # first 5 drives
    if not drive:
        continue
    
    d_start = drive.get("start", {})
    d_end   = drive.get("end",   {})
    
    def show_period(label, obj):
        p = obj.get("period", "MISSING") if isinstance(obj, dict) else "MISSING"
        if isinstance(p, dict):
            num = p.get("number", "MISSING")
            dv  = p.get("displayValue", "MISSING")
        elif isinstance(p, int):
            num = p; dv = "N/A (int)"
        else:
            num = "MISSING"; dv = "MISSING"
        print(f"    {label}: number={num!r}  displayValue={dv!r}")
    
    print(f"Drive {di}:")
    show_period("  start.period", d_start)
    show_period("  end.period",   d_end)
    
    for pi, play in enumerate(drive.get("plays", [])[:3]):
        clock = play.get("clock", {}).get("displayValue", "")
        desc  = (play.get("text","") or play.get("description",""))[:50]
        print(f"  Play {pi} ({clock}): {desc!r}")
        show_period("    play.period",       play)
        show_period("    play.start.period", play.get("start", {}))
        show_period("    play.end.period",   play.get("end",   {}))
    
    plays = drive.get("plays", [])
    if len(plays) > 3:
        print(f"  ... +{len(plays)-3} more plays")
    print()

# Also show what keys exist at top level of a play
print("\n=== TOP-LEVEL KEYS OF FIRST PLAY ===")
for drive in all_drives:
    plays = drive.get("plays", []) if drive else []
    if plays:
        print(json.dumps(list(plays[0].keys()), indent=2))
        # Also show the full period field
        print("play.period raw value:")
        print(json.dumps(plays[0].get("period"), indent=2))
        print("play.start raw value:")
        print(json.dumps(plays[0].get("start"), indent=2))
        break
