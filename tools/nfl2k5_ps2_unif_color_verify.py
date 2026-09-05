#!/usr/bin/env python3
"""Independently verify a PS2 NFL 2K5 uniform-colour write.

This is the evidence behind ``nfl2k5_ps2_unif_color_patch.py``.  Given the stock
image, the written image and the writer's receipt, it re-derives from the bytes
alone that

  1. the two images are the same size and the bounded ISO9660 replacement holds
     (delegated to ``ps2_iso9660_verify``, itself an independent decoder);
  2. **across every replaced pack extent the two images differ only inside the
     declared eight-byte colour spans** -- a stricter claim than the ISO
     verifier makes, because it compares against the *source*, not against the
     writer's own staged content;
  3. each declared span holds exactly the colours the receipt claims, and held
     exactly the retail digest the receipt claims before;
  4. every ``Unif`` resource in the written image still decodes -- chunk tag,
     80-byte body, object tag, ``uniform`` name, descriptor pointer landing on
     the colour pair -- and there are as many of them as the source has.

**It imports neither the patcher nor the ISO writer's parser.**  A verifier
that reuses the writer's decoder cannot see a bug in that decoder: both sides
would compute the same wrong offset and agree with each other.  So the archive
and resource layout below is restated here rather than imported, and the
receipt is an input to be checked, never evidence.

The self-test uses the patcher only to *manufacture* a fixture -- the shipped
discipline of ``ps2_iso9660_verify`` and ``nfl2k5_ps2_save_verify`` -- while
every assertion still runs through this module's own decode.

Usage::

    nfl2k5_ps2_unif_color_verify.py --source <stock.iso> --destination <new.iso> \\
        --receipt <receipt.json> [--report <verdict.json>]
    nfl2k5_ps2_unif_color_verify.py --selftest

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import ps2_iso9660_verify as iso_verify  # noqa: E402  (independent ISO decoder)


SCHEMA = "nfl2k5_ps2_unif_color_verify/v1"
WRITE_SCHEMA = "nfl2k5_ps2_unif_color_write/v1"
SERIAL = "SLUS-20919"

# Container constants, restated rather than imported; see the module docstring.
_PACK_DIRECTORY = "/VC_20919"
_PACK_NAMES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ALIGNMENT = 0x800
_PACK_SLOTS = 36
_OUTER_HEADER = 0x0C + _PACK_SLOTS * 4
_OUTER_ENTRY = 12
_CHUNK_HEADER = 0x20
_LZ_SENTINEL = 0xFEEDBEEF
_UNIF = b"Unif"
_UNIF_BODY = 80
_OBJ_FOURCC = 0x0C
_OBJ_NAME_PTR = 0x10
_OBJ_DESC_PTR = 0x14
_OBJ_NAME = "uniform"
_SPAN = 8
_COMPARE_CHUNK = 8 * 1024 * 1024
_MAX_ENTRIES = 1 << 20


class ColorVerifyError(AssertionError):
    """A written image did not hold what the receipt claimed about it."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ColorVerifyError(message)


def _read(handle, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    _require(len(data) == size,
             "short read of %d bytes at %d" % (size, offset))
    return data


def _relative_pointer(data: bytes, field: int) -> Optional[int]:
    value = struct.unpack_from("<i", data, field)[0]
    return None if value == 0 else field + value - 1


# --------------------------------------------------------------------------
# Independent archive decode
# --------------------------------------------------------------------------

def _pack_ordinal(iso_path: str) -> Optional[int]:
    """The archive ordinal of ``/VC_20919/<letter>[.]``, or None if not a pack.

    ``/VC_20919`` also holds a ``DATA/`` subtree of IOP modules and network
    assets; only the single-character resource packs make up the virtual
    archive, and their order is the order of ``_PACK_NAMES``, not disc order.
    """
    upper = iso_path.upper()
    if not upper.startswith(_PACK_DIRECTORY + "/"):
        return None
    leaf = upper[len(_PACK_DIRECTORY) + 1:]
    if leaf.endswith("."):
        leaf = leaf[:-1]
    if len(leaf) != 1 or leaf not in _PACK_NAMES:
        return None
    return _PACK_NAMES.index(leaf)


def pack_extents(path: Path) -> List[Tuple[str, int, int]]:
    """``[(iso_path, byte_offset, length)]`` for the resource packs, in order."""
    descriptor, volume = iso_verify.open_volume(path)
    try:
        entries = iso_verify.walk(descriptor, volume)
    finally:
        import os
        os.close(descriptor)
    found = []
    for entry in entries:
        if entry.is_dir:
            continue
        normalized = iso_verify.normalize_path(entry.path)
        ordinal = _pack_ordinal(normalized)
        if ordinal is None:
            continue
        found.append((ordinal, normalized,
                      entry.lba * volume.sector_size + volume.data_offset,
                      entry.length))
    _require(found, "%s carries no %s resource packs" % (path, _PACK_DIRECTORY))
    found.sort()
    _require([row[0] for row in found] == list(range(len(found))),
             "the %s resource packs are not a contiguous run from 0"
             % _PACK_DIRECTORY)
    return [(name, base, length) for _ordinal, name, base, length in found]


def unif_records(path: Path) -> List[Dict[str, Any]]:
    """Every decodable ``Unif`` resource in an image, by its own walk."""
    packs = pack_extents(path)
    starts = [0]
    for _name, _base, length in packs:
        starts.append(starts[-1] + length)

    def read_virtual(handle, offset: int, size: int) -> bytes:
        parts = []
        while size:
            index = max(i for i in range(len(packs)) if starts[i] <= offset)
            inside = offset - starts[index]
            take = min(size, packs[index][2] - inside)
            _require(take > 0, "virtual read fell off the archive at %d" % offset)
            parts.append(_read(handle, packs[index][1] + inside, take))
            offset += take
            size -= take
        return b"".join(parts)

    records = []  # type: List[Dict[str, Any]]
    with open(str(path), "rb") as handle:
        header = read_virtual(handle, 0, _OUTER_HEADER)
        entry_count, _reserved, populated = struct.unpack_from("<III", header, 0)
        _require(populated == len(packs),
                 "the outer index declares %d packs, the image has %d"
                 % (populated, len(packs)))
        _require(0 < entry_count <= _MAX_ENTRIES,
                 "the outer index declares %d entries" % entry_count)
        table = read_virtual(handle, _OUTER_HEADER, entry_count * _OUTER_ENTRY)
        for index in range(entry_count):
            name_id, size, blocks = struct.unpack_from(
                "<III", table, index * _OUTER_ENTRY)
            if size < _CHUNK_HEADER + _UNIF_BODY:
                continue
            virtual = blocks * _ALIGNMENT
            if virtual + _CHUNK_HEADER + _UNIF_BODY > starts[-1]:
                continue
            head = read_virtual(handle, virtual, _CHUNK_HEADER)
            if head[:4] != _UNIF:
                continue
            stored, _system, _video, sentinel = struct.unpack_from("<4I", head, 4)
            if sentinel == _LZ_SENTINEL:
                # A compressed body is never a writable target; record it so the
                # two images can still be compared record for record, and refuse
                # later if the receipt claims to have written into one.
                records.append({
                    "outer_index": index,
                    "outer_name_id": "0x%08x" % name_id,
                    "colour_offset_in_iso": None,
                    "colour_offset_in_chunk": None,
                    "compressed": True,
                    "span": None,
                })
                continue
            _require(stored == _UNIF_BODY,
                     "outer %d: Unif body is %d bytes, expected %d"
                     % (index, stored, _UNIF_BODY))
            body = read_virtual(handle, virtual + _CHUNK_HEADER, stored)
            _require(body[_OBJ_FOURCC:_OBJ_FOURCC + 4] == _UNIF,
                     "outer %d: the Unif object tag is gone" % index)
            name_at = _relative_pointer(body, _OBJ_NAME_PTR)
            descriptor = _relative_pointer(body, _OBJ_DESC_PTR)
            _require(name_at is not None and descriptor is not None,
                     "outer %d: a Unif pointer went null" % index)
            end = name_at
            while end + 2 <= len(body) and body[end:end + 2] != b"\x00\x00":
                end += 2
            _require(body[name_at:end].decode("utf-16le", "replace") == _OBJ_NAME,
                     "outer %d: the Unif object name is not %r" % (index, _OBJ_NAME))
            _require(descriptor + _SPAN <= len(body),
                     "outer %d: the descriptor leaves no room for the colour pair"
                     % index)
            absolute = None
            for ordinal, (_name, base, length) in enumerate(packs):
                inside = virtual + _CHUNK_HEADER + descriptor - starts[ordinal]
                if 0 <= inside and inside + _SPAN <= length:
                    absolute = base + inside
                    break
            _require(absolute is not None,
                     "outer %d: the colour span straddles a pack boundary" % index)
            records.append({
                "outer_index": index,
                "outer_name_id": "0x%08x" % name_id,
                "colour_offset_in_iso": absolute,
                "colour_offset_in_chunk": _CHUNK_HEADER + descriptor,
                "compressed": False,
                "span": body[descriptor:descriptor + _SPAN],
            })
    return records


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

def _declared_by_file(receipt: Dict[str, Any],
                      packs: Sequence[Tuple[str, int, int]]) -> Dict[str, List[Tuple[int, int]]]:
    """Group the receipt's declared image ranges by the pack extent holding them."""
    grouped = {}  # type: Dict[str, List[Tuple[int, int]]]
    for row in receipt.get("declared_ranges", []):
        start = int(row["start"])
        length = int(row["length"])
        _require(length == _SPAN,
                 "a declared colour range is %d bytes, expected %d" % (length, _SPAN))
        owner = None
        for name, base, extent in packs:
            if base <= start and start + length <= base + extent:
                owner = name
                break
        _require(owner is not None,
                 "the declared range at %d lies outside every %s pack"
                 % (start, _PACK_DIRECTORY))
        grouped.setdefault(owner, []).append((start, length))
    for ranges in grouped.values():
        ranges.sort()
        for left, right in zip(ranges, ranges[1:]):
            _require(left[0] + left[1] <= right[0],
                     "two declared ranges overlap at %d" % right[0])
    return grouped


def _compare_extent(source, destination, base: int, length: int,
                    allowed: Sequence[Tuple[int, int]]) -> int:
    """Bytes compared outside ``allowed``; raises on the first stray difference."""
    cuts = [0]
    for start, size in allowed:
        cuts.append(start - base)
        cuts.append(start - base + size)
    cuts.append(length)
    compared = 0
    for index in range(0, len(cuts) - 1, 2):
        begin, end = cuts[index], cuts[index + 1]
        _require(0 <= begin <= end <= length,
                 "a declared range is not inside the extent it claims")
        position = begin
        while position < end:
            take = min(_COMPARE_CHUNK, end - position)
            left = _read(source, base + position, take)
            right = _read(destination, base + position, take)
            if left != right:
                bad = next(i for i, pair in enumerate(zip(left, right))
                           if pair[0] != pair[1])
                raise ColorVerifyError(
                    "byte 0x%x changed outside every declared colour span; the "
                    "write did not stay in its lane" % (base + position + bad))
            compared += take
            position += take
    return compared


def verify(source, destination, receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Check one written image against its receipt.  Raises on any violation."""
    source = Path(source)
    destination = Path(destination)
    _require(receipt.get("schema") == WRITE_SCHEMA,
             "receipt schema is %r, expected %r"
             % (receipt.get("schema"), WRITE_SCHEMA))
    edits = receipt.get("edits") or []
    _require(edits, "the receipt declares no edits")

    iso_report = receipt.get("iso_write_report")
    _require(isinstance(iso_report, dict),
             "the receipt carries no ISO write report to check")

    packs = pack_extents(destination)
    source_packs = pack_extents(source)
    _require([row[0] for row in packs] == [row[0] for row in source_packs]
             and [row[1:] for row in packs] == [row[1:] for row in source_packs],
             "the pack extents moved between the two images")

    grouped = _declared_by_file(receipt, packs)
    replaced = set(receipt.get("files_replaced") or [])
    _require(replaced, "the receipt names no replaced file")
    for name in grouped:
        _require(name.upper() in {item.upper() for item in replaced},
                 "%s carries declared ranges but is not a replaced file" % name)

    compared = 0
    with open(str(source), "rb") as left, open(str(destination), "rb") as right:
        for name, base, length in packs:
            if name.upper() not in {item.upper() for item in replaced}:
                continue
            compared += _compare_extent(left, right, base, length,
                                        grouped.get(name, []))

        for edit in edits:
            offset = int(edit["offset_in_iso"])
            size = int(edit["span_size"])
            _require(size == _SPAN,
                     "%s declares a %d-byte span, expected %d"
                     % (edit.get("selector"), size, _SPAN))
            before = _read(left, offset, size)
            after = _read(right, offset, size)
            _require(hashlib.sha256(before).hexdigest() == edit["before_sha256"],
                     "%s: the stock image does not hold the retail span the "
                     "receipt recorded" % edit.get("selector"))
            _require(hashlib.sha256(after).hexdigest() == edit["after_sha256"],
                     "%s: the written image does not hold the span the receipt "
                     "recorded" % edit.get("selector"))
            _require(before != after,
                     "%s: the declared span did not change" % edit.get("selector"))
            changed = [name for index, name in enumerate(("facemask", "turtleneck"))
                       if before[index * 4:index * 4 + 4]
                       != after[index * 4:index * 4 + 4]]
            _require(set(changed) <= set(edit.get("words_changed") or []),
                     "%s: word(s) %s changed but the receipt claims %s"
                     % (edit.get("selector"), changed, edit.get("words_changed")))

    written = unif_records(destination)
    stock = unif_records(source)
    _require(len(written) == len(stock),
             "the written image decodes %d Unif records, the stock image %d"
             % (len(written), len(stock)))
    _require([row["outer_index"] for row in written]
             == [row["outer_index"] for row in stock]
             and [row["compressed"] for row in written]
             == [row["compressed"] for row in stock],
             "the Unif record set changed shape between the two images")
    by_offset = {row["colour_offset_in_iso"]: row for row in written
                 if not row["compressed"]}
    for edit in edits:
        record = by_offset.get(int(edit["offset_in_iso"]))
        _require(record is not None,
                 "%s: no decodable Unif record in the written image owns the "
                 "declared span" % edit.get("selector"))
        _require(record["outer_index"] == int(edit["outer_index"]),
                 "%s: the declared span belongs to outer %d, not %d"
                 % (edit.get("selector"), record["outer_index"],
                    int(edit["outer_index"])))

    # The bounded-replacement check runs last so that this module's own,
    # narrower findings name the offending byte first; its failures are
    # re-raised in this module's type so a caller has one surface to catch.
    try:
        iso_result = iso_verify.verify_replacement(source, destination, iso_report)
    except iso_verify.IsoVerifyError as exc:
        raise ColorVerifyError("the bounded ISO replacement did not verify: %s"
                               % exc)
    _require(iso_result.get("result") == "PASS",
             "the bounded ISO replacement did not verify: %r" % (iso_result,))

    return {
        "schema": SCHEMA,
        "result": "PASS",
        "serial": SERIAL,
        "source": str(source),
        "destination": str(destination),
        "edits_checked": len(edits),
        "unif_records_decoded": len(written),
        "files_replaced": sorted(replaced),
        "unchanged_bytes_compared": compared,
        "iso_verify": {key: iso_result[key] for key in sorted(iso_result)
                       if key in ("result", "unchanged_bytes_compared",
                                  "declared_bytes", "entry_count")},
    }


def write_json(path: Path, document: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    with open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

def selftest(tmp: Optional[str] = None) -> int:
    """Accept a correct write; reject the ways it can rot.  Needs no game data."""
    import tempfile

    if _HERE not in sys.path:  # pragma: no cover
        sys.path.insert(0, _HERE)
    import nfl2k5_ps2_unif_color_patch as writer          # fixture generator only
    import nfl2k5_ps2_unif_color_target_catalog as fixture  # fixture generator only

    failures = []  # type: List[str]

    def check(condition: object, message: str) -> None:
        if not condition:
            failures.append(message)

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        room = Path(work)
        source = room / "stock.iso"
        source.write_bytes(fixture.build_synthetic_iso())
        recipe = writer.parse_recipe({"schema": writer.RECIPE_SCHEMA, "edits": [
            {"selector": "18H0", "facemask": "#00FF00"},
            {"selector": "18A0", "turtleneck": "FF010203"},
        ]})
        good = room / "edited.iso"
        receipt = writer.apply(source, good, recipe)

        report = verify(source, good, receipt)
        check(report["result"] == "PASS", "a correct write must verify")
        check(report["edits_checked"] == 2, "both edits must be checked")
        check(report["unif_records_decoded"] == 3,
              "all three Unif records must be accounted for")
        check(report["unchanged_bytes_compared"] > 0,
              "the out-of-lane comparison must read something")

        # A JSON round trip must verify identically.
        verify(source, good, json.loads(json.dumps(receipt)))

        def rejected(name: str, mutate, why: str, override=None) -> None:
            candidate = room / name
            candidate.write_bytes(good.read_bytes())
            mutate(candidate)
            try:
                verify(source, candidate, override or receipt)
            except (ColorVerifyError, iso_verify.IsoVerifyError):
                return
            failures.append("%s must fail verification" % why)

        target = fixture.find_target(fixture.build_catalog(str(source)), "18H0")

        def poke(path: Path, offset: int, value: bytes) -> None:
            with open(str(path), "r+b") as handle:
                handle.seek(offset)
                handle.write(value)

        # One byte outside every declared span, but inside a replaced extent.
        stray = target["colour_offset_in_iso"] + 0x40
        rejected("stray.iso", lambda path: poke(path, stray, b"\xa5"),
                 "a byte changed outside every declared span")
        # A declared span rewritten to something the receipt does not claim.
        rejected("forged.iso",
                 lambda path: poke(path, target["colour_offset_in_iso"],
                                   b"\x01\x02\x03\x04"),
                 "a declared span that disagrees with the receipt")
        # The Unif object tag destroyed inside its own record.
        rejected("broken.iso",
                 lambda path: poke(path, target["colour_offset_in_iso"]
                                   - fixture.XBOX_COLOUR_OFFSET
                                   + fixture.XBOX_RECORD_TAG_OFFSET, b"XXXX"),
                 "a written image whose Unif object no longer decodes")

        forged_receipt = json.loads(json.dumps(receipt))
        forged_receipt["edits"][0]["before_sha256"] = "0" * 64
        try:
            verify(source, good, forged_receipt)
        except ColorVerifyError:
            pass
        else:
            failures.append("a receipt lying about the retail span must fail")

        forged_receipt = json.loads(json.dumps(receipt))
        forged_receipt["declared_ranges"] = []
        try:
            verify(source, good, forged_receipt)
        except ColorVerifyError:
            pass
        else:
            failures.append("dropping the declared ranges must fail")

        forged_receipt = json.loads(json.dumps(receipt))
        forged_receipt["schema"] = "nope"
        try:
            verify(source, good, forged_receipt)
        except ColorVerifyError:
            pass
        else:
            failures.append("a receipt with the wrong schema must fail")

    for failure in failures:
        print("FAIL: %s" % failure, file=sys.stderr)
    if failures:
        return 1
    print("NFL2K5_PS2_UNIF_COLOR_VERIFY_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--report", type=Path, help="write the verdict here")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--tmp", help="directory for self-test scratch files")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest(args.tmp)
    if not (args.source and args.destination and args.receipt):
        parser.error("--source, --destination and --receipt are required")

    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        report = verify(args.source, args.destination, receipt)
    except (ColorVerifyError, iso_verify.IsoVerifyError, OSError, ValueError) as exc:
        print("NFL2K5_PS2_UNIF_COLOR_VERIFY_FAIL %s" % exc, file=sys.stderr)
        return 1

    if args.report:
        write_json(args.report, report)
    print("NFL2K5_PS2_UNIF_COLOR_VERIFY_PASS edits=%d unif_records=%d "
          "unchanged_bytes=%d"
          % (report["edits_checked"], report["unif_records_decoded"],
             report["unchanged_bytes_compared"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
