#!/usr/bin/env python3
"""Create a deterministic, redistributable PCM16 menu sound."""

from __future__ import annotations

import argparse
import struct
import wave
from pathlib import Path


def write_sound(path: Path, sample_rate: int = 22_050, milliseconds: int = 90) -> None:
    if not 8_000 <= sample_rate <= 192_000:
        raise ValueError("sample rate must be between 8000 and 192000 Hz")
    if not 10 <= milliseconds <= 2_000:
        raise ValueError("duration must be between 10 and 2000 ms")
    frame_count = sample_rate * milliseconds // 1_000
    samples = bytearray()
    quarter_size = max(1, sample_rate // 4)
    for index in range(frame_count):
        phase = (index * 880 * 4) % sample_rate
        quarter = phase * 4 // sample_rate
        position = phase % quarter_size
        magnitude = position * 2 - quarter_size
        triangle = -magnitude if quarter in (1, 2) else magnitude
        envelope = frame_count - index
        value = triangle * 9_000 * envelope // quarter_size // frame_count
        samples.extend(struct.pack("<h", max(-32768, min(32767, value))))

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with wave.open(str(temporary), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(samples)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/mod/common/audio/menu_select.wav"),
    )
    parser.add_argument("--sample-rate", type=int, default=22_050)
    parser.add_argument("--milliseconds", type=int, default=90)
    args = parser.parse_args()
    write_sound(args.output, args.sample_rate, args.milliseconds)
    print(args.output)


if __name__ == "__main__":
    main()
