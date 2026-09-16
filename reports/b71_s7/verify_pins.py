"""Rebuild the modern colour pins from the retail extraction and compare every record with the committed file."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_color as mc
t0 = time.time()
fresh = mc.build_pins("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)", workers=3)
committed = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
same = json.dumps(fresh, sort_keys=True) == json.dumps(committed, sort_keys=True)
mismatch = [b["name"] for b, c in zip(fresh["bundles"], committed["bundles"]) if b != c]
tables = [t["name"] for t, c in zip(fresh["light_tables"], committed["light_tables"]) if t != c]
print(json.dumps(dict(identical=same, bundles=len(fresh["bundles"]), light_tables=len(fresh["light_tables"]),
                      mismatched_bundles=mismatch, mismatched_tables=tables, seconds=round(time.time() - t0, 1)), indent=1))
sys.exit(0 if same else 1)
