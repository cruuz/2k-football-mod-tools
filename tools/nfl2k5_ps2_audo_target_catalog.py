#!/usr/bin/env python3
"""Catalogue every ``AUDO`` sample slot on an ESPN NFL 2K5 PS2 disc.

An ``AUDO`` chunk is one named sound with its encoded payload inline, behind the
same 0x20 chunk wrapper every other resource on the disc uses::

    wrapper +0x00  "AUDO"
            +0x04  stored_size = system_bytes + video_bytes
            +0x08  system_bytes
            +0x0C  video_bytes        <- the SPU-ADPCM payload allocation
            +0x10  compression magic  (0 on every AUDO)

    body    +0x0C  "AUDO"             descriptor tag
            +0x10  17                 descriptor type
            +0x14  relative pointer to the descriptor, biased: N = 0x13 + value
            +0x20  UTF-16LE name, "PADDING*" filled

    body+N  the 8-word sound descriptor:
            channels, channels, 17, flags (0x35 mono / 0x75 stereo),
            data_size, data_offset, per_channel_bytes, sample_rate

That layout, and the SPU-ADPCM codec behind ``video_bytes``, are established in
``docs/product/PS2_PHASE2_AUDIO_RESEARCH.md``.  This tool turns them into the
target list a writer binds against: which slot, how many bytes it owns, how many
frames that is, and whether its name is unique on the disc.

**Retail-free by construction.**  The catalogue records names, offsets, sizes,
counts and descriptor field values.  It never records a payload hash, a decoded
digest or any audio, so it can be committed and shipped.

The identity of a slot is ``(outer entry index, chunk index)`` -- the same key
the disc inventory uses -- because names are not unique: 690 of the 844 chunks
share a name with another chunk.  ``unique_name`` says which 154 do not, and a
runtime witness should use one of those.

Stdlib only.  ``--selftest`` proves the walk on a synthetic disc.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
from typing import Iterable, List, Sequence, Tuple

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl2k5_ps2_disc_inventory as inv  # noqa: E402
import ps2_iso9660 as iso  # noqa: E402
import spu_adpcm  # noqa: E402

SCHEMA = "nfl2k5_ps2_audo_catalog/v1"
DEFAULT_REPORT = Path("reports/gameplay_tuning/nfl2k5_ps2_audo_catalog.v1.json")

AUDO = b"AUDO"
DESCRIPTOR_TYPE = 17
DESCRIPTOR_POINTER_BIAS = 0x13
DESCRIPTOR_WORDS = 8
FLAGS_MONO = 0x35
FLAGS_STEREO = 0x75
MAX_CHANNELS = 2

#: What the stock disc holds; a divergence is reported, never silently accepted.
EXPECTED_SLOT_COUNT = 844
EXPECTED_UNIQUE_NAME_COUNT = 154


class CatalogError(ValueError):
    """A disc, a chunk or a descriptor this tool refuses to guess about."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise CatalogError(message)


def parse_audo_body(body: bytes, system_bytes: int, video_bytes: int) -> dict:
    """Parse an ``AUDO`` system buffer into name + descriptor fields."""
    _require(len(body) >= system_bytes, "AUDO system buffer is short")
    _require(body[0x0C:0x10] == AUDO, "AUDO body is missing its descriptor tag")
    kind, pointer = struct.unpack_from("<2I", body, 0x10)
    _require(kind == DESCRIPTOR_TYPE,
             f"AUDO descriptor type is {kind}, expected {DESCRIPTOR_TYPE}")
    offset = DESCRIPTOR_POINTER_BIAS + pointer
    _require(
        0x20 < offset and offset + DESCRIPTOR_WORDS * 4 <= system_bytes,
        f"AUDO descriptor pointer {pointer} lands outside the {system_bytes}-byte "
        "system buffer",
    )
    name_field = offset - 0x20
    raw = body[0x20:offset]
    name = raw.decode("utf-16le", "replace").split("\x00", 1)[0]
    words = struct.unpack_from("<%dI" % DESCRIPTOR_WORDS, body, offset)
    channels, channels_again, codec, flags, data_size, data_offset, per_channel, rate = words
    _require(1 <= channels <= MAX_CHANNELS, f"{name}: channel count {channels}")
    _require(channels_again == channels, f"{name}: descriptor channel words disagree")
    _require(codec == DESCRIPTOR_TYPE, f"{name}: descriptor codec word {codec}")
    _require(flags in (FLAGS_MONO, FLAGS_STEREO), f"{name}: descriptor flags 0x{flags:x}")
    _require((flags == FLAGS_STEREO) == (channels == 2),
             f"{name}: descriptor stereo flag disagrees with the channel count")
    _require(data_offset == 0, f"{name}: descriptor data_offset {data_offset} is not 0")
    _require(data_size == video_bytes,
             f"{name}: descriptor data_size {data_size} != video_bytes {video_bytes}")
    _require(per_channel * channels == data_size,
             f"{name}: per-channel {per_channel} x {channels} != {data_size}")
    _require(per_channel % spu_adpcm.BLOCK_BYTES == 0,
             f"{name}: per-channel {per_channel} is not a multiple of "
             f"{spu_adpcm.BLOCK_BYTES}")
    _require(0 < rate <= 48000, f"{name}: sample rate {rate}")
    return {
        "name": name,
        "name_field_bytes": name_field,
        "descriptor_offset": offset,
        "channels": channels,
        "stereo": channels == 2,
        "descriptor_flags": flags,
        "sample_rate": rate,
        "per_channel_bytes": per_channel,
        "max_frames": spu_adpcm.max_frames_for_bytes(per_channel),
        "descriptor": list(words),
    }


def slot_id(entry_index: int, chunk_index: int) -> str:
    return "nfl2k5ps2.audio.audo.o%04d.c%04d" % (entry_index, chunk_index)


def walk_audo(archive, entries: Sequence[Tuple[int, int, int]]) -> List[dict]:
    """Every AUDO slot, in disc order.

    Mirrors the disc inventory's chunk walk exactly, including its zero-padding
    recovery, so ``chunk_index`` means the same thing in both tools.
    """
    slots: List[dict] = []
    for entry_index, (name_id, entry_size, offset_blocks) in enumerate(entries):
        virtual_base = offset_blocks * inv.ALIGNMENT
        pack_name = archive.packs[archive.pack_of(virtual_base)][0]
        offset = 0
        chunk_index = 0
        while entry_size - offset >= inv.CHUNK_HEADER_SIZE:
            header = archive.read(virtual_base + offset, inv.CHUNK_HEADER_SIZE)
            fourcc = header[:4]
            stored, system_bytes, video_bytes, magic = struct.unpack_from("<4I", header, 4)
            bounded = (inv.printable_fourcc(fourcc) and stored
                       and offset + inv.CHUNK_HEADER_SIZE + stored <= entry_size)
            if not bounded:
                successor = inv.find_after_zero_padding(
                    archive, virtual_base, entry_size, offset)
                if successor is None:
                    break
                offset = successor
                continue
            if fourcc == AUDO:
                _require(magic != inv.COMPRESSED_SENTINEL,
                         "AUDO chunk at entry %d chunk %d is LZ compressed"
                         % (entry_index, chunk_index))
                _require(stored == system_bytes + video_bytes,
                         "AUDO chunk at entry %d chunk %d has a %d-byte tail"
                         % (entry_index, chunk_index,
                            stored - system_bytes - video_bytes))
                body = archive.read(virtual_base + offset + inv.CHUNK_HEADER_SIZE,
                                    system_bytes)
                parsed = parse_audo_body(body, system_bytes, video_bytes)
                parsed.update({
                    "slot_id": slot_id(entry_index, chunk_index),
                    "pack": pack_name,
                    "entry_index": entry_index,
                    "entry_name_id": "0x%08x" % name_id,
                    "chunk_index": chunk_index,
                    "entry_offset": offset,
                    "virtual_offset": virtual_base + offset,
                    "payload_virtual_offset":
                        virtual_base + offset + inv.CHUNK_HEADER_SIZE + system_bytes,
                    "stored_size": stored,
                    "system_bytes": system_bytes,
                    "video_bytes": video_bytes,
                })
                slots.append(parsed)
            offset += inv.CHUNK_HEADER_SIZE + stored
            chunk_index += 1
    return slots


def _mark_unique_names(slots: List[dict]) -> None:
    counts: dict = {}
    for slot in slots:
        key = slot["name"].casefold()
        counts[key] = counts.get(key, 0) + 1
    for slot in slots:
        slot["unique_name"] = counts[slot["name"].casefold()] == 1


def build(iso_path) -> dict:
    """Open a disc read-only and return the catalogue."""
    image = iso.open_image(iso_path)
    identity = iso.boot_identity(image)
    packs = inv.discover_packs(image)
    archive = inv.VirtualPacks(str(iso_path), packs)
    try:
        _outer, entries = inv.read_outer_table(archive)
        slots = walk_audo(archive, entries)
    finally:
        archive.close()
    _require(slots, "no AUDO chunks found; this is not a SLUS-20919 audio layout")
    _mark_unique_names(slots)

    unique = sum(1 for slot in slots if slot["unique_name"])
    stereo = sum(1 for slot in slots if slot["stereo"])
    rates: dict = {}
    for slot in slots:
        rates[str(slot["sample_rate"])] = rates.get(str(slot["sample_rate"]), 0) + 1
    return {
        "schema": SCHEMA,
        "generated_by": "tools/nfl2k5_ps2_audo_target_catalog.py",
        "note": "names, offsets, sizes and descriptor fields only; no payload "
                "hashes and no audio",
        "disc": {
            "serial": identity["serial"],
            "expected_serial": inv.SERIAL,
            "serial_matches": identity["serial"] == inv.SERIAL,
            "boot_file": identity["boot_file"],
            "boot_size": identity["boot_size"],
            "boot_sha256": identity["boot_sha256"],
            "packs": [{"name": name, "size": size} for name, _base, size in packs],
        },
        "totals": {
            "slots": len(slots),
            "expected_slots": EXPECTED_SLOT_COUNT,
            "slots_match_expected": len(slots) == EXPECTED_SLOT_COUNT,
            "unique_names": unique,
            "expected_unique_names": EXPECTED_UNIQUE_NAME_COUNT,
            "distinct_names": len({slot["name"].casefold() for slot in slots}),
            "mono": len(slots) - stereo,
            "stereo": stereo,
            "payload_bytes": sum(slot["video_bytes"] for slot in slots),
            "sample_rates": dict(sorted(rates.items(), key=lambda kv: int(kv[0]))),
            "outer_entries_with_audo": len({slot["entry_index"] for slot in slots}),
        },
        "slots": slots,
    }


def find_slot(catalog: dict, wanted: str) -> dict:
    """Resolve a slot id, or a disc-unique name, to one catalogue row."""
    for slot in catalog["slots"]:
        if slot["slot_id"] == wanted:
            return slot
    matches = [s for s in catalog["slots"] if s["name"].casefold() == wanted.casefold()]
    _require(matches, f"no AUDO slot called {wanted!r}")
    _require(
        len(matches) == 1,
        f"{wanted!r} names {len(matches)} slots; use a slot id such as "
        f"{matches[0]['slot_id']}",
    )
    return matches[0]


def write_report(report: dict, destination) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=False, ensure_ascii=True) + "\n"
    # Bytes, not write_text: text mode would emit CRLF on Windows and the
    # artefact would stop matching everywhere else.
    destination.write_bytes(text.encode("utf-8"))
    return destination


# ------------------------------------------------------------------ selftest


def build_chunk(fourcc: bytes, system: bytes, video: bytes) -> bytes:
    """An uncompressed resource chunk: the 0x20 wrapper, then system + video."""
    header = bytearray(inv.CHUNK_HEADER_SIZE)
    header[0:4] = fourcc
    struct.pack_into("<4I", header, 4, len(system) + len(video),
                     len(system), len(video), 0)
    return bytes(header) + system + video


def build_audo_chunk(name: str, channels: int, rate: int, payload: bytes) -> bytes:
    """A synthetic AUDO chunk shaped exactly like the disc's own."""
    _require(len(payload) % channels == 0, "payload must divide by the channel count")
    encoded = name.encode("utf-16le") + b"\x00\x00"
    field = 0x20 if len(encoded) <= 0x20 else 0x40
    _require(len(encoded) <= field, "name is too long for a 64-byte field")
    filler = ("PADDING*" * 8).encode("utf-16le")
    body = bytearray(0x20 + field + 0x40 * channels)
    body[0x0C:0x10] = AUDO
    struct.pack_into("<2I", body, 0x10, DESCRIPTOR_TYPE,
                     field + 0x20 - DESCRIPTOR_POINTER_BIAS)
    body[0x20:0x20 + len(encoded)] = encoded
    body[0x20 + len(encoded):0x20 + field] = filler[:field - len(encoded)]
    base = 0x20 + field
    struct.pack_into(
        "<8I", body, base, channels, channels, DESCRIPTOR_TYPE,
        FLAGS_STEREO if channels == 2 else FLAGS_MONO,
        len(payload), 0, len(payload) // channels, rate,
    )
    return build_chunk(AUDO, bytes(body), payload)


def build_pack(entries_payload: Sequence[bytes]) -> bytes:
    """One VC outer pack holding *entries_payload*, 0x800-aligned."""
    table_size = inv.OUTER_HEADER_SIZE + len(entries_payload) * inv.OUTER_ENTRY_SIZE
    cursor = (table_size + inv.ALIGNMENT - 1) // inv.ALIGNMENT
    records = []
    for ordinal, payload in enumerate(entries_payload):
        records.append((0x2000_0000 + ordinal, len(payload), cursor))
        cursor += (len(payload) + inv.ALIGNMENT - 1) // inv.ALIGNMENT
    virtual = bytearray(cursor * inv.ALIGNMENT)
    for (_id, size, blocks), payload in zip(records, entries_payload):
        virtual[blocks * inv.ALIGNMENT:blocks * inv.ALIGNMENT + size] = payload
    header = bytearray(inv.OUTER_HEADER_SIZE)
    struct.pack_into("<III", header, 0, len(records), 0, 1)
    struct.pack_into("<I", header, 12, len(virtual) // inv.ALIGNMENT)
    table = b"".join(struct.pack("<III", *record) for record in records)
    return bytes(header) + table + bytes(virtual[len(header) + len(table):])


def build_disc(entries_payload: Sequence[bytes]) -> bytes:
    """A one-pack /VC_20919 disc, boot identity included."""
    return iso.build_synthetic_iso(
        files=[
            (b"SYSTEM.CNF;1", b"BOOT2 = cdrom0:\\SLUS_209.19;1\r\nVER = 1.01\r\n"),
            (b"SLUS_209.19;1", b"\x7fELF" + bytes(2044)),
        ],
        sub_name=b"VC_20919",
        sub_files=[(b"0.;1", build_pack(entries_payload))],
    )


def _synthetic_disc(payload_a: bytes, payload_b: bytes) -> bytes:
    """A one-pack /VC_20919 disc holding three AUDO chunks in two entries."""
    return build_disc([
        build_audo_chunk("selftest_beep", 1, 11025, payload_a)
        + build_audo_chunk("selftest_dupe", 1, 22050, payload_a),
        build_audo_chunk("selftest_dupe", 2, 22050, payload_b),
    ])


def selftest(tmp=None) -> int:
    import tempfile

    failures = 0

    def check(condition: object, label: str) -> None:
        nonlocal failures
        if condition:
            print(f"  ok   {label}")
        else:
            failures += 1
            print(f"  FAIL {label}")

    print("nfl2k5_ps2_audo_target_catalog selftest")
    mono = spu_adpcm.encode([0] * 280)
    stereo = spu_adpcm.encode([0] * 140) + spu_adpcm.encode([0] * 140)
    image = _synthetic_disc(mono, stereo)

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        path = Path(work) / "synthetic.iso"
        path.write_bytes(image)
        catalog = build(path)
        slots = catalog["slots"]
        check(len(slots) == 3, "three AUDO slots found")
        check([s["slot_id"] for s in slots] == [
            "nfl2k5ps2.audio.audo.o0000.c0000",
            "nfl2k5ps2.audio.audo.o0000.c0001",
            "nfl2k5ps2.audio.audo.o0001.c0000",
        ], "slot ids follow (entry, chunk)")
        check([s["name"] for s in slots]
              == ["selftest_beep", "selftest_dupe", "selftest_dupe"],
              "names decode from UTF-16LE")
        check([s["unique_name"] for s in slots] == [True, False, False],
              "duplicate names are marked")
        check(slots[0]["channels"] == 1 and slots[2]["channels"] == 2,
              "channel counts come from the descriptor")
        check(slots[2]["stereo"] and slots[2]["per_channel_bytes"] * 2
              == slots[2]["video_bytes"], "stereo halves the per-channel budget")
        check(slots[0]["max_frames"]
              == spu_adpcm.max_frames_for_bytes(slots[0]["per_channel_bytes"]),
              "max_frames follows the byte budget")
        check(slots[1]["sample_rate"] == 22050, "sample rate comes from the descriptor")
        check(find_slot(catalog, "selftest_beep")["slot_id"] == slots[0]["slot_id"],
              "a unique name resolves")
        check(find_slot(catalog, slots[2]["slot_id"])["channels"] == 2,
              "a slot id resolves")

        for label, call in (
            ("a duplicated name is refused", lambda: find_slot(catalog, "selftest_dupe")),
            ("an unknown name is refused", lambda: find_slot(catalog, "nope")),
        ):
            try:
                call()
            except CatalogError:
                check(True, label)
            else:
                check(False, label)

        written = write_report(catalog, Path(work) / "cat.json")
        raw = written.read_bytes()
        check(b"\r" not in raw, "the report is written LF-only")
        check(json.loads(raw.decode("utf-8"))["schema"] == SCHEMA, "the report reloads")

    print("PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 0 if failures == 0 else 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", type=Path, help="the user's own SLUS-20919 ISO")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                        help="where to write the catalogue")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the walk on a synthetic disc; no game data needed")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return selftest()
    if args.iso is None:
        parser.error("--iso is required (or use --selftest)")

    catalog = build(args.iso)
    destination = write_report(catalog, args.report)
    if not args.quiet:
        totals = catalog["totals"]
        print("AUDO slots: %d (expected %d, %s)"
              % (totals["slots"], totals["expected_slots"],
                 "match" if totals["slots_match_expected"] else "DIVERGES"))
        print("  %d mono, %d stereo, %d with a disc-unique name (expected %d)"
              % (totals["mono"], totals["stereo"], totals["unique_names"],
                 totals["expected_unique_names"]))
        print("  %d payload bytes across %d outer entries"
              % (totals["payload_bytes"], totals["outer_entries_with_audo"]))
        print("  sample rates: %s" % totals["sample_rates"])
        print("wrote %s" % destination)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CatalogError, inv.InventoryError, iso.Iso9660Error, spu_adpcm.SpuAdpcmError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
