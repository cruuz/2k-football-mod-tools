"""PROVED OFFLINE: compile and read back all E2 strings without writing a disc.

The optional plan contains source bytes and must remain private. Combining the
original edits with the 50-row production writer still needs its guard/Build
integration; this script proves serialization, not production installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_espn25_scenarios as sc
from mod_editor.core import nfl2k5_espn25_more_moments as mm


def validate(source, plan_path=None):
    authored = json.loads((ROOT / "data/espn25_previews_2026.json").read_text())
    edits = json.loads((ROOT / "data/espn25_previews_2026_originals.json").read_text())
    catalog = sc.Catalog.load(source)
    data = mm.Data.load()
    assert len(authored["moments"]) == 50
    plan = catalog.prepare(edits)
    replacements, already = sc.resolve_plan(catalog, plan)
    assert not already
    grown = mm.compile_situ(replacements[22], data, catalog.resource(5))
    body = grown[32:32 + sc.u32(grown, 4)]
    assert sc.u32(body, 64) == 50
    assert grown[32 + len(body):] == catalog.resource(22)[mm.FIRST_CHUNK:]
    allocations = dict(catalog.manifest["situ"]["strings"])
    receipts = []
    for i, row in enumerate(authored["moments"]):
        assert row["row"] == i + 1
        if i < 25:
            assert row["text"] == edits["moments"][i]["text"]
        else:
            actual = data.moments[i - 25]
            assert row["text"] == {"title": actual["title"], "description": actual["history"],
                                  "objective": actual["goal"], "date": actual["date"]}
        for field, offset in sc.TEXT.items():
            value = row["text"][field]
            assert value.isascii() and "\u2014" not in value
            actual = sc.utf16(body, sc.rel(body, sc.RECORDS + i * sc.STRIDE + offset))
            assert actual == value, (i + 1, field)
            encoded = len(value.encode("utf-16le")) + 2
            if i < 25:
                cap = allocations[sc.rel(catalog.situ, sc.RECORDS + i * sc.STRIDE + offset)]
                assert encoded <= cap, (i + 1, field, encoded, cap)
                budget = dict(kind="retail fixed allocation, including NUL", max_bytes=cap,
                              spare_bytes=cap - encoded)
            else:
                # M2's editorial contract is narrower than Data.validate's safety bounds.
                limits = {"title": (3, 27), "description": (320, 445), "objective": (46, 86)}
                if field in limits:
                    low, high = limits[field]
                    assert low <= len(value) <= high, (i + 1, field, len(value))
                else:
                    high = None  # date parser, not a fixed engine allocation
                budget = dict(kind="relocated UTF-16 pool; M2 editorial contract",
                              max_characters=high, engine_pool_limit_bytes=262144)
            receipts.append(dict(row=i + 1, field=field, characters=len(value),
                                 utf16_bytes_with_nul=encoded, **budget))
        if row["super_bowl"]:
            for field in ("description", "objective"):
                assert "Super Bowl " + row["super_bowl"] in row["text"][field]
    # Every non-pointer value in each original situation remains byte-identical.
    for i in range(25):
        for j in range(sc.STRIDE):
            if any(offset <= j < offset + 4 for offset in sc.POINTERS):
                continue
            assert body[sc.RECORDS + i * sc.STRIDE + j] == catalog.situ[sc.RECORDS + i * sc.STRIDE + j]
    if plan_path:
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    return dict(classification="PROVED OFFLINE", strings=len(receipts), rows=50,
                source_situ_sha256=hashlib.sha256(catalog.resource(22)).hexdigest(),
                edited_25_sha256=hashlib.sha256(replacements[22]).hexdigest(),
                edited_50_sha256=hashlib.sha256(grown).hexdigest(),
                situ_body_bytes=len(body), situ_body_limit_bytes=262144,
                unchanged="Original situation scalars and all non-SITU collection siblings",
                boundary="Compiled in memory and read back; no rendered UI or production combined writer claim",
                fields=receipts)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
    p.add_argument("--private-plan", type=Path)
    p.add_argument("--receipt", type=Path, default=ROOT / "e2/evidence/text_budgets.json")
    args = p.parse_args()
    result = validate(args.source, args.private_plan)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "fields"}))
