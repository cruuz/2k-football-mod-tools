"""The NCAA Football 09 disc's ``MMAP`` textures, measured and never written.

The disc carries **6,978 ``MMAP`` members across 35 containers** [M]: 1,200 in
``UNIFORM.DAT``, 888 in ``PLADATA.DAT`` and 396 in ``UIS_GEAR.DAT`` for the
kits and equipment, 64 player faces in ``PLYRFACE.DAT`` and 18 coach faces in
``COACFACE.DAT``, and the rest across the stadium, field and menu containers.

This lane opens each one's header through the **shared** reader
(:func:`mod_editor.games._formats.ea_terf.parse_mmap_header`) and reports what
the format declares -- version, format id, dimensions, header size -- for every
member of the kit and face containers.

**It does not export a PNG, and does not claim to.**  The ``MMAP`` pixel
decoder is now a shared format package
(:mod:`mod_editor.games._formats.mmap_art`), so the barrier that used to keep it
out of reach -- *a game imports a format package; it never imports another game*
-- is gone, and this module may import it.  What is still missing is this lane's
own export path, the independent verifier that has to fail on a tampered PNG,
and the evidence from this disc; so the row stays ``read-only-mapped`` and does
not claim ``extract-only``.  Run from a scratch harness against this disc, that
decoder draws **1,019 of 1,063** members sampled 40 per container and refuses 44
by name [M]; that number is a measurement of the decoder, not a capability of
this module.

Run it without a window::

    python3 -m mod_editor.games.ncaa09_ps2.texture_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers

CAPABILITY_ID = "ncaa09ps2.uniforms.texture_census"
LANE_ID = "uniforms.texture_census"
SCHEMA = "ncaa09_ps2_texture_census/v1"

#: The containers this lane walks: the kits and equipment, then the faces [M].
TEXTURE_CONTAINERS = containers.UNIFORM_CONTAINERS + containers.FACE_CONTAINERS

#: How many member rows the page lists.
MAX_MEMBER_TARGETS = 3000

#: How much of a member is unpacked to read its ``MMAP`` wrapper: the 40-byte
#: header plus the dimensions and descriptor that follow it, which is every byte
#: :func:`ea_terf.parse_mmap_header` reads.
HEADER_WINDOW = 0x40


class TextureLane:
    """The kit and face ``MMAP`` members, by their own headers, read-only."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Kit, equipment and face textures on the disc"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_ncaa09_ps2_textures.sh",
        "tools/validate_ncaa09_ps2_textures.bat",
    )
    fixed_allocation = True
    read_only = True

    REFUSAL = (
        "This lane reads each texture's header and writes nothing. Exporting a PNG needs "
        "the MMAP pixel decoder, which lives in the Madden 09 package and cannot be "
        "reached from here because a game never imports another game; move it into "
        "mod_editor/games/_formats and this row becomes an exporter."
    )

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        image = containers.open_disc(Path(source))
        present = {entry.name for entry in containers.data_files(image)}
        rows: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        targets: List[Target] = []
        sizes: Dict[str, int] = {}
        formats: Dict[str, int] = {}
        for name in TEXTURE_CONTAINERS:
            if name not in present:
                continue
            try:
                container = containers.load_container(image, name)
            except containers.DiscError as exc:
                refusals.append({"reader": "containers.load_container",
                                 "where": name, "sentence": str(exc)})
                continue
            for index in range(len(container)):
                if progress is not None and index % 128 == 0:
                    progress(f"{name} member {index} of {len(container)}…")
                # Only the wrapper header is wanted, so only the wrapper header
                # is unpacked.  UNIFORM.DAT's 1,200 LZH1 members unpack to
                # 127 MB in full and to 76,800 bytes at this window; the whole
                # census runs in seconds instead of seven minutes [M].
                try:
                    head = container.member(index, max_output=HEADER_WINDOW)
                except ea_terf.TerfError as exc:
                    refusals.append({"reader": "ea_terf.member",
                                     "where": f"{name}:{index}", "sentence": str(exc)})
                    continue
                if ea_terf.identify_member(head) != "MMAP":
                    continue
                try:
                    header = ea_terf.parse_mmap_header(head)
                except ea_terf.TerfError as exc:
                    refusals.append({"reader": "ea_terf.parse_mmap_header",
                                     "where": f"{name}:{index}", "sentence": str(exc)})
                    continue
                row = {
                    "container": name,
                    "member": index,
                    "bytes": container.members[index].decompressed_size,
                    "version": int(header.version),
                    "header_size": int(header.header_size),
                    "payload_size": int(header.payload_size),
                    "width": int(header.width),
                    "height": int(header.height),
                    "codec": container.members[index].codec_name,
                }
                size_key = f"{row['width']}x{row['height']}"
                sizes[size_key] = sizes.get(size_key, 0) + 1
                shape = f"v{row['version']}/header{row['header_size']}"
                formats[shape] = formats.get(shape, 0) + 1
                rows.append(row)
                if len(targets) < MAX_MEMBER_TARGETS:
                    targets.append(self._member_target(row))
        document = {
            "schema": SCHEMA,
            "source": str(source),
            "containers": list(TEXTURE_CONTAINERS),
            "mmap_members": len(rows),
            "member_rows_listed": len(targets),
            "member_rows_cap": MAX_MEMBER_TARGETS,
            "dimensions": dict(sorted(sizes.items(), key=lambda kv: -kv[1])),
            "version_header_shapes": dict(sorted(formats.items(), key=lambda kv: -kv[1])),
            "decoder": "none in this module: the MMAP pixel decoder is not in "
                       "mod_editor/games/_formats, and a game never imports another game",
            "rows": rows,
            "refusals": refusals,
        }
        return Catalogue(schema=SCHEMA, lane_id=self.lane_id, source=str(source),
                         targets=tuple(targets), document=document)

    @staticmethod
    def _member_target(row: Mapping[str, Any]) -> Target:
        return Target(
            key=f"texture:{row['container']}:{row['member']}",
            label=f"{row['container']} member {row['member']}",
            detail=" · ".join([
                f"{row['width']}x{row['height']}",
                f"v{row['version']}, {row['header_size']}-byte header",
                f"{row['payload_size']:,} byte payload",
                f"{row['bytes']:,} bytes",
                row["codec"],
            ]),
            budget="Read-only: this lane never writes to your disc.",
            searchable=f"{row['container']} {row['member']} "
                       f"{row['width']}x{row['height']} mmap",
            raw=dict(row),
            fields=(
                Field("width", "note", "Width",
                      "What the member's own header declares.", read_only=True),
                Field("height", "note", "Height",
                      "What the member's own header declares.", read_only=True),
                Field("version", "note", "Version",
                      "The wrapper version the header declares.", read_only=True),
                Field("payload_size", "note", "Payload size",
                      "The size the header declares past its own bytes.", read_only=True),
                Field("codec", "note", "Codec",
                      "How the container packs this member.", read_only=True),
            ),
        )

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "ncaa09-ps2-textures-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.ncaa09_ps2.texture_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.ncaa09_ps2.texture_lane",
        description="Measure the kit and face MMAP textures on an NCAA Football 09 (PS2) "
                    "disc. Read-only; headers only, no pixels.",
    )
    parser.add_argument("--source", help="the user's own SLUS-21752 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    lane = TextureLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = lane.build_catalogue(lane.synthetic_source(Path(room)))
        else:
            catalogue = lane.build_catalogue(
                Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("TEXTURES members=%d sizes=%s"
          % (document["mmap_members"],
             ",".join(f"{k}:{v}" for k, v in list(document["dimensions"].items())[:8])))
    return 0


__all__ = ["CAPABILITY_ID", "HEADER_WINDOW", "LANE_ID", "MAX_MEMBER_TARGETS", "SCHEMA",
           "TEXTURE_CONTAINERS", "TextureLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
