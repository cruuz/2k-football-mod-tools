"""XXH3-64, in pure Python, for the game modules.

PCSX2 names a replacement texture by ``XXH3_64bits`` over the texture's GS
block image and, separately, over its CLUT.  A game module that wants to
*derive* those names from a disc -- rather than learn them from a dump --
needs the hash inside the plugin boundary, and a game may import only the
contract and the shared format packages, so the algorithm lives here.

It is the same algorithm ``tools/xxh3.py`` carries for the dev-time NFL 2K5
texture map; that copy is pinned by the release checker and is not touched.
The two are held together by ``tests/mod_editor/test_pcsx2_texture_name.py``,
which hashes the same inputs through both and through the ``xxhash`` C
extension when it happens to be importable.  Nothing shipped requires that
package: the pure path is the product, the extension is an accelerator.

Reference: xxHash 0.8.3 (``XXH_VERSION_NUMBER`` 803), the header PCSX2 vendors.
Only the 64-bit variant is implemented; PCSX2 uses nothing else.  Standard
library only.
"""

from __future__ import annotations

import os
import struct
from typing import Optional

__all__ = [
    "xxh3_64",
    "xxh3_64_hex",
    "xxh3_64_python",
    "KSECRET",
    "ACCELERATED",
    "accelerator_name",
]

_M64 = 0xFFFFFFFFFFFFFFFF
_M32 = 0xFFFFFFFF

PRIME32_1 = 0x9E3779B1
PRIME32_2 = 0x85EBCA77
PRIME32_3 = 0xC2B2AE3D

PRIME64_1 = 0x9E3779B185EBCA87
PRIME64_2 = 0xC2B2AE3D27D4EB4F
PRIME64_3 = 0x165667B19E3779F9
PRIME64_4 = 0x85EBCA77C2B2AE63
PRIME64_5 = 0x27D4EB2F165667C5

PRIME_MX1 = 0x165667919E3779F9
PRIME_MX2 = 0x9FB21C651E98DF25

SECRET_DEFAULT_SIZE = 192
SECRET_SIZE_MIN = 136
SECRET_CONSUME_RATE = 8
SECRET_MERGEACCS_START = 11
SECRET_LASTACC_START = 7
STRIPE_LEN = 64
ACC_NB = STRIPE_LEN // 8

MIDSIZE_MAX = 240
MIDSIZE_STARTOFFSET = 3
MIDSIZE_LASTOFFSET = 17

#: ``XXH3_kSecret``, verbatim.  sha256 of these 192 bytes:
#: 2cf2f88bf9b71283059b6df53e5bcde20adbfd9e8d6ce2c1ab106262bb283bed
KSECRET = bytes((
    0xb8, 0xfe, 0x6c, 0x39, 0x23, 0xa4, 0x4b, 0xbe, 0x7c, 0x01, 0x81, 0x2c,
    0xf7, 0x21, 0xad, 0x1c, 0xde, 0xd4, 0x6d, 0xe9, 0x83, 0x90, 0x97, 0xdb,
    0x72, 0x40, 0xa4, 0xa4, 0xb7, 0xb3, 0x67, 0x1f, 0xcb, 0x79, 0xe6, 0x4e,
    0xcc, 0xc0, 0xe5, 0x78, 0x82, 0x5a, 0xd0, 0x7d, 0xcc, 0xff, 0x72, 0x21,
    0xb8, 0x08, 0x46, 0x74, 0xf7, 0x43, 0x24, 0x8e, 0xe0, 0x35, 0x90, 0xe6,
    0x81, 0x3a, 0x26, 0x4c, 0x3c, 0x28, 0x52, 0xbb, 0x91, 0xc3, 0x00, 0xcb,
    0x88, 0xd0, 0x65, 0x8b, 0x1b, 0x53, 0x2e, 0xa3, 0x71, 0x64, 0x48, 0x97,
    0xa2, 0x0d, 0xf9, 0x4e, 0x38, 0x19, 0xef, 0x46, 0xa9, 0xde, 0xac, 0xd8,
    0xa8, 0xfa, 0x76, 0x3f, 0xe3, 0x9c, 0x34, 0x3f, 0xf9, 0xdc, 0xbb, 0xc7,
    0xc7, 0x0b, 0x4f, 0x1d, 0x8a, 0x51, 0xe0, 0x4b, 0xcd, 0xb4, 0x59, 0x31,
    0xc8, 0x9f, 0x7e, 0xc9, 0xd9, 0x78, 0x73, 0x64, 0xea, 0xc5, 0xac, 0x83,
    0x34, 0xd3, 0xeb, 0xc3, 0xc5, 0x81, 0xa0, 0xff, 0xfa, 0x13, 0x63, 0xeb,
    0x17, 0x0d, 0xdd, 0x51, 0xb7, 0xf0, 0xda, 0x49, 0xd3, 0x16, 0x55, 0x26,
    0x29, 0xd4, 0x68, 0x9e, 0x2b, 0x16, 0xbe, 0x58, 0x7d, 0x47, 0xa1, 0xfc,
    0x8f, 0xf8, 0xb8, 0xd1, 0x7a, 0xd0, 0x31, 0xce, 0x45, 0xcb, 0x3a, 0x8f,
    0x95, 0x16, 0x04, 0x28, 0xaf, 0xd7, 0xfb, 0xca, 0xbb, 0x4b, 0x40, 0x7e,
))
assert len(KSECRET) == SECRET_DEFAULT_SIZE

_U64 = struct.Struct("<Q")
_U32 = struct.Struct("<I")
_U64X8 = struct.Struct("<8Q")


def _rotl64(value: int, count: int) -> int:
    return ((value << count) | (value >> (64 - count))) & _M64


def _swap32(value: int) -> int:
    return (((value << 24) & 0xFF000000) | ((value << 8) & 0x00FF0000)
            | ((value >> 8) & 0x0000FF00) | ((value >> 24) & 0x000000FF))


def _swap64(value: int) -> int:
    return int.from_bytes(_U64.pack(value & _M64), "big")


def _mul128_fold64(left: int, right: int) -> int:
    product = left * right
    return (product ^ (product >> 64)) & _M64


def _avalanche64(h: int) -> int:
    h &= _M64
    h ^= h >> 33
    h = (h * PRIME64_2) & _M64
    h ^= h >> 29
    h = (h * PRIME64_3) & _M64
    return h ^ (h >> 32)


def _avalanche3(h: int) -> int:
    h &= _M64
    h ^= h >> 37
    h = (h * PRIME_MX1) & _M64
    return h ^ (h >> 32)


def _rrmxmx(h: int, length: int) -> int:
    h &= _M64
    h ^= _rotl64(h, 49) ^ _rotl64(h, 24)
    h = (h * PRIME_MX2) & _M64
    h ^= ((h >> 35) + length) & _M64
    h = (h * PRIME_MX2) & _M64
    return h ^ (h >> 28)


def _secret_words(secret: bytes) -> list:
    return [_U64.unpack_from(secret, 8 * i)[0]
            for i in range((len(secret) - 8) // 8 + 1)]


def _init_custom_secret(seed: int) -> bytes:
    out = bytearray(SECRET_DEFAULT_SIZE)
    for i in range(SECRET_DEFAULT_SIZE // 16):
        low = (_U64.unpack_from(KSECRET, 16 * i)[0] + seed) & _M64
        high = (_U64.unpack_from(KSECRET, 16 * i + 8)[0] - seed) & _M64
        _U64.pack_into(out, 16 * i, low)
        _U64.pack_into(out, 16 * i + 8, high)
    return bytes(out)


def _len_1to3(data: bytes, length: int, secret: bytes, seed: int) -> int:
    c1 = data[0]
    c2 = data[length >> 1]
    c3 = data[length - 1]
    combined = ((c1 << 16) | (c2 << 24) | c3 | (length << 8)) & _M32
    bitflip = ((_U32.unpack_from(secret, 0)[0] ^ _U32.unpack_from(secret, 4)[0])
               + seed) & _M64
    return _avalanche64(combined ^ bitflip)


def _len_4to8(data: bytes, length: int, secret: bytes, seed: int) -> int:
    seed ^= (_swap32(seed & _M32) << 32) & _M64
    input1 = _U32.unpack_from(data, 0)[0]
    input2 = _U32.unpack_from(data, length - 4)[0]
    bitflip = ((_U64.unpack_from(secret, 8)[0] ^ _U64.unpack_from(secret, 16)[0])
               - seed) & _M64
    input64 = (input2 + (input1 << 32)) & _M64
    return _rrmxmx(input64 ^ bitflip, length)


def _len_9to16(data: bytes, length: int, secret: bytes, seed: int) -> int:
    bitflip1 = ((_U64.unpack_from(secret, 24)[0] ^ _U64.unpack_from(secret, 32)[0])
                + seed) & _M64
    bitflip2 = ((_U64.unpack_from(secret, 40)[0] ^ _U64.unpack_from(secret, 48)[0])
                - seed) & _M64
    low = _U64.unpack_from(data, 0)[0] ^ bitflip1
    high = _U64.unpack_from(data, length - 8)[0] ^ bitflip2
    acc = (length + _swap64(low) + high + _mul128_fold64(low, high)) & _M64
    return _avalanche3(acc)


def _len_0to16(data: bytes, length: int, secret: bytes, seed: int) -> int:
    if length > 8:
        return _len_9to16(data, length, secret, seed)
    if length >= 4:
        return _len_4to8(data, length, secret, seed)
    if length:
        return _len_1to3(data, length, secret, seed)
    return _avalanche64(
        seed ^ _U64.unpack_from(secret, 56)[0] ^ _U64.unpack_from(secret, 64)[0])


def _mix16(data: bytes, doff: int, secret: bytes, soff: int, seed: int) -> int:
    low = _U64.unpack_from(data, doff)[0]
    high = _U64.unpack_from(data, doff + 8)[0]
    return _mul128_fold64(
        low ^ ((_U64.unpack_from(secret, soff)[0] + seed) & _M64),
        high ^ ((_U64.unpack_from(secret, soff + 8)[0] - seed) & _M64),
    )


def _len_17to128(data: bytes, length: int, secret: bytes, seed: int) -> int:
    acc = (length * PRIME64_1) & _M64
    if length > 32:
        if length > 64:
            if length > 96:
                acc += _mix16(data, 48, secret, 96, seed)
                acc += _mix16(data, length - 64, secret, 112, seed)
            acc += _mix16(data, 32, secret, 64, seed)
            acc += _mix16(data, length - 48, secret, 80, seed)
        acc += _mix16(data, 16, secret, 32, seed)
        acc += _mix16(data, length - 32, secret, 48, seed)
    acc += _mix16(data, 0, secret, 0, seed)
    acc += _mix16(data, length - 16, secret, 16, seed)
    return _avalanche3(acc & _M64)


def _len_129to240(data: bytes, length: int, secret: bytes, seed: int) -> int:
    acc = (length * PRIME64_1) & _M64
    rounds = length // 16
    for i in range(8):
        acc += _mix16(data, 16 * i, secret, 16 * i, seed)
    acc = _avalanche3(acc & _M64)
    for i in range(8, rounds):
        acc += _mix16(data, 16 * i, secret, 16 * (i - 8) + MIDSIZE_STARTOFFSET, seed)
    acc += _mix16(data, length - 16, secret, SECRET_SIZE_MIN - MIDSIZE_LASTOFFSET, seed)
    return _avalanche3(acc & _M64)


def _accumulate(acc: list, data: bytes, offset: int, stripes: int,
                stripe_secrets: list) -> None:
    unpack = _U64X8.unpack_from
    a0, a1, a2, a3, a4, a5, a6, a7 = acc
    for stripe in range(stripes):
        d0, d1, d2, d3, d4, d5, d6, d7 = unpack(data, offset)
        offset += STRIPE_LEN
        s0, s1, s2, s3, s4, s5, s6, s7 = stripe_secrets[stripe]
        k = d0 ^ s0
        a0 += (k & _M32) * (k >> 32) + d1
        k = d1 ^ s1
        a1 += (k & _M32) * (k >> 32) + d0
        k = d2 ^ s2
        a2 += (k & _M32) * (k >> 32) + d3
        k = d3 ^ s3
        a3 += (k & _M32) * (k >> 32) + d2
        k = d4 ^ s4
        a4 += (k & _M32) * (k >> 32) + d5
        k = d5 ^ s5
        a5 += (k & _M32) * (k >> 32) + d4
        k = d6 ^ s6
        a6 += (k & _M32) * (k >> 32) + d7
        k = d7 ^ s7
        a7 += (k & _M32) * (k >> 32) + d6
    acc[:] = [a0, a1, a2, a3, a4, a5, a6, a7]


def _scramble(acc: list, scramble_secret: list) -> None:
    for i in range(ACC_NB):
        value = acc[i] & _M64
        value ^= value >> 47
        value ^= scramble_secret[i]
        acc[i] = (value * PRIME32_1) & _M64


def _merge_accs(acc: list, secret: bytes, start: int) -> int:
    result = start
    for i in range(4):
        result += _mul128_fold64(
            acc[2 * i] ^ _U64.unpack_from(secret, SECRET_MERGEACCS_START + 16 * i)[0],
            acc[2 * i + 1] ^ _U64.unpack_from(secret, SECRET_MERGEACCS_START + 16 * i + 8)[0],
        )
    return _avalanche3(result & _M64)


def _hash_long(data: bytes, length: int, secret: bytes) -> int:
    words = _secret_words(secret)
    secret_size = len(secret)
    stripes_per_block = (secret_size - STRIPE_LEN) // SECRET_CONSUME_RATE
    stripe_secrets = [tuple(words[n:n + ACC_NB]) for n in range(stripes_per_block)]
    scramble_secret = [_U64.unpack_from(secret, secret_size - STRIPE_LEN + 8 * i)[0]
                       for i in range(ACC_NB)]
    block_len = STRIPE_LEN * stripes_per_block
    blocks = (length - 1) // block_len

    acc = [PRIME32_3, PRIME64_1, PRIME64_2, PRIME64_3,
           PRIME64_4, PRIME32_2, PRIME64_5, PRIME32_1]
    offset = 0
    for _ in range(blocks):
        _accumulate(acc, data, offset, stripes_per_block, stripe_secrets)
        _scramble(acc, scramble_secret)
        offset += block_len

    remaining = ((length - 1) - block_len * blocks) // STRIPE_LEN
    _accumulate(acc, data, offset, remaining, stripe_secrets)

    last = [_U64.unpack_from(secret, secret_size - STRIPE_LEN - SECRET_LASTACC_START + 8 * i)[0]
            for i in range(ACC_NB)]
    _accumulate(acc, data, length - STRIPE_LEN, 1, [tuple(last)])

    acc = [value & _M64 for value in acc]
    return _merge_accs(acc, secret, (length * PRIME64_1) & _M64)


def xxh3_64_python(data, seed: int = 0) -> int:
    """XXH3-64 of *data*, always through the pure-Python path."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("xxh3_64 takes bytes-like data")
    if isinstance(data, memoryview):
        data = data.tobytes()
    seed &= _M64
    length = len(data)
    if length <= 16:
        return _len_0to16(data, length, KSECRET, seed)
    if length <= 128:
        return _len_17to128(data, length, KSECRET, seed)
    if length <= MIDSIZE_MAX:
        return _len_129to240(data, length, KSECRET, seed)
    secret = KSECRET if seed == 0 else _init_custom_secret(seed)
    return _hash_long(data, length, secret)


#: Set ``XXH3_PURE_PYTHON=1`` to force the pure path even where the C extension
#: is importable, which is how the tests prove the pure path rather than the
#: accelerator.
_FORCE_PURE = os.environ.get("XXH3_PURE_PYTHON", "") not in ("", "0")

try:
    if _FORCE_PURE:
        raise ImportError("XXH3_PURE_PYTHON is set")
    import xxhash as _xxhash  # type: ignore

    def _xxh3_64_native(data, seed: int = 0) -> int:
        return _xxhash.xxh3_64_intdigest(data, seed)

    ACCELERATED = True
except Exception:  # pragma: no cover - the norm on a machine without xxhash
    _xxh3_64_native = None
    ACCELERATED = False


def accelerator_name() -> Optional[str]:
    """``"xxhash"`` when the C extension is in use, else ``None``."""

    return "xxhash" if ACCELERATED else None


def xxh3_64(data, seed: int = 0) -> int:
    """XXH3-64 as PCSX2 computes it, accelerated when ``xxhash`` is importable."""

    if _xxh3_64_native is not None:
        return _xxh3_64_native(data, seed)
    return xxh3_64_python(data, seed)


def xxh3_64_hex(data, seed: int = 0) -> str:
    """The digest the way PCSX2 prints it: ``%llx``, unpadded, lower case."""

    return "%x" % xxh3_64(data, seed)
