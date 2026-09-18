"""Bounded optimal token selection for the existing lossless VC-LZ format.

An independent chain can miss a retail slot by a few hundred bytes. The usual
greedy encoder chooses the longest current match. This fallback minimizes the
complete token bit cost (9 per literal, 17 per match), including flag bits. It
keeps the existing distance/length format and the native backward-copy rule:
every match is at most its distance. No decoded byte or sibling changes.
"""

from __future__ import annotations

from array import array
from pathlib import Path
import struct
import os
import hashlib
import platform
import stat
import subprocess
import sys
import time

OPTIMAL_SECONDS = 5.0


TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_txtr import TxtrError, decompress_vc_lz


class EquipmentSearchTimeout(TxtrError):
    """The optional lossless search exhausted its per-item wall-clock budget."""


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


class EquipmentSizeOverflow(TxtrError):
    """A measured size or proved lower bound; never a partial encoded stream."""

    def __init__(self, required: int, budget: int, *, exact: bool):
        self.required = required
        self.exact = exact
        super().__init__(f"VC-LZ stream is {required} bytes, exceeds {budget}-byte bound"
                         + (" (lower bound)" if not exact else ""))


def minimum_equipment_size(count: int, offset_bits: int = 10) -> int:
    """Optimistic format-only bound valid for every possible palette/index byte.

    Literals cost 9 bits for one byte; matches cost 17 for at most L bytes.
    Even granting matches at byte zero, each decoded byte costs at least 17/L.
    Changing palette values cannot change this bound; reducing dimensions can.
    """
    length = (1 << (16 - offset_bits)) + 2
    return 9 + (17 * count + 8 * length - 1) // (8 * length)


def compress_equipment_optimal(source: bytes, *, stream_tag: int, offset_bits: int,
                               max_encoded_size: int,
                               max_candidate_comparisons: int = 50_000_000,
                               timeout: float = OPTIMAL_SECONDS) -> bytes:
    deadline = time.monotonic() + timeout
    def check_time():
        if time.monotonic() >= deadline:
            raise EquipmentSearchTimeout(
                f'Equipment optimal fit reached its {timeout:g}-second limit. '
                'Use Refit equipment to reduce colours or size, or revert this item.')
    check_time()
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
                 str(4 * 1024 * 1024), str(max_candidate_comparisons)],
                input=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=max(0.001, deadline - time.monotonic()), check=False,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            result = completed.stdout
            if completed.returncode == 0 and 9 <= len(result) <= 4 * 1024 * 1024:
                decoded, info = decompress_vc_lz(result, len(source))
                if (decoded == source and info.consumed_bytes == len(result)
                        and result[:9] == struct.pack("<IIB", len(source), stream_tag, offset_bits)):
                    check_time()
                    if len(result) > max_encoded_size:
                        raise EquipmentSizeOverflow(len(result), max_encoded_size, exact=True)
                    return result
            raise EquipmentSearchTimeout('Equipment optimal fit reached its search limit or returned invalid bytes. '
                                         'Use Refit equipment to reduce colours or size, or revert this item.')
        except subprocess.TimeoutExpired as exc:
            raise EquipmentSearchTimeout(
                f'Equipment optimal fit reached its {timeout:g}-second limit. '
                'Use Refit equipment to reduce colours or size, or revert this item.') from exc
        except (EquipmentSizeOverflow, EquipmentSearchTimeout):
            raise
        except (OSError, subprocess.SubprocessError):
            pass
    check_time()
    count = len(source)
    maximum_distance = (1 << offset_bits) - 1
    maximum_length = (1 << (16 - offset_bits)) + 2
    # Exact three-byte hash chains, bounded by the distance window. Ranks let
    # a C-level full-match search skip a run of candidates while charging the
    # SAME number of comparisons as beta 69's nearest-first traversal.
    previous = array("i", [-1]) * count
    ranks = array("I", [0]) * count
    heads: dict[bytes, int] = {}
    window_counts = {}
    within = array("I", [0]) * count
    for position in range(count - 2):
        if position % 256 == 0:
            check_time()
        key = source[position:position + 3]
        within[position] = window_counts.get(key, 0)
        window_counts[key] = within[position] + 1
        prior = heads.get(key, -1)
        previous[position] = prior
        ranks[position] = ranks[prior] + 1 if prior >= 0 else 0
        heads[key] = position
        expired = position - maximum_distance
        if expired >= 0:
            old_key = source[expired:expired + 3]
            window_counts[old_key] -= 1
            if not window_counts[old_key]:
                del window_counts[old_key]
            if heads.get(old_key) == expired:
                del heads[old_key]

    distances = array("H", [0]) * count
    costs = array("I", [0]) * (count + 1)
    choices = array("B", [1]) * count
    comparisons = 0
    for position in range(count - 1, -1, -1):
        if position % 256 == 0:
            check_time()
        best, distance = 2, 0
        upper = min(maximum_length, count - position)
        prior = previous[position]
        cutoff = position - maximum_distance
        prefix = source[position:position + 3]
        full_match = (source.rfind(source[position:position + upper], max(0, cutoff), position)
                      if upper >= 3 else -1)
        if full_match >= 0:
            comparisons += ranks[position] - ranks[full_match]
            best, distance = upper, position - full_match
            prior = -1
        elif upper >= 3:
            # No full-length match exists, so the original nearest-first scan
            # visits every three-byte candidate. C substring searches find the
            # same longest match and nearest tie without walking that chain.
            comparisons += within[position]
            low, high = 2, upper
            fragment = source[position:position + upper]
            while low + 1 < high:
                middle = (low + high) // 2
                match_at = source.rfind(fragment[:middle], max(0, cutoff), position)
                if match_at >= 0:
                    low, distance = middle, position - match_at
                else:
                    high = middle
            best = low
        if comparisons > max_candidate_comparisons:
            raise TxtrError("Equipment compression search limit exceeded; simplify the image")
        cost, choice = 9 + costs[position + 1], 1
        if best >= 3:
            distances[position] = distance
            # array slicing/min/index execute the short range search in C.
            # index retains the first length, and literals retain equal costs.
            following = costs[position + 3:position + best + 1]
            cheapest = min(following)
            if 17 + cheapest < cost:
                cost, choice = 17 + cheapest, 3 + following.index(cheapest)
        costs[position], choices[position] = cost, choice
        if position and position % 256 == 0:
            # A token crossing this boundary ends before position + max_length.
            # Relax the preceding bytes to unlimited maximum-length matches;
            # allow ANY such crossing end. This is a lower bound, not a guess
            # based on entropy or on a previous palette's compressed size.
            lower_bits = (17 * position // maximum_length
                          + min(costs[position:min(count + 1, position + maximum_length)]))
            lower_bytes = 9 + (lower_bits + 7) // 8
            if lower_bytes > max_encoded_size:
                raise EquipmentSizeOverflow(lower_bytes, max_encoded_size, exact=False)
    required = 9 + (costs[0] + 7) // 8
    if required > max_encoded_size:
        raise EquipmentSizeOverflow(required, max_encoded_size, exact=True)
    encoded = bytearray(struct.pack("<IIB", count, stream_tag, offset_bits))
    position = 0
    while position < count:
        check_time()
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
    check_time()
    if len(result) != required or decoded != source or info.consumed_bytes != len(result):
        raise TxtrError("Equipment optimal stream failed independent decode")
    return result
