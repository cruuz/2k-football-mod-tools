#!/usr/bin/env python3
"""Find exact semantic string anchors shared by two console executables."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


PRINTABLE = set(range(0x20, 0x7F))


def ascii_strings(data: bytes, minimum: int):
    start = None
    for index, value in enumerate(data + b"\0"):
        if value in PRINTABLE:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                yield start, "ascii", data[start:index].decode("ascii")
            start = None


def utf16_strings(data: bytes, minimum: int, byteorder: str):
    low_index = 0 if byteorder == "little" else 1
    high_index = 1 - low_index
    for parity in (0, 1):
        start = None
        cursor = parity
        while cursor + 1 < len(data):
            pair = data[cursor : cursor + 2]
            printable = pair[low_index] in PRINTABLE and pair[high_index] == 0
            if printable:
                if start is None:
                    start = cursor
            elif start is not None:
                length = (cursor - start) // 2
                if length >= minimum:
                    encoding = "utf-16le" if byteorder == "little" else "utf-16be"
                    yield start, encoding, data[start:cursor].decode(encoding)
                start = None
            cursor += 2


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().replace("\\", "/")).lower()


def inventory(path: Path, minimum: int):
    data = path.read_bytes()
    result: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    generators = (
        ascii_strings(data, minimum),
        utf16_strings(data, minimum, "little"),
        utf16_strings(data, minimum, "big"),
    )
    for strings in generators:
        for offset, encoding, value in strings:
            key = normalize(value)
            if key and len(result[key]) < 16:
                result[key].append((offset, encoding, value))
            basename = key.rsplit("/", 1)[-1]
            if basename != key and len(basename) >= minimum and len(result[basename]) < 16:
                result[basename].append((offset, encoding, value))
    return result


def anchor_score(value: str, left_count: int, right_count: int) -> float:
    variety = len(set(value))
    path_bonus = 12 if "." in value or "/" in value else 0
    rarity = 8.0 / max(1, left_count + right_count)
    return len(value) + variety * 0.4 + path_bonus + rarity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--minimum", type=int, default=7)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    left = inventory(args.left, args.minimum)
    right = inventory(args.right, args.minimum)
    common = []
    for value in left.keys() & right.keys():
        if not any(character.isalpha() for character in value):
            continue
        score = anchor_score(value, len(left[value]), len(right[value]))
        common.append((score, value, left[value], right[value]))
    common.sort(key=lambda item: (-item[0], item[1]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        output.write("score\tstring\tleft_offsets\tright_offsets\n")
        for score, value, left_hits, right_hits in common[: args.limit]:
            left_text = ",".join(f"0x{o:X}:{e}" for o, e, _ in left_hits)
            right_text = ",".join(f"0x{o:X}:{e}" for o, e, _ in right_hits)
            output.write(f"{score:.2f}\t{value}\t{left_text}\t{right_text}\n")
    print(
        f"{len(left)} left strings; {len(right)} right strings; "
        f"{len(common)} shared; wrote {min(len(common), args.limit)}"
    )


if __name__ == "__main__":
    main()
