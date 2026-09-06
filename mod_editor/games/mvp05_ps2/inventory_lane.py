"""All Textures: every ``SHPS`` bank in every EA ``BIG`` archive on the disc, counted.

211 archives, 643 nested archives, 16,371 banks [M].  This lane walks all of
them -- each entry classified from its first 32 bytes, each bank parsed for
its directory -- and lists one row per archive with its bank, image, decodable
and refused counts by pixel code.  It draws nothing and writes nothing: the
art pages are where an image is exported or replaced, and the refusal every
``0x0e`` image carries is quoted here rather than restated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_big, ea_shps
from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers

CAPABILITY_ID = "mvp05ps2.textures.bank_inventory"
LANE_ID = "textures.bank_inventory"
SCHEMA = "mvp05_ps2_bank_inventory/v1"


class TextureInventoryLane:
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "textures"
    page = "textures"
    title = "Every SHPS image bank on the disc"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = ("tools/validate_mvp05_ps2_inventory.sh", "tools/validate_mvp05_ps2_inventory.bat")
    fixed_allocation = True
    read_only = True
    REFUSAL = ("This lane counts every bank and image and writes nothing; export or replace an "
               "image on the page that owns its archive (stadiums, presentation, menus), and the "
               "code-0x0e archives are listed on theirs with the measured reason nothing is drawn.")

    @staticmethod
    def _count(archive: ea_big.BigArchive, summary: Dict[str, Any], codes: Dict[str, int],
               refusals: List[Dict[str, str]], depth: int) -> None:
        for row in archive.entries:
            if row.size == 0:
                continue
            kind = archive.entry_format(row.index)
            summary["formats"][kind] = summary["formats"].get(kind, 0) + 1
            if kind == "BIGF" and depth == 0:
                try:
                    nested = archive.nested(row.index)
                except ea_big.BigError as exc:
                    refusals.append({"where": f"{archive.name}!{row.name}", "sentence": str(exc)})
                    continue
                summary["nested"] += 1
                TextureInventoryLane._count(nested, summary, codes, refusals, depth + 1)
                continue
            if kind != "SHPS":
                continue
            try:
                bank = ea_shps.parse(archive.member(row.index), row.name)
            except (ea_big.BigError, ea_shps.ShpsError) as exc:
                refusals.append({"where": f"{archive.name}!{row.name}", "sentence": str(exc)})
                continue
            summary["banks"] += 1
            for image in bank.images:
                code = "0x%02x" % image.code
                summary["images"] += 1
                summary["codes"][code] = summary["codes"].get(code, 0) + 1
                codes[code] = codes.get(code, 0) + 1
                if bank.undecodable_reason(image.index) is None:
                    summary["decodable"] += 1

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        rows: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        codes: Dict[str, int] = {}
        targets: List[Target] = []
        with containers.Disc(Path(source)) as disc:
            files = disc.big_files()
            for number, entry in enumerate(files):
                if progress is not None:
                    progress(f"{entry.path} ({number + 1} of {len(files)})…")
                summary: Dict[str, Any] = {"path": entry.path, "bytes": int(entry.length), "entries": 0,
                                           "nested": 0, "banks": 0, "images": 0, "decodable": 0,
                                           "codes": {}, "formats": {}, "packed": 0}
                try:
                    archive = disc.archive(entry)
                except containers.DiscError as exc:
                    refusals.append({"where": entry.path, "sentence": str(exc)})
                    continue
                summary["entries"] = len(archive)
                summary["packed"] = archive.compressed_count()
                self._count(archive, summary, codes, refusals, 0)
                rows.append(summary)
                targets.append(Target(
                    key=f"archive:{entry.path}", label=entry.path,
                    detail=f"{summary['entries']} entries · {summary['banks']} banks · {summary['images']} images · "
                           f"{summary['decodable']} decode · codes {summary['codes']}",
                    budget="Read-only: this lane counts and writes nothing.",
                    searchable=f"{entry.path} {' '.join(summary['codes'])}", raw=dict(summary),
                    fields=(Field("banks", "note", "Banks", str(summary["banks"]), read_only=True),
                            Field("images", "note", "Images", str(summary["images"]), read_only=True),
                            Field("decodable", "note", "Decodable", str(summary["decodable"]), read_only=True),
                            Field("codes", "note", "Pixel codes", json.dumps(summary["codes"], sort_keys=True), read_only=True))))
        document = {"schema": SCHEMA, "source": str(source), "archives": len(rows),
                    "nested": sum(r["nested"] for r in rows), "banks": sum(r["banks"] for r in rows),
                    "images": sum(r["images"] for r in rows), "decodable": sum(r["decodable"] for r in rows),
                    "codes": dict(sorted(codes.items())), "refusals": refusals, "rows": rows,
                    "block_codec_note": ea_shps.CODE_NOTES.get(0x0E, ""), "why": self.REFUSAL}
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": SCHEMA, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "mvp05-ps2-inventory-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


LANE = TextureInventoryLane()


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mod_editor.games.mvp05_ps2.inventory_lane",
                                     description="Count every SHPS bank on an MVP Baseball 2005 (PS2) disc. Read-only.")
    parser.add_argument("--source")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = LANE.build_catalogue(LANE.synthetic_source(Path(room)))
        else:
            catalogue = LANE.build_catalogue(Path(arguments.source),
                                             progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    print("INVENTORY archives=%d nested=%d banks=%d images=%d decodable=%d codes=%s" % (
        document["archives"], document["nested"], document["banks"], document["images"],
        document["decodable"], document["codes"]))
    return 0


__all__ = ["CAPABILITY_ID", "LANE", "LANE_ID", "SCHEMA", "TextureInventoryLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
