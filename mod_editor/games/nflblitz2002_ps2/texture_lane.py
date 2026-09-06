"""The RenderWare texture dictionaries: one inventory and two export pages.

761 ``.rtd`` members on the 2002 disc and 840 on the 2003 disc, holding 10,420
and 11,828 PS2 native rasters [M].  :mod:`mod_editor.games._formats.rw_txd`
opens all of them and decodes the 8-bit and 32-bit ones; the 4-bit ones are
listed with the measured reason nothing is drawn, which the reader states once
and every row here quotes rather than restates.

===========================================================  ==========  ==========
                                                             2002        2003
===========================================================  ==========  ==========
dictionaries read                                            761 of 761  840 of 840
rasters read (equal to the count each dictionary declares)   10,420      11,828
rasters decoded to RGBA (8-bit and 32-bit)                   4,189       6,392
PCSX2 replacement identities derived (8-bit)                 4,166       6,365
rasters listed and not drawn (4-bit)                         6,231       5,436
refusals                                                     0           0
===========================================================  ==========  ==========

**Three rows.**  ``textures.dictionary_inventory`` walks every dictionary on the
disc and writes nothing.  ``uniforms.team_textures`` and ``menus.screen_textures``
are the same walker over two selections -- the 594 dictionaries whose name is
``<a team prefix>_...`` and the 167 that are not -- and each exports a decoded
raster as PNG (2,408 of 8,434 rasters and 1,781 of 1,986 respectively) [M].  The team prefixes are read
off the disc's own ``<two letters>_crowd.ini`` members, so the selection is a
measurement of the disc in hand and never a table to keep in step with it.
None of the three writes: putting a raster back means re-swizzling into the GS
memory image and rewriting the member at its own length, which this module can
do for 8-bit rasters and has **not** proved, so it is not offered.

**Identities are derived, none confirmed.**  A name is what PCSX2's documented
rules compute from the raster's own bytes.  No texture dump of either Blitz disc
exists in this project, so nothing here says a replacement pack was found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_shps, rw_txd
from mod_editor.games.contract import (
    Artifact, Catalogue, Edit, EncodedArt, Field, Plan, Receipt, Refusal, Target, Verdict,
    require,
)

from . import containers, zip_lane

SCHEMA = "nflblitz2002_ps2_texture_dictionaries/v1"
GAME_ID = containers.GAME_ID
_PREFIX = GAME_ID.replace("_", "")

_NO_WRITER = ("This lane exports a raster and writes nothing: putting one back means "
              "re-swizzling it into the GS memory image and rewriting the member at its own "
              "length, which this module has not proved, so no import is offered.")
_INVENTORY_ONLY = ("This lane counts every dictionary and raster on the disc and writes "
                   "nothing; export a raster on the page that owns its dictionary, Uniforms "
                   "& Equipment for a team logo and Menus & UI for everything else.")


def _rows_for(disc: containers.Disc, members: Sequence[Any], *, decode: bool,
              progress: Optional[Callable[[str], None]] = None,
              targets: Optional[List[Target]] = None) -> Dict[str, Any]:
    """Walk a selection of dictionaries; count, and optionally build art targets."""

    totals = {"dictionaries": 0, "rasters": 0, "decodable": 0, "identities": 0,
              "listed_not_drawn": 0}
    depths: Dict[str, int] = {}
    dimensions: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []
    refusals: List[Dict[str, str]] = []
    for number, member in enumerate(members):
        if progress is not None:
            progress(f"{member.name} ({number + 1} of {len(members)})…")
        try:
            dictionary = disc.texture_dictionary(member.name)
        except containers.DiscError as exc:
            refusals.append({"where": member.name, "sentence": str(exc)})
            continue
        totals["dictionaries"] += 1
        row = {"member": member.name, "bytes": member.size, "crc32": "%08x" % member.crc32,
               "library_version": "0x%08x" % dictionary.library_version,
               "declared_textures": dictionary.declared_textures,
               "rasters": len(dictionary.rasters),
               "section_accounts_for_file": dictionary.section_accounts_for_file,
               "decodable": 0}
        for raster in dictionary.rasters:
            totals["rasters"] += 1
            key = str(raster.depth)
            depths[key] = depths.get(key, 0) + 1
            size = f"{raster.width}x{raster.height}"
            dimensions[size] = dimensions.get(size, 0) + 1
            reason = rw_txd.undecodable_reason(raster)
            if reason is None:
                totals["decodable"] += 1
                row["decodable"] += 1
            else:
                totals["listed_not_drawn"] += 1
            identity = None
            if decode and reason is None:
                identity = rw_txd.replacement_identity(dictionary, raster)
            if identity:
                totals["identities"] += 1
            if targets is not None and len(targets) < containers.MAX_TARGETS:
                targets.append(Target(
                    key=f"{member.name}#{raster.index}",
                    label=f"{member.name} · {raster.name or raster.index}",
                    detail=f"{size} · {raster.depth}-bit · "
                           + ("decodes" if reason is None else "listed, not drawn"),
                    budget=("Export only: a PNG import is not offered." if reason is None
                            else "Listed, not drawn."),
                    searchable=f"{member.name} {raster.name} {size}",
                    raw={"member": member.name, "raster": raster.index, "width": raster.width,
                         "height": raster.height, "depth": raster.depth,
                         "raster_format": "0x%08x" % raster.raster_format,
                         "psm": raster.psm, "texture_name": raster.name,
                         "texel_bytes": raster.texel_bytes,
                         "palette_bytes": raster.palette_bytes,
                         "replacement_identity": identity, "refusal": reason},
                    fields=(Field("size", "note", "Size", size, read_only=True),
                            Field("depth", "note", "Bits per texel", str(raster.depth),
                                  read_only=True),
                            Field("identity", "note", "PCSX2 name (derived)", identity or "-",
                                  read_only=True),
                            Field("refusal", "note", "Why not drawn", reason or "-",
                                  read_only=True))))
        rows.append(row)
    return {"totals": totals, "depths": depths, "dimensions": dimensions, "rows": rows,
            "refusals": refusals}


class TextureDictionaryLane:
    """The shared walker.  ``read_only`` lanes count; art lanes also export."""

    recipe_schema = SCHEMA

    def __init__(self, lane_id: str, surface: str, page: str, title: str, classification: str,
                 *, selection: str, refusal: str, validator: str, read_only: bool) -> None:
        self.lane_id = lane_id
        self.capability_id = f"{_PREFIX}.{lane_id}"
        self.surface = surface
        self.page = page
        self.title = title
        self.classification = classification
        self.selection = selection
        self.REFUSAL = refusal
        self.read_only = read_only
        #: An inventory changes nothing; an export writes PNG files beside the disc, not
        #: into it, so neither lane is a fixed-allocation image writer.
        self.fixed_allocation = False
        self.validators = (f"tools/validate_{GAME_ID}_{validator}.sh",
                           f"tools/validate_{GAME_ID}_{validator}.bat")

    def members(self, disc: containers.Disc) -> Tuple[Any, ...]:
        """Which dictionaries this row owns.

        A team's dictionaries are the ones named ``<a team prefix>_...``, and the
        prefixes come off the disc's own crowd tables (:meth:`Disc.team_prefixes`)
        rather than a list this module would have to keep in step: 594 of the 2002
        disc's 761 dictionaries and 653 of the 2003 disc's 840 carry one [M].
        """

        every = disc.members_named(suffix=containers.TEXTURE_SUFFIX)
        if self.selection == "all":
            return every
        prefixes = disc.team_prefixes()
        team = tuple(member for member in every
                     if disc.is_team_member(member.name, prefixes))
        if self.selection == "team":
            return team
        owned = {member.name for member in team}
        return tuple(member for member in every if member.name not in owned)

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = [] if not self.read_only else []
        with containers.Disc(Path(source)) as disc:
            walk = _rows_for(disc, self.members(disc), decode=not self.read_only,
                             progress=progress, targets=targets)
        document = {"schema": SCHEMA, "source": str(source), "lane": self.lane_id,
                    "selection": self.selection, "why": self.REFUSAL,
                    "not_drawn_reason": rw_txd.undecodable_reason(
                        rw_txd.Raster(0, "", "", 8, 8, 4, 0, 0, 0, 0, 0, 0, 0, 0)),
                    "targets_listed": len(targets), **walk}
        if self.read_only:
            targets = [Target(
                key=f"dictionary:{row['member']}", label=row["member"],
                detail=f"{row['rasters']} raster(s) · {row['decodable']} decode · "
                       f"{row['bytes']} bytes",
                budget="Read-only: this lane counts and writes nothing.",
                searchable=row["member"], raw=dict(row),
                fields=(Field("rasters", "note", "Rasters", str(row["rasters"]), read_only=True),
                        Field("decodable", "note", "Decodable", str(row["decodable"]),
                              read_only=True))) for row in walk["rows"][:containers.MAX_TARGETS]]
            document["targets_listed"] = len(targets)
        return Catalogue(SCHEMA, self.lane_id, str(source), tuple(targets), document)

    # -- exporting: an art lane writes PNG files, never the disc ------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """An export carries no values; any value proposed is refused by name."""

        if self.read_only or values:
            return self.REFUSAL
        if target.raw.get("refusal"):
            return str(target.raw["refusal"])
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        if self.read_only:
            return {"schema": SCHEMA, "lane": self.lane_id, "exports": []}
        return {"schema": SCHEMA, "lane": self.lane_id,
                "exports": [edit.target_key for edit in edits]}

    def _resolve(self, catalogue: Catalogue, recipe: Mapping[str, Any]) -> List[Target]:
        if self.read_only:
            raise Refusal(self.REFUSAL)
        keys = list(recipe.get("exports") or ())
        if not keys:
            raise Refusal("This recipe names no raster; choose one to export before building.")
        out = []
        for key in keys:
            target = catalogue.target(str(key))
            reason = target.raw.get("refusal")
            if reason:
                raise Refusal(str(reason))
            out.append(target)
        return out

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        targets = self._resolve(catalogue, recipe)
        return Plan(self.lane_id, tuple(target.key for target in targets), (),
                    {"schema": SCHEMA, "lane": self.lane_id, "exports": len(targets),
                     "note": "An export writes PNG files beside the disc; it declares files, "
                             "not byte ranges, and never touches the source."})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        targets = self._resolve(catalogue, recipe)
        destination = Path(destination)
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite it.")
        artifacts: List[Artifact] = []
        rows: List[Dict[str, Any]] = []
        for number, target in enumerate(targets):
            png = self.decode_png(Path(source), target)
            where = destination if number == 0 else destination.with_name(
                f"{destination.stem}-{number}{destination.suffix or '.png'}")
            where.write_bytes(png)
            digest = hashlib.sha256(png).hexdigest()
            artifacts.append(Artifact(str(where), digest, kind="png"))
            rows.append({"target": target.key, "path": str(where), "bytes": len(png),
                         "sha256": digest, "width": int(target.raw["width"]),
                         "height": int(target.raw["height"]),
                         "replacement_identity": target.raw.get("replacement_identity")})
        document = {"schema": SCHEMA, "lane": self.lane_id, "exports": rows,
                    "no_writer": _NO_WRITER}
        return Receipt(SCHEMA, self.lane_id, str(source), str(destination), (), document,
                       tuple(artifacts))

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-decode every exported raster from the source and compare, importing no build state."""

        failures: List[str] = []
        rows = list(receipt.document.get("exports") or ())
        destination = Path(destination)
        for number, row in enumerate(rows):
            # The file to check is the destination this call names, laid out by the same
            # rule the build used, not the path the receipt happens to remember: a
            # verifier that read the receipt's path would never see a tampered copy.
            path = destination if number == 0 else destination.with_name(
                f"{destination.stem}-{number}{destination.suffix or '.png'}")
            if not path.is_file():
                failures.append(f"{path} was not written")
                continue
            written = path.read_bytes()
            if hashlib.sha256(written).hexdigest() != row["sha256"]:
                failures.append(f"{path} does not carry the bytes the receipt names")
            member, _, index = str(row["target"]).rpartition("#")
            with containers.Disc(Path(source)) as disc:
                dictionary = disc.texture_dictionary(member)
                raster = dictionary.raster(int(index))
                rgba = rw_txd.decode_rgba(dictionary, raster)
            again = ea_shps.encode_png(raster.width, raster.height, rgba)
            if again != written:
                failures.append(f"{path} is not what the source's own bytes decode to")
            if raster.width != int(row["width"]) or raster.height != int(row["height"]):
                failures.append(f"{path} does not carry the raster's measured size")
        if not rows:
            failures.append("the receipt names no export")
        summary = (f"{len(rows)} raster(s) exported and re-decoded from the source; every PNG "
                   f"matches its digest and the source's own bytes")
        if failures:
            summary = "; ".join(failures[:3])
        return Verdict(not failures, summary,
                       {"exports": len(rows), "failures": failures, "no_writer": _NO_WRITER})

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        if self.read_only:
            raise Refusal(self.REFUSAL)
        for target in catalogue.targets:
            if not target.raw.get("refusal"):
                return (Edit(target.key, {}, note="conformance: export this raster"),)
        raise Refusal("This catalogue lists no raster this reader draws.")

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{GAME_ID}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    # -- ArtLane ------------------------------------------------------------

    def decode_png(self, source: Path, target: Target) -> bytes:
        with containers.Disc(Path(source)) as disc:
            dictionary = disc.texture_dictionary(str(target.raw["member"]))
            raster = dictionary.raster(int(target.raw["raster"]))
            rgba = rw_txd.decode_rgba(dictionary, raster)
        return ea_shps.encode_png(raster.width, raster.height, rgba)

    def encode(self, source: Path, target: Target, png: bytes) -> EncodedArt:
        raise Refusal(_NO_WRITER)

    def replacement_identity(self, target: Target) -> Optional[str]:
        value = target.raw.get("replacement_identity")
        return str(value) if value else None


INVENTORY_LANE = TextureDictionaryLane(
    "textures.dictionary_inventory", "textures", "textures",
    "Every RenderWare texture dictionary on the disc", "read-only-mapped",
    selection="all", refusal=_INVENTORY_ONLY, validator="textures", read_only=True)
TEAM_LANE = TextureDictionaryLane(
    "uniforms.team_textures", "uniforms", "uniforms",
    "The per-team texture dictionaries", "extract-only",
    selection="team", refusal=_NO_WRITER, validator="art", read_only=False)
SCREEN_LANE = TextureDictionaryLane(
    "menus.screen_textures", "menus", "menus",
    "Every texture dictionary that is not a team's", "extract-only",
    selection="other", refusal=_NO_WRITER, validator="art", read_only=False)

LANES = (INVENTORY_LANE, TEAM_LANE, SCREEN_LANE)
_BY_NAME = {"inventory": INVENTORY_LANE, "team": TEAM_LANE, "screens": SCREEN_LANE}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"mod_editor.games.{GAME_ID}.texture_lane",
        description="Walk the RenderWare texture dictionaries of an NFL Blitz 2002 (PS2) disc.")
    parser.add_argument("--lane", choices=sorted(_BY_NAME), default="inventory")
    parser.add_argument("--source")
    parser.add_argument("--out")
    parser.add_argument("--export-png")
    parser.add_argument("--target")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = _BY_NAME[arguments.lane]
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                source = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(source)
                document = dict(catalogue.document)
                exported = 0
                if not lane.read_only:
                    for target in catalogue.targets:
                        if target.raw.get("refusal") is None:
                            png = lane.decode_png(source, target)
                            if not png.startswith(b"\x89PNG"):
                                print("error: the export is not a PNG", file=sys.stderr)
                                return 1
                            exported += 1
                    if exported == 0:
                        print("error: the synthetic source exported no raster", file=sys.stderr)
                        return 1
                totals = document["totals"]
                print("SELFTEST lane=%s dictionaries=%d rasters=%d decodable=%d identities=%d "
                      "exported=%d" % (lane.lane_id, totals["dictionaries"], totals["rasters"],
                                       totals["decodable"], totals["identities"], exported))
                return 0
        if not arguments.source:
            parser.error("give --source a disc image, or --selftest")
        catalogue = lane.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
        document = dict(catalogue.document)
        if arguments.export_png and arguments.target:
            png = lane.decode_png(Path(arguments.source), catalogue.target(arguments.target))
            Path(arguments.export_png).write_bytes(png)
            print("EXPORT %s %d bytes" % (arguments.export_png, len(png)))
        totals = document["totals"]
        print("TEXTURES lane=%s dictionaries=%d rasters=%d decodable=%d identities=%d "
              "not_drawn=%d refusals=%d"
              % (lane.lane_id, totals["dictionaries"], totals["rasters"], totals["decodable"],
                 totals["identities"], totals["listed_not_drawn"], len(document["refusals"])))
        if arguments.out:
            Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


__all__ = ["INVENTORY_LANE", "LANES", "SCHEMA", "SCREEN_LANE", "TEAM_LANE",
           "TextureDictionaryLane"]


if __name__ == "__main__":
    raise SystemExit(_main())
