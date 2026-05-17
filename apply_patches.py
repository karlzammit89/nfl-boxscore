#!/usr/bin/env python3
"""
apply_patches.py — Apply the 4 targeted app.py changes
Run once from the same directory as app.py: python3 apply_patches.py
"""
import sys

with open("app.py", "r") as f:
    src = f.read()

original_len = len(src)
errors = []

# ── Patch 1: add _get_game_summary_for_debug import ───────────────────────────
OLD1 = """from nfl.api import get_live_games
from nfl.api import get_core_plays as _get_core_plays_for_debug"""
NEW1 = """from nfl.api import get_live_games
from nfl.api import get_core_plays as _get_core_plays_for_debug
from nfl.api import get_game_summary as _get_game_summary_for_debug"""
if OLD1 in src:
    src = src.replace(OLD1, NEW1, 1)
    print("✅ Patch 1 applied: added _get_game_summary_for_debug import")
else:
    errors.append("❌ Patch 1 NOT applied: target string not found")

# ── Patch 2: add _summary key to load_all_stats ───────────────────────────────
OLD2 = """        "core_plays":  _get_core_plays_for_debug(game_id),  # reused for debug CSV
    }"""
NEW2 = """        "core_plays":  _get_core_plays_for_debug(game_id),  # reused for debug CSV
        "_summary":    _get_game_summary_for_debug(game_id),   # cached; used by debug builder
    }"""
if OLD2 in src:
    src = src.replace(OLD2, NEW2, 1)
    print("✅ Patch 2 applied: added _summary key to load_all_stats")
else:
    errors.append("❌ Patch 2 NOT applied: target string not found")

# ── Patch 3: populate _d_tid from summary + add alias map ────────────────────
OLD3 = """                        _d_tid = {}
                        def _db_team(ref):
                            _m = _DBRE_TM.search(ref or "")
                            return _d_tid.get(_m.group(1), "") if _m else "" """
NEW3 = """                        _d_tid = {}
                        # Populate team ID → abbreviation from cached game summary
                        try:
                            _gsumm = _gdata.get("_summary") or {}
                            for _tbx in _gsumm.get("boxscore", {}).get("teams", []):
                                _t_id  = str(_tbx.get("team", {}).get("id", ""))
                                _t_abr = _tbx.get("team", {}).get("abbreviation", "")
                                if _t_id and _t_abr:
                                    _d_tid[_t_id] = _t_abr
                        except Exception:
                            pass
                        # Alias map: ESPN play text uses internal codes; boxscore uses display codes
                        _D_ALIAS = {"CLV":"CLE","WAS":"WSH","HST":"HOU","ARZ":"ARI","BLT":"BAL","LA":"LAR"}
                        def _db_team(ref):
                            _m = _DBRE_TM.search(ref or "")
                            return _d_tid.get(_m.group(1), "") if _m else "" """
if OLD3 in src:
    src = src.replace(OLD3, NEW3, 1)
    print("✅ Patch 3 applied: _d_tid populated from summary + alias map added")
else:
    errors.append("❌ Patch 3 NOT applied: target string not found")

# ── Patch 4: normalize pen_team with alias map ───────────────────────────────
OLD4 = """                            _dpm6  = _dbre.search(r"PENALTY ON ([A-Z]{2,3})[^A-Z]", _dtxt6)
                            _dpt6b = _dpm6.group(1) if _dpm6 else "—" """
NEW4 = """                            _dpm6  = _dbre.search(r"PENALTY ON ([A-Z]{2,3})[^A-Z]", _dtxt6)
                            _dpt6b_raw = _dpm6.group(1) if _dpm6 else "—"
                            _dpt6b = _D_ALIAS.get(_dpt6b_raw, _dpt6b_raw)  # normalize alias codes"""
if OLD4 in src:
    src = src.replace(OLD4, NEW4, 1)
    print("✅ Patch 4 applied: pen_team alias normalization added")
else:
    errors.append("❌ Patch 4 NOT applied: target string not found")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)

with open("app.py", "w") as f:
    f.write(src)

print(f"\n✅ All patches applied. app.py: {original_len:,} → {len(src):,} chars (+{len(src)-original_len:,})")
