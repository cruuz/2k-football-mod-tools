#!/usr/bin/env python3
"""PlayStation 2 SPU-ADPCM: decoder, encoder, and structural validation.

ESPN NFL 2K5's PS2 disc stores every ``AUDO`` sample and every ``AUSB`` stream
bank as SPU-ADPCM.  The format is 16-byte blocks of 28 samples::

    byte 0   (shift & 0x0F) | (filter << 4)     shift <= 12, filter <= 4
    byte 1   flags                              bit0 LOOP_END, bit1 LOOP,
                                                bit2 LOOP_START
    bytes 2..15  28 nibbles, low nibble of each byte first

Decoding is a 2-tap IIR over the previous two reconstructed samples::

    delta = signed_nibble << (12 - shift)
    pcm   = clamp(delta + (c1 * prev1 + c2 * prev2 + 32) // 64)

The five coefficient pairs and the flag bits are transcribed from the SPU2
implementation this project already depends on -- ``XA_decode_block`` and
``tbl_XA_Factor`` in ``pcsx2/SPU2/Mixer.cpp``.  Nothing here is guessed: see
``docs/product/PS2_PHASE2_AUDIO_RESEARCH.md`` §4 for the confirmation, which
includes re-encoding a decoded retail block sequence back to its own bytes.

**Encoding** picks, per block, the ``(filter, shift)`` pair whose reconstruction
has the lowest squared error, simulating the decoder exactly so the round trip
is bit-exact rather than approximate.  ``shift_candidates`` narrows the search
from all 13 shifts to the few around the analytic bound when speed matters; the
default is exhaustive, because a mod tool encodes one short sound at a time.

**Slot fitting.** A replacement never has to match the retail length exactly.
SPU-ADPCM is self-terminating: put ``LOOP_END | LOOP`` on the last real block
and the voice stops there, so a shorter sound is padded with silent blocks up to
the byte count the container already declares.  ``encode_to_slot`` does that and
is the only entry point a writer needs.

Stdlib only.  ``--selftest`` proves the round trip and the structural rules on
synthetic signals; no game data is required, and none is embedded.
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import Iterable, List, Sequence, Tuple

BLOCK_BYTES = 16
BLOCK_FRAMES = 28
MAX_SHIFT = 12
MAX_FILTER = 4

# pcsx2/SPU2/Mixer.cpp tbl_XA_Factor, in 1/64 units.
FILTERS: Tuple[Tuple[int, int], ...] = (
    (0, 0),
    (60, 0),
    (115, -52),
    (98, -55),
    (122, -60),
)

# pcsx2/SPU2/Mixer.cpp XAFLAG_*
FLAG_LOOP_END = 0x01
FLAG_LOOP = 0x02
FLAG_LOOP_START = 0x04

#: What 2K5 writes on every interior block, and on the final block.
FLAG_INTERIOR = FLAG_LOOP
FLAG_TERMINAL = FLAG_LOOP_END | FLAG_LOOP

PCM_MIN = -0x8000
PCM_MAX = 0x7FFF

SILENT_INTERIOR = bytes([0x00, FLAG_INTERIOR]) + b"\x00" * 14
SILENT_TERMINAL = bytes([0x00, FLAG_TERMINAL]) + b"\x00" * 14


class SpuAdpcmError(ValueError):
    """A block, a payload or a request that this codec refuses."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise SpuAdpcmError(message)


def _clamp(value: int) -> int:
    if value < PCM_MIN:
        return PCM_MIN
    if value > PCM_MAX:
        return PCM_MAX
    return value


# --------------------------------------------------------------------- sizes


def blocks_for_frames(frames: int) -> int:
    """Blocks needed to hold *frames* samples of one channel."""
    _require(frames >= 0, "frame count cannot be negative")
    return (frames + BLOCK_FRAMES - 1) // BLOCK_FRAMES


def max_frames_for_bytes(payload_bytes: int) -> int:
    """The most frames one channel of a *payload_bytes* allocation can carry."""
    _require(payload_bytes >= 0, "payload size cannot be negative")
    _require(
        payload_bytes % BLOCK_BYTES == 0,
        f"payload size {payload_bytes} is not a multiple of {BLOCK_BYTES}",
    )
    return payload_bytes // BLOCK_BYTES * BLOCK_FRAMES


# ------------------------------------------------------------------ decoding


def decode_block(block: bytes, prev1: int = 0, prev2: int = 0):
    """Decode one 16-byte block.  Returns ``(28 samples, prev1, prev2)``."""
    _require(len(block) == BLOCK_BYTES, f"a block is {BLOCK_BYTES} bytes, got {len(block)}")
    header = block[0]
    shift = header & 0x0F
    index = header >> 4
    _require(shift <= MAX_SHIFT, f"shift {shift} exceeds {MAX_SHIFT}")
    _require(index <= MAX_FILTER, f"filter index {index} exceeds {MAX_FILTER}")
    c1, c2 = FILTERS[index]
    step = 1 << (MAX_SHIFT - shift)
    out: List[int] = []
    for byte in block[2:BLOCK_BYTES]:
        for nibble in (byte & 0x0F, byte >> 4):
            if nibble > 7:
                nibble -= 16
            pcm = _clamp(nibble * step + ((c1 * prev1 + c2 * prev2 + 32) >> 6))
            out.append(pcm)
            prev2, prev1 = prev1, pcm
    return out, prev1, prev2


def decode(data: bytes, prev1: int = 0, prev2: int = 0):
    """Decode a whole single-channel payload.  Returns ``(samples, p1, p2)``."""
    _require(
        len(data) % BLOCK_BYTES == 0,
        f"payload of {len(data)} bytes is not a multiple of {BLOCK_BYTES}",
    )
    out: List[int] = []
    for start in range(0, len(data), BLOCK_BYTES):
        samples, prev1, prev2 = decode_block(data[start:start + BLOCK_BYTES], prev1, prev2)
        out.extend(samples)
    return out, prev1, prev2


# ------------------------------------------------------------------ encoding


def _shift_candidates(residual_peak: int, width: int) -> Sequence[int]:
    """Shifts to try, widest step first, centred on the analytic bound."""
    if width >= MAX_SHIFT + 1:
        return range(MAX_SHIFT + 1)
    if residual_peak <= 0:
        best = MAX_SHIFT
    else:
        # step = 1 << (12 - shift); the coarsest step that still covers the peak
        # within the [-8, 7] nibble range is the one with step >= peak / 7.
        need = max(0, math.ceil(math.log2(max(1.0, residual_peak / 7.0))))
        best = max(0, min(MAX_SHIFT, MAX_SHIFT - need))
    half = width // 2
    return [s for s in range(best - half, best + width - half) if 0 <= s <= MAX_SHIFT]


def encode_block(
    frames: Sequence[int],
    prev1: int = 0,
    prev2: int = 0,
    flags: int = FLAG_INTERIOR,
    shift_candidates: int = MAX_SHIFT + 1,
):
    """Encode up to 28 samples into one block.  Returns ``(bytes, p1, p2)``.

    Short input is zero-padded.  Every ``(filter, shift)`` pair in the search is
    scored by decoding it back, so the chosen block is the one a real SPU will
    reproduce most closely.
    """
    _require(len(frames) <= BLOCK_FRAMES, f"a block holds at most {BLOCK_FRAMES} frames")
    _require(0 <= flags <= 0xFF, "flags must be one byte")
    _require(shift_candidates >= 1, "shift_candidates must be at least 1")
    block_frames = list(frames) + [0] * (BLOCK_FRAMES - len(frames))

    best: Tuple[int, int, int, List[int], int, int] | None = None
    for index in range(MAX_FILTER + 1):
        c1, c2 = FILTERS[index]
        peak = 0
        p1, p2 = prev1, prev2
        for sample in block_frames:
            residual = sample - ((c1 * p1 + c2 * p2 + 32) >> 6)
            if abs(residual) > peak:
                peak = abs(residual)
            p2, p1 = p1, sample
        for shift in _shift_candidates(peak, shift_candidates):
            step = 1 << (MAX_SHIFT - shift)
            half = step >> 1
            p1, p2 = prev1, prev2
            error = 0
            nibbles: List[int] = []
            for sample in block_frames:
                predicted = (c1 * p1 + c2 * p2 + 32) >> 6
                residual = sample - predicted
                # round-half-away-from-zero division by the step
                if residual >= 0:
                    quantised = (residual + half) // step
                else:
                    quantised = -((-residual + half) // step)
                if quantised > 7:
                    quantised = 7
                elif quantised < -8:
                    quantised = -8
                pcm = _clamp(quantised * step + predicted)
                delta = sample - pcm
                error += delta * delta
                nibbles.append(quantised & 0x0F)
                p2, p1 = p1, pcm
            if best is None or error < best[0]:
                best = (error, index, shift, nibbles, p1, p2)
            if error == 0:
                break
        if best is not None and best[0] == 0:
            break

    assert best is not None
    _error, index, shift, nibbles, p1, p2 = best
    block = bytearray(BLOCK_BYTES)
    block[0] = (index << 4) | shift
    block[1] = flags
    for i in range(14):
        block[2 + i] = nibbles[2 * i] | (nibbles[2 * i + 1] << 4)
    return bytes(block), p1, p2


def encode(
    frames: Sequence[int],
    shift_candidates: int = MAX_SHIFT + 1,
    terminate: bool = True,
) -> bytes:
    """Encode one channel.  The last block carries ``LOOP_END | LOOP``."""
    count = blocks_for_frames(len(frames))
    out = bytearray()
    prev1 = prev2 = 0
    for number in range(count):
        chunk = frames[number * BLOCK_FRAMES:(number + 1) * BLOCK_FRAMES]
        last = number == count - 1
        flags = FLAG_TERMINAL if (last and terminate) else FLAG_INTERIOR
        block, prev1, prev2 = encode_block(chunk, prev1, prev2, flags, shift_candidates)
        out += block
    return bytes(out)


def encode_to_slot(
    frames: Sequence[int],
    payload_bytes: int,
    shift_candidates: int = MAX_SHIFT + 1,
) -> bytes:
    """Encode one channel and pad it to exactly *payload_bytes*.

    The last block of the real audio terminates, so the SPU never reaches the
    filler; the filler exists only so the container's declared size does not
    have to change.  Refuses input that would not fit.
    """
    ceiling = max_frames_for_bytes(payload_bytes)
    _require(
        len(frames) <= ceiling,
        f"{len(frames)} frames need {blocks_for_frames(len(frames)) * BLOCK_BYTES} "
        f"bytes but the slot holds {payload_bytes} ({ceiling} frames). "
        "This writer never grows a slot.",
    )
    body = encode(frames, shift_candidates=shift_candidates)
    padding = payload_bytes - len(body)
    if padding:
        filler = SILENT_INTERIOR * (padding // BLOCK_BYTES - 1) + SILENT_TERMINAL
        body += filler
    assert len(body) == payload_bytes
    return body


# ---------------------------------------------------------------- validation


def block_headers(data: bytes):
    """Yield ``(index, shift, filter, flags)`` for every block in *data*."""
    for number in range(len(data) // BLOCK_BYTES):
        header = data[number * BLOCK_BYTES]
        yield number, header & 0x0F, header >> 4, data[number * BLOCK_BYTES + 1]


def validate_payload(data: bytes, expect_terminal: bool = True) -> dict:
    """Structural check of one channel's payload.  Raises on any violation."""
    _require(len(data) > 0, "payload is empty")
    _require(
        len(data) % BLOCK_BYTES == 0,
        f"payload of {len(data)} bytes is not a multiple of {BLOCK_BYTES}",
    )
    terminators = []
    for number, shift, index, flags in block_headers(data):
        _require(shift <= MAX_SHIFT, f"block {number}: shift {shift} exceeds {MAX_SHIFT}")
        _require(index <= MAX_FILTER, f"block {number}: filter {index} exceeds {MAX_FILTER}")
        _require(
            flags in (FLAG_INTERIOR, FLAG_TERMINAL),
            f"block {number}: flag byte 0x{flags:02x} is not 0x02 or 0x03",
        )
        if flags & FLAG_LOOP_END:
            terminators.append(number)
    total = len(data) // BLOCK_BYTES
    if expect_terminal:
        _require(
            terminators and terminators[-1] == total - 1,
            "the final block does not carry LOOP_END | LOOP",
        )
    return {
        "blocks": total,
        "bytes": len(data),
        "frames": total * BLOCK_FRAMES,
        "terminators": terminators,
        "audible_frames": (terminators[0] + 1) * BLOCK_FRAMES if terminators else None,
    }


# ------------------------------------------------------------------ selftest


def _tone(count: int, rate: int, hz: float, amplitude: int) -> List[int]:
    return [
        int(round(amplitude * math.sin(2.0 * math.pi * hz * n / rate)))
        for n in range(count)
    ]


def _sweep(count: int, amplitude: int) -> List[int]:
    out = []
    for n in range(count):
        phase = 2.0 * math.pi * (0.002 + 0.00004 * n) * n
        out.append(_clamp(int(round(amplitude * math.sin(phase)))))
    return out


def _snr(reference: Sequence[int], produced: Sequence[int]) -> float:
    count = min(len(reference), len(produced))
    signal = sum(v * v for v in reference[:count])
    noise = sum((reference[i] - produced[i]) ** 2 for i in range(count))
    if noise == 0:
        return float("inf")
    if signal == 0:
        return float("-inf")
    return 10.0 * math.log10(signal / noise)


def selftest() -> int:
    failures = 0

    def check(condition: object, label: str) -> None:
        nonlocal failures
        if condition:
            print(f"  ok   {label}")
        else:
            failures += 1
            print(f"  FAIL {label}")

    print("spu_adpcm selftest")

    # 1. A block round-trips through its own decoder bit-exactly.
    frames = _tone(BLOCK_FRAMES, 22050, 440.0, 9000)
    block, p1, p2 = encode_block(frames)
    back, b1, b2 = decode_block(block)
    check(len(back) == BLOCK_FRAMES, "a block decodes to 28 frames")
    check((b1, b2) == (p1, p2), "encoder and decoder agree on the carried state")

    # 2. Re-encoding an already-decoded payload reproduces the same audio.
    #    This is the synthetic form of the retail proof in the research doc:
    #    a payload that IS a valid SPU-ADPCM lattice point must survive
    #    decode -> encode -> decode unchanged.
    reference = encode(_sweep(28 * 64, 11000))
    decoded, _, _ = decode(reference)
    reencoded = encode(decoded)
    check(len(reencoded) == len(reference), "re-encode keeps the payload length")
    again, _, _ = decode(reencoded)
    check(again == decoded, "decode(encode(decode(x))) == decode(x)")
    check(reencoded == reference, "re-encode reproduces the payload byte for byte")

    # 3. Every emitted block obeys the structural rules.
    report = validate_payload(reference)
    check(report["blocks"] == 64, "block count matches the frame count")
    check(report["terminators"] == [63], "exactly one terminator, at the end")
    flags = {flag for _n, _s, _f, flag in block_headers(reference)}
    check(flags <= {FLAG_INTERIOR, FLAG_TERMINAL}, "flags are only 0x02 / 0x03")
    shifts_ok = all(s <= MAX_SHIFT and f <= MAX_FILTER
                    for _n, s, f, _flag in block_headers(reference))
    check(shifts_ok, "every block has shift <= 12 and filter <= 4")

    # 4. Quality on a signal that is not already on the lattice.
    source = _sweep(28 * 200, 12000)
    produced, _, _ = decode(encode(source))
    snr = _snr(source, produced[:len(source)])
    check(snr > 18.0, f"off-lattice SNR {snr:.1f} dB is above 18 dB")

    narrow, _, _ = decode(encode(source, shift_candidates=3))
    narrow_snr = _snr(source, narrow[:len(source)])
    check(narrow_snr > 15.0, f"narrow-search SNR {narrow_snr:.1f} dB is above 15 dB")

    # 5. Slot fitting.
    slot = 64 * BLOCK_BYTES
    short = _tone(28 * 10, 11025, 300.0, 8000)
    padded = encode_to_slot(short, slot)
    check(len(padded) == slot, "encode_to_slot fills the allocation exactly")
    padded_report = validate_payload(padded)
    check(padded_report["terminators"][0] == 9, "the real audio terminates at its own end")
    check(padded_report["terminators"][-1] == 63, "the filler still ends with a terminator")
    tail, _, _ = decode(padded[10 * BLOCK_BYTES:])
    check(set(tail) == {0}, "the filler decodes to silence")
    exact = encode_to_slot(_tone(max_frames_for_bytes(slot), 11025, 300.0, 8000), slot)
    check(len(exact) == slot, "a full-length sound fits with no filler")
    check(validate_payload(exact)["terminators"] == [63], "full-length has one terminator")

    # 6. Refusals.
    for label, call in (
        ("over-length input is refused",
         lambda: encode_to_slot(_tone(max_frames_for_bytes(slot) + 1, 11025, 300.0, 8000), slot)),
        ("a non-multiple-of-16 slot is refused", lambda: encode_to_slot([0], 17)),
        ("a short block is refused by the decoder", lambda: decode_block(b"\x00" * 15)),
        ("a bad shift is refused by the decoder",
         lambda: decode_block(bytes([0x0D, 0x02]) + b"\x00" * 14)),
        ("a bad filter is refused by the decoder",
         lambda: decode_block(bytes([0x50, 0x02]) + b"\x00" * 14)),
        ("a stray flag byte is refused by the validator",
         lambda: validate_payload(bytes([0x00, 0x07]) + b"\x00" * 14)),
        ("an unterminated payload is refused",
         lambda: validate_payload(SILENT_INTERIOR)),
    ):
        try:
            call()
        except SpuAdpcmError:
            check(True, label)
        else:
            check(False, label)

    print("PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 0 if failures == 0 else 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true",
                        help="run the built-in proofs; no game data required")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.selftest:
        return selftest()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
