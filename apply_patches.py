#!/usr/bin/env python3
"""
apply_patches.py  (patches 3 and 4 only — 1 and 2 already applied)
Run from your project root:  python3 apply_patches.py
"""
import sys, shutil, os

SRC = "app.py"
BAK = "app.py.bak"

if not os.path.exists(SRC):
    print(f"{SRC} not found. Run from your project root.")
    sys.exit(1)

with open(SRC, "r") as f:
    src = f.read()

patch3_old = '                        _d_tid = {}\n                        def _db_team(ref):\n                            _m = _DBRE_TM.search(ref or "")\n                            return _d_tid.get(_m.group(1), "") if _m else ""'
patch3_new = '                        _d_tid = {}\n                        # Populate team ID -> abbreviation from cached game summary\n                        try:\n                            _gsumm = _gdata.get("_summary") or {}\n                            for _tbx in _gsumm.get("boxscore", {}).get("teams", []):\n                                _t_id  = str(_tbx.get("team", {}).get("id",  ""))\n                                _t_abr = _tbx.get("team", {}).get("abbreviation", "")\n                                if _t_id and _t_abr:\n                                    _d_tid[_t_id] = _t_abr\n                        except Exception:\n                            pass\n                        _D_ALIAS = {\n                            "CLV": "CLE", "WAS": "WSH", "HST": "HOU",\n                            "ARZ": "ARI", "BLT": "BAL", "LA":  "LAR",\n                        }\n                        def _db_team(ref):\n                            _m = _DBRE_TM.search(ref or "")\n                            return _d_tid.get(_m.group(1), "") if _m else ""'
patch4_old = '                            _dpm6  = _dbre.search(r"PENALTY ON ([A-Z]{2,3})[^A-Z]", _dtxt6)\n                            _dpt6b = _dpm6.group(1) if _dpm6 else "—"'
patch4_new = '                            _dpm6      = _dbre.search(r"PENALTY ON ([A-Z]{2,3})[^A-Z]", _dtxt6)\n                            _dpt6b_raw = _dpm6.group(1) if _dpm6 else "—"\n                            _dpt6b     = _D_ALIAS.get(_dpt6b_raw, _dpt6b_raw)'

PATCHES = [
    ("PATCH 3 — populate _d_tid and add _D_ALIAS map", patch3_old, patch3_new),
    ("PATCH 4 — normalize pen_team with _D_ALIAS",     patch4_old, patch4_new),
]

print("Checking patches...\n")
missing = []
for name, old, _ in PATCHES:
    count = src.count(old)
    if count == 0:
        missing.append(name)
        print(f"  NOT FOUND -- {name}")
    elif count > 1:
        print(f"  AMBIGUOUS ({count}x) -- {name}")
    else:
        print(f"  Found     -- {name}")

if missing:
    print(f"\n{len(missing)} patch(es) not found. app.py NOT modified.")
    sys.exit(1)

shutil.copy(SRC, BAK)
print(f"\nBackup saved -> {BAK}")

for name, old, new in PATCHES:
    src = src.replace(old, new, 1)
    print(f"Applied: {name}")

with open(SRC, "w") as f:
    f.write(src)

print(f"\nDone. {SRC} updated successfully.")
