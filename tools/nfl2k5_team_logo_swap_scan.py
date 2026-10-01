#!/usr/bin/env python3
"""Proof scan for the team-logo swap (job pf, P1): every SCNE in the archive, which of them the field swap can bind (the
scenes named ``field``, 0x9C185), and which carry the name ``teamlogo`` (UTF-16, four spellings) anywhere.

The eighth swap pair acts only on a field scene with a material named ``teamlogo``; the practice facility's field is
the only one the Build names so. On the retail archive (2026-09-27): 4,255 SCNEs, 477 of them named ``field``, none of
those carrying ``teamlogo``; ten other scenes do (the franchise office's coach_desk and front_office, the Crib's
bar_sign, cap, glass_00, glass_01, guitar, mug and team_plaque, and bench_04), which the field swap never binds.

    python3 tools/nfl2k5_team_logo_swap_scan.py SOURCE [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402

NAMES = tuple(w.encode("utf-16le") for w in ("teamlogo", "TeamLogo", "TEAMLOGO", "Teamlogo"))


def scene_name(decoded):
    value = struct.unpack_from("<i", decoded, 0x10)[0]
    at = 0x10 + value - 1
    end = at
    while end + 1 < len(decoded) and decoded[end:end + 2] != b"\0\0":
        end += 2
    return decoded[at:end].decode("utf-16le", "replace")


def scan(source):
    tx = ml._tools()[0]
    out = dict(entries=0, scenes=0, field_scenes=0, field_hits=[], other_hits=[])
    with ml._outer_image()(str(source)) as archive:
        for index, entry in enumerate(archive.entries):
            out["entries"] += 1
            data = archive.read(entry.virtual_offset, entry.size)
            try:
                chunks = tx.parse_chunks(data, allow_trailing=True)
            except Exception:  # noqa: BLE001 - not a chunked package
                continue
            for chunk in chunks:
                if chunk.kind != "SCNE":
                    continue
                decoded, _ = tx.decode_chunk(data, chunk)
                decoded = bytes(decoded)
                out["scenes"] += 1
                name = scene_name(decoded)
                hit = any(n in decoded for n in NAMES)
                if name == "field":
                    out["field_scenes"] += 1
                    if hit:
                        out["field_hits"].append([index, chunk.index])
                elif hit:
                    out["other_hits"].append([index, chunk.index, name])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="retail disc image or extracted folder")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    report = scan(args.source)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"TEAM_LOGO_SCAN scenes={report['scenes']} field={report['field_scenes']} "
          f"field_hits={len(report['field_hits'])} other_hits={len(report['other_hits'])}")
    for row in report["other_hits"]:
        print("  other", row)
    return 0 if not report["field_hits"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
