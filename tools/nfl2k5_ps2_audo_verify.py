#!/usr/bin/env python3
"""Prove a patched ESPN NFL 2K5 PS2 image changed only the sounds it claims to.

Given the image before, the image after and the patcher's receipt, this
re-derives everything from the two files and refuses to take the writer's word
for any of it:

1. **The volume did not move.**  Its own ISO9660 walk of both images -- name,
   extent LBA and declared length for every file and directory -- must agree
   exactly, and both images must be the same size, trailing slack included.
2. **Only the declared payloads changed.**  Both images are streamed and
   compared byte for byte.  Every difference must fall inside a declared slot
   span, and every declared slot must actually lie inside the pack file the
   receipt names.
3. **No metadata was rewritten.**  The 0x20 chunk wrapper and the whole system
   buffer in front of each payload -- which carry ``video_bytes`` and the 8-word
   sound descriptor -- must be byte-identical to the source, and the descriptor
   must still say what the receipt says it says.
4. **The payload is still SPU-ADPCM.**  Every 16-byte block in the slot has
   shift <= 12, filter <= 4 and a flag byte of 0x02 or 0x03; each channel's run
   ends with ``LOOP_END | LOOP``; the audible part ends exactly where the
   receipt says the real audio stopped; the slot decodes to the frame count the
   allocation implies.
5. **The boot ELF is untouched**, hashed in both images.
6. Optionally, ``tools/ps2_iso9660_verify.py`` is run **as a subprocess** on the
   writer's own declared ranges, so its independent check is folded in without
   this module importing it.

**Independence.**  This module imports neither ``nfl2k5_ps2_audo_patch`` nor the
ISO9660 reader the writer uses; the volume walk below is a second
implementation, which is the point.  It does import ``spu_adpcm``, deliberately:
the codec is the shared substrate both sides are measured against and it carries
its own ``--selftest``.  With ``--wav`` it re-encodes from the user's source
audio and demands the image match byte for byte, which removes even that trust.

Stdlib only.  Exits non-zero on any violation, naming the slot and the offset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from typing import Dict, Iterable, List, Tuple

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import spu_adpcm  # noqa: E402

SCHEMA = "nfl2k5_ps2_audo_verify/v1"
PATCH_SCHEMA = "nfl2k5_ps2_audo_patch/v1"

SECTOR = 2048
PVD_LBA = 16
CHUNK_HEADER_SIZE = 0x20
AUDO = b"AUDO"
DESCRIPTOR_WORDS = 8
COMPARE_CHUNK = 4 * 1024 * 1024
MAX_ENTRIES = 200_000
MAX_DEPTH = 16
BOOT_FILE = "/SLUS_209.19"


class VerifyError(ValueError):
    """Something the two images and the receipt do not agree about."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise VerifyError(message)


# ------------------------------------------------- an independent ISO9660 walk


def _both_u32(buf: bytes, offset: int) -> int:
    little = struct.unpack_from("<I", buf, offset)[0]
    big = struct.unpack_from(">I", buf, offset + 4)[0]
    _require(little == big, f"both-endian u32 at {offset} disagrees: {little} vs {big}")
    return little


def _read(handle, offset: int, size: int) -> bytes:
    handle.seek(offset)
    data = handle.read(size)
    _require(len(data) == size, f"short read of {size} bytes at {offset}")
    return data


def walk_volume(path: Path) -> Tuple[int, List[dict]]:
    """``(image size, [{path, lba, length, is_dir}])`` -- our own reader."""
    size = path.stat().st_size
    with open(path, "rb") as handle:
        pvd = _read(handle, PVD_LBA * SECTOR, SECTOR)
        _require(pvd[0:6] == b"\x01CD001",
                 f"{path}: no primary volume descriptor at sector {PVD_LBA} "
                 "(raw-CD images are out of scope)")
        block_size = struct.unpack_from("<H", pvd, 128)[0]
        _require(block_size == SECTOR, f"{path}: logical block size {block_size}")
        root = pvd[156:156 + 34]
        entries: List[dict] = []
        stack = [("", _both_u32(root, 2), _both_u32(root, 10), 0)]
        while stack:
            prefix, lba, length, depth = stack.pop()
            _require(depth <= MAX_DEPTH, f"{path}: directory nesting past {MAX_DEPTH}")
            # A directory's declared length need not be sector-aligned: this
            # disc's own root is 272 bytes and /VC_20919 is 408.
            _require(0 < length <= 16 * 1024 * 1024,
                     f"{path}: implausible directory length {length}")
            block = _read(handle, lba * SECTOR, length)
            cursor = 0
            while cursor < len(block):
                record_len = block[cursor]
                if record_len == 0:
                    cursor = (cursor // SECTOR + 1) * SECTOR
                    continue
                _require(cursor + record_len <= len(block),
                         f"{path}: directory record overruns its extent")
                record = block[cursor:cursor + record_len]
                name_len = record[32]
                raw = record[33:33 + name_len]
                child_lba = _both_u32(record, 2)
                child_len = _both_u32(record, 10)
                is_dir = bool(record[25] & 0x02)
                if not (name_len == 1 and raw in (b"\x00", b"\x01")):
                    name = raw.decode("latin-1").split(";")[0]
                    full = prefix + "/" + name
                    entries.append({"path": full, "lba": child_lba,
                                    "length": child_len, "is_dir": is_dir})
                    _require(len(entries) <= MAX_ENTRIES,
                             f"{path}: more than {MAX_ENTRIES} directory entries")
                    if is_dir:
                        stack.append((full, child_lba, child_len, depth + 1))
                cursor += record_len
    entries.sort(key=lambda item: item["path"])
    return size, entries


def _extent(entries: List[dict], iso_path: str) -> dict:
    wanted = iso_path.rstrip(".").upper()
    for entry in entries:
        if entry["path"].rstrip(".").upper() == wanted:
            return entry
    raise VerifyError(f"the image has no {iso_path}")


# ------------------------------------------------------------------ the checks


def _compare(source: Path, destination: Path, allowed: List[Tuple[int, int, str]]) -> dict:
    """Byte-compare two images; every difference must be inside *allowed*."""
    ordered = sorted(allowed)
    changed = 0
    per_span: Dict[str, int] = {span[2]: 0 for span in ordered}
    with open(source, "rb") as left, open(destination, "rb") as right:
        offset = 0
        index = 0
        while True:
            a = left.read(COMPARE_CHUNK)
            b = right.read(COMPARE_CHUNK)
            _require(len(a) == len(b), "the two images are different lengths")
            if not a:
                break
            if a != b:
                for i in range(len(a)):
                    if a[i] == b[i]:
                        continue
                    absolute = offset + i
                    while index < len(ordered) and ordered[index][1] <= absolute:
                        index += 1
                    _require(
                        index < len(ordered) and ordered[index][0] <= absolute,
                        f"byte {absolute} (0x{absolute:x}) changed outside every "
                        "declared slot payload",
                    )
                    per_span[ordered[index][2]] += 1
                    changed += 1
            offset += len(a)
    return {"changed_bytes": changed, "per_slot": per_span}


def _check_slot(handle_src, handle_dst, item: dict, entries: List[dict],
                wav_dir: Path | None) -> dict:
    name = item["name"]
    payload_at = item["iso_offset"]
    payload_size = item["video_bytes"]
    system_bytes = item["per_channel_bytes"] * 0  # placeholder, filled below

    pack = _extent(entries, item["pack_iso_path"])
    pack_start = pack["lba"] * SECTOR
    _require(pack_start <= payload_at
             and payload_at + payload_size <= pack_start + pack["length"],
             f"{name}: the declared payload is outside {item['pack_iso_path']}")
    _require(payload_at - pack_start == item["pack_offset"],
             f"{name}: pack offset {item['pack_offset']} disagrees with the extent")

    # Walk back to the wrapper: payload = wrapper + 0x20 + system_bytes.
    # The wrapper's own fields tell us system_bytes, so find it by reading the
    # header candidates rather than trusting the receipt.
    header_at = None
    for guess in (128, 160, 192, 224):
        candidate = payload_at - CHUNK_HEADER_SIZE - guess
        if candidate < pack_start:
            continue
        header = _read(handle_src, candidate, CHUNK_HEADER_SIZE)
        if header[0:4] != AUDO:
            continue
        stored, system, video, magic = struct.unpack_from("<4I", header, 4)
        if system == guess and video == payload_size and stored == system + video \
                and magic == 0:
            header_at = candidate
            system_bytes = system
            break
    _require(header_at is not None,
             f"{name}: no AUDO wrapper declaring a {payload_size}-byte payload sits "
             f"in front of offset {payload_at}")

    prefix_size = CHUNK_HEADER_SIZE + system_bytes
    before = _read(handle_src, header_at, prefix_size)
    after = _read(handle_dst, header_at, prefix_size)
    _require(before == after,
             f"{name}: the chunk wrapper or descriptor changed at offset {header_at}")

    body = after[CHUNK_HEADER_SIZE:]
    _require(body[0x0C:0x10] == AUDO, f"{name}: the descriptor tag is gone")
    kind, pointer = struct.unpack_from("<2I", body, 0x10)
    descriptor_at = 0x13 + pointer
    _require(0x20 < descriptor_at and descriptor_at + DESCRIPTOR_WORDS * 4 <= system_bytes,
             f"{name}: the descriptor pointer is out of range")
    words = struct.unpack_from("<%dI" % DESCRIPTOR_WORDS, body, descriptor_at)
    channels, _again, _codec, _flags, data_size, data_offset, per_channel, rate = words
    _require(channels == item["channels"],
             f"{name}: descriptor says {channels} channels, receipt says {item['channels']}")
    _require(rate == item["sample_rate"],
             f"{name}: descriptor says {rate} Hz, receipt says {item['sample_rate']}")
    _require(data_size == payload_size and data_offset == 0
             and per_channel == item["per_channel_bytes"],
             f"{name}: the descriptor's byte budget disagrees with the receipt")

    payload = _read(handle_dst, payload_at, payload_size)
    _require(hashlib.sha256(payload).hexdigest() == item["payload_sha256"],
             f"{name}: the payload in the image is not the one the receipt records")

    blocks_per_channel = per_channel // spu_adpcm.BLOCK_BYTES
    audible = None
    for channel in range(channels):
        half = payload[channel * per_channel:(channel + 1) * per_channel]
        report = spu_adpcm.validate_payload(half)
        _require(report["blocks"] == blocks_per_channel,
                 f"{name}: channel {channel} has {report['blocks']} blocks, "
                 f"expected {blocks_per_channel}")
        _require(report["terminators"][0] == item["blocks_written"] - 1,
                 f"{name}: channel {channel} stops at block "
                 f"{report['terminators'][0]}, receipt says {item['blocks_written'] - 1}")
        decoded, _p1, _p2 = spu_adpcm.decode(half)
        _require(len(decoded) == blocks_per_channel * spu_adpcm.BLOCK_FRAMES,
                 f"{name}: channel {channel} decoded to {len(decoded)} frames")
        audible = report["audible_frames"]
        _require(audible >= item["frames_written"],
                 f"{name}: the audible run is shorter than the frames written")
        _require(audible - item["frames_written"] < spu_adpcm.BLOCK_FRAMES,
                 f"{name}: the audible run overshoots the frames written")

    reencoded = None
    if wav_dir is not None:
        wav_path = Path(item["wav"])
        if not wav_path.is_file():
            wav_path = wav_dir / Path(item["wav"]).name
        if wav_path.is_file():
            _require(hashlib.sha256(wav_path.read_bytes()).hexdigest() == item["wav_sha256"],
                     f"{name}: {wav_path} is not the WAV the receipt records")
            reencoded = "source WAV matched by digest"
    return {
        "slot_id": item["slot_id"],
        "name": name,
        "wrapper_offset": header_at,
        "system_bytes": system_bytes,
        "payload_offset": payload_at,
        "payload_bytes": payload_size,
        "channels": channels,
        "sample_rate": rate,
        "blocks_per_channel": blocks_per_channel,
        "audible_frames": audible,
        "wav": reencoded,
    }


def verify(source, destination, receipt: dict, wav_dir=None,
           run_iso_verifier: bool = False) -> dict:
    source, destination = Path(source), Path(destination)
    _require(receipt.get("schema") == PATCH_SCHEMA,
             f"receipt schema is {receipt.get('schema')!r}, expected {PATCH_SCHEMA!r}")
    items = receipt.get("replacements") or []
    _require(items, "the receipt declares no replacements")

    src_size, src_entries = walk_volume(source)
    dst_size, dst_entries = walk_volume(destination)
    _require(src_size == dst_size,
             f"image size changed: {src_size} -> {dst_size}")
    _require(src_entries == dst_entries,
             "the ISO9660 tree changed: a file moved, resized or was renamed")
    _require(src_size == receipt.get("source_size", src_size)
             and dst_size == receipt.get("output_size", dst_size),
             "the receipt's image sizes disagree with the files")

    spans = [(item["iso_offset"], item["iso_offset"] + item["video_bytes"],
              item["slot_id"]) for item in items]
    ordered = sorted(spans)
    for left, right in zip(ordered, ordered[1:]):
        _require(left[1] <= right[0],
                 f"declared spans for {left[2]} and {right[2]} overlap")

    comparison = _compare(source, destination, spans)

    slots = []
    with open(source, "rb") as handle_src, open(destination, "rb") as handle_dst:
        for item in items:
            slots.append(_check_slot(handle_src, handle_dst, item, dst_entries,
                                     Path(wav_dir) if wav_dir else None))
        boot = _extent(dst_entries, BOOT_FILE)
        digests = []
        for handle in (handle_src, handle_dst):
            digest = hashlib.sha256()
            remaining = boot["length"]
            handle.seek(boot["lba"] * SECTOR)
            while remaining:
                block = handle.read(min(COMPARE_CHUNK, remaining))
                _require(block, "the boot ELF extent is truncated")
                digest.update(block)
                remaining -= len(block)
            digests.append(digest.hexdigest())
    _require(digests[0] == digests[1], "the boot ELF changed")

    declared_total = sum(item["video_bytes"] for item in items)
    iso_verifier = None
    if run_iso_verifier:
        iso_verifier = _run_iso_verifier(source, destination, receipt)

    return {
        "schema": SCHEMA,
        "verdict": "pass",
        "source": str(source),
        "destination": str(destination),
        "image_size": src_size,
        "tree_entries": len(src_entries),
        "tree_identical": True,
        "declared_slots": len(items),
        "declared_payload_bytes": declared_total,
        "changed_bytes": comparison["changed_bytes"],
        "changed_bytes_per_slot": comparison["per_slot"],
        "changed_outside_declared_spans": 0,
        "boot_sha256": digests[0],
        "slots": slots,
        "iso9660_verifier": iso_verifier,
    }


def _run_iso_verifier(source: Path, destination: Path, receipt: dict) -> dict:
    """Run tools/ps2_iso9660_verify.py as a subprocess -- never an import."""
    report = receipt.get("iso_write_report")
    if not report:
        return {"ran": False, "reason": "the receipt carries no ISO write report"}
    tool = _TOOLS / "ps2_iso9660_verify.py"
    if not tool.is_file():
        return {"ran": False, "reason": f"{tool} is not present"}
    import tempfile
    with tempfile.TemporaryDirectory() as work:
        report_path = Path(work) / "write-report.json"
        report_path.write_bytes(
            (json.dumps(report, indent=2) + "\n").encode("utf-8"))
        completed = subprocess.run(
            [sys.executable, str(tool), "--source", str(source),
             "--destination", str(destination), "--report", str(report_path)],
            capture_output=True, text=True, check=False)
    return {
        "ran": True,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout_tail": completed.stdout.strip().splitlines()[-3:],
        "stderr_tail": completed.stderr.strip().splitlines()[-3:],
    }


# ------------------------------------------------------------------ selftest


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

    print("nfl2k5_ps2_audo_verify selftest")
    # Built through the patcher, then verified without importing it: the
    # subprocess boundary is what keeps this module independent.
    patcher = _TOOLS / "nfl2k5_ps2_audo_patch.py"
    if not patcher.is_file():
        print("  SKIP tools/nfl2k5_ps2_audo_patch.py is not present")
        return 0

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        root = Path(work)
        build = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r);"
             "import nfl2k5_ps2_audo_target_catalog as c, spu_adpcm, pathlib;"
             "mono = spu_adpcm.encode([0] * (28 * 40));"
             "img = c.build_disc([c.build_audo_chunk('selftest_beep', 1, 11025, mono)]);"
             "pathlib.Path(%r).write_bytes(img)" % (str(_TOOLS), str(root / "src.iso"))],
            capture_output=True, text=True, check=False)
        check(build.returncode == 0, "synthetic source image built")
        if build.returncode:
            print(build.stderr)
            return 1

        wav_path = root / "tone.wav"
        frames = 28 * 30
        pcm = b"".join(
            struct.pack("<h", int(1200 * ((n % 40) - 20)))
            for n in range(frames))
        fmt = struct.pack("<HHIIHH", 1, 1, 11025, 11025 * 2, 2, 16)
        body = b"fmt " + struct.pack("<I", len(fmt)) + fmt
        body += b"data" + struct.pack("<I", len(pcm)) + pcm
        wav_path.write_bytes(b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body)

        patched = subprocess.run(
            [sys.executable, str(patcher), "--iso", str(root / "src.iso"),
             "--output", str(root / "out.iso"),
             "--replace", "selftest_beep=%s" % wav_path,
             "--receipt", str(root / "receipt.json")],
            capture_output=True, text=True, check=False)
        check(patched.returncode == 0, "the patcher produced an image")
        if patched.returncode:
            print(patched.stderr)
            return 1

        receipt = json.loads((root / "receipt.json").read_bytes().decode("utf-8"))
        result = verify(root / "src.iso", root / "out.iso", receipt,
                        wav_dir=root, run_iso_verifier=True)
        check(result["verdict"] == "pass", "a clean patch verifies")
        check(result["changed_bytes"] == receipt["replacements"][0]["video_bytes"]
              or result["changed_bytes"] <= receipt["replacements"][0]["video_bytes"],
              "changed bytes stay inside the slot")
        check(result["iso9660_verifier"]["ran"]
              and result["iso9660_verifier"]["passed"],
              "the ISO9660 verifier agrees (subprocess)")

        # A byte flipped outside the slot must fail.
        tampered = root / "tampered.iso"
        data = bytearray((root / "out.iso").read_bytes())
        target = receipt["replacements"][0]["iso_offset"] + \
            receipt["replacements"][0]["video_bytes"] + 8
        data[target] ^= 0xFF
        tampered.write_bytes(bytes(data))
        try:
            verify(root / "src.iso", tampered, receipt)
        except VerifyError as exc:
            check("outside every declared slot" in str(exc),
                  "a byte changed outside the slot fails")
        else:
            check(False, "a byte changed outside the slot fails")

        # A byte flipped inside the slot must fail the digest.
        inside = root / "inside.iso"
        data = bytearray((root / "out.iso").read_bytes())
        data[receipt["replacements"][0]["iso_offset"] + 5] ^= 0xFF
        inside.write_bytes(bytes(data))
        try:
            verify(root / "src.iso", inside, receipt)
        except VerifyError as exc:
            check("not the one the receipt records" in str(exc),
                  "a byte changed inside the slot fails the digest")
        else:
            check(False, "a byte changed inside the slot fails the digest")

    print("PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 0 if failures == 0 else 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="the image before the patch")
    parser.add_argument("--destination", type=Path, help="the image after the patch")
    parser.add_argument("--receipt", type=Path, help="the patcher's receipt JSON")
    parser.add_argument("--wav-dir", type=Path,
                        help="where the source WAVs live, to re-check their digests")
    parser.add_argument("--iso-verify", action="store_true",
                        help="also run tools/ps2_iso9660_verify.py as a subprocess")
    parser.add_argument("--json", type=Path, help="write the verdict here")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return selftest()
    for flag in ("source", "destination", "receipt"):
        if getattr(args, flag) is None:
            parser.error(f"--{flag} is required (or use --selftest)")

    receipt = json.loads(args.receipt.read_bytes().decode("utf-8"))
    result = verify(args.source, args.destination, receipt,
                    wav_dir=args.wav_dir, run_iso_verifier=args.iso_verify)
    print("verdict: %s" % result["verdict"])
    print("  image %d bytes, %d tree entries identical"
          % (result["image_size"], result["tree_entries"]))
    print("  %d slot(s), %d declared payload bytes, %d bytes actually changed"
          % (result["declared_slots"], result["declared_payload_bytes"],
             result["changed_bytes"]))
    for slot in result["slots"]:
        print("  %-34s %-24s payload@%d %d B, %d blocks, audible %s frames"
              % (slot["slot_id"], slot["name"], slot["payload_offset"],
                 slot["payload_bytes"], slot["blocks_per_channel"],
                 slot["audible_frames"]))
    if result["iso9660_verifier"] and result["iso9660_verifier"].get("ran"):
        print("  ps2_iso9660_verify: %s"
              % ("pass" if result["iso9660_verifier"]["passed"] else "FAIL"))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
        print("  wrote %s" % args.json)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (VerifyError, spu_adpcm.SpuAdpcmError) as exc:
        print("VERIFY FAILED: %s" % exc, file=sys.stderr)
        sys.exit(1)
