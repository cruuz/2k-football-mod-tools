#!/usr/bin/env python3
"""cm1: rewrite data/nfl2k5_modern_coaches/pins.json from a retail USA image and the shipped coach art and geometry.

The rows come from co2's recorder (``co2_record_pins.py``: bodies, glasses, Reid's derived head, the two portraits);
``record_pins`` now also pins each club's ``geometry.json`` (b77 cm1), and every earlier applied digest of a coach
scene is carried forward as ``superseded_sha256`` so a disc built with the earlier art reads ``previous``. The two
Coach Matchup portraits ship no PNG since pr2 (the pictures come from the SOFTDRINK league project), so only their
rejected render digests, which co2's recorder carries itself, remain.

  python3 tools/b77/cm1_record_pins.py --retail RETAIL.iso [--write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402
import co2_record_pins  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retail", required=True)
    p.add_argument("--write", action="store_true")
    a = p.parse_args(argv)
    before = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
    co2_record_pins.main(["--retail", a.retail, "--write"])
    doc = json.loads(mc.PINS_PATH.read_text(encoding="utf-8"))
    mc._check_pins(doc)
    text = json.dumps(doc, indent=1) + "\n"
    if a.write:
        mc.PINS_PATH.write_text(text, encoding="utf-8", newline="\n")
    else:
        mc.PINS_PATH.write_text(json.dumps(before, indent=1) + "\n", encoding="utf-8", newline="\n")
    for row in doc["teams"]:
        if row.get("geometry"):
            print(row["team"], row["archive"], "geometry", row["geometry"][:12], "applied", row["applied_sha256"][:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
