"""Every ``/DATA`` container on the user's Madden 09 disc, listed and never written.

This is the module's first rung and the one every other lane stands on.  It
walks the disc's ``/DATA`` directory, opens each EA ``TERF`` container through
the shared reader, and says what is in it: the chunk chain, the alignment, how
many members, which codec packs them, and -- because a packed member's stored
magic tells you nothing -- what format each member's *decompressed* bytes
actually carry.

It writes nothing.  ``plan``, ``build`` and ``verify`` refuse by contract
rather than quietly doing nothing, which is what ``read_only`` marks and what
the studio reads to draw this page as a table instead of an editor.

**Retail-free.**  Names, offsets, sizes, codecs and format labels.  No member
payload leaves the user's disc.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.inventory_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import (
    Catalogue,
    Edit,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
)

from . import containers

CAPABILITY_ID = "madden09ps2.textures.container_inventory"
LANE_ID = "textures.container_inventory"
SCHEMA = "madden09_ps2_container_inventory/v1"

#: A retail disc holds 107 containers and 47,769 members [M].  A page of a few
#: thousand rows is a table; more is a data dump nobody reads.  The document
#: keeps the whole census either way -- per-container counts and histograms are
#: complete however many member rows are listed.
MAX_MEMBER_TARGETS = 4000

#: How many members of one container are decompressed to classify their
#: format.  Classifying every member of every container means unpacking tens of
#: thousands of ``LZH1`` streams in pure Python; a per-container sample of this
#: many gives an honest histogram in seconds, and the row says how much of the
#: container the histogram covers so nobody reads it as the whole.
FORMAT_SAMPLE = 256


class InventoryLane:
    """The disc's containers and their members, read-only."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "textures"
    page = "textures"
    title = "Every /DATA container on the disc"
    classification = "read-only-mapped"
    recipe_schema = SCHEMA
    validators = (
        "tools/validate_madden09_ps2_inventory.sh",
        "tools/validate_madden09_ps2_inventory.bat",
    )
    fixed_allocation = False
    #: The marker a shell reads.  A protocol with no member of its own would
    #: match every lane at runtime, so this value is the whole distinction.
    read_only = True

    REFUSAL = (
        "The container inventory only lists what is on your disc; it writes nothing, so "
        "there is nothing here to plan, build or verify. Use the Uniforms page to export "
        "art, or wait for a writer lane -- none exists yet, because no Madden 09 container "
        "has been rebuilt and booted."
    )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        files = containers.data_files(image)
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        members_listed = 0
        totals: Dict[str, int] = {}
        codec_totals: Dict[str, int] = {}
        container_count = 0
        member_count = 0
        for position, entry in enumerate(files):
            if progress is not None:
                progress(f"{entry.name} ({position + 1} of {len(files)})…")
            report, container = containers.describe_container(image, entry, with_formats=False)
            sampled = 0
            formats: Dict[str, int] = {}
            if container is not None:
                container_count += 1
                member_count += len(container)
                for name, count in report.codec_histogram.items():
                    codec_totals[name] = codec_totals.get(name, 0) + count
                for index in range(min(len(container), FORMAT_SAMPLE)):
                    label = self._member_format(container, index)
                    formats[label] = formats.get(label, 0) + 1
                    totals[label] = totals.get(label, 0) + 1
                    sampled += 1
            row = report.document()
            row["formats"] = formats
            row["formats_sampled"] = sampled
            rows.append(row)
            targets.append(self._container_target(row))
            if container is None:
                continue
            for index in range(len(container)):
                if members_listed >= MAX_MEMBER_TARGETS:
                    break
                member = container.members[index]
                targets.append(self._member_target(
                    entry.name, member,
                    self._member_format(container, index) if index < sampled else None,
                ))
                members_listed += 1
        document = {
            "schema": SCHEMA,
            "source": str(source),
            "data_directory": containers.DATA_DIRECTORY,
            "files": len(files),
            "containers": container_count,
            "members": member_count,
            "member_rows_listed": members_listed,
            "member_rows_cap": MAX_MEMBER_TARGETS,
            "format_sample_per_container": FORMAT_SAMPLE,
            "codec_totals": codec_totals,
            "format_totals": totals,
            "rows": rows,
        }
        return Catalogue(
            schema=SCHEMA,
            lane_id=self.lane_id,
            source=str(source),
            targets=tuple(targets),
            document=document,
        )

    @staticmethod
    def _member_format(container: ea_terf.TerfContainer, index: int) -> str:
        """What member *index* holds, after decompression, or why it is unknown.

        A member the codec cannot open is named as such rather than counted as
        an unclassified one: "this reader cannot open it" and "there is nothing
        recognisable there" are different facts.
        """

        try:
            return container.member_format(index) or "unclassified"
        except ea_terf.UnsupportedCodec:
            return "unsupported codec"
        except ea_terf.TerfError:
            return "unreadable"

    @staticmethod
    def _container_target(row: Mapping[str, Any]) -> Target:
        detail = [row["kind"], f"{row['recorded_length']:,} bytes"]
        if row.get("chunk_chain"):
            detail.append(row["chunk_chain"])
        if row.get("member_count"):
            detail.append(f"{row['member_count']:,} members")
        if row.get("note"):
            detail.append(row["note"])
        return Target(
            key=f"container:{row['name']}",
            label=row["path"],
            detail=" · ".join(detail),
            budget="Read-only: this lane never writes to your disc.",
            searchable=f"{row['name']} {row['kind']} {row.get('chunk_chain', '')}",
            raw=dict(row),
            fields=(
                Field("kind", "note", "Kind",
                      "Whether this file is a TERF container, a bare EA TDB, or neither.",
                      read_only=True),
                Field("chunk_chain", "note", "Chunk chain",
                      "The chunks the container walks, in order.", read_only=True),
                Field("alignment", "note", "Alignment",
                      "The member-data alignment the container declares.", read_only=True),
                Field("member_count", "note", "Members",
                      "How many members its directory lists.", read_only=True),
                Field("codecs", "note", "Codecs",
                      "How many members each codec packs.", read_only=True),
                Field("formats", "note", "Member formats",
                      "What the sampled members' decompressed bytes carry.", read_only=True),
                Field("recorded_length", "note", "Recorded size",
                      "What the disc's own directory record says.", read_only=True),
            ),
        )

    @staticmethod
    def _member_target(container_name: str, member: ea_terf.Member,
                       member_format: Optional[str]) -> Target:
        detail = [
            f"stored {member.stored_size:,} bytes",
            member.codec_name,
        ]
        if member.compressed:
            detail.append(f"unpacks to {member.decompressed_size:,}")
        if member_format:
            detail.append(member_format)
        return Target(
            key=f"member:{container_name}:{member.index}",
            label=f"{container_name} member {member.index}",
            detail=" · ".join(detail),
            budget="Read-only: this lane never writes to your disc.",
            searchable=f"{container_name} {member.index} {member.codec_name} {member_format or ''}",
            raw={
                "container": container_name,
                "index": member.index,
                "offset": member.offset,
                "stored_size": member.stored_size,
                "codec": member.codec,
                "codec_name": member.codec_name,
                "decompressed_size": member.decompressed_size,
                "format": member_format,
                "empty": member.empty,
            },
            fields=(
                Field("offset", "note", "Offset",
                      "Where the member sits, relative to the DATA chunk's tag.",
                      read_only=True),
                Field("stored_size", "note", "Stored size",
                      "How many bytes it occupies on the disc.", read_only=True),
                Field("codec_name", "note", "Codec",
                      "How the member is packed, if it is.", read_only=True),
                Field("decompressed_size", "note", "Unpacked size",
                      "What the container's codec table says it unpacks to.",
                      read_only=True),
                Field("format", "note", "Format",
                      "What its decompressed bytes carry; blank when it was not sampled.",
                      read_only=True),
            ),
        )

    # -- the three refusals --------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        """An empty recipe.  Composing is not where a read-only lane refuses.

        Refusing here would refuse while the user is still reading the table,
        which is the wrong moment and the wrong sentence.  The three methods
        that would *write* are where this lane says no.
        """

        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "madden09-ps2-inventory-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.inventory_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.inventory_lane",
        description="List every /DATA container on a Madden NFL 09 (PS2) disc. Read-only.",
    )
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--selftest", action="store_true",
                        help="run the lane on its synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = InventoryLane()
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
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
    print("INVENTORY containers=%d members=%d listed=%d formats=%s"
          % (document["containers"], document["members"],
             document["member_rows_listed"],
             ",".join(f"{k}:{v}" for k, v in sorted(document["format_totals"].items()))))
    return 0


__all__ = ["CAPABILITY_ID", "FORMAT_SAMPLE", "InventoryLane", "LANE_ID",
           "MAX_MEMBER_TARGETS", "SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())
