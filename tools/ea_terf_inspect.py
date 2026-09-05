#!/usr/bin/env python3
"""Inspect an EA ``TERF`` container -- Madden / NCAA Football PS2 ``/DATA/*.DAT``.

Reads a container either straight out of a disc image by path, so no disc has to
be unpacked to look at one file, or from a loose file already on disk.  It
prints the header, the chunk chain, and a member table carrying each member's
offset, stored size, codec, decompressed size and the **format of its
decompressed bytes** -- which is the only one of those that means anything: a
packed member's stored magic tells you nothing about what it holds, and on the
Madden 09 disc 39 of 107 containers change classification between the two.

Nothing here writes to the image or to the container.  ``--extract`` is the one
command that writes, and only to the file it is given.

Usage::

    ea_terf_inspect.py --iso "Madden NFL 09 (USA).iso" --path /DATA/UNIFORMS.DAT
    ea_terf_inspect.py --file DB_TEAMS.DAT --json
    ea_terf_inspect.py --iso disc.iso --path /DATA/TEMPLATE.DAT --extract 1 --out roster.bin
    ea_terf_inspect.py --selftest        # synthetic containers only; needs no disc

The format itself lives in ``mod_editor/games/_formats/ea_terf.py``; this file is
only a way to point it at bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

from mod_editor.games._formats import ea_terf  # noqa: E402

#: How much of a container this tool will hold in memory without being told to.
#: Madden 09's six speech and music containers run from 124 MB to 415 MB; they
#: are refused by name rather than silently swallowed.
DEFAULT_SIZE_LIMIT = 96 * 1024 * 1024


class InspectError(Exception):
    """A refusal from the command line, printed as one sentence."""


def _load_from_iso(image_path: str, member_path: str,
                   limit: Optional[int]) -> bytes:
    import ps2_iso9660 as iso_lib

    try:
        image = iso_lib.open_image(image_path)
    except (iso_lib.Iso9660Error, OSError, ValueError) as error:
        raise InspectError(str(error).strip() or error.__class__.__name__)
    entry = iso_lib.find(image, member_path)
    if entry is None:
        raise InspectError(
            "%s holds no file at %s. Run ps2_iso9660.py --image %s --list to "
            "see what it does hold." % (image_path, member_path, image_path))
    if entry.is_dir:
        raise InspectError("%s is a directory on %s, not a container."
                           % (member_path, image_path))
    if limit is not None and entry.length > limit:
        raise InspectError(
            "%s is %d byte(s); this tool reads a container into memory and "
            "stops at %d. Pass --allow-large to read it anyway."
            % (member_path, entry.length, limit))
    data = iso_lib.read_file(image, entry)
    # The directory record and the container do not always agree.  Six
    # containers on the community's Madden 09 Deluxe disc are recorded 4 to
    # 26,168 bytes short of what they carry; reading the record's length
    # truncates them and loses every member past the cut.  The bytes are on the
    # disc -- ISO9660 extents are whole sectors -- so read what the container
    # itself declares, straight out of the image.
    try:
        wanted = ea_terf.declared_length(data[:1 << 16])
    except ea_terf.TerfError:
        return data
    if wanted <= len(data):
        return data
    if limit is not None and wanted > limit:
        raise InspectError(
            "%s declares itself %d byte(s) long; this tool stops at %d. Pass "
            "--allow-large to read it anyway." % (member_path, wanted, limit))
    extra = _read_extent(image, entry.lba, wanted)
    if extra is None:
        return data
    print("note: %s is recorded in ISO9660 as %d byte(s) but declares %d; "
          "read the %d the container claims."
          % (member_path, entry.length, wanted, wanted), file=sys.stderr)
    return extra


def _read_extent(image, lba: int, wanted: int) -> Optional[bytes]:
    """*wanted* bytes from the extent at *lba*, sector by sector, or None.

    Goes through the reader's own addressing rather than multiplying by the
    sector size, because a raw-CD image's logical blocks are not contiguous in
    the file.
    """
    import ps2_iso9660 as iso_lib

    out = bytearray()
    try:
        with open(image.path, "rb") as handle:
            block = 0
            while len(out) < wanted:
                handle.seek(iso_lib.extent_byte_offset(image, lba + block, 0))
                chunk = handle.read(min(iso_lib.SECTOR_USER_BYTES,
                                        wanted - len(out)))
                if not chunk:
                    return None
                out += chunk
                block += 1
    except (OSError, ValueError):
        return None
    return bytes(out[:wanted]) if len(out) >= wanted else None


def _load_from_file(path: str, limit: Optional[int]) -> bytes:
    file_path = Path(path).resolve()
    try:
        size = file_path.stat().st_size
    except OSError as error:
        raise InspectError("%s cannot be read: %s." % (file_path, error))
    if limit is not None and size > limit:
        raise InspectError(
            "%s is %d byte(s); this tool reads a container into memory and "
            "stops at %d. Pass --allow-large to read it anyway."
            % (file_path, size, limit))
    return file_path.read_bytes()


def describe(container: ea_terf.TerfContainer, source: str,
             formats: bool = True) -> Dict[str, Any]:
    """Everything the report and the JSON both come from."""
    members: List[Dict[str, Any]] = []
    codec_counts: Dict[str, int] = {}
    format_counts: Dict[str, int] = {}
    for member in container.members:
        record: Dict[str, Any] = {
            "index": member.index,
            "offset": member.offset,
            "stored": member.stored_size,
            "codec": member.codec,
            "codec_name": member.codec_name,
            "decompressed": member.decompressed_size,
        }
        codec_counts[member.codec_name] = codec_counts.get(member.codec_name, 0) + 1
        if formats:
            try:
                name = container.member_format(member.index) or "unclassified"
            except ea_terf.TerfError as error:
                name = "undecodable"
                record["error"] = str(error)
            record["format"] = name
            format_counts[name] = format_counts.get(name, 0) + 1
        members.append(record)
    return {
        "source": source,
        "header_size": container.header_size,
        "version_word": container.version_word.hex(),
        "alignment": container.alignment,
        "member_count": container.member_count,
        "chunks": [{"tag": chunk.tag, "offset": chunk.offset, "size": chunk.size}
                   for chunk in container.chunks],
        "chunk_chain": container.chunk_chain,
        "chunk_kind": "COMP" if container.compressed else "DATA",
        "data_offset": container.data_offset,
        "data_size": container.data_size,
        "layout_violations": container.layout_violations(),
        "codec_counts": codec_counts,
        "format_counts": format_counts,
        "members": members,
    }


def _print_report(report: Dict[str, Any], limit: Optional[int]) -> None:
    print("source          %s" % report["source"])
    print("header          %d bytes, version word %s, member alignment %d"
          % (report["header_size"], report["version_word"], report["alignment"]))
    print("chunk chain     %s" % report["chunk_chain"])
    for chunk in report["chunks"]:
        print("                %-5s off %-10d size %d"
              % (chunk["tag"], chunk["offset"], chunk["size"]))
    print("member data     %s chunk at %d, %d bytes"
          % (report["chunk_kind"], report["data_offset"], report["data_size"]))
    print("members         %d" % report["member_count"])
    print("codecs          %s"
          % ", ".join("%s %d" % (name, count)
                      for name, count in sorted(report["codec_counts"].items())))
    if report["format_counts"]:
        print("formats         %s"
              % ", ".join("%s %d" % (name, count) for name, count
                          in sorted(report["format_counts"].items(),
                                    key=lambda item: -item[1])))
    violations = report["layout_violations"]
    if violations:
        print("layout          %d departure(s) from the measured rules:"
              % len(violations))
        for problem in violations:
            print("                %s" % problem)
    else:
        print("layout          follows the measured rules")
    print()
    print("%5s  %10s  %10s  %-14s %10s  %s"
          % ("index", "offset", "stored", "codec", "unpacked", "format"))
    shown = report["members"] if limit is None else report["members"][:limit]
    for member in shown:
        print("%5d  %10d  %10d  %-14s %10d  %s"
              % (member["index"], member["offset"], member["stored"],
                 member["codec_name"], member["decompressed"],
                 member.get("format", "-")))
    if limit is not None and len(report["members"]) > limit:
        print("... %d more member(s); pass --limit 0 for all"
              % (len(report["members"]) - limit))


def selftest() -> int:
    """Build, rewrite, re-parse.  Synthetic bytes only -- no disc is touched."""
    checks = 0

    def check(condition: object, message: str) -> None:
        nonlocal checks
        if not condition:
            raise AssertionError(message)
        checks += 1

    payloads = [
        b"MMAP" + bytes(range(60)),
        b"",
        b"DB\x00\x08" + b"\x00" * 12 + (3).to_bytes(4, "little") + b"table",
        b"the quick brown fox jumps over the lazy dog, twice over",
    ]
    plain = ea_terf.build_terf(payloads)
    parsed = ea_terf.parse_terf(plain)
    check(parsed.member_count == len(payloads), "built container lost a member")
    check(parsed.chunk_chain == "TERF -> DIR1 -> DATA",
          "plain container should have no COMP chunk")
    check(not parsed.layout_violations(),
          "the writer disagrees with the layout rules the reader checks")
    check([parsed.member(i) for i in range(len(payloads))] == payloads,
          "a member did not survive build -> parse")
    check(parsed.member_format(0) == "MMAP" and parsed.member_format(1) == "empty"
          and parsed.member_format(2) == "TDB" and parsed.member_format(3) == "TEXT",
          "format identification changed")
    checks += 0

    packed = ea_terf.build_terf(
        payloads, chunk="COMP",
        codecs=[ea_terf.CODEC_STORED, ea_terf.CODEC_STORED,
                ea_terf.CODEC_RLE1, ea_terf.CODEC_RLE1])
    repacked = ea_terf.parse_terf(packed)
    check(repacked.chunk_chain == "TERF -> DIR1 -> COMP -> DATA",
          "COMP container should carry a codec table")
    check([repacked.member(i) for i in range(len(payloads))] == payloads,
          "a member did not survive an RLE1 round trip")

    replacement = b"MMAP" + bytes(64)
    rewritten = ea_terf.rewrite_member(plain, 0, replacement)
    after = ea_terf.parse_terf(rewritten)
    check(after.member(0) == replacement, "rewrite did not take")
    check([after.member(i) for i in range(1, len(payloads))] == payloads[1:],
          "rewrite disturbed a member it was not given")
    check(not after.layout_violations(), "rewrite broke the layout rules")

    same_slot = ea_terf.rewrite_member(plain, 3, b"x" * len(payloads[3]))
    check(len(same_slot) == len(plain),
          "a same-size rewrite should not change the file length")
    check(same_slot[:parsed.data_offset] == plain[:parsed.data_offset],
          "a same-size rewrite should not change the header or the tables")

    refused = 0
    for call, why in (
        (lambda: ea_terf.parse_terf(b"NOPE" + bytes(60)), "a non-TERF file"),
        (lambda: ea_terf.rewrite_member(plain, 99, b"x"), "a member index that does not exist"),
        (lambda: ea_terf.build_terf([b"x"], chunk="DATA", codecs=[0]), "codecs on a DATA container"),
        (lambda: ea_terf.build_terf([b"x"], chunk="COMP", codecs=[ea_terf.CODEC_LZH1]), "an LZH1 write"),
        (lambda: ea_terf.lzh1_decompress(b"\x00\x00"), "a truncated LZH1 stream"),
        (lambda: ea_terf.rle1_decompress(b"!\x41", 8), "a truncated RLE1 stream"),
        (lambda: ea_terf.parse_mmap_header(b"SMF\x00" + bytes(60)), "a non-MMAP member"),
    ):
        try:
            call()
        except (ea_terf.TerfError, AssertionError):
            refused += 1
        else:
            raise AssertionError("%s was not refused" % why)
    check(refused == 7, "a refusal went missing")

    digest = hashlib.sha256(plain).hexdigest()[:16]
    print("EA_TERF_SELFTEST_PASS checks=%d members=%d refusals=%d "
          "chunks=DATA+COMP codecs=stored+RLE1 digest=%s"
          % (checks, len(payloads), refused, digest))
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect an EA TERF container (Madden / NCAA PS2 .DAT).")
    parser.add_argument("--iso", metavar="IMAGE",
                        help="read the container out of this PS2 disc image")
    parser.add_argument("--path", metavar="/DATA/FILE.DAT",
                        help="path of the container inside --iso")
    parser.add_argument("--file", metavar="FILE",
                        help="read a container already on disk")
    parser.add_argument("--extract", metavar="N", type=int,
                        help="write member N, decompressed, to --out")
    parser.add_argument("--out", metavar="FILE", help="where --extract writes")
    parser.add_argument("--limit", metavar="N", type=int, default=40,
                        help="member table rows to print; 0 for all "
                             "(default: 40)")
    parser.add_argument("--no-formats", action="store_true",
                        help="skip decompression; print the tables only")
    parser.add_argument("--allow-large", action="store_true",
                        help="read a container past the %d-byte limit"
                             % DEFAULT_SIZE_LIMIT)
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON")
    parser.add_argument("--selftest", action="store_true",
                        help="run the synthetic self-test and exit")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    limit = None if args.allow_large else DEFAULT_SIZE_LIMIT
    try:
        if args.iso:
            if not args.path:
                raise InspectError(
                    "--iso needs --path naming the container inside the image, "
                    "for example --path /DATA/UNIFORMS.DAT.")
            source = "%s!%s" % (args.iso, args.path)
            data = _load_from_iso(args.iso, args.path, limit)
        elif args.file:
            source = args.file
            data = _load_from_file(args.file, limit)
        else:
            raise InspectError(
                "nothing to inspect: pass --iso IMAGE --path /DATA/FILE.DAT, "
                "or --file FILE, or --selftest.")
        container = ea_terf.parse_terf(data)
        if args.extract is not None:
            if not args.out:
                raise InspectError("--extract needs --out naming the file to "
                                   "write the member to.")
            payload = container.member(args.extract)
            destination = Path(args.out).resolve()
            destination.write_bytes(payload)
            print("wrote %s: member %d of %s, %d byte(s), format %s, sha256 %s"
                  % (destination, args.extract, source, len(payload),
                     ea_terf.identify_member(payload) or "unclassified",
                     hashlib.sha256(payload).hexdigest()))
            return 0
        report = describe(container, source, formats=not args.no_formats)
        if args.json:
            print(json.dumps(report, indent=1))
        else:
            _print_report(report, None if args.limit == 0 else args.limit)
        return 0
    except (InspectError, ea_terf.TerfError) as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
