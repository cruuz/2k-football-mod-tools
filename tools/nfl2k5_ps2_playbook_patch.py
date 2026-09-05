#!/usr/bin/env python3
"""Write authored formations and plays into the PS2 ESPN NFL 2K5 disc.

The PS2 release (``SLUS-20919``) carries the **same 37 ``PLAY`` playbooks as
the Xbox disc** -- same 78,736-byte body, same 32-bit content ids, same corpus
of 1,533 formations / 9,251 plays / 91,833 nodes -- and the executable-side
tables the play codec was reverse-engineered from (lane table, 29-entry opcode
table, named-spot tables) are present verbatim in ``SLUS_209.19``.  So this tool
does **no** PS2-specific format work: it drives the shipped Xbox
``mod_editor.core.nfl2k5_formation_play_writer`` unchanged and only retargets
*where the bytes live*.  See ``docs/product/PS2_PHASE2_PLAYBOOKS_RESEARCH.md``.

Allocation is fixed, twice over:

* the compiled book is asserted to be **exactly** ``0x20 + 0x13390`` = 78,768
  bytes, the size it replaces -- the writer inhabits empty formation/play slots
  inside the fixed body and never grows or relocates anything;
* the modified ``/VC_20919/0.`` pack is asserted to be byte-for-byte the same
  length as the original, and is installed with
  ``ps2_iso9660_writer.replace_files``, which copies the source to a **new**
  image and refuses any replacement that does not fit the extent its file
  already owns.  The source ISO is opened read-only and never written.

**The ``PLAY`` chunks are stored uncompressed** (``lz=0`` on all 37, and the
outer chunk header's compression sentinel ``0xFEEDBEEF`` is absent), so there is
no decompression on read and **no recompression step on write** -- the body is
patched in place inside the pack and the surrounding bytes are untouched.

Refusals inherited from the Xbox writer, unchanged on PS2: the 270-play and
50-formation capacities, the node-pool budget, the name-pool zero-tail and
pool-count-word invariants, and the "changed an unowned byte" guard.

Usage::

    nfl2k5_ps2_playbook_patch.py list  --iso SRC.iso [--json OUT.json]
    nfl2k5_ps2_playbook_patch.py patch --iso SRC.iso --recipe R.json \\
        --output NEW.iso [--report REPORT.json] [--workdir DIR]

Recipe schema (``nfl2k5_ps2_playbook_patch/v1``)::

    {"schema": "nfl2k5_ps2_playbook_patch/v1",
     "edits": [{"book_id": "0xf20774de",
                "formations": [{"donor_formation_index": 0,
                                "custom_name": "GUN TRIPS RT",
                                "slot_positions": [[x_cm, depth_cm], ...x11],
                                "category_index": null}],
                "plays":      [{"donor_play_index": 0,
                                "custom_name": "SMASH"}],
                "links":      [{"formation_index": 3, "play_index": 41}]}]}

Nothing here bundles or emits game data: ``list`` reports ids, sizes and counts,
and ``patch`` writes only into the caller's own output image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _entry in (_ROOT, _HERE):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import ps2_iso9660  # noqa: E402
import ps2_iso9660_writer  # noqa: E402

SCHEMA = "nfl2k5_ps2_playbook_patch/v1"

PACK_DIR = "/VC_20919"
PACK_LETTERS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALIGNMENT = 0x800
PACK_SLOT_COUNT = 36
OUTER_HEADER_SIZE = 0x0C + PACK_SLOT_COUNT * 4
OUTER_ENTRY_SIZE = 12
CHUNK_HEADER_SIZE = 0x20

RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE = 0x13390
PLAY_RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE   # 78,768
PLAY_FOURCC = b"PLAY"

COPY_CHUNK = 8 * 1024 * 1024


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read without ``os.pread``, which Windows does not have."""
    os.lseek(fd, offset, os.SEEK_SET)
    parts = []
    while count:
        block = os.read(fd, count)
        if not block:
            break
        parts.append(block)
        count -= len(block)
    return b"".join(parts)


class PlaybookPatchError(ValueError):
    """A refusal: a bad recipe, a missing book, or a rule the writer enforces."""


def _require(condition, message):
    if not condition:
        raise PlaybookPatchError(message)


# ---------------------------------------------------------------------------
# The heavy studio imports are deliberately lazy
# ---------------------------------------------------------------------------
# Importing ``mod_editor`` pulls the whole editor package (Pillow included).
# ``list`` does not need it, and ``test_shipped_tools_are_self_sufficient``
# imports this module with tools/ off sys.path, so keeping module import to
# stdlib + siblings makes that check independent of the editor's own deps.

def _studio():
    from mod_editor.core import nfl2k5_formation_play_writer as writer
    from mod_editor.core import nfl2k5_playbook_inspector as inspector
    _require(
        inspector.BODY_SIZE == BODY_SIZE
        and inspector.RESOURCE_HEADER_SIZE == RESOURCE_HEADER_SIZE,
        "the studio playbook layout constants no longer match this tool",
    )
    return writer, inspector


# ---------------------------------------------------------------------------
# Locating the packs and the PLAY resources inside them
# ---------------------------------------------------------------------------

class Pack(object):
    __slots__ = ("letter", "iso_path", "byte_offset", "size", "virtual_start")

    def __init__(self, letter, iso_path, byte_offset, size, virtual_start):
        self.letter = letter
        self.iso_path = iso_path
        self.byte_offset = byte_offset
        self.size = size
        self.virtual_start = virtual_start


class PlaybookTarget(object):
    """One ``PLAY`` resource: where it is and what it declares."""

    __slots__ = ("book_id", "entry_index", "virtual_offset", "pack",
                 "pack_offset", "absolute_offset")

    def __init__(self, book_id, entry_index, virtual_offset, pack, pack_offset,
                 absolute_offset):
        self.book_id = book_id
        self.entry_index = entry_index
        self.virtual_offset = virtual_offset
        self.pack = pack
        self.pack_offset = pack_offset
        self.absolute_offset = absolute_offset

    @property
    def id_text(self):
        return "0x%08x" % self.book_id

    def as_dict(self):
        return {
            "book_id": self.id_text,
            "entry_index": self.entry_index,
            "pack": self.pack.letter,
            "pack_iso_path": self.pack.iso_path,
            "pack_offset": self.pack_offset,
            "absolute_offset": self.absolute_offset,
            "resource_size": PLAY_RESOURCE_SIZE,
            "body_size": BODY_SIZE,
            "compressed": False,
        }


def open_packs(image):
    """Every ``/VC_20919/<letter>.`` pack, in archive order."""
    packs = []
    virtual = 0
    for letter in PACK_LETTERS:
        found = (ps2_iso9660.find(image, "%s/%s." % (PACK_DIR, letter))
                 or ps2_iso9660.find(image, "%s/%s" % (PACK_DIR, letter)))
        if found is None or found.is_dir:
            break
        packs.append(Pack(letter, found.path, found.lba * ALIGNMENT,
                          found.length, virtual))
        virtual += found.length
    _require(packs, "no %s packs in that image -- is it ESPN NFL 2K5 (PS2)?" % PACK_DIR)
    return packs


class _Archive(object):
    """Read-only view of the concatenated packs, addressed by virtual offset."""

    def __init__(self, iso_path, packs):
        self.packs = packs
        self.total = sum(p.size for p in packs)
        self._fd = os.open(str(iso_path), os.O_RDONLY | getattr(os, "O_BINARY", 0))

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def pack_of(self, virtual_offset):
        for pack in reversed(self.packs):
            if pack.virtual_start <= virtual_offset:
                return pack
        raise PlaybookPatchError("negative archive offset")

    def read(self, virtual_offset, size):
        _require(0 <= virtual_offset and virtual_offset + size <= self.total,
                 "read outside the archive")
        parts = []
        while size:
            pack = self.pack_of(virtual_offset)
            inside = virtual_offset - pack.virtual_start
            take = min(size, pack.size - inside)
            block = _pread(self._fd, take, pack.byte_offset + inside)
            _require(len(block) == take, "short read from pack %s" % pack.letter)
            parts.append(block)
            virtual_offset += take
            size -= take
        return b"".join(parts)


def find_targets(iso_path):
    """Every ``PLAY`` resource on the disc.

    On both the PS2 and Xbox discs each playbook is **chunk 0 of its own outer
    entry** at offset 0, so the whole 4,322-entry table resolves from one
    32-byte read per entry rather than a full chunk walk.
    """
    image = ps2_iso9660.open_image(str(iso_path))
    packs = open_packs(image)
    targets = []
    with _Archive(iso_path, packs) as archive:
        header = archive.read(0, OUTER_HEADER_SIZE)
        entry_count, _reserved, populated = struct.unpack_from("<III", header, 0)
        _require(0 < entry_count <= 1 << 20, "implausible outer entry count")
        _require(populated == len(packs),
                 "index declares %d packs, the image has %d" % (populated, len(packs)))
        table = archive.read(OUTER_HEADER_SIZE, entry_count * OUTER_ENTRY_SIZE)
        for index in range(entry_count):
            name_id, size, blocks = struct.unpack_from(
                "<III", table, index * OUTER_ENTRY_SIZE)
            if size < PLAY_RESOURCE_SIZE:
                continue
            virtual = blocks * ALIGNMENT
            if virtual + CHUNK_HEADER_SIZE > archive.total:
                continue
            head = archive.read(virtual, CHUNK_HEADER_SIZE)
            if head[:4] != PLAY_FOURCC:
                continue
            stored, _system, _video, magic = struct.unpack_from("<4I", head, 4)
            if stored != BODY_SIZE or magic == 0xFEEDBEEF:
                continue
            pack = archive.pack_of(virtual)
            pack_offset = virtual - pack.virtual_start
            _require(
                pack_offset + PLAY_RESOURCE_SIZE <= pack.size,
                "PLAY resource at 0x%x straddles a pack boundary" % virtual,
            )
            targets.append(PlaybookTarget(
                name_id, index, virtual, pack, pack_offset,
                pack.byte_offset + pack_offset))
    _require(targets, "that image contains no PLAY playbooks")
    return targets


def read_resource(iso_path, target):
    """The 78,768 raw bytes of one playbook."""
    with open(str(iso_path), "rb") as handle:
        handle.seek(target.absolute_offset)
        raw = handle.read(PLAY_RESOURCE_SIZE)
    _require(len(raw) == PLAY_RESOURCE_SIZE, "short read of the PLAY resource")
    _require(raw[:4] == PLAY_FOURCC, "that offset does not hold a PLAY resource")
    return raw


def summarize(iso_path, targets=None):
    """Ids, sizes and capacity headroom for every book -- counts, no payload."""
    writer, inspector = _studio()
    targets = targets if targets is not None else find_targets(iso_path)
    node_capacity = (inspector.STRING_BASE - inspector.NODE_BASE) // inspector.NODE_SIZE
    rows = []
    for target in targets:
        raw = read_resource(iso_path, target)
        book = inspector._parse_body(
            raw[RESOURCE_HEADER_SIZE:], asset_id=target.id_text,
            outer_index=target.entry_index)
        row = target.as_dict()
        row.update({
            "book_name": book.book_name,
            "formations": len(book.formations),
            "plays": len(book.plays),
            "categories": len(book.categories),
            "nodes": book.node_count,
            "chains": len(book.chains),
            "formation_headroom": inspector.FORMATION_CAPACITY - len(book.formations),
            "play_headroom": inspector.PLAY_CAPACITY - len(book.plays),
            "node_headroom": node_capacity - book.node_count,
            "at_play_capacity": len(book.plays) == inspector.PLAY_CAPACITY,
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Recipe
# ---------------------------------------------------------------------------

def _as_int(value, label, low=None, high=None):
    _require(isinstance(value, int) and not isinstance(value, bool),
             "%s must be an integer" % label)
    if low is not None:
        _require(value >= low, "%s must be >= %d" % (label, low))
    if high is not None:
        _require(value <= high, "%s must be <= %d" % (label, high))
    return value


def _book_key(text):
    _require(isinstance(text, str), "book_id must be a string like \"0xf20774de\"")
    try:
        return int(text, 16) & 0xFFFFFFFF
    except ValueError:
        raise PlaybookPatchError("book_id %r is not hexadecimal" % text)


def load_recipe(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlaybookPatchError("could not read the recipe: %s" % exc)
    _require(isinstance(data, dict), "the recipe must be a JSON object")
    _require(data.get("schema") == SCHEMA,
             "recipe schema must be %r" % SCHEMA)
    edits = data.get("edits")
    _require(isinstance(edits, list) and edits,
             "the recipe needs a non-empty \"edits\" list")
    seen = set()
    parsed = []
    for raw_edit in edits:
        _require(isinstance(raw_edit, dict), "each edit must be an object")
        key = _book_key(raw_edit.get("book_id"))
        _require(key not in seen, "book 0x%08x appears twice in the recipe" % key)
        seen.add(key)
        parsed.append((key, raw_edit))
    return parsed


def _requests(writer, asset_id, edit):
    formations, plays, links = [], [], []
    for row in edit.get("formations", []) or []:
        _require(isinstance(row, dict), "each formation request must be an object")
        slots = row.get("slot_positions")
        if slots is not None:
            _require(isinstance(slots, list) and len(slots) == 11,
                     "slot_positions needs exactly 11 [x_cm, depth_cm] pairs")
            pairs = []
            for pair in slots:
                _require(isinstance(pair, (list, tuple)) and len(pair) == 2,
                         "each slot position must be an [x_cm, depth_cm] pair")
                pairs.append((int(round(pair[0])), int(round(pair[1]))))
            slots = tuple(pairs)
        formations.append(writer.FormationCreateRequest(
            asset_id=asset_id,
            donor_formation_index=_as_int(
                row.get("donor_formation_index", 0), "donor_formation_index", 0),
            custom_name=row.get("custom_name"),
            slot_positions=slots,
            category_index=row.get("category_index"),
            replace_index=row.get("replace_index"),
        ))
    for row in edit.get("plays", []) or []:
        _require(isinstance(row, dict), "each play request must be an object")
        plays.append(writer.PlayCreateRequest(
            asset_id=asset_id,
            donor_play_index=_as_int(
                row.get("donor_play_index", 0), "donor_play_index", 0),
            custom_name=row.get("custom_name"),
            assignments=row.get("assignments"),
            replace_index=row.get("replace_index"),
            play_flags=row.get("play_flags"),
        ))
    for row in edit.get("links", []) or []:
        _require(isinstance(row, dict), "each link request must be an object")
        links.append(writer.FormationLinkRequest(
            asset_id=asset_id,
            formation_index=_as_int(row.get("formation_index"), "formation_index", 0),
            play_index=_as_int(row.get("play_index"), "play_index", 0),
            group=row.get("group"),
        ))
    _require(formations or plays or links,
             "edit for book %s asks for nothing" % asset_id)
    return formations, plays, links


# ---------------------------------------------------------------------------
# Compile
# ---------------------------------------------------------------------------

def compile_edits(iso_path, recipe):
    """Resolve every edit to replacement bytes.  Refuses before anything is written."""
    writer, inspector = _studio()
    targets = {t.book_id: t for t in find_targets(iso_path)}
    compiled = []
    for key, edit in recipe:
        target = targets.get(key)
        _require(target is not None,
                 "book 0x%08x is not on this disc (it has %d books)"
                 % (key, len(targets)))
        raw = read_resource(iso_path, target)
        before = inspector._parse_body(
            raw[RESOURCE_HEADER_SIZE:], asset_id=target.id_text,
            outer_index=target.entry_index)
        formations, plays, links = _requests(writer, target.id_text, edit)
        try:
            result = writer.compile_formation_play_creations(
                raw, formations, plays, links)
        except Exception as exc:
            raise PlaybookPatchError(
                "book %s: %s" % (target.id_text, exc))
        replacement = result.replacement
        _require(
            len(replacement) == PLAY_RESOURCE_SIZE,
            "book %s compiled to %d bytes; fixed allocation requires %d"
            % (target.id_text, len(replacement), PLAY_RESOURCE_SIZE),
        )
        _require(replacement[:RESOURCE_HEADER_SIZE] == raw[:RESOURCE_HEADER_SIZE],
                 "book %s: the chunk header changed" % target.id_text)
        after = inspector._parse_body(
            replacement[RESOURCE_HEADER_SIZE:], asset_id=target.id_text,
            outer_index=target.entry_index)
        compiled.append({
            "target": target,
            "raw": raw,
            "replacement": replacement,
            "selector": result.selector,
            "changed_byte_count": result.changed_byte_count,
            "changed_ranges": [list(r) for r in result.changed_ranges],
            "new_formation_indices": list(result.new_formation_indices),
            "new_play_indices": list(result.new_play_indices),
            "before": {"formations": len(before.formations),
                       "plays": len(before.plays),
                       "categories": len(before.categories),
                       "nodes": before.node_count},
            "after": {"formations": len(after.formations),
                      "plays": len(after.plays),
                      "categories": len(after.categories),
                      "nodes": after.node_count},
        })
    return compiled


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------

def _rebuild_pack(iso_path, pack, edits, destination):
    """A copy of *pack* with each edit's bytes patched in, same length."""
    written = 0
    with open(str(iso_path), "rb") as src, open(str(destination), "wb") as dst:
        src.seek(pack.byte_offset)
        remaining = pack.size
        while remaining:
            block = src.read(min(COPY_CHUNK, remaining))
            _require(block, "short read while copying pack %s" % pack.letter)
            dst.write(block)
            remaining -= len(block)
            written += len(block)
    _require(written == pack.size, "pack copy is the wrong length")
    with open(str(destination), "r+b") as dst:
        for item in edits:
            dst.seek(item["target"].pack_offset)
            dst.write(item["replacement"])
        dst.flush()
        os.fsync(dst.fileno())
    _require(os.path.getsize(str(destination)) == pack.size,
             "the rebuilt pack changed length -- fixed allocation violated")
    return destination


def patch(iso_path, recipe, output_path, workdir=None):
    """Compile every edit and write a new ISO.  The source is never modified."""
    iso_path = Path(iso_path)
    output_path = Path(output_path)
    _require(iso_path.is_file(), "source ISO not found: %s" % iso_path)
    _require(not output_path.exists(),
             "output already exists (refusing to overwrite): %s" % output_path)

    compiled = compile_edits(iso_path, recipe)
    packs = {item["target"].pack.letter: item["target"].pack for item in compiled}
    _require(len(packs) == 1,
             "this tool patches one pack per run; the recipe spans %d" % len(packs))
    pack = list(packs.values())[0]

    workdir = Path(workdir) if workdir else output_path.parent
    workdir.mkdir(parents=True, exist_ok=True)
    staged = workdir / ("%s.pack%s.staged" % (output_path.name, pack.letter))
    if staged.exists():
        staged.unlink()
    try:
        _rebuild_pack(iso_path, pack, compiled, staged)
        writer_report = ps2_iso9660_writer.replace_files(
            iso_path, output_path, {pack.iso_path: staged})
    finally:
        if staged.exists():
            staged.unlink()

    report = {
        "schema": SCHEMA,
        "source_iso": str(iso_path),
        "source_iso_size": iso_path.stat().st_size,
        "output_iso": str(output_path),
        "output_iso_size": output_path.stat().st_size,
        "pack_iso_path": pack.iso_path,
        "pack_size": pack.size,
        "resource_size": PLAY_RESOURCE_SIZE,
        "body_size": BODY_SIZE,
        "compressed": False,
        "play_edits": [
            {
                "book_id": item["target"].id_text,
                "entry_index": item["target"].entry_index,
                "pack_offset": item["target"].pack_offset,
                "absolute_offset": item["target"].absolute_offset,
                "resource_size": PLAY_RESOURCE_SIZE,
                "selector": item["selector"],
                "changed_byte_count": item["changed_byte_count"],
                "changed_ranges": item["changed_ranges"],
                "new_formation_indices": item["new_formation_indices"],
                "new_play_indices": item["new_play_indices"],
                "before": item["before"],
                "after": item["after"],
                "source_sha256": hashlib.sha256(item["raw"]).hexdigest(),
                "replacement_sha256": hashlib.sha256(item["replacement"]).hexdigest(),
            }
            for item in compiled
        ],
        "iso_writer_report": ps2_iso9660_writer.report_to_json(writer_report),
    }
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_list(args):
    rows = summarize(args.iso)
    payload = {"schema": SCHEMA, "source_iso": str(args.iso), "books": rows}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
            newline="\n")
    print("%d PLAY playbooks" % len(rows))
    for row in rows:
        print("  %s  %-24s formations %2d/%d  plays %3d/%d  nodes %4d  "
              "headroom f%d p%d n%d%s"
              % (row["book_id"], row["book_name"], row["formations"], 50,
                 row["plays"], 270, row["nodes"], row["formation_headroom"],
                 row["play_headroom"], row["node_headroom"],
                 "  AT PLAY CAP" if row["at_play_capacity"] else ""))
    return 0


def _cmd_patch(args):
    recipe = load_recipe(args.recipe)
    report = patch(args.iso, recipe, args.output, args.workdir)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    for edit in report["play_edits"]:
        print("book %s: %s -> %s (%d bytes changed in the body)"
              % (edit["book_id"],
                 "%(formations)df/%(plays)dp/%(nodes)dn" % edit["before"],
                 "%(formations)df/%(plays)dp/%(nodes)dn" % edit["after"],
                 edit["changed_byte_count"]))
    print("wrote %s (%d bytes)" % (report["output_iso"], report["output_iso_size"]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    lister = sub.add_parser("list", help="report every PLAY playbook and its headroom")
    lister.add_argument("--iso", required=True)
    lister.add_argument("--json")
    lister.set_defaults(func=_cmd_list)

    patcher = sub.add_parser("patch", help="write a new ISO with authored books")
    patcher.add_argument("--iso", required=True)
    patcher.add_argument("--recipe", required=True)
    patcher.add_argument("--output", required=True)
    patcher.add_argument("--report")
    patcher.add_argument("--workdir")
    patcher.set_defaults(func=_cmd_patch)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except PlaybookPatchError as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
