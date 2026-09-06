"""``CPTH`` camera paths, and the two container heads beside them that stay unread.

The disc carries 85 ``.cap`` members on the 2002 disc and 88 on the 2003 disc,
each beginning ``CPTH``.  The owner's scoping study names the family ``HTPC``,
which is that tag read as a little-endian word; the bytes are ``CPTH`` and this
module matches the bytes [M].  The header's own arithmetic is exact and is what
makes the shape measured rather than guessed [M]::

    +0  char[4] "CPTH"     +8  u32 records      16 + records * 32 == the member
    +4  u32 (7 / 1 / 5 / 3) +12 u32 0            85 of 85 and 88 of 88

Word 1 takes four values across the discs -- 7 on 43 (46) members, 1 on 20, 5 on
19 and 3 on 3 -- and is reported unnamed [M].  A record is 32 bytes of what read
as IEEE floats; nothing here says which of them is a position and which a time,
so the lane lists a path's record count and stride and offers no editor.

The same page names the two container families beside it whose heads are all
that is read [M]:

* **``WIFF``** -- 190 members on the 2002 disc and 209 on the 2003 disc, across
  ``.wip`` / ``.wom`` / ``.wmp``.  It is a **big-endian RIFF**: the ``u32`` after
  the tag plus 8 is the member's own length on 190 of 190 and 209 of 209, and
  the form type after it is ``WIPS`` (167 / 181), ``WOMS`` (16 / 21) or ``WOM ``
  (7 / 7).  That is the whole of what is measured; no chunk inside one is read.
* **``.dff``** -- 1,272 and 1,436 RenderWare clump streams.  The owner's disc map
  left these as a raw magic because a single-section length rule fails on all
  2,708 of them.  It fails because **a DFF stream is more than one section**: a
  top-level walk over the whole member consumes it exactly on 1,043 of 1,272 and
  1,167 of 1,436, and the sequence is ``Clump(0x10)`` then ``Extension(0x03)`` on
  1,043 and 1,145 of those, or ``Clump`` alone on 162 and 149 [M].  So the id is
  not a coincidence and Midway wrote no variant; the map's rule was the wrong
  rule for a multi-section file.  Reading a clump's geometry is a different job
  and is not done here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import rw_txd
from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

from . import containers

SCHEMA = "nflblitz2002_ps2_camera_paths/v1"
GAME_ID = containers.GAME_ID
LANE_ID = "presentation.camera_paths"
CAPABILITY_ID = f"{GAME_ID.replace('_', '')}.{LANE_ID}"

REFUSAL = ("This lane lists every camera path, WIFF container and RenderWare clump on the disc "
           "and writes nothing: a path's 32-byte record is four-byte fields whose meanings are "
           "not measured, so there is nothing here it would be honest to offer an editor for.")


def read_camera(payload: bytes, name: str) -> Dict[str, Any]:
    """The ``CPTH`` header, refusing anything whose own arithmetic does not hold."""

    if len(payload) < containers.CAMERA_HEADER_BYTES or payload[:4] != containers.CAMERA_MAGIC:
        raise containers.DiscError(
            f"{name} does not begin with {containers.CAMERA_MAGIC.decode('latin-1')}; it is not "
            f"a Blitz camera path.")
    word1, records, word3 = struct.unpack_from("<3I", payload, 4)
    expected = containers.CAMERA_HEADER_BYTES + records * containers.CAMERA_RECORD_BYTES
    if expected != len(payload):
        raise containers.DiscError(
            f"{name} declares {records} records, which is {expected} bytes with its header, and "
            f"the member is {len(payload)}; it is not a Blitz camera path.")
    return {"records": records, "word1": word1, "word3": word3,
            "record_bytes": containers.CAMERA_RECORD_BYTES}


def read_wiff(head: bytes, size: int, name: str) -> Dict[str, Any]:
    """The big-endian ``WIFF`` head, refusing anything whose declared size is not the member."""

    if len(head) < 12 or head[:4] != containers.WIFF_MAGIC:
        raise containers.DiscError(
            f"{name} does not begin with {containers.WIFF_MAGIC.decode('latin-1')}; it is not a "
            f"Blitz WIFF container.")
    declared = struct.unpack_from(">I", head, 4)[0]
    if declared + 8 != size:
        raise containers.DiscError(
            f"{name} declares {declared} big-endian body bytes in a {size}-byte member, and "
            f"{declared} + 8 is not {size}; it is not a Blitz WIFF container.")
    return {"declared_body_bytes": declared, "form": head[8:12].decode("latin-1")}


def walk_clump(payload: bytes, name: str) -> Dict[str, Any]:
    """A ``.dff``'s top-level RenderWare sections, and whether they consume the member."""

    sections = list(rw_txd.walk(payload, 0, len(payload)))
    consumed = bool(sections) and sections[-1].end == len(payload)
    return {"sections": len(sections), "consumed_whole_member": consumed,
            "ids": ["0x%x" % section.id for section in sections[:8]],
            "library_version": "0x%08x" % sections[0].version if sections else None}


class ContainerInventoryLane:
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "scorebug_presentation"
    page = "presentation"
    title = "Camera paths, WIFF containers and RenderWare clumps"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (f"tools/validate_{GAME_ID}_containers.sh",
                  f"tools/validate_{GAME_ID}_containers.bat")
    fixed_allocation = True
    read_only = True
    REFUSAL = REFUSAL

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        cameras: List[Dict[str, Any]] = []
        wiffs: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        camera_words: Dict[str, int] = {}
        wiff_forms: Dict[str, int] = {}
        clump_totals = {"members": 0, "consumed_whole_member": 0}
        clump_sequences: Dict[str, int] = {}
        versions: Dict[str, int] = {}
        with containers.Disc(Path(source)) as disc:
            for member in disc.members_named(suffix=containers.CAMERA_SUFFIX):
                if progress is not None:
                    progress(f"{member.name}…")
                try:
                    row = read_camera(disc.member_bytes(member.name), member.name)
                except containers.DiscError as exc:
                    refusals.append({"where": member.name, "sentence": str(exc)})
                    continue
                row.update({"member": member.name, "bytes": member.size})
                cameras.append(row)
                camera_words[str(row["word1"])] = camera_words.get(str(row["word1"]), 0) + 1
                if len(targets) < containers.MAX_TARGETS:
                    targets.append(Target(
                        key=f"camera:{member.name}", label=member.name,
                        detail=f"{row['records']} record(s) x "
                               f"{containers.CAMERA_RECORD_BYTES} bytes · {member.size} bytes",
                        budget="Read-only: a record's fields are not measured.",
                        searchable=member.name, raw=dict(row),
                        fields=(Field("records", "note", "Records", str(row["records"]),
                                      read_only=True),
                                Field("word1", "note", "Header word 1 (unnamed)",
                                      str(row["word1"]), read_only=True))))
            for suffix in containers.WIFF_SUFFIXES:
                for member in disc.members_named(suffix=suffix):
                    try:
                        row = read_wiff(disc.head(member.name, 12), member.size, member.name)
                    except containers.DiscError as exc:
                        refusals.append({"where": member.name, "sentence": str(exc)})
                        continue
                    row.update({"member": member.name, "bytes": member.size})
                    wiffs.append(row)
                    wiff_forms[row["form"]] = wiff_forms.get(row["form"], 0) + 1
                    if len(targets) < containers.MAX_TARGETS:
                        targets.append(Target(
                            key=f"wiff:{member.name}", label=member.name,
                            detail=f"WIFF form {row['form']!r} · {member.size} bytes",
                            budget="Read-only: no chunk inside a WIFF is read.",
                            searchable=member.name, raw=dict(row),
                            fields=(Field("form", "note", "Form type", row["form"],
                                          read_only=True),)))
            for member in disc.members_named(suffix=containers.MODEL_SUFFIX):
                try:
                    row = walk_clump(disc.member_bytes(member.name), member.name)
                except containers.DiscError as exc:
                    refusals.append({"where": member.name, "sentence": str(exc)})
                    continue
                clump_totals["members"] += 1
                clump_totals["consumed_whole_member"] += 1 if row["consumed_whole_member"] else 0
                key = " ".join(row["ids"])
                clump_sequences[key] = clump_sequences.get(key, 0) + 1
                if row["library_version"]:
                    versions[row["library_version"]] = versions.get(row["library_version"], 0) + 1
        document = {
            "schema": SCHEMA, "source": str(source), "lane": self.lane_id, "why": self.REFUSAL,
            "camera_paths": len(cameras), "camera_records": sum(r["records"] for r in cameras),
            "camera_header_word1_census": camera_words,
            "wiff_members": len(wiffs), "wiff_forms": wiff_forms,
            "clump_members": clump_totals["members"],
            "clumps_whose_walk_consumes_the_member": clump_totals["consumed_whole_member"],
            "clump_top_level_sequences": dict(sorted(clump_sequences.items(),
                                                     key=lambda item: -item[1])[:6]),
            "clump_library_versions": versions,
            "targets_listed": len(targets), "cameras": cameras, "wiffs": wiffs,
            "refusals": refusals,
        }
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": SCHEMA, "lane": self.lane_id, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


LANE = ContainerInventoryLane()


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{GAME_ID}.camera_lane",
        description="List the camera paths, WIFF containers and clumps of an NFL Blitz 2002 "
                    "(PS2) disc. Read-only.")
    parser.add_argument("--source")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                catalogue = LANE.build_catalogue(LANE.synthetic_source(Path(room)))
        else:
            if not arguments.source:
                parser.error("give --source a disc image, or --selftest")
            catalogue = LANE.build_catalogue(Path(arguments.source))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    print("CONTAINERS cameras=%d records=%d wiff=%d forms=%s clumps=%d consumed=%d refusals=%d"
          % (document["camera_paths"], document["camera_records"], document["wiff_members"],
             document["wiff_forms"], document["clump_members"],
             document["clumps_whose_walk_consumes_the_member"], len(document["refusals"])))
    return 0


__all__ = ["CAPABILITY_ID", "ContainerInventoryLane", "LANE", "LANE_ID", "REFUSAL", "SCHEMA",
           "read_camera", "read_wiff", "walk_clump"]


if __name__ == "__main__":
    raise SystemExit(_main())
