"""The ``/DATA`` container census every module on this stack opens with.

The first rung and the one every other lane stands on: walk ``/DATA``, open each
EA ``TERF`` container through the shared reader, and say what is in it -- the
chunk chain, the alignment, how many members, which codec packs them, and,
because a packed member's stored magic tells you nothing, what format each
member's *decompressed* bytes carry.

It writes nothing.  ``plan``, ``build`` and ``verify`` refuse by contract rather
than quietly doing nothing, which is what ``read_only`` marks and what the
studio reads to draw this page as a table instead of an editor.

**What a game supplies** is its ``containers`` module, the four identity
strings, its two validators and one refusal sentence.  Everything else -- the
walk, the sampling, the two target shapes and their read-only fields -- is the
same on every disc in this family, and was written three times before it was
written here.

**The member cap is per container, not per disc.**  A flat cap spent in disc
order leaves every container after the big one with no rows at all: NFL Street
3 holds 27,178 members and 16,259 of them are in one container, so a flat 4,000
would have listed that container and nothing after it.  The same defect listed
130 of 1,407 banks on MVP 05 until it was found.  :attr:`max_members_per_container`
is the second bound, and the document says both.

**Retail-free.**  Names, offsets, sizes, codecs and format labels.  No member
payload leaves the user's disc.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict,
)

#: How many member rows the page lists across the whole disc.  A page of a few
#: thousand rows is a table; more is a data dump nobody reads.  The document
#: keeps the whole census either way.
MAX_MEMBER_TARGETS = 4000

#: How many members of one container are decompressed to classify their format.
#: Classifying every member of a large ``LZH1`` archive in pure Python costs
#: minutes; a per-container sample gives an honest histogram in seconds, and
#: the row says how much of the container it covers.
FORMAT_SAMPLE = 256

#: The per-container share of :data:`MAX_MEMBER_TARGETS`, so one large archive
#: cannot spend the whole budget before the walk reaches the next container.
MAX_MEMBERS_PER_CONTAINER = 200


class ContainerInventoryLane:
    """The disc's containers and their members, read-only."""

    #: The game's own ``containers`` module.
    discs: Any = None
    lane_id = ""
    capability_id = ""
    surface = "textures"
    page = "textures"
    title = "Every /DATA container on the disc"
    classification = "read-only-mapped"
    recipe_schema = ""
    validators: Tuple[str, ...] = ()
    fixed_allocation = False
    read_only = True

    #: The sentence the three write entry points raise, verbatim.  A game sets
    #: it because it names that game's own documents.
    REFUSAL = ""

    #: The two bounds, and how deep the format sample goes.
    max_member_targets = MAX_MEMBER_TARGETS
    max_members_per_container = MAX_MEMBERS_PER_CONTAINER
    format_sample = FORMAT_SAMPLE

    #: What :meth:`synthetic_source` calls the image it writes.
    synthetic_name = "inventory-synthetic.iso"

    # -- catalogue -----------------------------------------------------

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        discs = self.discs
        image = discs.open_disc(Path(source))
        files = discs.data_files(image)
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        members_listed = 0
        totals: Dict[str, int] = {}
        codec_totals: Dict[str, int] = {}
        container_count = 0
        member_count = 0
        unread = 0
        for position, entry in enumerate(files):
            if progress is not None:
                progress(f"{entry.name} ({position + 1} of {len(files)})…")
            report, container = discs.describe_container(image, entry, with_formats=False)
            sampled = 0
            formats: Dict[str, int] = {}
            if container is not None:
                container_count += 1
                member_count += len(container)
                for name, count in (report.codec_histogram or {}).items():
                    codec_totals[name] = codec_totals.get(name, 0) + count
                for index in range(min(len(container), self.format_sample)):
                    label = self._member_format(container, index)
                    formats[label] = formats.get(label, 0) + 1
                    totals[label] = totals.get(label, 0) + 1
                    sampled += 1
            elif report.kind == "not-read":
                unread += 1
            row = report.document()
            row["formats"] = formats
            row["formats_sampled"] = sampled
            rows.append(row)
            targets.append(self._container_target(row))
            if container is None:
                continue
            here = 0
            for index in range(len(container)):
                if members_listed >= self.max_member_targets:
                    break
                if here >= self.max_members_per_container:
                    break
                member = container.members[index]
                targets.append(self._member_target(
                    entry.name, member,
                    self._member_format(container, index) if index < sampled else None))
                members_listed += 1
                here += 1
        document = {
            "schema": self.recipe_schema,
            "source": str(source),
            "data_directory": discs.DATA_DIRECTORY,
            "files": len(files),
            "containers": container_count,
            "containers_not_read": unread,
            "members": member_count,
            "member_rows_listed": members_listed,
            "member_rows_cap": self.max_member_targets,
            "member_rows_cap_per_container": self.max_members_per_container,
            "format_sample_per_container": self.format_sample,
            "container_size_limit": discs.CONTAINER_SIZE_LIMIT,
            "codec_totals": codec_totals,
            "format_totals": totals,
            "rows": rows,
        }
        return Catalogue(schema=self.recipe_schema, lane_id=self.lane_id,
                         source=str(source), targets=tuple(targets), document=document)

    @staticmethod
    def _member_format(container: ea_terf.TerfContainer, index: int) -> str:
        """What member *index* holds after decompression, or why it is unknown.

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
        detail = [f"stored {member.stored_size:,} bytes", member.codec_name]
        if member.compressed:
            detail.append(f"unpacks to {member.decompressed_size:,}")
        if member_format:
            detail.append(member_format)
        return Target(
            key=f"member:{container_name}:{member.index}",
            label=f"{container_name} member {member.index}",
            detail=" · ".join(detail),
            budget="Read-only: this lane never writes to your disc.",
            searchable=(f"{container_name} {member.index} {member.codec_name} "
                        f"{member_format or ''}"),
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
        """An empty recipe.  Composing is not where a read-only lane refuses."""

        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / self.synthetic_name
        path.write_bytes(self.discs.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


__all__ = ["ContainerInventoryLane", "FORMAT_SAMPLE", "MAX_MEMBERS_PER_CONTAINER",
           "MAX_MEMBER_TARGETS"]
