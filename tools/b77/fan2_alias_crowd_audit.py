#!/usr/bin/env python3
"""fan2: do the Anniversary moment stadiums draw the same fans as their venues? (read only, offline)

    python3 tools/b77/fan2_alias_crowd_audit.py --disc IMAGE [--retail RETAIL_IMAGE] [--out receipt.json]

Every moment plays in its own ``aNN<variant>.iff`` alias, a copy of a venue bundle taken when the period fields are
compiled. For each of the 51 rows this compares the alias's stadium crowd (``nfl2k5_espn25_fields.stadium_crowd_digest``:
crowd shapes, UVs, draw words and the embedded crowd atlas) with the venue it was copied from: the disc's own ``sNN``
file for built rows, the retail ``sNN`` file for retail rows (when ``--retail`` is given). It also reports the share of
each alias's crowd area whose fans are drawn more than 15 percent wider or narrower than the retail median
(``cr1_crowd_measure``), so a stale copy of the pre-cr1 crowd shows up as squashed or stretched fans.

Exit status 1 when any built alias's crowd differs from its venue. Nothing is written except ``--out``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools" / "b77")]

from mod_editor.core import nfl2k5_espn25_fields as fields  # noqa: E402
from mod_editor.core import nfl2k5_espn25_more_moments as moments  # noqa: E402
from mod_editor.core import nfl2k5_historic_styles as styles  # noqa: E402

RETAIL_ASPECT = 1.081   # cr1's retail median texel aspect
TOLERANCE = 0.15


def flagged_share(bundle):
    import numpy as np
    import cr1_crowd_measure as measure
    rows, _ = measure.measure_scene(measure.stadium_scene(bundle))
    rows = [r for r in rows if "texel_aspect" in r]
    if not rows:
        return None, None
    aspect = np.array([r["texel_aspect"] for r in rows])
    area = np.array([r["area"] for r in rows])
    flagged = np.abs(aspect / RETAIL_ASPECT - 1) > TOLERANCE
    return float(np.median(aspect)), float(area[flagged].sum() / area.sum())


def audit(disc, retail=None):
    out = []
    with styles.Source(disc) as image:
        retail_source = styles.Source(retail) if retail else None
        try:
            situ = image.get(identity=moments.SITU_ID)
            for row in fields.catalog():
                index = row["row"] - 1
                code = fields.variant(situ, index)
                alias, source = f"a{index:02d}{code}.iff", row["source_prefix"] + code + ".iff"
                bundle = image.get(alias)
                venue = (image.get(source) if row["source_kind"] == "built"
                         else retail_source.get(source) if retail_source else None)
                median, share = flagged_share(bundle)
                item = dict(row=row["row"], title=row.get("title"), alias=alias, source=source,
                            source_kind=row["source_kind"], alias_crowd=fields.stadium_crowd_digest(bundle),
                            median_texel_aspect=median, flagged_crowd_area=share)
                if venue is not None:
                    item["source_crowd"] = fields.stadium_crowd_digest(venue)
                    item["matches_source"] = item["alias_crowd"] == item["source_crowd"]
                    item["source_flagged_crowd_area"] = flagged_share(venue)[1]
                out.append(item)
        finally:
            if retail_source is not None:
                retail_source.__exit__(None, None, None)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--disc", type=Path, required=True)
    p.add_argument("--retail", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    rows = audit(a.disc, a.retail)
    for r in rows:
        match = {True: "same crowd as venue", False: "DIFFERENT crowd from venue"}.get(r.get("matches_source"), "-")
        print(f"{r['row']:2d} {r['alias']} <- {r['source']} {r['source_kind']:6s} {match:26s} "
              f"flagged {r['flagged_crowd_area'] or 0:.3f}")
    drift = [r for r in rows if r["source_kind"] == "built" and not r["matches_source"]]
    print(f"built rows {sum(r['source_kind'] == 'built' for r in rows)}, drifted {len(drift)}")
    if a.out:
        a.out.write_text(json.dumps(dict(schema="b775_fan2_alias_crowd_audit/v1", disc=str(a.disc), rows=rows),
                                    indent=1) + "\n", newline="\n")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
