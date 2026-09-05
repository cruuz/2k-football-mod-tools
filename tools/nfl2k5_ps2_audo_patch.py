#!/usr/bin/env python3
"""Replace ESPN NFL 2K5 PS2 sounds in place, inside the slots they already own.

Reads the user's own ``SLUS-20919`` ISO, writes a **new** ISO with one or more
``AUDO`` payloads replaced by encoded WAV files.  The source image is opened
read-only and never modified.

**Nothing moves.**  A replacement is encoded to SPU-ADPCM and padded with silent
blocks to exactly the byte count the slot already declares, so:

* ``stored_size`` / ``system_bytes`` / ``video_bytes`` never change,
* the 8-word sound descriptor -- including ``data_size``, ``per_channel_bytes``
  and the sample rate -- is never rewritten,
* the chunk that follows keeps its offset, the outer entry keeps its size, the
  pack keeps its length and the ISO9660 tree keeps every extent and LBA.

SPU-ADPCM makes that free rather than clever: the block carrying
``LOOP_END | LOOP`` ends the sound, so filler after it is never played.  A
shorter sound therefore fits any larger slot exactly.  A *longer* one is
refused -- chunks are packed back to back with no slack, and growing one would
mean rebuilding the image.

**What the user supplies.**  Strict 16-bit PCM RIFF/WAVE, ``fmt `` then ``data``
and nothing else.  Channels must match the slot (only 38 of the 844 slots are
stereo).  A differing sample rate is resampled -- see ``resample`` for the
method and its limits -- but supplying the slot's own rate is always better.

The write itself goes through ``tools/ps2_iso9660_writer.py``'s fixed-allocation
``replace_files``, so the change is bounded and declared; ``ps2_iso9660_verify``
and ``tools/nfl2k5_ps2_audo_verify.py`` then prove it independently.

Stdlib only.  ``--selftest`` patches a synthetic disc end to end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
from typing import Iterable, List, Sequence, Tuple

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl2k5_ps2_audo_target_catalog as catalogue  # noqa: E402
import nfl2k5_ps2_disc_inventory as inv  # noqa: E402
import ps2_iso9660 as iso  # noqa: E402
import ps2_iso9660_writer as isowriter  # noqa: E402
import spu_adpcm  # noqa: E402

SCHEMA = "nfl2k5_ps2_audo_patch/v1"
RECIPE_SCHEMA = "nfl2k5_ps2_audo_recipe/v1"
PACK_DIRECTORY = inv.PACK_DIRECTORY

MAX_WAV_BYTES = 64 * 1024 * 1024
MAX_REPLACEMENTS = 256
COPY_CHUNK = 8 * 1024 * 1024

#: Half-width of the resampler's windowed-sinc kernel, in output samples.
RESAMPLE_TAPS = 16


class PatchError(ValueError):
    """A recipe, a WAV or a slot this writer refuses."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise PatchError(message)


# ----------------------------------------------------------------- WAV input


def parse_wav(data: bytes) -> dict:
    """Strict 16-bit PCM RIFF/WAVE.  Returns rate, channels and per-channel PCM.

    Deliberately narrow: the chunks must tile the file, the only chunks allowed
    are ``fmt `` then ``data``, and every derived field must agree.  Anything
    looser and a file that "plays fine" in a media player can still carry a
    surprise into a fixed-size slot.
    """
    _require(len(data) <= MAX_WAV_BYTES,
             f"WAV is {len(data)} bytes; the cap is {MAX_WAV_BYTES}")
    _require(len(data) >= 44, "WAV is too short to hold a header")
    _require(data[0:4] == b"RIFF", "not a RIFF file")
    riff_size = struct.unpack_from("<I", data, 4)[0]
    _require(riff_size + 8 == len(data),
             f"RIFF size {riff_size} does not describe a {len(data)}-byte file")
    _require(data[8:12] == b"WAVE", "RIFF file is not WAVE")

    cursor = 12
    seen: List[bytes] = []
    fmt = None
    pcm = None
    while cursor < len(data):
        _require(cursor + 8 <= len(data), "a chunk header runs past the file")
        name = data[cursor:cursor + 4]
        size = struct.unpack_from("<I", data, cursor + 4)[0]
        body_at = cursor + 8
        _require(body_at + size <= len(data), f"chunk {name!r} runs past the file")
        seen.append(name)
        if name == b"fmt ":
            fmt = data[body_at:body_at + size]
        elif name == b"data":
            pcm = data[body_at:body_at + size]
        cursor = body_at + size + (size & 1)
    _require(cursor == len(data), "the chunks do not tile the file exactly")
    _require(
        seen == [b"fmt ", b"data"],
        "a WAV for a fixed slot must contain exactly 'fmt ' then 'data'; this "
        f"one has {[n.decode('latin1') for n in seen]}. Remove metadata chunks.",
    )
    assert fmt is not None and pcm is not None
    _require(len(fmt) == 16, f"fmt chunk is {len(fmt)} bytes, expected the 16-byte PCM form")
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack("<HHIIHH", fmt)
    _require(tag == 1, f"format tag {tag} is not integer PCM (1)")
    _require(bits == 16, f"{bits}-bit samples; this writer takes 16-bit PCM")
    _require(1 <= channels <= spu_adpcm_max_channels(),
             f"{channels} channels; the disc has mono and stereo slots only")
    _require(0 < rate <= 48000, f"sample rate {rate} is out of range")
    _require(block_align == channels * 2, f"block align {block_align} disagrees with the format")
    _require(byte_rate == rate * block_align, f"byte rate {byte_rate} disagrees with the format")
    _require(len(pcm) % block_align == 0,
             f"data chunk of {len(pcm)} bytes is not a whole number of frames")
    frames = len(pcm) // block_align
    _require(frames > 0, "the data chunk is empty")

    samples = struct.unpack("<%dh" % (frames * channels), pcm)
    planes = [list(samples[c::channels]) for c in range(channels)]
    return {"rate": rate, "channels": channels, "frames": frames, "planes": planes}


def spu_adpcm_max_channels() -> int:
    return catalogue.MAX_CHANNELS


# ------------------------------------------------------------------ resample


def resample(samples: Sequence[int], source_rate: int, target_rate: int) -> List[int]:
    """Windowed-sinc resampling, ``RESAMPLE_TAPS`` either side of each output.

    The kernel is a Blackman-windowed sinc whose cutoff is the lower of the two
    Nyquist limits, so downsampling is anti-aliased rather than decimated.  It is
    a fixed-width direct convolution -- honest but not a polyphase soxr -- and it
    exists so a slightly-wrong WAV still works.  For the best result supply audio
    already at the slot's rate, or conform it with ``tools/game_audio_convert.py``,
    which resamples with soxr.
    """
    _require(source_rate > 0 and target_rate > 0, "sample rates must be positive")
    if source_rate == target_rate:
        return list(samples)
    ratio = target_rate / source_rate
    count = max(1, int(math.floor(len(samples) * ratio)))
    cutoff = min(0.5, 0.5 * ratio)           # cycles per input sample
    scale = 2.0 * cutoff
    width = RESAMPLE_TAPS / min(1.0, ratio)  # widen the window when decimating
    out: List[int] = []
    for n in range(count):
        centre = n / ratio
        first = int(math.floor(centre - width))
        last = int(math.ceil(centre + width))
        total = 0.0
        norm = 0.0
        for i in range(first, last + 1):
            offset = centre - i
            if abs(offset) > width:
                continue
            x = 2.0 * math.pi * cutoff * offset
            sinc = 1.0 if x == 0.0 else math.sin(x) / x
            phase = math.pi * (offset / width + 1.0)      # 0 .. 2*pi
            window = 0.42 - 0.5 * math.cos(phase) + 0.08 * math.cos(2.0 * phase)
            tap = scale * sinc * window
            norm += tap
            if 0 <= i < len(samples):
                total += samples[i] * tap
        if norm:
            total /= norm
        value = int(round(total))
        out.append(-0x8000 if value < -0x8000 else (0x7FFF if value > 0x7FFF else value))
    return out


# -------------------------------------------------------------------- planning


def _pack_iso_path(letter: str) -> str:
    return "%s/%s." % (PACK_DIRECTORY, letter)


def plan(iso_path, requests: Sequence[Tuple[str, Path]], catalog: dict | None = None) -> dict:
    """Resolve slots, read and encode the WAVs.  Raises before anything is written."""
    _require(requests, "no replacements were given")
    _require(len(requests) <= MAX_REPLACEMENTS,
             f"{len(requests)} replacements is past the {MAX_REPLACEMENTS} cap")
    if catalog is None:
        catalog = catalogue.build(iso_path)
    _require(catalog.get("schema") == catalogue.SCHEMA,
             f"catalogue schema is {catalog.get('schema')!r}")

    image = iso.open_image(iso_path)
    packs = inv.discover_packs(image)
    starts = [0]
    for _name, _base, size in packs:
        starts.append(starts[-1] + size)

    seen: set = set()
    items: List[dict] = []
    for wanted, wav_path in requests:
        slot = catalogue.find_slot(catalog, wanted)
        _require(slot["slot_id"] not in seen,
                 f"{slot['slot_id']} appears twice in the recipe")
        seen.add(slot["slot_id"])

        wav_path = Path(wav_path)
        _require(not wav_path.is_symlink(),
                 f"{wav_path}: refusing to read a replacement through a symlink")
        _require(wav_path.is_file(), f"{wav_path}: not a regular file")
        wav = parse_wav(wav_path.read_bytes())
        _require(
            wav["channels"] == slot["channels"],
            f"{slot['name']} is a {slot['channels']}-channel slot but the WAV has "
            f"{wav['channels']}; supply "
            f"{'mono' if slot['channels'] == 1 else 'stereo'} audio.",
        )
        planes = wav["planes"]
        resampled_from = None
        if wav["rate"] != slot["sample_rate"]:
            resampled_from = wav["rate"]
            planes = [resample(p, wav["rate"], slot["sample_rate"]) for p in planes]
        frames = len(planes[0])
        _require(
            frames <= slot["max_frames"],
            f"{slot['name']}: {frames} frames at {slot['sample_rate']} Hz need "
            f"{spu_adpcm.blocks_for_frames(frames) * spu_adpcm.BLOCK_BYTES} bytes "
            f"per channel but the slot holds {slot['per_channel_bytes']} "
            f"({slot['max_frames']} frames, "
            f"{slot['max_frames'] / slot['sample_rate']:.3f} s). This writer never "
            "grows a slot; shorten the audio.",
        )

        payload = b"".join(
            spu_adpcm.encode_to_slot(p, slot["per_channel_bytes"]) for p in planes
        )
        _require(len(payload) == slot["video_bytes"], "internal: payload size drifted")

        virtual = slot["payload_virtual_offset"]
        pack_index = next(i for i in range(len(packs) - 1, -1, -1)
                          if starts[i] <= virtual)
        pack_offset = virtual - starts[pack_index]
        _require(pack_offset + len(payload) <= packs[pack_index][2],
                 f"{slot['name']}: payload crosses a pack boundary")
        items.append({
            "slot_id": slot["slot_id"],
            "name": slot["name"],
            "unique_name": slot["unique_name"],
            "entry_index": slot["entry_index"],
            "chunk_index": slot["chunk_index"],
            "channels": slot["channels"],
            "sample_rate": slot["sample_rate"],
            "per_channel_bytes": slot["per_channel_bytes"],
            "video_bytes": slot["video_bytes"],
            "max_frames": slot["max_frames"],
            "frames_written": frames,
            "blocks_written": spu_adpcm.blocks_for_frames(frames),
            "pad_blocks": slot["per_channel_bytes"] // spu_adpcm.BLOCK_BYTES
                          - spu_adpcm.blocks_for_frames(frames),
            "resampled_from": resampled_from,
            "wav": str(wav_path),
            "wav_sha256": hashlib.sha256(wav_path.read_bytes()).hexdigest(),
            "pack": packs[pack_index][0],
            "pack_iso_path": _pack_iso_path(packs[pack_index][0]),
            "pack_offset": pack_offset,
            "iso_offset": packs[pack_index][1] + pack_offset,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "_payload": payload,
            "_pack_index": pack_index,
        })

    # No two writes may touch the same bytes.
    spans = sorted((i["iso_offset"], i["iso_offset"] + i["video_bytes"], i["slot_id"])
                   for i in items)
    for left, right in zip(spans, spans[1:]):
        _require(left[1] <= right[0],
                 f"{left[2]} and {right[2]} overlap in the image")
    return {"catalog": catalog, "packs": packs, "items": items}


def _materialise_pack(iso_path: Path, base: int, size: int,
                      patches: Sequence[Tuple[int, bytes]], destination: Path) -> None:
    """Copy one pack out of the image, applying *patches* at pack offsets."""
    ordered = sorted(patches)
    with open(iso_path, "rb") as source, open(destination, "wb") as out:
        source.seek(base)
        written = 0
        for offset, payload in ordered:
            while written < offset:
                block = source.read(min(COPY_CHUNK, offset - written))
                _require(block, "the image ended inside a pack")
                out.write(block)
                written += len(block)
            out.write(payload)
            source.seek(base + offset + len(payload))
            written += len(payload)
        while written < size:
            block = source.read(min(COPY_CHUNK, size - written))
            _require(block, "the image ended inside a pack")
            out.write(block)
            written += len(block)
    _require(destination.stat().st_size == size, "the rebuilt pack changed size")


def apply(prepared: dict, iso_path, destination, work_dir=None) -> dict:
    """Write the new image.  Returns the receipt."""
    iso_path = Path(iso_path)
    destination = Path(destination)
    packs = prepared["packs"]
    items = prepared["items"]

    by_pack: dict = {}
    for item in items:
        by_pack.setdefault(item["_pack_index"], []).append(
            (item["pack_offset"], item["_payload"]))

    with tempfile.TemporaryDirectory(dir=work_dir) as work:
        replacements = {}
        for pack_index, patches in sorted(by_pack.items()):
            name, base, size = packs[pack_index]
            staged = Path(work) / ("pack_%s.bin" % name)
            _materialise_pack(iso_path, base, size, patches, staged)
            replacements[_pack_iso_path(name)] = staged
        report = isowriter.replace_files(iso_path, destination, replacements)

    receipt = {
        "schema": SCHEMA,
        "generated_by": "tools/nfl2k5_ps2_audo_patch.py",
        "source_iso": str(iso_path),
        "source_size": iso_path.stat().st_size,
        "output_iso": str(destination),
        "output_size": destination.stat().st_size,
        "catalog_schema": prepared["catalog"]["schema"],
        "disc": prepared["catalog"]["disc"],
        "encoder": {
            "module": "tools/spu_adpcm.py",
            "block_bytes": spu_adpcm.BLOCK_BYTES,
            "block_frames": spu_adpcm.BLOCK_FRAMES,
            "search": "exhaustive 5 filters x 13 shifts",
            "resampler": "windowed-sinc, %d taps" % RESAMPLE_TAPS,
        },
        "replacements": [
            {k: v for k, v in item.items() if not k.startswith("_")}
            for item in items
        ],
        "iso_write_report": isowriter.report_to_json(report),
    }
    return receipt


def write_receipt(receipt: dict, destination) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(receipt, indent=2, ensure_ascii=True) + "\n"
    destination.write_bytes(text.encode("utf-8"))
    return destination


def load_recipe(path) -> List[Tuple[str, Path]]:
    data = json.loads(Path(path).read_bytes().decode("utf-8"))
    _require(data.get("schema") == RECIPE_SCHEMA,
             f"recipe schema is {data.get('schema')!r}, expected {RECIPE_SCHEMA!r}")
    rows = data.get("replacements")
    _require(isinstance(rows, list) and rows, "recipe has no replacements")
    base = Path(path).resolve().parent
    out = []
    for row in rows:
        _require(isinstance(row, dict) and "slot" in row and "wav" in row,
                 "each replacement needs 'slot' and 'wav'")
        wav = Path(row["wav"])
        out.append((str(row["slot"]), wav if wav.is_absolute() else base / wav))
    return out


# ------------------------------------------------------------------ selftest


def _wav(planes: Sequence[Sequence[int]], rate: int) -> bytes:
    channels = len(planes)
    frames = len(planes[0])
    interleaved = []
    for i in range(frames):
        for plane in planes:
            interleaved.append(plane[i])
    pcm = struct.pack("<%dh" % len(interleaved), *interleaved)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


def _tone(count: int, rate: int, hz: float, amplitude: int) -> List[int]:
    return [int(round(amplitude * math.sin(2.0 * math.pi * hz * n / rate)))
            for n in range(count)]


def selftest(tmp=None) -> int:
    failures = 0

    def check(condition: object, label: str) -> None:
        nonlocal failures
        if condition:
            print(f"  ok   {label}")
        else:
            failures += 1
            print(f"  FAIL {label}")

    print("nfl2k5_ps2_audo_patch selftest")
    mono_slot = spu_adpcm.encode([0] * (28 * 40))
    stereo_slot = spu_adpcm.encode([0] * (28 * 20)) + spu_adpcm.encode([0] * (28 * 20))
    image = catalogue.build_disc([
        catalogue.build_audo_chunk("selftest_beep", 1, 11025, mono_slot),
        catalogue.build_audo_chunk("selftest_pair", 2, 22050, stereo_slot),
    ])

    with tempfile.TemporaryDirectory(dir=tmp) as work:
        root = Path(work)
        source = root / "source.iso"
        source.write_bytes(image)
        catalog = catalogue.build(source)
        beep = catalogue.find_slot(catalog, "selftest_beep")

        good = root / "good.wav"
        good.write_bytes(_wav([_tone(28 * 30, 11025, 400.0, 9000)], 11025))
        prepared = plan(source, [("selftest_beep", good)], catalog)
        item = prepared["items"][0]
        check(len(item["_payload"]) == beep["video_bytes"], "payload fills the slot exactly")
        check(item["pad_blocks"] == 10, "the short sound leaves 10 filler blocks")
        out = root / "out.iso"
        receipt = apply(prepared, source, out)
        check(out.stat().st_size == source.stat().st_size, "the image keeps its size")

        before = source.read_bytes()
        after = out.read_bytes()
        differing = [i for i in range(len(before)) if before[i] != after[i]]
        low = item["iso_offset"]
        high = low + item["video_bytes"]
        check(differing and all(low <= i < high for i in differing),
              "every changed byte is inside the declared payload")
        wrapper = after[low - beep["system_bytes"] - inv.CHUNK_HEADER_SIZE:low]
        check(wrapper == before[low - beep["system_bytes"] - inv.CHUNK_HEADER_SIZE:low],
              "the wrapper and descriptor are byte-identical")
        report = spu_adpcm.validate_payload(after[low:high])
        check(report["blocks"] == beep["video_bytes"] // 16, "the slot still parses")
        check(report["terminators"][0] == item["blocks_written"] - 1,
              "the real audio terminates at its own end")
        check(receipt["replacements"][0]["frames_written"] == 28 * 30,
              "the receipt records the frame count")

        # resampling
        off_rate = root / "off.wav"
        off_rate.write_bytes(_wav([_tone(1000, 22050, 400.0, 9000)], 22050))
        prepared2 = plan(source, [("selftest_beep", off_rate)], catalog)
        check(prepared2["items"][0]["resampled_from"] == 22050, "a rate mismatch resamples")
        check(abs(prepared2["items"][0]["frames_written"] - 500) <= 1,
              "resampling halves the frame count for a halved rate")

        # stereo
        pair = root / "pair.wav"
        pair.write_bytes(_wav([_tone(28 * 15, 22050, 300.0, 8000),
                               _tone(28 * 15, 22050, 500.0, 8000)], 22050))
        prepared3 = plan(source, [("selftest_pair", pair)], catalog)
        stereo = catalogue.find_slot(catalog, "selftest_pair")
        check(len(prepared3["items"][0]["_payload"]) == stereo["video_bytes"],
              "stereo fills the slot exactly")
        halves = prepared3["items"][0]["_payload"]
        half = stereo["per_channel_bytes"]
        check(spu_adpcm.validate_payload(halves[:half])["terminators"][-1]
              == half // 16 - 1
              and spu_adpcm.validate_payload(halves[half:])["terminators"][-1]
              == half // 16 - 1,
              "stereo is two contiguous, separately terminated halves")

        # refusals
        long_wav = root / "long.wav"
        long_wav.write_bytes(_wav([_tone(beep["max_frames"] + 1, 11025, 400.0, 9000)], 11025))
        wrong_channels = root / "wrong.wav"
        wrong_channels.write_bytes(_wav([_tone(280, 11025, 400.0, 9000)] * 2, 11025))
        bad = root / "bad.wav"
        bad.write_bytes(b"RIFF" + struct.pack("<I", 4) + b"WAVE")
        eight_bit = root / "eight.wav"
        raw = _wav([_tone(280, 11025, 400.0, 9000)], 11025)
        eight_bit.write_bytes(raw[:34] + struct.pack("<H", 8) + raw[36:])
        for label, call in (
            ("over-length audio is refused",
             lambda: plan(source, [("selftest_beep", long_wav)], catalog)),
            ("a channel-count mismatch is refused",
             lambda: plan(source, [("selftest_beep", wrong_channels)], catalog)),
            ("a malformed WAV is refused",
             lambda: plan(source, [("selftest_beep", bad)], catalog)),
            ("8-bit PCM is refused",
             lambda: plan(source, [("selftest_beep", eight_bit)], catalog)),
            ("a missing WAV is refused",
             lambda: plan(source, [("selftest_beep", root / "nope.wav")], catalog)),
            ("an unknown slot is refused",
             lambda: plan(source, [("no_such_sound", good)], catalog)),
            ("the same slot twice is refused",
             lambda: plan(source, [("selftest_beep", good),
                                   (beep["slot_id"], good)], catalog)),
        ):
            try:
                call()
            except (PatchError, catalogue.CatalogError, spu_adpcm.SpuAdpcmError):
                check(True, label)
            else:
                check(False, label)

        refused = root / "refused.iso"
        try:
            apply(plan(source, [("selftest_beep", long_wav)], catalog), source, refused)
        except (PatchError, spu_adpcm.SpuAdpcmError):
            check(not refused.exists(), "a refusal leaves no output image behind")
        else:
            check(False, "a refusal leaves no output image behind")

    print("PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 0 if failures == 0 else 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", type=Path, help="the user's own SLUS-20919 ISO")
    parser.add_argument("--output", type=Path, help="the new ISO to write")
    parser.add_argument("--replace", action="append", default=[],
                        metavar="SLOT=WAV",
                        help="slot id or disc-unique name = path to a 16-bit PCM WAV")
    parser.add_argument("--recipe", type=Path, help="a %s file" % RECIPE_SCHEMA)
    parser.add_argument("--catalog", type=Path,
                        help="a prebuilt catalogue; built from the ISO when absent")
    parser.add_argument("--receipt", type=Path, help="where to write the receipt JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan and encode, but write no image")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return selftest()
    if args.iso is None:
        parser.error("--iso is required (or use --selftest)")

    requests: List[Tuple[str, Path]] = []
    if args.recipe:
        requests.extend(load_recipe(args.recipe))
    for item in args.replace:
        _require("=" in item, f"--replace wants SLOT=WAV, got {item!r}")
        slot, _sep, wav = item.partition("=")
        requests.append((slot.strip(), Path(wav.strip())))
    if not requests:
        parser.error("give at least one --replace or a --recipe")

    catalog = None
    if args.catalog:
        catalog = json.loads(args.catalog.read_bytes().decode("utf-8"))
    prepared = plan(args.iso, requests, catalog)

    for item in prepared["items"]:
        print("%-34s %-26s %d ch @%d Hz  %d/%d frames, %d filler blocks%s"
              % (item["slot_id"], item["name"], item["channels"], item["sample_rate"],
                 item["frames_written"], item["max_frames"], item["pad_blocks"],
                 "" if item["resampled_from"] is None
                 else "  (resampled from %d Hz)" % item["resampled_from"]))
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    if args.output is None:
        parser.error("--output is required unless --dry-run is given")

    receipt = apply(prepared, args.iso, args.output)
    print("wrote %s (%d bytes)" % (args.output, receipt["output_size"]))
    if args.receipt:
        print("receipt %s" % write_receipt(receipt, args.receipt))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PatchError, catalogue.CatalogError, spu_adpcm.SpuAdpcmError,
            inv.InventoryError, iso.Iso9660Error, isowriter.IsoWriteError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        sys.exit(1)
