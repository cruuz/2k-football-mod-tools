#!/usr/bin/env python3
"""cr1: copy every venue bundle (sNN{d,a,n}{d,r,s}.iff) out of a disc image, with a hash manifest (read only)."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as ml


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--disc", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--codes", nargs="*")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    with ml._outer_image()(str(a.disc)) as archive:
        byid = {e.name_id: e for e in archive.entries}
        for v in range(48):
            code = f"s{v:02}"
            if a.codes and code not in a.codes:
                continue
            for t in "dan":
                for w in "drs":
                    name = f"{code}{t}{w}.iff"
                    e = byid.get(ml.name_id(name))
                    if e is None:
                        continue
                    raw = archive.read(e.virtual_offset, e.size)
                    (a.out / name).write_bytes(raw)
                    rows.append(dict(name=name, outer_index=e.index, name_id=e.name_id, virtual_offset=e.virtual_offset,
                                     size=e.size, sha256=hashlib.sha256(raw).hexdigest()))
    (a.out / "manifest.json").write_text(json.dumps(dict(schema="b77_cr1_extract/v1", disc=str(a.disc), entries=rows),
                                                    indent=1) + "\n", newline="\n")
    print(len(rows), "bundles")


if __name__ == "__main__":
    raise SystemExit(main())
