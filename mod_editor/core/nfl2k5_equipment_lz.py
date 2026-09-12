"""Bounded optimal token selection for the existing lossless VC-LZ format.

An independent chain can miss a retail slot by a few hundred bytes. The usual
greedy encoder chooses the longest current match. This fallback minimizes the
complete token bit cost (9 per literal, 17 per match), including flag bits. It
keeps the existing distance/length format and the native backward-copy rule:
every match is at most its distance. No decoded byte or sibling changes.
"""

from __future__ import annotations

from array import array
from collections import defaultdict, deque
from pathlib import Path
import struct
import os
import hashlib
import platform
import stat
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_txtr import TxtrError, decompress_vc_lz


# Reviewed Linux x86-64 build of tools/nfl2k5_equipment_optimal.c. Other
# platforms keep the Python fallback until their helper is built and reviewed.
_NATIVE_SIZE = 16504
_NATIVE_SHA256 = "949aad6a251de3f039f83bff15d4aa033183c250dbeadd1029e7c79dee4817c4"


def _optimal_helper() -> Path | None:
    if not sys.platform.startswith("linux") or platform.machine().lower() not in {"x86_64", "amd64"}:
        return None
    path = TOOLS / "nfl2k5_equipment_optimal"
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size != _NATIVE_SIZE or info.st_mode & 0o022
                or not info.st_mode & stat.S_IXUSR):
            return None
        if hashlib.sha256(path.read_bytes()).hexdigest() == _NATIVE_SHA256:
            return path
    except OSError:
        pass
    return None


def compress_equipment_optimal(source: bytes, *, stream_tag: int, offset_bits: int,
                               max_encoded_size: int,
                               max_candidate_comparisons: int = 50_000_000) -> bytes:
    if not 0 < len(source) <= 2 * 1024 * 1024 or not 10 <= offset_bits <= 13:
        raise TxtrError("Equipment optimal compression exceeds its size/geometry bounds")
    if not 0 <= stream_tag <= 0xFFFFFFFF or max_encoded_size < 10 or max_candidate_comparisons < 1:
        raise TxtrError("Equipment optimal compression has invalid bounds")
    # Optional reviewed native implementation of this exact parse. Never build
    # a compiler command at runtime. Other platforms and missing/broken helpers
    # retain the Python implementation and its same errors and safety gates.
    helper = _optimal_helper()
    if (os.environ.get("NFL2K5_DISABLE_NATIVE_LZ") != "1"
            and helper is not None and max_encoded_size <= 4 * 1024 * 1024):
        try:
            completed = subprocess.run(
                [str(helper), str(len(source)), str(stream_tag), str(offset_bits),
                 str(max_encoded_size), str(max_candidate_comparisons)],
                input=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=30, check=False,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            result = completed.stdout
            if completed.returncode == 0 and 9 <= len(result) <= max_encoded_size:
                decoded, info = decompress_vc_lz(result, len(source))
                if (decoded == source and info.consumed_bytes == len(result)
                        and result[:9] == struct.pack("<IIB", len(source), stream_tag, offset_bits)):
                    return result
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    count = len(source)
    maximum_distance = (1 << offset_bits) - 1
    maximum_length = (1 << (16 - offset_bits)) + 2
    lengths = array("B", [0]) * count
    distances = array("H", [0]) * count
    chains: dict[bytes, deque[int]] = defaultdict(deque)
    comparisons = 0
    for position in range(count - 2):
        key = source[position:position + 3]
        queue = chains[key]
        # Evict globally, so stale keys cannot retain the whole input window.
        expired = position - maximum_distance - 1
        if expired >= 0:
            old_key = source[expired:expired + 3]
            old = chains[old_key]
            old.popleft()
            if not old and old_key != key:
                del chains[old_key]
        best, distance = 2, 0
        upper = min(maximum_length, count - position)
        for previous in reversed(queue):
            comparisons += 1
            if comparisons > max_candidate_comparisons:
                raise TxtrError("Equipment compression search limit exceeded; simplify the image")
            limit = min(upper, position - previous)
            if limit <= best or source[position:position + best + 1] != source[previous:previous + best + 1]:
                continue
            length = best + 1
            while length < limit and source[position + length] == source[previous + length]:
                length += 1
            best, distance = length, position - previous
            if best == upper:
                break
        if best >= 3:
            lengths[position], distances[position] = best, distance
        queue.append(position)

    costs = array("I", [0]) * (count + 1)
    choices = array("B", [1]) * count
    for position in range(count - 1, -1, -1):
        cost, choice = 9 + costs[position + 1], 1
        for length in range(3, lengths[position] + 1):
            candidate = 17 + costs[position + length]
            if candidate < cost:
                cost, choice = candidate, length
        costs[position], choices[position] = cost, choice
    required = 9 + (costs[0] + 7) // 8
    if required > max_encoded_size:
        raise TxtrError(f"VC-LZ stream is {required} bytes, exceeds {max_encoded_size}-byte bound")
    encoded = bytearray(struct.pack("<IIB", count, stream_tag, offset_bits))
    position = 0
    while position < count:
        flag_position = len(encoded)
        encoded.append(0)
        for bit in range(8):
            if position == count:
                break
            length = choices[position]
            if length == 1:
                encoded.append(source[position])
            else:
                encoded[flag_position] |= 1 << bit
                encoded.extend(struct.pack("<H", distances[position] | ((length - 3) << offset_bits)))
            position += length
    result = bytes(encoded)
    decoded, info = decompress_vc_lz(result, count)
    if len(result) != required or decoded != source or info.consumed_bytes != len(result):
        raise TxtrError("Equipment optimal stream failed independent decode")
    return result
