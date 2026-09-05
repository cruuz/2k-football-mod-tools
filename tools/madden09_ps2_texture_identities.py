#!/usr/bin/env python3
"""Pair a PCSX2 texture dump of Madden NFL 09 with the disc's own ``MMAP`` textures.

PCSX2 finds a replacement texture by a filename it builds while the game
draws: ``<tex0 hash>-<clut hash>-<bits>.png``, where the two hashes are XXH3-64
over the GS's own texture and CLUT memory and ``bits`` packs ``PSM | TW<<6 |
TH<<10 | TCC<<14``.  Nothing in a disc file carries that name, so a lane that
wants to write a replacement pack has to *learn* the mapping from a run of the
game.

**This tool learns it from pixels.**  Given a directory PCSX2 filled with
``DumpDirectTextures``/``DumpPaletteTextures`` and the user's own disc, it
decodes every ``MMAP`` surface on the disc, decodes every dumped PNG, and pairs
them on exact pixel equality.  A pair is a fact about two files the user owns:
*this member, this image, this mip level* is the thing PCSX2 saw, and *that* is
the name it will look for.

Two details make the equality exact rather than approximate, and both were
measured against a real dump of the retail disc:

* **PCSX2 dumps the CLUT's own alpha**, 0..128 as the PS2 stores it, not
  rescaled to 0..255.  (Across 348 dumped textures the alpha histogram peaks
  hard at 128 and reaches 155; a 0..255 rescale could not produce either.)
  So the disc side is decoded with ``mmap_art.decode_rgba(raw_alpha=True)``.
* **A texture is dumped once per naming convention.**  With
  ``ClassicTextureNames`` the ``bits`` word carries TCC in bit 14 and stock
  PCSX2 drops it, so the same pixels arrive under two names.  Both are kept:
  the classic name is what PenguinScreen2 and the legacy packs load, the modern
  one is what a stock build looks for.

What this tool does **not** do is claim the emulator will load the result: it
records the names PCSX2 wrote while dumping, and a pack is only proved when one
is loaded.  It also does not put a single pixel in the repository -- the
document it writes is counts, dimensions, filenames and member indexes.

Usage::

    madden09_ps2_texture_identities.py --source DISC.iso --dump-dir DIR \\
        --out docs/product/measured/madden09_ps2/pcsx2-texture-identities.json
    madden09_ps2_texture_identities.py --source DISC.iso --index CACHE.jsonl \\
        --containers UNIFORMS.DAT,FIELDART.DAT
    madden09_ps2_texture_identities.py --selftest
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import time
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_terf                      # noqa: E402
from mod_editor.games.madden09_ps2 import containers, mmap_art     # noqa: E402
from mod_editor.games.madden09_ps2.uniform_art import (            # noqa: E402
    IDENTITY_DOCUMENT,
    IDENTITY_SCHEMA,
    load_identities,
    read_rgba_png,
    write_rgba_png,
)

#: The schema and the path are the lane's, not this tool's: the lane is what
#: reads the table, so it owns where it lives and what it must say.
SCHEMA = IDENTITY_SCHEMA
INDEX_SCHEMA = "madden09_ps2_disc_texture_index/v1"
DEFAULT_OUT = IDENTITY_DOCUMENT

#: The containers worth scanning: every one whose members carry ``MMAP``
#: textures the decoder reads.  ``UIS_MCFL.DAT`` is left out on purpose --
#: all 1,188 of its members store their pixels under EA codec 4 (``IPU1``),
#: which nothing here decodes.
DEFAULT_CONTAINERS = (
    "UNIFORMS.DAT", "PLYRFACE.DAT", "COACFACE.DAT", "TATTOOS.DAT",
    "FIELDART.DAT", "STADIUMS.DAT",
)

#: PCSX2's own filename grammar.  The region suffix appears when the game
#: draws a sub-rectangle of a larger texture; it is part of the name and is
#: carried through rather than interpreted.
_NAME = re.compile(
    r"^(?P<tex0>[0-9a-f]{1,16})-(?P<clut>[0-9a-f]{1,16})"
    r"(?:-r(?P<rw>\d+)x(?P<rh>\d+))?"
    r"(?:-mip(?P<mip>\d+))?"
    r"-(?P<bits>[0-9a-f]{8})\.png$"
)

#: ``GSTextureReplacements.cpp``'s packed property word.
PSM_MASK = 0x3F

#: How many other disc textures an identity records by name before it records
#: only how many there were.  A flat or near-flat texture appears in hundreds
#: of members -- one dump in this corpus matches 598 -- and listing every one
#: on every one of them turns a useful table into a ten-megabyte one without
#: saying anything the count does not.
SHARED_SAMPLE = 8


class IdentityError(ValueError):
    """The tool could not do what it was asked; the sentence says why."""


def texture_bits(psm: int, tw: int, th: int, tcc: int) -> int:
    """``PSM | TW<<6 | TH<<10 | TCC<<14`` -- PCSX2's packed property word."""

    return (psm & PSM_MASK) | (tw << 6) | (th << 10) | (tcc << 14)


def replacement_name(tex0_hash: int, clut_hash: Optional[int], bits: int) -> str:
    """The filename PCSX2 looks for.  ``%llx`` is unpadded; ``bits`` is not."""

    if clut_hash is None:
        return "%x-%08x.png" % (tex0_hash, bits)
    return "%x-%x-%08x.png" % (tex0_hash, clut_hash, bits)


@dataclass(frozen=True)
class DumpTexture:
    """One PNG PCSX2 wrote, and what its name says about it."""

    name: str
    convention: str
    width: int
    height: int
    tex0: int
    clut: Optional[int]
    bits: int
    region: Optional[Tuple[int, int]]
    mip: Optional[int]
    rgba_digest: str
    rgb_digest: str
    #: Which captured frames wrote this file.  A name is a name: the same
    #: texture drawn in two frames is one entry with two frames, not two
    #: textures, and the count is how the common UI art tells itself apart
    #: from a kit that appears in one matchup only.
    frames: Tuple[str, ...] = ()

    @property
    def psm(self) -> int:
        return self.bits & PSM_MASK

    @property
    def tcc(self) -> int:
        return (self.bits >> 14) & 1

    def as_dict(self) -> dict:
        return {
            "name": self.name, "convention": self.convention,
            "width": self.width, "height": self.height,
            "bits": "%08x" % self.bits, "psm": self.psm, "tcc": self.tcc,
            "region": list(self.region) if self.region else None,
            "mip": self.mip, "frames": list(self.frames),
        }


@dataclass(frozen=True)
class DiscTexture:
    """One decoded surface of one member, digested rather than kept."""

    container: str
    member: int
    image: int
    level: int
    width: int
    height: int
    rgba_digest: str
    rgb_digest: str
    name: str = ""

    @property
    def key(self) -> str:
        return f"{self.container}:{self.member}:{self.image}"

    def as_dict(self) -> dict:
        return {
            "container": self.container, "member": self.member, "image": self.image,
            "level": self.level, "width": self.width, "height": self.height,
            "rgba": self.rgba_digest, "rgb": self.rgb_digest, "name": self.name,
        }

    @classmethod
    def from_dict(cls, row: dict) -> "DiscTexture":
        return cls(container=row["container"], member=int(row["member"]),
                   image=int(row["image"]), level=int(row["level"]),
                   width=int(row["width"]), height=int(row["height"]),
                   rgba_digest=row["rgba"], rgb_digest=row["rgb"],
                   name=row.get("name", ""))


def _digests(width: int, height: int, rgba: bytes) -> Tuple[str, str]:
    """``(RGBA digest, RGB-only digest)`` for one decoded surface.

    The RGB-only digest exists so a texture whose alpha the game overrides --
    ``TCC`` says the CLUT's alpha is ignored -- can still be recognised, and
    so a near-miss can be told apart from a miss.
    """

    rgb = bytearray(width * height * 3)
    rgb[0::3] = rgba[0::4]
    rgb[1::3] = rgba[1::4]
    rgb[2::3] = rgba[2::4]
    return hashlib.sha256(rgba).hexdigest(), hashlib.sha256(bytes(rgb)).hexdigest()


def scan_dump(directory: Path, *, convention: Optional[str] = None) -> List[DumpTexture]:
    """Every PNG in *directory*, parsed and digested.

    A subdirectory is one naming convention: ``classic`` and ``modern`` are
    what a two-pass dump produces, and a flat directory is taken as one
    unnamed convention.
    """

    directory = Path(directory)
    if not directory.is_dir():
        raise IdentityError(f"{directory} is not a directory of dumped PNGs.")
    #: Every directory below *directory* that actually holds PNGs.  A capture
    #: session is ``<stamp>/<convention>/``, one stamp per frame, so the leaf
    #: name is the convention and its parent is the frame -- and a flat
    #: directory of PNGs is one unnamed frame.
    leaves = sorted(path for path in [directory, *directory.rglob("*")]
                    if path.is_dir() and any(path.glob("*.png")))
    seen: Dict[Tuple[str, str], DumpTexture] = {}
    frames: Dict[Tuple[str, str], List[str]] = {}
    for path in leaves:
        label = convention or path.name
        frame = path.parent.name if path != directory else ""
        for png in sorted(path.glob("*.png")):
            match = _NAME.match(png.name)
            if match is None:
                continue
            key = (label, png.name)
            frames.setdefault(key, [])
            if frame and frame not in frames[key]:
                frames[key].append(frame)
            if key in seen:
                # PCSX2 names a texture after its own pixels, so the same name
                # in two frames is the same picture.  Decoding it twice would
                # cost minutes across a seventeen-frame capture and could not
                # tell us anything new.
                continue
            width, height, rgba = read_rgba_png(png.read_bytes())
            rgba_digest, rgb_digest = _digests(width, height, rgba)
            seen[key] = DumpTexture(
                name=png.name, convention=label, width=width, height=height,
                tex0=int(match.group("tex0"), 16),
                clut=int(match.group("clut"), 16) if match.group("clut") else None,
                bits=int(match.group("bits"), 16),
                region=((int(match.group("rw")), int(match.group("rh")))
                        if match.group("rw") else None),
                mip=int(match.group("mip")) if match.group("mip") else None,
                rgba_digest=rgba_digest, rgb_digest=rgb_digest,
            )
    out = [dump if not frames[(dump.convention, dump.name)]
           else DumpTexture(**{**dump.__dict__,
                               "frames": tuple(sorted(frames[(dump.convention, dump.name)]))})
           for dump in seen.values()]
    out.sort(key=lambda dump: (dump.convention, dump.name))
    if not out:
        raise IdentityError(
            f"{directory} holds no file PCSX2 would have named: a dumped texture is "
            f"<tex0>-<clut>[-r<W>x<H>][-mipN]-<bits>.png. Point this at the "
            f"textures/dumps directory the emulator filled.")
    return out


def index_disc(source: Path, containers_wanted: Sequence[str] = DEFAULT_CONTAINERS, *,
               progress=None) -> Iterable[DiscTexture]:
    """Decode every ``MMAP`` surface of the named containers, digest by digest.

    Yields rather than returning: on the retail disc this is thousands of
    members and a few minutes, and a caller that writes each row as it arrives
    can be interrupted and resumed.
    """

    image = containers.open_disc(Path(source))
    present = {entry.name: entry for entry in containers.data_files(image)}
    for name in containers_wanted:
        entry = present.get(name)
        if entry is None:
            continue
        if progress is not None:
            progress(f"{name}…")
        blob = containers.read_file(image, entry)
        container = ea_terf.parse_terf(blob, allow_size_mismatch=True)
        for member in container.members:
            try:
                payload = container.member(member.index)
            except Exception:                              # noqa: BLE001
                continue
            if not payload.startswith(mmap_art.MMAP_MAGIC):
                continue
            try:
                texture = mmap_art.parse(payload)
            except mmap_art.MmapError:
                continue
            for entry_image in texture.images:
                if texture.undecodable_reason(entry_image) is not None:
                    continue
                for level in range(entry_image.mip_count):
                    try:
                        width, height, rgba = mmap_art.decode_rgba(
                            payload, image=entry_image.index, level=level,
                            texture=texture, raw_alpha=True)
                    except mmap_art.MmapError:
                        continue
                    rgba_digest, rgb_digest = _digests(width, height, rgba)
                    yield DiscTexture(
                        container=name, member=member.index, image=entry_image.index,
                        level=level, width=width, height=height,
                        rgba_digest=rgba_digest, rgb_digest=rgb_digest,
                        name=entry_image.name)
            if progress is not None and member.index % 64 == 0:
                progress(f"{name}: member {member.index}")


def write_index(source: Path, path: Path,
                containers_wanted: Sequence[str] = DEFAULT_CONTAINERS, *,
                progress=None) -> int:
    """Build the disc index into *path*, skipping containers already there."""

    path = Path(path)
    done = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line).get("container"))
    wanted = [name for name in containers_wanted if name not in done]
    written = 0
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in index_disc(source, wanted, progress=progress):
            handle.write(json.dumps(row.as_dict(), sort_keys=True) + "\n")
            written += 1
    return written


def write_dump_index(path: Path, dumps: Sequence[DumpTexture]) -> None:
    """Cache the decoded dump digests, so a second pairing is seconds."""

    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        for dump in dumps:
            row = dict(dump.__dict__)
            row["frames"] = list(dump.frames)
            row["region"] = list(dump.region) if dump.region else None
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_dump_index(path: Path) -> List[DumpTexture]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["frames"] = tuple(row.get("frames") or ())
        row["region"] = tuple(row["region"]) if row.get("region") else None
        out.append(DumpTexture(**row))
    return out


def read_index(path: Path) -> List[DiscTexture]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(DiscTexture.from_dict(json.loads(line)))
    return rows


@dataclass
class MatchReport:
    """What pairing found, in the shape a document and a lane both want."""

    matched: Dict[str, dict] = field(default_factory=dict)
    ambiguous: List[dict] = field(default_factory=list)
    unmatched_dumps: List[dict] = field(default_factory=list)
    rgb_only: List[dict] = field(default_factory=list)
    #: Frame stamp -> the target keys that frame's dumps identified.
    by_frame: Dict[str, List[str]] = field(default_factory=dict)
    dumps_matched: int = 0
    dumps_seen: int = 0
    disc_seen: int = 0


def pair(dumps: Sequence[DumpTexture], disc: Sequence[DiscTexture]) -> MatchReport:
    """Pair on exact pixels, then report what only nearly matched.

    Exactness first and no tolerance at all: two textures that differ by one
    byte are two textures, and a matcher that shrugs at that would hand a lane
    a name for the wrong jersey.  The tolerant leg is a *report*, never a
    match: a dump that agrees on RGB and not on alpha is listed as such,
    because ``TCC`` lets the game ignore a CLUT's alpha and that is a real
    reason for the two to differ.
    """

    report = MatchReport(dumps_seen=len(dumps), disc_seen=len(disc))
    by_rgba: Dict[Tuple[int, int, str], List[DiscTexture]] = {}
    by_rgb: Dict[Tuple[int, int, str], List[DiscTexture]] = {}
    for row in disc:
        by_rgba.setdefault((row.width, row.height, row.rgba_digest), []).append(row)
        by_rgb.setdefault((row.width, row.height, row.rgb_digest), []).append(row)

    for dump in dumps:
        found = by_rgba.get((dump.width, dump.height, dump.rgba_digest))
        if not found:
            loose = by_rgb.get((dump.width, dump.height, dump.rgb_digest))
            if loose:
                report.rgb_only.append({
                    **dump.as_dict(),
                    "candidates": sorted({row.key for row in loose})[:8],
                })
            else:
                report.unmatched_dumps.append(dump.as_dict())
            continue
        keys = sorted({row.key for row in found})
        report.dumps_matched += 1
        if len(keys) > 1:
            # The same picture in more than one member is a real thing on this
            # disc -- two members can carry the same sheet -- and it does not
            # make the name wrong: PCSX2 hashes pixels, so one file replaces
            # every one of them.  The identity is written on all of them and
            # each says which others it shares with, rather than being dropped
            # for an ambiguity the emulator does not have.
            report.ambiguous.append({**dump.as_dict(), "candidates": keys[:12],
                                     "candidate_count": len(keys)})
        for row in {candidate.key: candidate for candidate in found}.values():
            levels = sorted({other.level for other in found if other.key == row.key})
            entry = report.matched.setdefault(row.key, {
                "container": row.container, "member": row.member, "image": row.image,
                "width": row.width, "height": row.height,
                "texture_name": row.name, "levels": levels, "names": {},
            })
            if len(keys) > 1:
                shared = sorted(set(entry.get("shared_with", ())) | (set(keys) - {row.key}))
                entry["shared_count"] = len(shared)
                entry["shared_with"] = shared[:SHARED_SAMPLE]
            entry["names"].setdefault(dump.convention, [])
            if dump.name not in entry["names"][dump.convention]:
                entry["names"][dump.convention].append(dump.name)
            for frame in dump.frames:
                keys_for_frame = report.by_frame.setdefault(frame, [])
                if row.key not in keys_for_frame:
                    keys_for_frame.append(row.key)
            entry.setdefault("frames", [])
            # Frames from a dump that matched THIS texture and nothing else.
            # Attribution runs on those: a picture several members share tells
            # you which frames drew the picture, not which drew the member.
            entry.setdefault("exclusive_frames", [])
            for frame in dump.frames:
                if frame not in entry["frames"]:
                    entry["frames"].append(frame)
                if len(keys) == 1 and frame not in entry["exclusive_frames"]:
                    entry["exclusive_frames"].append(frame)
    for entry in report.matched.values():
        entry["frames"] = sorted(entry.get("frames", []))
        entry["exclusive_frames"] = sorted(entry.get("exclusive_frames", []))
        if entry["exclusive_frames"] == entry["frames"]:
            del entry["exclusive_frames"]
        for names in entry["names"].values():
            names.sort()
    return report


def attribute_teams(identities: Mapping[str, dict],
                    frame_teams: Mapping[str, Mapping[str, str]],
                    *, container: str = "UNIFORMS.DAT") -> Dict[str, dict]:
    """Which team's kit each identified texture belongs to, from frames alone.

    ``UNIFORMS.DAT`` names nothing -- 455 members, about fifteen unnamed images
    each -- so which team a member belongs to is not in the file.  It **is** in
    the capture: each frame shows exactly two teams, one in its coloured kit
    and one in white, so a texture drawn in a set of frames belongs to whatever
    team is in **all** of them, and the side it was on says which kit.

    * a texture in only frames where *T* wore colour -> *T*'s home kit;
    * a texture in only frames where *T* wore white -> *T*'s away kit;
    * a texture in both -> *T*, shared between its kits (helmets and numbers);
    * a texture whose frames have no team in common -> not attributable: it is
      art more than one matchup drew, which is what the referees, the crowd and
      the UI are.

    This is inference from the capture, not a fact read off the disc, and the
    document labels it as such.
    """

    out: Dict[str, dict] = {}
    for key, entry in identities.items():
        if entry.get("container") != container:
            continue
        seen_frames = entry.get("exclusive_frames") or entry.get("frames", ())
        frames = [frame for frame in seen_frames if frame in frame_teams]
        if not frames:
            continue
        common = None
        sides: Dict[str, set] = {}
        for frame in frames:
            pair = frame_teams[frame]
            teams = {value for value in pair.values() if value}
            common = teams if common is None else (common & teams)
            for side, team in pair.items():
                if team:
                    sides.setdefault(team, set()).add(side)
        if common and len(common) == 2:
            # Every frame that drew this texture is the same matchup, so it
            # belongs to one of those two teams and the frame list cannot say
            # which: in each frame one side wore colour and the other white,
            # and only the pixels know which kit this is.
            candidates = []
            for team in sorted(common):
                seen = sides.get(team, set())
                candidates.append({
                    "team": team,
                    "kit": ("home" if seen == {"colour"} else
                            "away" if seen == {"white"} else "both"),
                })
            out[key] = {"team": None, "kit": "one matchup", "frames": len(frames),
                        "candidates": candidates}
            continue
        if not common or len(common) != 1:
            out[key] = {"team": None, "kit": "shared", "frames": len(frames)}
            continue
        team = next(iter(common))
        seen = sides.get(team, set())
        kit = ("home" if seen == {"colour"} else
               "away" if seen == {"white"} else "both")
        out[key] = {"team": team, "kit": kit, "frames": len(frames)}
    return out


def _add(rows: Dict[str, dict], team: str, kit: str, key: str) -> None:
    entry = rows.setdefault(team, {}).setdefault(kit, {"textures": 0, "members": []})
    entry["textures"] += 1
    member = int(key.split(":")[1])
    if member not in entry["members"]:
        entry["members"].append(member)


def team_summary(attribution: Mapping[str, dict]) -> Dict[str, dict]:
    """``team -> {kit: {textures, members}}`` plus the unattributable bucket."""

    rows: Dict[str, dict] = {}
    for key, row in attribution.items():
        if row["team"] is None and row.get("candidates"):
            # Counted against both candidates, under a kit name that says the
            # texture is one of the two rather than certainly this one.
            for candidate in row["candidates"]:
                if candidate["team"]:
                    _add(rows, candidate["team"], "either side of one matchup", key)
            continue
        team = row["team"] or "(shared across matchups)"
        kit = row["kit"]
        _add(rows, team, kit, key)
    for bucket in rows.values():
        for entry in bucket.values():
            entry["members"].sort()
            entry["member_count"] = len(entry["members"])
            # A team's kits live in a handful of members; the shared bucket can
            # cover most of the container, and listing 444 indexes there says
            # nothing the count does not.
            if entry["member_count"] > 32:
                entry["members"] = entry["members"][:32]
                entry["members_truncated"] = True
    return dict(sorted(rows.items()))


def _count_containers(keys: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key in keys:
        container = key.split(":", 1)[0]
        out[container] = out.get(container, 0) + 1
    return dict(sorted(out.items()))


def build_document(source: Path, dump_dir: Path, dumps: Sequence[DumpTexture],
                   disc: Sequence[DiscTexture], report: MatchReport, *,
                   note: str = "", frame_labels: Optional[Mapping[str, str]] = None,
                   frame_teams: Optional[Mapping[str, Mapping[str, str]]] = None) -> dict:
    """The evidence file: counts, dimensions, filenames, member indexes.

    No pixel and no digest of a retail pixel goes in it -- a digest is not a
    picture, but it is derived from one, and the rule here is that the
    repository carries names and numbers.
    """

    by_dimension: Dict[str, int] = {}
    regions = 0
    for dump in report.unmatched_dumps:
        key = f"{dump['width']}x{dump['height']}"
        by_dimension[key] = by_dimension.get(key, 0) + 1
        if dump.get("region"):
            regions += 1
    conventions = sorted({dump.convention for dump in dumps})
    attribution = attribute_teams(report.matched, frame_teams or {})
    per_container: Dict[str, int] = {}
    for entry in report.matched.values():
        per_container[entry["container"]] = per_container.get(entry["container"], 0) + 1
    return {
        "schema": SCHEMA,
        "generated_by": "tools/madden09_ps2_texture_identities.py",
        "method": "exact pixel equality, RGBA with the CLUT's own 0..128 alpha",
        "source": Path(source).name,
        "dump_directory": str(dump_dir),
        "conventions": conventions,
        "counts": {
            "dump_files": report.dumps_seen,
            "dump_files_matched": report.dumps_matched,
            "dump_files_rgb_only": len(report.rgb_only),
            "dump_files_ambiguous": len(report.ambiguous),
            "dump_files_unmatched": len(report.unmatched_dumps),
            "disc_surfaces_indexed": report.disc_seen,
            "disc_textures_matched": len(report.matched),
            "unmatched_region_dumps": regions,
            "frames": len({frame for dump in dumps for frame in dump.frames}),
            "uniform_textures_attributed": sum(
                1 for row in attribution.values() if row["team"]),
            "uniform_textures_narrowed_to_one_matchup": sum(
                1 for row in attribution.values() if row.get("candidates")),
            "uniform_textures_shared": sum(
                1 for row in attribution.values()
                if not row["team"] and not row.get("candidates")),
        },
        "matched_by_container": dict(sorted(per_container.items())),
        "unmatched_by_dimension": dict(sorted(by_dimension.items())),
        "region_note": (
            "A name carrying -r<W>x<H> is a region: the game drew a sub-rectangle of a "
            "larger texture and the PNG is that rectangle, so it cannot equal a whole "
            "surface on the disc unless the region is the whole of one. Those are "
            "counted here rather than treated as a failure of the match."),
        "note": note,
        "team_attribution_note": (
            "Inferred from the capture, not read off the disc: UNIFORMS.DAT names none of its "
            "members, and each frame shows two teams, one in colour and one in white. A "
            "texture belongs to the team present in every frame that drew it, and the side "
            "that team was on says which kit."),
        "teams": team_summary(attribution),
        # Which frame identified what is on each identity's own row, so this
        # section is the summary and not a second copy of the table.
        "frames": {
            frame: {
                "label": (frame_labels or {}).get(frame, ""),
                "textures": len(keys),
                "by_container": _count_containers(keys),
            }
            for frame, keys in sorted(report.by_frame.items())
        },
        "identities": {key: report.matched[key] for key in sorted(report.matched)},
        "ambiguous": report.ambiguous,
        "rgb_only": report.rgb_only,
        "unmatched": [dump["name"] for dump in report.unmatched_dumps],
    }


# --------------------------------------------------------------------------
# Self-test: a synthetic member, "dumped" under a synthetic name
# --------------------------------------------------------------------------

def selftest(tmp: Optional[Path] = None) -> int:
    """Prove the matcher on data this file made, with no disc and no emulator."""

    import tempfile

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work).resolve()
        disc_path = room / "synthetic.iso"
        disc_path.write_bytes(containers.build_synthetic_disc())
        indexed = list(index_disc(disc_path, ("UNIFORMS.DAT",)))
        if not indexed:
            raise IdentityError("the synthetic disc indexed no textures")

        # "Dump" two of them the way PCSX2 would, and invent one that is not
        # on the disc at all so the unmatched leg is exercised too.
        dumps = room / "dumps" / "classic"
        dumps.mkdir(parents=True)
        image = containers.open_disc(disc_path)
        present = {entry.name: entry for entry in containers.data_files(image)}
        container = ea_terf.parse_terf(
            containers.read_file(image, present["UNIFORMS.DAT"]), allow_size_mismatch=True)
        wanted = [row for row in indexed if row.level == 0][:2]
        for number, row in enumerate(wanted):
            payload = container.member(row.member)
            width, height, rgba = mmap_art.decode_rgba(
                payload, image=row.image, level=row.level, raw_alpha=True)
            bits = texture_bits(0x13, 4, 4, 1)
            name = replacement_name(0xABCDEF00 + number, 0x1234 + number, bits)
            (dumps / name).write_bytes(write_rgba_png(rgba, width, height))
        stranger = bytes(bytearray(
            ((position * 37) & 0xFF) for position in range(8 * 8 * 4)))
        (dumps / replacement_name(0xDEAD, 0xBEEF, texture_bits(0x13, 3, 3, 1))
         ).write_bytes(write_rgba_png(stranger, 8, 8))

        scanned = scan_dump(room / "dumps")
        if len(scanned) != len(wanted) + 1:
            raise IdentityError(f"scanned {len(scanned)} dumps, expected {len(wanted) + 1}")
        if {dump.convention for dump in scanned} != {"classic"}:
            raise IdentityError("the convention should come from the subdirectory name")
        report = pair(scanned, indexed)
        if report.dumps_matched != len(wanted):
            raise IdentityError(
                f"{report.dumps_matched} of {len(wanted)} synthetic dumps matched")
        if len(report.unmatched_dumps) != 1:
            raise IdentityError("the invented texture should not have matched anything")
        document = build_document(disc_path, room / "dumps", scanned, indexed, report)
        out = room / "identities.json"
        out.write_bytes((json.dumps(document, indent=2, sort_keys=True) + "\n").encode())
        loaded = load_identities(out)   # the lane's own reader, not a copy of it
        if len(loaded) != len(report.matched):
            raise IdentityError("the document did not round-trip through load_identities")
        for entry in loaded.values():
            if not entry.get("classic"):
                raise IdentityError("a loaded identity carries no classic name")

        # A name PCSX2 would never have written is not a dump.
        (dumps / "not-a-texture.png").write_bytes(write_rgba_png(stranger, 8, 8))
        if len(scan_dump(room / "dumps")) != len(scanned):
            raise IdentityError("a file outside PCSX2's grammar must be ignored")

    print("MADDEN09_PS2_TEXTURE_IDENTITIES_SELFTEST_PASS matcher=exact-pixels "
          "alpha=clut-raw conventions=from-subdirectory refuses=ungrammatical-names")
    return 0


# --------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, help="the user's own SLUS-21770 image")
    parser.add_argument("--dump-dir", type=Path,
                        help="the directory PCSX2 filled with dumped textures")
    parser.add_argument("--index", type=Path,
                        help="build or extend the disc index at this JSONL path")
    parser.add_argument("--containers", default=",".join(DEFAULT_CONTAINERS),
                        help="which /DATA containers to index")
    parser.add_argument("--dump-index", type=Path,
                        help="cache the decoded dump digests here; re-pairing then costs "
                             "seconds instead of re-reading every PNG")
    parser.add_argument("--out", type=Path, help="write the identity document here")
    parser.add_argument("--frame-labels", type=Path,
                        help="a JSON object of frame directory name -> what that frame shows; "
                             "the labels are the operator's, never inferred here")
    parser.add_argument("--frame-teams", type=Path,
                        help="a JSON object of frame directory name -> "
                             '{"colour": TEAM, "white": TEAM}; the operator\'s reading of '
                             "the capture, never inferred here")
    parser.add_argument("--note", default="", help="one line kept in the document")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    if arguments.selftest:
        return selftest()
    if not arguments.source:
        parser.error("--source is required unless --selftest is given")
    wanted = tuple(name.strip() for name in arguments.containers.split(",") if name.strip())

    def note(line: str) -> None:
        print(line, file=sys.stderr)

    started = time.time()
    if arguments.index:
        written = write_index(arguments.source, arguments.index, wanted, progress=note)
        print(f"INDEX rows={written} file={arguments.index} "
              f"seconds={time.time() - started:.0f}")
        if not arguments.dump_dir:
            return 0
        disc = read_index(arguments.index)
    else:
        if not arguments.dump_dir:
            parser.error("give --dump-dir, --index, or both")
        disc = list(index_disc(arguments.source, wanted, progress=note))

    dumps = None
    if arguments.dump_index and arguments.dump_index.is_file():
        dumps = read_dump_index(arguments.dump_index)
        note(f"{len(dumps)} dump digest(s) from {arguments.dump_index}")
    if dumps is None:
        dumps = scan_dump(arguments.dump_dir)
        if arguments.dump_index:
            write_dump_index(arguments.dump_index, dumps)
    report = pair(dumps, disc)
    labels = {}
    if arguments.frame_labels:
        labels = json.loads(arguments.frame_labels.read_text(encoding="utf-8"))
    teams = {}
    if arguments.frame_teams:
        teams = json.loads(arguments.frame_teams.read_text(encoding="utf-8"))
    document = build_document(arguments.source, arguments.dump_dir, dumps, disc, report,
                              note=arguments.note, frame_labels=labels, frame_teams=teams)
    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_bytes(
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    counts = document["counts"]
    print("IDENTITIES dumps=%d matched=%d rgb_only=%d ambiguous=%d unmatched=%d "
          "disc_surfaces=%d textures=%d frames=%d attributed=%d narrowed=%d shared=%d "
          "seconds=%.0f"
          % (counts["dump_files"], counts["dump_files_matched"],
             counts["dump_files_rgb_only"], counts["dump_files_ambiguous"],
             counts["dump_files_unmatched"], counts["disc_surfaces_indexed"],
             counts["disc_textures_matched"], counts["frames"],
             counts["uniform_textures_attributed"],
             counts["uniform_textures_narrowed_to_one_matchup"],
             counts["uniform_textures_shared"],
             time.time() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
