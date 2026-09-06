#!/usr/bin/env python3
"""Pair a PCSX2 texture dump with a PlayStation 2 disc's own ``MMAP`` textures.

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

**One engine, one game per ``--game``.**  Madden NFL 09 was the first disc
this was written for and every fact above was measured on it; NCAA Football 09
puts its art in the same ``TERF``/``MMAP`` containers, so which disc is being
paired is a :class:`GameProfile` -- the containers module, the containers worth
indexing, and where the two evidence documents live -- and not a second copy of
the matcher.  ``tools/madden09_ps2_texture_identities.py`` is this file with
``--game madden09_ps2`` already chosen, kept because its name is what the
Madden lane, its registry row and its documents cite.

Usage::

    ps2_texture_identities.py --game ncaa09_ps2 --source DISC.iso --dump-dir DIR
    ps2_texture_identities.py --game madden09_ps2 --source DISC.iso \\
        --index CACHE.jsonl --containers UNIFORMS.DAT,FIELDART.DAT
    ps2_texture_identities.py --game ncaa09_ps2 --selftest
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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_terf, mmap_art           # noqa: E402
from mod_editor.games.contract import Refusal                     # noqa: E402
from mod_editor.games._lanes.terf_art import (                    # noqa: E402
    derive_texture_names,
    load_identities,
    read_rgba_png,
    write_rgba_png,
)

class IdentityError(ValueError):
    """The tool could not do what it was asked; the sentence says why."""


#: One disc this tool can pair, and everything about it that is not the
#: matcher.  A game is data here rather than a module of its own: the pixels,
#: the hashes and the grammar are PCSX2's and the same on every disc, and what
#: differs is which containers hold textures and where that game's lane reads
#: its table from.
@dataclass(frozen=True)
class GameProfile:
    """Which disc, which containers, and where the two documents live."""

    game_id: str
    serial: str
    title: str
    #: The game module's ``containers`` -- ``open_disc``, ``data_files``,
    #: ``read_file``, ``member_uncached`` and ``build_synthetic_disc``.
    module: str
    #: Which ``/DATA`` containers to index by default: every one whose members
    #: carry ``MMAP`` textures the decoder reads.
    default_containers: Tuple[str, ...]
    #: The schema the game's lane expects its identity document to declare,
    #: and where that document lives.  The lane is what reads the table, so it
    #: owns both; this tool writes what the lane will read.
    identity_schema: str
    identity_document: Path
    derivation_schema: str
    derivation_document: Path
    #: The container whose textures the team-attribution rule runs over --
    #: the one holding kits, which names none of its members on either disc.
    attribution_container: str
    #: What the document says about that rule for this game.
    team_attribution_note: str
    #: A container in the game's own synthetic disc, for the self-test.
    synthetic_container: str
    #: The token ``--selftest`` prints.  A validator greps for it, so it is
    #: the game's and not this file's.
    selftest_token: str
    #: How the document names the tool that wrote it.
    generated_by: str = "tools/ps2_texture_identities.py"

    @property
    def discs(self):
        """The game's ``containers`` module, imported on first use."""

        import importlib

        return importlib.import_module(self.module)


PROFILES: Dict[str, GameProfile] = {
    "madden09_ps2": GameProfile(
        game_id="madden09_ps2",
        serial="SLUS-21770",
        title="Madden NFL 09 (PlayStation 2)",
        module="mod_editor.games.madden09_ps2.containers",
        # ``UIS_MCFL.DAT`` is left out on purpose -- all 1,188 of its members
        # store their pixels under EA codec 4 (``IPU1``), which nothing here
        # decodes.
        default_containers=("UNIFORMS.DAT", "PLYRFACE.DAT", "COACFACE.DAT",
                            "TATTOOS.DAT", "FIELDART.DAT", "STADIUMS.DAT"),
        identity_schema="madden09_ps2_pcsx2_texture_identities/v1",
        identity_document=Path(
            "docs/product/measured/madden09_ps2/pcsx2-texture-identities.json"),
        derivation_schema="madden09_ps2_pcsx2_texture_identity_derivation/v1",
        derivation_document=Path(
            "docs/product/measured/madden09_ps2/pcsx2-texture-identity-derivation.json"),
        attribution_container="UNIFORMS.DAT",
        team_attribution_note='Inferred from the capture, not read off the disc: UNIFORMS.DAT names none of its members, and each frame shows two teams, one in colour and one in white. A texture belongs to the team present in every frame that drew it, and the side that team was on says which kit.',
        synthetic_container="UNIFORMS.DAT",
        selftest_token="MADDEN09_PS2_TEXTURE_IDENTITIES_SELFTEST_PASS",
        generated_by="tools/madden09_ps2_texture_identities.py",
    ),
    "ncaa09_ps2": GameProfile(
        game_id="ncaa09_ps2",
        serial="SLUS-21752",
        title="NCAA Football 09 (PlayStation 2)",
        module="mod_editor.games.ncaa09_ps2.containers",
        # Every container the module's six art rows read, in the order a run
        # gets through them fastest: the stored ones first, the 127 MB
        # ``LZH1`` kit container last.  ``STADIUMS.DAT`` (197 MB) and
        # ``MOVIEDAT.DAT`` (333 MB) are not here: the first is past the
        # module's read limit and carries no ``MMAP`` member, the second is
        # movie streams [M].
        default_containers=("UIS_GEAR.DAT", "COACFACE.DAT", "PLYRFACE.DAT",
                            "UIS_STAD.DAT", "FANDATA.DAT", "LOADDATA.DAT",
                            "UIS_TMLO.DAT", "MSCTDATA.DAT", "STADATA.DAT",
                            "FLDDATA.DAT", "PLADATA.DAT", "UNIFORM.DAT"),
        identity_schema="ncaa09_ps2_pcsx2_texture_identities/v1",
        identity_document=Path(
            "docs/product/measured/ncaa09_ps2/pcsx2-texture-identities.json"),
        derivation_schema="ncaa09_ps2_pcsx2_texture_identity_derivation/v1",
        derivation_document=Path(
            "docs/product/measured/ncaa09_ps2/pcsx2-texture-identity-derivation.json"),
        attribution_container="UNIFORM.DAT",
        team_attribution_note='No kit is attributed to a school on this disc. The attribution rule needs a reading of each frame that names the two sides, and the two frames captured here are one matchup whose schools the capture does not name -- the fixtures manifest records the colours and the end-zone lettering, not the two teams. So the teams block is empty on purpose rather than filled with a guess, and no texture in UNIFORM.DAT is claimed for any school.',
        synthetic_container="UNIFORM.DAT",
        selftest_token="NCAA09_PS2_TEXTURE_IDENTITIES_SELFTEST_PASS",
    ),
}


def profile(game_id: str) -> GameProfile:
    """The named game's profile, or a refusal that lists the ones there are."""

    found = PROFILES.get(game_id)
    if found is None:
        raise IdentityError(
            f"{game_id} is not a disc this tool knows how to pair; give --game "
            f"{' or --game '.join(sorted(PROFILES))}.")
    return found


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


def index_disc(source: Path, containers_wanted: Sequence[str], *,
               discs, progress=None) -> Iterable[DiscTexture]:
    """Decode every ``MMAP`` surface of the named containers, digest by digest.

    Yields rather than returning: on the retail disc this is thousands of
    members and a few minutes, and a caller that writes each row as it arrives
    can be interrupted and resumed.
    """

    image = discs.open_disc(Path(source))
    present = {entry.name: entry for entry in discs.data_files(image)}
    for name in containers_wanted:
        entry = present.get(name)
        if entry is None:
            continue
        if progress is not None:
            progress(f"{name}…")
        blob = discs.read_file(image, entry)
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


def write_index(source: Path, path: Path, containers_wanted: Sequence[str], *,
                discs, progress=None) -> int:
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
        for row in index_disc(source, wanted, discs=discs, progress=progress):
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


def coverage_by_container(disc: Sequence[DiscTexture], report: MatchReport,
                          containers_wanted: Sequence[str] = ()) -> Dict[str, dict]:
    """Per container: textures indexed, textures named, and frames that drew one.

    The first number is the disc's -- how many distinct ``container:member:image``
    surfaces the index decoded.  The other two are the **capture's**: how many of
    those a dumped file paired with, and how many captured frames were drawing at
    least one texture of that container when PCSX2 wrote its dump.  A container no
    frame reached has a zero in both, and that zero is a fact about which screens
    were captured rather than about the container.

    Every container asked for appears, including one the index found nothing in,
    because a row of zeroes is the honest entry and a missing row reads as an
    oversight.
    """

    out: Dict[str, dict] = {name: {"textures_indexed": 0, "textures_named": 0,
                                   "frames_that_drew_one": 0}
                            for name in containers_wanted}
    seen: Dict[str, set] = {}
    for row in disc:
        seen.setdefault(row.container, set()).add(row.key)
    for name, keys in seen.items():
        out.setdefault(name, {"textures_indexed": 0, "textures_named": 0,
                              "frames_that_drew_one": 0})["textures_indexed"] = len(keys)
    for entry in report.matched.values():
        row = out.setdefault(str(entry["container"]),
                             {"textures_indexed": 0, "textures_named": 0,
                              "frames_that_drew_one": 0})
        row["textures_named"] += 1
    frames: Dict[str, set] = {}
    for frame, keys in report.by_frame.items():
        for key in keys:
            frames.setdefault(key.split(":", 1)[0], set()).add(frame)
    for name, stamps in frames.items():
        out.setdefault(name, {"textures_indexed": 0, "textures_named": 0,
                              "frames_that_drew_one": 0})["frames_that_drew_one"] = len(stamps)
    return dict(sorted(out.items()))


def build_document(source: Path, dump_dir: Path, dumps: Sequence[DumpTexture],
                   disc: Sequence[DiscTexture], report: MatchReport, *,
                   game: GameProfile, note: str = "",
                   frame_labels: Optional[Mapping[str, str]] = None,
                   frame_teams: Optional[Mapping[str, Mapping[str, str]]] = None,
                   coverage: Optional[Mapping[str, dict]] = None) -> dict:
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
    attribution = attribute_teams(report.matched, frame_teams or {},
                                  container=game.attribution_container)
    per_container: Dict[str, int] = {}
    for entry in report.matched.values():
        per_container[entry["container"]] = per_container.get(entry["container"], 0) + 1
    document: Dict[str, Any] = {
        "schema": game.identity_schema,
        "generated_by": game.generated_by,
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
        "team_attribution_note": game.team_attribution_note,
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
    if coverage:
        document["coverage_note"] = (
            "Per container: how many distinct disc textures the index decoded, how many of "
            "them a dumped file named, and how many of the captured frames were drawing at "
            "least one texture of that container. The last two are facts about the capture, "
            "not about the disc: a container no frame reached has no named texture and that "
            "is the corpus's limit, not the container's.")
        document["coverage"] = dict(sorted(coverage.items()))
    return document


# --------------------------------------------------------------------------
# Derivation: the names computed from the disc, checked against the dumps
# --------------------------------------------------------------------------

#: How many identities whose dumped name the derivation did not reproduce are
#: listed by key before the document records only how many there were.
MISS_SAMPLE = 48

#: How many members after a miss the cross-member mip-chain probe will walk.
#: A GS mip chain is at most seven levels, and this disc's split pyramids are
#: four to six members long, so seven is one more than anything real.
CHAIN_PROBE_MEMBERS = 7


def _texture_levels(payload: bytes, texture, image):
    """Every mip level of *image* as :class:`pcsx2_texture_name.TextureLevel`."""

    from mod_editor.games._formats import pcsx2_texture_name as identity

    levels = []
    for level in range(image.mip_count):
        surface = texture.surfaces[image.first_surface + level]
        indices = mmap_art.unpack_indices(mmap_art.surface_pixels(payload, surface), surface)
        bits = 8 if surface.pixel_layout == mmap_art.PIXELS_INDEXED_8 else 4
        levels.append(identity.TextureLevel(surface.width, surface.height, bits, indices))
    return levels


def _single_level(container, member: int):
    """``(hashed stream, width, height, bits, CLUT hash)`` for a one-image one-level member.

    ``None`` for anything else.  This is the shape a mip pyramid split across
    consecutive ``TERF`` members takes: each member holds one image with one
    surface, and the run shares a palette.  A surface whose stored block is
    padded past its own texel count -- an 8x4 4-bit level is stored in 32 bytes
    and needs 16 -- is trimmed to the texels it declares rather than refused,
    because the padding is storage and not picture.
    """

    from mod_editor.games._formats import pcsx2_texture_name as identity

    try:
        payload = container.member(member)
        texture = mmap_art.parse(payload)
    except Exception:                                  # noqa: BLE001 - absence is the answer
        return None
    if len(texture.images) != 1:
        return None
    image = texture.images[0]
    if image.mip_count != 1 or image.palette_count == 0:
        return None
    surface = texture.surfaces[image.first_surface]
    bits = 8 if surface.pixel_layout == mmap_art.PIXELS_INDEXED_8 else 4
    try:
        raw = bytes(mmap_art.surface_pixels(payload, surface))
        needed = surface.width * surface.height * bits // 8
        raw = raw[:needed]
        if len(raw) != needed:
            return None
        if bits == 8:
            indices = list(raw)
        else:
            indices = []
            for byte in raw:
                indices.append(byte & 0x0F)
                indices.append((byte >> 4) & 0x0F)
        stream = identity.hashed_stream(indices, surface.width, surface.height, bits)[0]
        clut = identity.clut_hash(mmap_art.read_palette(payload,
                                                        texture.palettes[image.first_palette]))
    except Exception:                                  # noqa: BLE001 - absence is the answer
        return None
    return stream, surface.width, surface.height, bits, clut


def _cross_member_chain(container, member: int, parsed, cache: Dict[int, Any]) -> Optional[dict]:
    """Is the dumped ``TEX0`` the hash of this member **and the members after it**?

    A ``TERF`` container can hold one texture's mip pyramid as a run of
    consecutive one-level members -- ``64x64, 32x32, 16x16, 8x8`` under one
    palette -- and PCSX2 feeds every level of the draw's LOD range into one hash
    state.  The deriver hashes a member on its own, so every name of such a run
    is a miss.  This walks forward while the size halves and the palette holds,
    hashing the growing chain, and answers with the run that reproduces the name
    or ``None`` [M].
    """

    from mod_editor.games._formats import xxhash3_64

    first = cache.setdefault(member, _single_level(container, member))
    if first is None:
        return None
    stream, width, height, bits, clut = first
    if parsed.clut is not None and clut != parsed.clut:
        return None
    joined = stream
    for step in range(1, CHAIN_PROBE_MEMBERS):
        following = cache.setdefault(member + step, _single_level(container, member + step))
        if following is None:
            return None
        if following[1] != max(1, width >> step) or following[2] != max(1, height >> step):
            return None
        if following[3] != bits or following[4] != clut:
            return None
        joined += following[0]
        if xxhash3_64.xxh3_64(joined) == parsed.tex0:
            return {"member": member, "levels": step + 1,
                    "last_member": member + step,
                    "base": f"{width}x{height}"}
    return None


def derivation_check(source: Path, document: Mapping, *, discs, progress=None) -> dict:
    """Re-derive every dump-identified texture's names from the disc and count what agrees.

    For each identity the pixel matcher recorded, the texture's mip levels are
    read off the user's disc, the GS block hash of every mip chain and the CLUT
    hash of every palette in the member are computed, and each dumped name is
    checked against them.  Three outcomes are counted separately:

    * **reproduced** -- the dumped TEX0 hash is one of this texture's chains;
    * **PSM disagrees** -- the dumped name says 8-bit and the surface is 4-bit
      (or the reverse).  The pixel matcher paired the dump with every surface
      that draws the same picture, and a flat 8x8 texture exists in both
      widths; the dump is another surface's and this one is not wrong;
    * **not reproduced** -- the same PSM and no chain matches.  Listed by key.

    An 8-bit surface is checked against **two** readings, because a game may
    upload an 8-bit texture as the high-byte ``PSMT8H`` surface instead, and
    that has a different ``bits`` word *and* a different TEX0 hash for the same
    pixels: the ordinary block reading for a ``PSMT8`` (19) name and the linear
    reading for a ``PSMT8H`` (27) one.  ``dumped_names_by_psm`` records how many
    names of each GS mode the dump actually wrote, so a later reader can see
    whether the second reading had anything to answer.

    A name that no reading reproduces is put to one more question: is it the
    hash of this member **and the members after it**?  See
    :func:`_cross_member_chain`.

    The CLUT half is counted as: in the image's own palette, in another
    palette of the same member (an alternate kit CLUT), or in no palette the
    member carries (a CLUT the game built at run time).
    """

    from mod_editor.games._formats import pcsx2_texture_name as identity

    identities = document.get("identities") or {}
    by_container: Dict[str, List[Tuple[str, dict]]] = {}
    for key, entry in identities.items():
        by_container.setdefault(str(entry["container"]), []).append((key, entry))
    image = discs.open_disc(Path(source))
    present = {entry.name: entry for entry in discs.data_files(image)}
    counts: Dict[str, int] = {
        "identities": len(identities), "identities_checked": 0, "identities_not_derivable": 0,
        "identities_confirmed": 0, "names": 0, "names_psm_disagrees": 0,
        "names_tex0_reproduced": 0, "names_tex0_not_reproduced": 0,
        "names_high_byte_checked": 0, "names_high_byte_reproduced": 0,
        "clut_in_own_palette": 0, "clut_in_another_palette_of_the_member": 0,
        "clut_not_in_the_member": 0,
    }
    per_class: Dict[str, Dict[str, int]] = {}
    per_container: Dict[str, Dict[str, int]] = {}
    chains: Dict[str, int] = {}
    not_derivable: Dict[str, int] = {}
    misses: List[str] = []
    by_psm: Dict[str, Dict[str, int]] = {}
    chain_hits: List[dict] = []
    chain_cache: Dict[str, Dict[int, Any]] = {}
    chain_misses = 0
    for name in sorted(by_container):
        entry = present.get(name)
        if entry is None:
            continue
        if progress is not None:
            progress(f"{name}: checking {len(by_container[name])} identit(ies)…")
        container = ea_terf.parse_terf(discs.read_file(image, entry), allow_size_mismatch=True)
        for key, row in by_container[name]:
            payload = container.member(int(row["member"]))
            texture = mmap_art.parse(payload)
            image_entry = texture.images[int(row["image"])]
            try:
                levels = _texture_levels(payload, texture, image_entry)
                by_hash = {value: base_count for base_count, value
                           in identity.tex0_hash_chains(levels).items()}
            except Exception as exc:  # noqa: BLE001 - a refusal is a count here
                counts["identities_not_derivable"] += 1
                reason = str(exc).split(";")[0][:80]
                not_derivable[reason] = not_derivable.get(reason, 0) + 1
                continue
            counts["identities_checked"] += 1
            own = range(image_entry.first_palette,
                        image_entry.first_palette + image_entry.palette_count)
            palettes: Dict[int, int] = {}
            for palette in texture.palettes:
                try:
                    entries = mmap_art.read_palette(payload, palette)
                    if len(entries) in (16, 256):
                        palettes.setdefault(identity.clut_hash(entries), palette.index)
                except mmap_art.MmapError:
                    continue
            base = levels[0]
            label = f"{name} {base.bits}-bit {base.width}x{base.height}"
            bucket = per_class.setdefault(label, {"reproduced": 0, "not_reproduced": 0})
            container_bucket = per_container.setdefault(
                name, {"identities": 0, "confirmed": 0, "names_reproduced": 0,
                       "names_not_reproduced": 0})
            container_bucket["identities"] += 1
            confirmed = False
            dumped = sorted({value for values in (row.get("names") or {}).values()
                             for value in values})
            high_byte_psm = identity.HIGH_BYTE_PSM.get(base.bits)
            by_hash_high: Dict[int, Tuple[int, int]] = {}
            for dumped_name in dumped:
                parsed = identity.parse_name(dumped_name)
                mode = by_psm.setdefault(str(parsed.psm), {
                    "names": 0, "tex0 reproduced": 0, "tex0 not reproduced": 0,
                    "not a reading of this surface": 0})
                table = by_hash
                if parsed.psm != base.psm:
                    if high_byte_psm is None or parsed.psm != high_byte_psm:
                        counts["names_psm_disagrees"] += 1
                        mode["not a reading of this surface"] += 1
                        continue
                    if not by_hash_high:
                        by_hash_high = {value: base_count for base_count, value
                                        in identity.tex0_hash_chains(
                                            levels, psm=high_byte_psm).items()}
                    table = by_hash_high
                    counts["names_high_byte_checked"] += 1
                counts["names"] += 1
                mode["names"] += 1
                found = table.get(parsed.tex0)
                mode["tex0 reproduced" if found is not None
                     else "tex0 not reproduced"] += 1
                if found is not None and table is by_hash_high:
                    counts["names_high_byte_reproduced"] += 1
                if found is not None:
                    counts["names_tex0_reproduced"] += 1
                    bucket["reproduced"] += 1
                    container_bucket["names_reproduced"] += 1
                    chain = f"{found[0]}+{found[1]}"
                    chains[chain] = chains.get(chain, 0) + 1
                    confirmed = True
                else:
                    counts["names_tex0_not_reproduced"] += 1
                    bucket["not_reproduced"] += 1
                    container_bucket["names_not_reproduced"] += 1
                    if len(misses) < MISS_SAMPLE and key not in misses:
                        misses.append(key)
                    chain = _cross_member_chain(container, int(row["member"]), parsed,
                                                chain_cache.setdefault(name, {}))
                    if chain is None:
                        chain_misses += 1
                    else:
                        chain_hits.append({"container": name, "key": key, **chain})
                if parsed.clut is None:
                    continue
                palette_index = palettes.get(parsed.clut)
                if palette_index is None:
                    counts["clut_not_in_the_member"] += 1
                elif palette_index in own:
                    counts["clut_in_own_palette"] += 1
                else:
                    counts["clut_in_another_palette_of_the_member"] += 1
            if confirmed:
                counts["identities_confirmed"] += 1
                container_bucket["confirmed"] += 1
    return {
        "counts": counts,
        "per_container": per_container,
        "per_class": dict(sorted(per_class.items())),
        "lod_chains": dict(sorted(chains.items(), key=lambda item: -item[1])),
        "not_derivable_reasons": not_derivable,
        "not_reproduced_sample": misses,
        "dumped_names_by_psm": {psm: by_psm[psm] for psm in sorted(by_psm, key=int)},
        "dumped_names_by_psm_note": (
            "Every dumped name of every identity, by the GS pixel mode its bits word "
            "declares: 19 is PSMT8, 20 is PSMT4, 27 is the high-byte PSMT8H. 'not a reading "
            "of this surface' is a name of a mode this surface has none -- a 4-bit name on an "
            "8-bit surface, which the pixel matcher paired because a picture exists at both "
            "depths -- and those are the psm_disagrees count, split by mode. A mode absent "
            "from this table is a mode no draw in this capture used, so the reading for it "
            "had nothing to answer."),
        "cross_member_chain": {
            "names_explained": len(chain_hits),
            "names_still_unexplained": chain_misses,
            "chains": chain_hits[:MISS_SAMPLE],
            "question": ("A TERF container can hold one texture's mip pyramid as a run of "
                         "consecutive one-level members under a single palette, and PCSX2 "
                         "hashes every level of the draw's LOD range into one state, so a "
                         "member hashed on its own reproduces none of the run's names. Each "
                         "unreproduced name is re-checked against the chain that starts at "
                         "its own member and walks forward while the size halves and the "
                         "palette holds."),
        },
    }


def derivation_census(source: Path, containers_wanted: Optional[Sequence[str]] = None, *,
                      discs, dumped_names: Optional[Sequence[str]] = None,
                      already_identified: Optional[Sequence[str]] = None,
                      progress=None) -> dict:
    """How many textures on the disc get a derived name at all, container by container.

    Walks every ``MMAP`` member of the named containers -- or of every
    container under the read limit when none are named -- and derives each
    image's names, counting the images that get one and, by reason, the ones
    that do not.  This is the census the lane's catalogue reproduces one
    texture at a time.

    When *dumped_names* is given -- every filename a PCSX2 dump wrote -- each
    plain (region-less) name is looked up among the derived TEX0 hashes, and
    the document records how many the hash alone places, and how many of
    those the pixel matcher (*already_identified*) could not.  Nothing but the
    counts and the hashes' membership is kept.
    """

    from mod_editor.games._formats import pcsx2_texture_name as identity

    image = discs.open_disc(Path(source))
    out: Dict[str, dict] = {}
    totals = {"containers": 0, "members": 0, "images": 0, "images_derived": 0,
              "names_derived": 0, "images_not_derived": 0}
    reasons: Dict[str, int] = {}
    derived_tex0: set = set()
    keys_by_tex0: Dict[int, set] = {}
    for entry in discs.data_files(image):
        if containers_wanted is not None and entry.name not in containers_wanted:
            continue
        if containers_wanted is None and not entry.name.endswith(".DAT"):
            continue
        try:
            blob = discs.read_file(image, entry)
        except discs.DiscError:
            continue
        if not blob.startswith(ea_terf.TERF_MAGIC):
            continue
        try:
            container = ea_terf.parse_terf(blob, allow_size_mismatch=True)
        except ea_terf.TerfError:
            continue
        row = {"members": 0, "images": 0, "images_derived": 0, "names_derived": 0,
               "images_not_derived": 0}
        for member in container.members:
            try:
                payload = discs.member_uncached(container, member.index)
            except Exception:  # noqa: BLE001
                continue
            if not payload.startswith(mmap_art.MMAP_MAGIC):
                continue
            try:
                texture = mmap_art.parse(payload)
            except mmap_art.MmapError:
                continue
            row["members"] += 1
            for image_entry in texture.images:
                row["images"] += 1
                if texture.undecodable_reason(image_entry) is not None:
                    row["images_not_derived"] += 1
                    reason = str(texture.undecodable_reason(image_entry)).split(":")[0][:60]
                    reasons[reason] = reasons.get(reason, 0) + 1
                    continue
                names, note = derive_texture_names(payload, texture, image_entry)
                if names:
                    row["images_derived"] += 1
                    row["names_derived"] += sum(len(values) for values in names.values())
                    if dumped_names is not None:
                        key = f"{entry.name}:{member.index}:{image_entry.index}"
                        for value in names.get("modern", ()):
                            tex0 = identity.parse_name(value).tex0
                            derived_tex0.add(tex0)
                            keys_by_tex0.setdefault(tex0, set()).add(key)
                else:
                    row["images_not_derived"] += 1
                    reason = note.split("(")[0].split(":")[-1].strip()[:60]
                    reasons[reason] = reasons.get(reason, 0) + 1
        if row["members"]:
            out[entry.name] = row
            totals["containers"] += 1
            for field_name in ("members", "images", "images_derived", "names_derived",
                               "images_not_derived"):
                totals[field_name] += row[field_name]
        if progress is not None:
            progress(f"{entry.name}: {row['members']} MMAP member(s), "
                     f"{row['images_derived']} image(s) named")
    document = {"totals": totals, "per_container": out,
                "not_derived_reasons": dict(sorted(reasons.items(), key=lambda item: -item[1]))}
    if dumped_names is not None:
        known = set(already_identified or ())
        placed: Dict[str, int] = {"plain_names": 0, "plain_names_placed_by_hash": 0,
                                  "plain_names_placed_that_pixels_could_not": 0,
                                  "region_names": 0, "region_names_placed_by_hash": 0}
        images_placed: set = set()
        for value in sorted(set(dumped_names)):
            try:
                parsed = identity.parse_name(value)
            except Refusal:
                # parse_name refuses a name outside PCSX2's grammar; that is
                # a name to skip, not a reason to abandon the census.
                continue
            if parsed.region is not None:
                placed["region_names"] += 1
                if parsed.tex0 in derived_tex0:
                    placed["region_names_placed_by_hash"] += 1
                continue
            placed["plain_names"] += 1
            if parsed.tex0 in derived_tex0:
                placed["plain_names_placed_by_hash"] += 1
                images_placed.update(keys_by_tex0.get(parsed.tex0, ()))
                if value not in known:
                    placed["plain_names_placed_that_pixels_could_not"] += 1
        placed["images_placed_by_hash"] = len(images_placed)
        placed_containers: Dict[str, int] = {}
        for key in images_placed:
            name = key.split(":", 1)[0]
            placed_containers[name] = placed_containers.get(name, 0) + 1
        document["dumped_names_by_hash"] = placed
        document["images_placed_by_hash_per_container"] = dict(sorted(placed_containers.items()))
    return document


def build_derivation_document(source: Path, check: Mapping, census: Mapping, *,
                              game: GameProfile) -> dict:
    """The evidence file for the derivation: counts, keys and chain labels only."""

    from mod_editor.games._formats import xxhash3_64

    return {
        "schema": game.derivation_schema,
        "generated_by": f"{game.generated_by} --derive-check",
        "source": Path(source).name,
        "method": (
            "TEX0: XXH3-64 over the texture's GS block image (256-byte blocks in row-major "
            "order; a level smaller than a block hashes its linear texels), every mip chain "
            "fed into one hash state. CLUT: XXH3-64 over the palette in drawing order. "
            "Checked against the names a real PCSX2 dump wrote for the same disc texture."),
        "hash_implementation": ("xxhash C extension" if xxhash3_64.ACCELERATED
                                else "pure Python (mod_editor.games._formats.xxhash3_64)"),
        "dump_check": dict(check),
        "disc_census": dict(census),
        "what_this_proves": (
            "A dumped name that the derivation reproduces was computed by PCSX2 from the same "
            "bytes this tool hashed, so the rule is the emulator's for that texture class. A "
            "derived name for a texture no dump has shown is the same computation and is "
            "proved only to that extent. Nothing here has loaded a replacement pack."),
        "what_this_does_not_prove": [
            "that a pack built from these names is loaded by any emulator build",
            "the second half of a name for a texture the game draws with a CLUT it builds at "
            "run time, or with another member's palette",
            "any name for a texture whose width or height is not a power of two, or for a "
            "region-clamped draw, whose rectangle offset is in no file",
        ],
    }


# --------------------------------------------------------------------------
# Self-test: a synthetic member, "dumped" under a synthetic name
# --------------------------------------------------------------------------

def selftest(game: GameProfile, tmp: Optional[Path] = None) -> int:
    """Prove the matcher on data this file made, with no disc and no emulator."""

    import tempfile

    discs = game.discs
    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work).resolve()
        disc_path = room / "synthetic.iso"
        disc_path.write_bytes(discs.build_synthetic_disc())
        indexed = list(index_disc(disc_path, (game.synthetic_container,), discs=discs))
        if not indexed:
            raise IdentityError("the synthetic disc indexed no textures")

        # "Dump" two of them the way PCSX2 would, and invent one that is not
        # on the disc at all so the unmatched leg is exercised too.
        dumps = room / "dumps" / "classic"
        dumps.mkdir(parents=True)
        image = discs.open_disc(disc_path)
        present = {entry.name: entry for entry in discs.data_files(image)}
        container = ea_terf.parse_terf(
            discs.read_file(image, present[game.synthetic_container]),
            allow_size_mismatch=True)
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
        document = build_document(
            disc_path, room / "dumps", scanned, indexed, report, game=game,
            coverage=coverage_by_container(indexed, report, (game.synthetic_container,)))
        if document["coverage"][game.synthetic_container]["textures_named"] != len(report.matched):
            raise IdentityError("the coverage block disagrees with the identities")
        out = room / "identities.json"
        out.write_bytes((json.dumps(document, indent=2, sort_keys=True) + "\n").encode())
        # The lane's own reader, not a copy of it: a document this tool writes
        # that the lane cannot read is a document nothing will ever use.
        loaded = load_identities(out, game.identity_schema)
        if len(loaded) != len(report.matched):
            raise IdentityError("the document did not round-trip through load_identities")
        for entry in loaded.values():
            if not entry.get("classic"):
                raise IdentityError("a loaded identity carries no classic name")

        # A name PCSX2 would never have written is not a dump.
        (dumps / "not-a-texture.png").write_bytes(write_rgba_png(stranger, 8, 8))
        if len(scan_dump(room / "dumps")) != len(scanned):
            raise IdentityError("a file outside PCSX2's grammar must be ignored")

    print(f"{game.selftest_token} matcher=exact-pixels alpha=clut-raw "
          f"conventions=from-subdirectory refuses=ungrammatical-names "
          f"game={game.game_id}")
    return 0


# --------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None, *, game_id: Optional[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    if game_id is None:
        parser.add_argument("--game", default=None, choices=sorted(PROFILES),
                            help="which disc to pair; required")
    parser.add_argument("--source", type=Path, help="the user's own disc image")
    parser.add_argument("--dump-dir", type=Path,
                        help="the directory PCSX2 filled with dumped textures")
    parser.add_argument("--index", type=Path,
                        help="build or extend the disc index at this JSONL path")
    parser.add_argument("--containers", default="",
                        help="which /DATA containers to index; default the game's own list")
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
    parser.add_argument("--coverage", action="store_true",
                        help="add the per-container coverage block: textures indexed, "
                             "textures named, and how many captured frames drew one")
    parser.add_argument("--derive-check", action="store_true",
                        help="re-derive every identity's names from the disc, check them against "
                             "the dumped names, census the whole disc, and write the derivation "
                             "document")
    parser.add_argument("--identities", type=Path, default=None,
                        help="the identity document --derive-check reads; default the "
                             "game's own")
    parser.add_argument("--derive-out", type=Path, default=None,
                        help="where --derive-check writes its document; default the "
                             "game's own")
    parser.add_argument("--census-containers", default="",
                        help="comma-separated containers for the derivation census; default "
                             "every container under the read limit")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    chosen = game_id or getattr(arguments, "game", None)
    if not chosen:
        parser.error("--game is required: " + ", ".join(sorted(PROFILES)))
    game = profile(chosen)
    discs = game.discs

    if arguments.selftest:
        return selftest(game)
    if not arguments.source:
        parser.error("--source is required unless --selftest is given")
    wanted = tuple(name.strip() for name in arguments.containers.split(",")
                   if name.strip()) or game.default_containers

    def note(line: str) -> None:
        print(line, file=sys.stderr)

    started = time.time()
    if arguments.derive_check:
        identities_path = arguments.identities or game.identity_document
        if not identities_path.is_absolute():
            identities_path = ROOT / identities_path
        document = json.loads(identities_path.read_text(encoding="utf-8"))
        check = derivation_check(arguments.source, document, discs=discs, progress=note)
        census_wanted = tuple(name.strip() for name in arguments.census_containers.split(",")
                              if name.strip()) or None
        dumped: List[str] = list(document.get("unmatched") or [])
        dumped += [row["name"] for row in document.get("ambiguous") or [] if "name" in row]
        dumped += [row["name"] for row in document.get("rgb_only") or [] if "name" in row]
        already: List[str] = []
        for entry in (document.get("identities") or {}).values():
            for values in (entry.get("names") or {}).values():
                dumped.extend(values)
                already.extend(values)
        census = derivation_census(arguments.source, census_wanted, discs=discs,
                                   dumped_names=dumped, already_identified=already,
                                   progress=note)
        out = build_derivation_document(arguments.source, check, census, game=game)
        target = arguments.derive_out or game.derivation_document
        if not target.is_absolute():
            target = ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((json.dumps(out, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        counts = check["counts"]
        totals = census["totals"]
        by_hash = census.get("dumped_names_by_hash", {})
        print("DERIVATION identities=%d checked=%d confirmed=%d names=%d reproduced=%d "
              "not_reproduced=%d psm_disagrees=%d clut_own=%d clut_other=%d clut_none=%d | "
              "census containers=%d images=%d derived=%d names=%d not_derived=%d | "
              "dumped plain=%d placed=%d newly=%d region=%d images_placed=%d seconds=%.0f"
              % (counts["identities"], counts["identities_checked"],
                 counts["identities_confirmed"], counts["names"],
                 counts["names_tex0_reproduced"], counts["names_tex0_not_reproduced"],
                 counts["names_psm_disagrees"], counts["clut_in_own_palette"],
                 counts["clut_in_another_palette_of_the_member"],
                 counts["clut_not_in_the_member"], totals["containers"], totals["images"],
                 totals["images_derived"], totals["names_derived"],
                 totals["images_not_derived"], by_hash.get("plain_names", 0),
                 by_hash.get("plain_names_placed_by_hash", 0),
                 by_hash.get("plain_names_placed_that_pixels_could_not", 0),
                 by_hash.get("region_names", 0), by_hash.get("images_placed_by_hash", 0),
                 time.time() - started))
        return 0
    if arguments.index:
        written = write_index(arguments.source, arguments.index, wanted, discs=discs,
                              progress=note)
        print(f"INDEX rows={written} file={arguments.index} "
              f"seconds={time.time() - started:.0f}")
        if not arguments.dump_dir:
            return 0
        disc = read_index(arguments.index)
    else:
        if not arguments.dump_dir:
            parser.error("give --dump-dir, --index, or both")
        disc = list(index_disc(arguments.source, wanted, discs=discs, progress=note))

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
    coverage = (coverage_by_container(disc, report, wanted) if arguments.coverage else None)
    document = build_document(arguments.source, arguments.dump_dir, dumps, disc, report,
                              game=game, note=arguments.note, frame_labels=labels,
                              frame_teams=teams, coverage=coverage)
    out_path = arguments.out
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(
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
