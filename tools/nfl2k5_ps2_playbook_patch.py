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
# Synthetic fixture and self-test
# ---------------------------------------------------------------------------
# These used to live in ``tests/mod_editor/test_nfl2k5_ps2_playbook.py``, which
# meant the lane's validator ran ``python -m unittest`` and therefore could not
# pass in a shipped tree -- ``tests/`` is not in the release allowlist.  The
# fixture and the claims it supports belong to the tool that makes them, so they
# are here, reachable as ``--selftest``, and the release stage carries them.
#
# Nothing below reads a disc.  A ``PLAY`` body is built field by field until the
# shipped inspector parses it and the ported retail validator accepts every
# play; that body is wrapped in a real outer archive and a real ISO9660 volume
# from ``ps2_iso9660``'s own builder.

SELFTEST_BOOK_ID = 0x49CD9F21
SELFTEST_OTHER_BOOK_ID = 0x2C3DEF14
#: Family 1 (defense), type code 4.  The retail validator's ball-handler and
#: snapper requirements are unconditional for this family, so a two-node
#: coverage chain in every slot is the smallest play it accepts.
SELFTEST_PLAY_FLAGS = 4 | (1 << 6)
SELFTEST_CHAIN_OPS = (0x1B, 0x0D)          # Defense Start -> Zone Coverage


def _codec():
    from mod_editor.core import nfl2k5_play_codec as codec
    return codec


def _put_rel(body, field, target):
    """Store the book's self-relative pointer form: ``target = field - 1 + v``."""
    struct.pack_into("<i", body, field, target - field + 1)


def build_synthetic_body(formations=3, plays=2, categories=2):
    """A ``0x13390`` playbook body the shipped inspector and validator accept."""
    writer, insp = _studio()
    codec = _codec()
    slots = codec.SLOT_COUNT
    nodes_per_chain = len(SELFTEST_CHAIN_OPS)

    body = bytearray(insp.BODY_SIZE)
    body[0x0C:0x10] = b"PLAY"
    struct.pack_into("<I", body, 0x10, 0x11)
    struct.pack_into("<i", body, 0x14, -19)
    body[0x20:0x28] = b"p\0l\0b\0\0\0"

    # --- name pool, then the zero tail the custom-name path requires ---
    pool = bytearray()
    offset = {}
    for key, text in (("book", "TESTBOOK"), ("formation", "FORMATION"),
                      ("play", "PLAY"), ("category", "CATEGORY")):
        offset[key] = insp.STRING_BASE + len(pool)
        pool += text.encode("utf-16le") + b"\0\0"
    body[insp.STRING_BASE:insp.STRING_BASE + len(pool)] = pool
    pool_end = insp.STRING_BASE + len(pool)
    struct.pack_into("<I", body, writer.POOL_COUNT_WORD,
                     (pool_end - insp.STRING_BASE) // 2)

    # --- one two-node chain per slot, shared by every play ---
    blob = bytearray()
    for _slot in range(slots):
        chain = [codec.Node(op, 0, codec.decode_operands(op, 0))
                 for op in SELFTEST_CHAIN_OPS]
        codec.assign_node_flags(chain)
        for node in chain:
            blob += node.to_bytes()
    node_count = len(blob) // insp.NODE_SIZE
    body[insp.NODE_BASE:insp.NODE_BASE + len(blob)] = blob

    struct.pack_into("<I", body, 0x34, formations)
    struct.pack_into("<I", body, 0x38, plays)
    struct.pack_into("<I", body, 0x3C, categories)
    struct.pack_into("<I", body, 0x40, node_count)
    _put_rel(body, 0x30, offset["book"])
    _put_rel(body, 0x44, insp.FORMATION_BASE)
    _put_rel(body, 0x48, insp.FORMATION_AUX_BASE)
    _put_rel(body, 0x60, insp.PLAY_BASE)
    _put_rel(body, 0x64, insp.CATEGORY_BASE)
    _put_rel(body, 0x68, insp.NODE_BASE)

    chains = []
    for slot in range(slots):
        start = insp.NODE_BASE + slot * nodes_per_chain * insp.NODE_SIZE
        chains.append([bytes(body[start + n * insp.NODE_SIZE:
                                  start + (n + 1) * insp.NODE_SIZE])
                       for n in range(nodes_per_chain)])
    staged = [(0, chains[slot]) for slot in range(slots)]
    descriptors = [codec.build_descriptor(SELFTEST_PLAY_FLAGS, staged, slot, 0xB0)
                   for slot in range(slots)]

    for index in range(plays):
        base = insp.PLAY_BASE + index * insp.PLAY_SIZE
        _put_rel(body, base, offset["play"])
        struct.pack_into("<I", body, base + 4, SELFTEST_PLAY_FLAGS)
        for slot in range(slots):
            struct.pack_into("<I", body, base + 8 + slot * 8, descriptors[slot])
            _put_rel(body, base + 0x0C + slot * 8,
                     insp.NODE_BASE + slot * nodes_per_chain * insp.NODE_SIZE)

    for index in range(formations):
        base = insp.FORMATION_BASE + index * insp.FORMATION_SIZE
        _put_rel(body, base, offset["formation"])
        struct.pack_into("<I", body, base + 4,
                         codec.FORMATION_FLAG_UNDER_CENTER | (1 << 8))
        body[base + 0x0D:base + 0x18] = bytes(range(11))     # package map
        for slot in range(slots):
            record = (base + codec.FORMATION_SLOT_BASE
                      + slot * codec.FORMATION_SLOT_STRIDE)
            body[record + 1] = (codec.NO_MIRROR << 4) | 3
            lateral = (slot - 5) * 120
            struct.pack_into("<hhh", body, record + 2, lateral, lateral, lateral)
            struct.pack_into("<hhh", body, record + 8, 0, 0, 0)
        aux = insp.FORMATION_AUX_BASE + index * insp.FORMATION_AUX_SIZE
        for link in range(insp.FORMATION_PLAY_LINKS):
            struct.pack_into("<H", body, aux + link * 2, 0 if link == 0 else 0x01FF)

    for index in range(categories):
        base = insp.CATEGORY_BASE + index * insp.CATEGORY_SIZE
        _put_rel(body, base, offset["category"])
        body[base + 4] = index
        body[base + 5:base + 16] = bytes(range(11))

    return bytes(body)


def build_synthetic_resource(body):
    """A ``PLAY`` chunk: the 32-byte header plus the body, uncompressed."""
    head = bytearray(RESOURCE_HEADER_SIZE)
    head[0:4] = PLAY_FOURCC
    struct.pack_into("<4I", head, 4, len(body), len(body), 0, 0)
    return bytes(head) + body


def build_synthetic_pack(resources):
    """A ``/VC_20919/0.`` outer archive holding one chunk per entry."""
    count = len(resources)
    table_end = OUTER_HEADER_SIZE + count * OUTER_ENTRY_SIZE
    block = -(-table_end // ALIGNMENT)
    placed = []
    for name_id, payload in resources:
        placed.append((name_id, len(payload), block, payload))
        block += -(-len(payload) // ALIGNMENT)
    buffer = bytearray(block * ALIGNMENT)
    struct.pack_into("<III", buffer, 0, count, 0, 1)
    struct.pack_into("<I", buffer, 0x0C, block)
    for index, (name_id, size, at, payload) in enumerate(placed):
        struct.pack_into("<III", buffer,
                         OUTER_HEADER_SIZE + index * OUTER_ENTRY_SIZE,
                         name_id, size, at)
        buffer[at * ALIGNMENT:at * ALIGNMENT + len(payload)] = payload
    return bytes(buffer)


def build_synthetic_disc(plays=2, books=None):
    """A PS2-shaped ISO9660 volume carrying two synthetic playbooks."""
    if books is None:
        books = [(SELFTEST_BOOK_ID, build_synthetic_resource(
                      build_synthetic_body(plays=plays))),
                 (SELFTEST_OTHER_BOOK_ID, build_synthetic_resource(
                      build_synthetic_body(plays=plays)))]
    return ps2_iso9660.build_synthetic_iso(
        files=[(b"SYSTEM.CNF;1",
                b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.01\r\n"
                b"VMODE = NTSC\r\n"),
               (b"SLUS_209.19;1", b"\x7fELF" + bytes(2044))],
        sub_name=b"VC_20919",
        sub_files=[(b"0.;1", build_synthetic_pack(books))])


def selftest_recipe():
    return {"schema": SCHEMA,
            "edits": [{"book_id": "0x%08x" % SELFTEST_BOOK_ID,
                       "formations": [{"donor_formation_index": 0,
                                       "custom_name": "GUN TRIPS RT",
                                       "slot_positions": [
                                           [(s - 5) * 130, -90 if s == 0 else 0]
                                           for s in range(11)]}],
                       "plays": [{"donor_play_index": 0,
                                  "custom_name": "SMASH"}]}]}


def selftest(tmp=None):
    """Every claim the lane's validator makes, against synthetic bytes only."""
    import shutil
    import tempfile

    import nfl2k5_ps2_playbook_verify as verifier

    writer, insp = _studio()
    codec = _codec()
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    def refuses(call, why):
        try:
            call()
        except PlaybookPatchError:
            return
        except Exception as exc:                    # pragma: no cover - defensive
            failures.append("wrong error for %s: %r" % (why, exc))
            return
        failures.append("accepted: %s" % why)

    owned = tmp is None
    root = Path(tmp or tempfile.mkdtemp(prefix="ps2-playbook-selftest-"))
    try:
        # 1. The fixture has to be a real book, or nothing below proves anything.
        body = build_synthetic_body()
        book = insp._parse_body(body, asset_id="synthetic", outer_index=0)
        check(len(book.formations) == 3, "synthetic formation count")
        check(len(book.plays) == 2, "synthetic play count")
        check(book.node_count == codec.SLOT_COUNT * len(SELFTEST_CHAIN_OPS),
              "synthetic node count")
        check(len(book.chains) == codec.SLOT_COUNT, "synthetic chain count")
        for play in book.plays:
            assignments = [
                (a.descriptor_word,
                 [bytes.fromhex(n.raw_hex)
                  for n in book.chain(a.chain_start_index).nodes])
                for a in play.assignments]
            check(codec.validate_play(play.flags_or_id, assignments) is None,
                  "the ported retail validator rejected a synthetic play")

        source = root / "source.iso"
        source.write_bytes(build_synthetic_disc())
        recipe_path = root / "recipe.json"
        recipe_path.write_text(json.dumps(selftest_recipe()), encoding="utf-8",
                               newline="\n")

        # 2. Both books are found, at their offsets, at the fixed size.
        targets = find_targets(source)
        check([t.book_id for t in targets]
              == [SELFTEST_BOOK_ID, SELFTEST_OTHER_BOOK_ID],
              "target discovery order")
        for target in targets:
            check(target.pack.iso_path == "/VC_20919/0.", "target pack path")
            check(len(read_resource(source, target)) == PLAY_RESOURCE_SIZE,
                  "target resource size")

        # 3. A formation and a play are added, and the independent verifier
        #    passes the image that results.
        output = root / "output.iso"
        report = patch(source, load_recipe(recipe_path), output, workdir=root)
        check(len(report["play_edits"]) == 1, "one declared edit")
        edit = report["play_edits"][0]
        check(edit["before"] == {"formations": 3, "plays": 2,
                                 "categories": 2, "nodes": 22},
              "counts before the edit: %r" % (edit["before"],))
        check(edit["after"] == {"formations": 4, "plays": 3,
                                "categories": 2, "nodes": 22},
              "counts after the edit: %r" % (edit["after"],))
        check(edit["resource_size"] == PLAY_RESOURCE_SIZE, "edited resource size")
        check(source.stat().st_size == output.stat().st_size,
              "the patched image changed length")

        result = verifier.verify(source, output, report)
        check(result["verdict"] == "PASS", "verifier verdict %r" % result["verdict"])
        check(result["declared_edits"] == 1, "verifier declared-edit count")
        check(result["play_resources_found"] == 2, "verifier resource count")
        check(result["books"][0]["counts"]["plays"] == 3, "verifier play count")
        check(result["books"][0]["plays_validated"] == 3, "verifier plays validated")
        check(result["changed_byte_total"] > 0, "verifier saw no change")

        # 4. The book the recipe never named keeps every byte.
        edited_at = edit["absolute_offset"]
        for book_id, offset in verifier._play_resources(output):
            before = verifier._read_at(source, offset, PLAY_RESOURCE_SIZE)
            after = verifier._read_at(output, offset, PLAY_RESOURCE_SIZE)
            if offset == edited_at:
                check(before != after, "the edited book did not change")
            else:
                check(before == after, "book %s changed" % book_id)

        # 5. A verifier that cannot fail is a rubber stamp.  The other book's
        #    resource is a real, addressable, out-of-lane target.
        stray = next((offset for _id, offset in verifier._play_resources(output)
                      if offset != edited_at), None)
        check(stray is not None, "no out-of-lane byte to flip")
        if stray is not None:
            strayed = root / "strayed.iso"
            shutil.copyfile(str(output), str(strayed))
            with open(str(strayed), "r+b") as handle:
                handle.seek(stray + RESOURCE_HEADER_SIZE + 0x40)
                original = handle.read(1)
                handle.seek(stray + RESOURCE_HEADER_SIZE + 0x40)
                handle.write(bytes([original[0] ^ 0xFF]))
            try:
                verifier.verify(source, strayed, report)
                failures.append("the verifier passed a byte changed outside "
                                "the declared playbook span")
            except Exception:
                pass

        # 6. Refusals, each leaving no output image behind.
        def refusal(name, source_path, recipe_document):
            destination = root / name
            path = root / (name + ".json")
            path.write_text(json.dumps(recipe_document), encoding="utf-8",
                            newline="\n")
            refuses(lambda: patch(source_path, load_recipe(path), destination,
                                  workdir=root), name)
            check(not destination.exists(),
                  "%s created an output image" % name)

        full = root / "full.iso"
        full.write_bytes(build_synthetic_disc(books=[
            (SELFTEST_BOOK_ID, build_synthetic_resource(
                build_synthetic_body(plays=insp.PLAY_CAPACITY)))]))
        refusal("at-the-play-capacity", full, selftest_recipe())

        unknown = json.loads(json.dumps(selftest_recipe()))
        unknown["edits"][0]["book_id"] = "0xdeadbeef"
        refusal("an-unknown-book-id", source, unknown)

        bad_schema = root / "bad-schema.json"
        bad_schema.write_text(json.dumps({"schema": "nope", "edits": []}),
                              encoding="utf-8", newline="\n")
        refuses(lambda: load_recipe(bad_schema), "a recipe with the wrong schema")

        # A compile that returns the wrong body length must be refused *before*
        # the output image is created, so a fixed-allocation violation can never
        # reach the disk.
        real = writer.compile_formation_play_creations

        def truncating(raw, *args, **kwargs):
            result = real(raw, *args, **kwargs)
            object.__setattr__(result, "replacement", result.replacement[:-16])
            return result

        writer.compile_formation_play_creations = truncating
        try:
            short = root / "short-compile.iso"
            refuses(lambda: patch(source, load_recipe(recipe_path), short,
                                  workdir=root),
                    "a compile that returned the wrong body length")
            check(not short.exists(),
                  "a fixed-allocation refusal created an output image")
        finally:
            writer.compile_formation_play_creations = real
    finally:
        if owned:
            shutil.rmtree(str(root), ignore_errors=True)

    for line in failures:
        print("FAIL: %s" % line, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_PLAYBOOK_PATCH_SELFTEST_PASS books=2 plays_validated=3 "
          "refusals=4 verifier_failed_on_stray_byte=true")
    return 0


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
    argv = list(sys.argv[1:] if argv is None else argv)
    # ``--selftest`` is spelled the way every other PS2 lane tool spells it, so
    # a validator manifest can name it without knowing this tool has
    # subcommands.
    if argv and argv[0] in ("--selftest", "selftest"):
        return selftest()

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("selftest", help="prove the lane against synthetic bytes")

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
