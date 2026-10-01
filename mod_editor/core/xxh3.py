"""Canonical XXH3-64 (seed 0, default secret), in Python with NumPy for long inputs.

The 2K5 Edition xemu names every texture it can replace by an "x2" key whose hashes are canonical XXH3-64
(``nfl2k5_xemu_texture_packs``). The Studio computes the same keys from disc bytes without running the game, so
it needs the same function, and the Windows runtime has no ``xxhash`` wheel. NumPy (when installed) vectorises the
long-input path; without it the same path runs in plain Python, slower and with identical results. This is the
reference algorithm of xxHash 0.8.3 (``XXH3_64bits``), written out;
``tests/mod_editor/test_nfl2k5_xemu_texture_packs.py`` checks it against vectors produced by the C library (every
code path and the block seams of the long path), with and without NumPy.

Note what "canonical" rules out: xemu's own build of xxHash is compiled with ``XXH_CPU_LITTLE_ENDIAN=0`` (a meson
option default), which byte-swaps every word on x86 and gives different values. The Edition pins the canonical
form inside its texture hook; nothing here reproduces the byte-swapped variant.
"""

from __future__ import annotations

import importlib

M64 = (1 << 64) - 1
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

SECRET = bytes.fromhex(
    "b8fe6c3923a44bbe7c01812cf721ad1cded46de9839097db7240a4a4b7b3671f"
    "cb79e64eccc0e578825ad07dccff7221b8084674f743248ee03590e6813a264c"
    "3c2852bb91c300cb88d0658b1b532ea371644897a20df94e3819ef46a9deacd8"
    "a8fa763fe39c343ff9dcbbc7c70b4f1d8a51e04bcdb45931c89f7ec9d9787364"
    "eac5ac8334d3ebc3c581a0fffa1363eb170ddd51b7f0da49d316552629d4689e"
    "2b16be587d47a1fc8ff8b8d17ad031ce45cb3a8f95160428afd7fbcabb4b407e"
)
SECRET_SIZE = 192
STRIPE_LEN = 64
STRIPES_PER_BLOCK = (SECRET_SIZE - STRIPE_LEN) // 8  # 16
BLOCK_LEN = STRIPE_LEN * STRIPES_PER_BLOCK  # 1024
INIT_ACC = (PRIME32_3, PRIME64_1, PRIME64_2, PRIME64_3, PRIME64_4, PRIME32_2, PRIME64_5, PRIME32_1)


def _r32(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _r64(data, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 8], "little")


def _swap32(value: int) -> int:
    return int.from_bytes(value.to_bytes(4, "little"), "big")


def _swap64(value: int) -> int:
    return int.from_bytes(value.to_bytes(8, "little"), "big")


def _rotl64(value: int, amount: int) -> int:
    return ((value << amount) | (value >> (64 - amount))) & M64


def _fold64(a: int, b: int) -> int:
    product = a * b
    return (product ^ (product >> 64)) & M64


def _xxh64_avalanche(h: int) -> int:
    h ^= h >> 33
    h = (h * PRIME64_2) & M64
    h ^= h >> 29
    h = (h * PRIME64_3) & M64
    return h ^ (h >> 32)


def _avalanche(h: int) -> int:
    h ^= h >> 37
    h = (h * PRIME_MX1) & M64
    return h ^ (h >> 32)


def _rrmxmx(h: int, length: int) -> int:
    h ^= _rotl64(h, 49) ^ _rotl64(h, 24)
    h = (h * PRIME_MX2) & M64
    h ^= (h >> 35) + length
    h = (h * PRIME_MX2) & M64
    return h ^ (h >> 28)


def _mix16(data, offset: int, secret_offset: int) -> int:
    return _fold64(_r64(data, offset) ^ _r64(SECRET, secret_offset),
                   _r64(data, offset + 8) ^ _r64(SECRET, secret_offset + 8))


def _short(data, n: int) -> int:
    if n == 0:
        return _xxh64_avalanche(_r64(SECRET, 56) ^ _r64(SECRET, 64))
    if n <= 3:
        combined = (data[0] << 16) | (data[n >> 1] << 24) | data[n - 1] | (n << 8)
        return _xxh64_avalanche(combined ^ ((_r32(SECRET, 0) ^ _r32(SECRET, 4)) & M64))
    if n <= 8:
        input64 = _r32(data, n - 4) + (_r32(data, 0) << 32)
        return _rrmxmx(input64 ^ (_r64(SECRET, 8) ^ _r64(SECRET, 16)), n)
    if n <= 16:
        lo = _r64(data, 0) ^ (_r64(SECRET, 24) ^ _r64(SECRET, 32))
        hi = _r64(data, n - 8) ^ (_r64(SECRET, 40) ^ _r64(SECRET, 48))
        return _avalanche((n + _swap64(lo) + hi + _fold64(lo, hi)) & M64)
    if n <= 128:
        acc = (n * PRIME64_1) & M64
        if n > 32:
            if n > 64:
                if n > 96:
                    acc += _mix16(data, 48, 96) + _mix16(data, n - 64, 112)
                acc += _mix16(data, 32, 64) + _mix16(data, n - 48, 80)
            acc += _mix16(data, 16, 32) + _mix16(data, n - 32, 48)
        acc += _mix16(data, 0, 0) + _mix16(data, n - 16, 16)
        return _avalanche(acc & M64)
    # 129..240
    acc = (n * PRIME64_1) & M64
    for i in range(8):
        acc += _mix16(data, 16 * i, 16 * i)
    acc_end = _mix16(data, n - 16, 136 - 17)
    acc = _avalanche(acc & M64)
    for i in range(8, n // 16):
        acc_end += _mix16(data, 16 * i, 16 * (i - 8) + 3)
    return _avalanche((acc + acc_end) & M64)


_NUMPY = None


def _numpy():
    """NumPy and the secret as NumPy arrays, or None when NumPy is not installed (the Studio runs without it)."""
    global _NUMPY
    if _NUMPY is None:
        try:
            np = importlib.import_module("numpy")
        except ImportError:
            _NUMPY = False
        else:
            keys = np.frombuffer(SECRET, dtype="<u8").astype(np.uint64)  # 24 words at 8-byte steps
            _NUMPY = {
                "np": np,
                "stripe_keys": np.stack([keys[s:s + 8] for s in range(STRIPES_PER_BLOCK)]),  # (16, 8)
                "scramble_keys": np.frombuffer(SECRET[SECRET_SIZE - STRIPE_LEN:], dtype="<u8").astype(np.uint64),
                "swap": np.array([1, 0, 3, 2, 5, 4, 7, 6]),
                "lo32": np.uint64(0xFFFFFFFF), "s32": np.uint64(32), "s47": np.uint64(47),
                "p32": np.uint64(PRIME32_1),
            }
    return _NUMPY or None


def _merge(acc: list[int], n: int) -> int:
    result = (n * PRIME64_1) & M64
    for i in range(4):
        result += _fold64(acc[2 * i] ^ _r64(SECRET, 11 + 16 * i), acc[2 * i + 1] ^ _r64(SECRET, 11 + 16 * i + 8))
    return _avalanche(result & M64)


def _accumulate_py(acc: list[int], data, offset: int, key_offset: int) -> None:
    for i in range(8):
        value = _r64(data, offset + 8 * i)
        keyed = value ^ _r64(SECRET, key_offset + 8 * i)
        acc[i ^ 1] = (acc[i ^ 1] + value) & M64
        acc[i] = (acc[i] + (keyed & 0xFFFFFFFF) * (keyed >> 32)) & M64


def _long_py(data: bytes, n: int) -> int:
    acc = list(INIT_ACC)
    nb_blocks = (n - 1) // BLOCK_LEN
    for block in range(nb_blocks):
        base = block * BLOCK_LEN
        for stripe in range(STRIPES_PER_BLOCK):
            _accumulate_py(acc, data, base + stripe * STRIPE_LEN, stripe * 8)
        for i in range(8):
            value = acc[i]
            value ^= value >> 47
            value ^= _r64(SECRET, SECRET_SIZE - STRIPE_LEN + 8 * i)
            acc[i] = (value * PRIME32_1) & M64
    start = nb_blocks * BLOCK_LEN
    for stripe in range(((n - 1) - start) // STRIPE_LEN):
        _accumulate_py(acc, data, start + stripe * STRIPE_LEN, stripe * 8)
    _accumulate_py(acc, data, n - STRIPE_LEN, SECRET_SIZE - STRIPE_LEN - 7)
    return _merge(acc, n)


def _long_np(data: bytes, n: int, npx: dict) -> int:
    np = npx["np"]
    lo32, s32, s47, swap = npx["lo32"], npx["s32"], npx["s47"], npx["swap"]

    def stripe_sums(words, keys):
        keyed = words ^ keys
        product = (keyed & lo32) * (keyed >> s32)
        return (words[..., swap] + product).sum(axis=-2, dtype=np.uint64)

    acc = np.array(INIT_ACC, dtype=np.uint64)
    nb_blocks = (n - 1) // BLOCK_LEN
    with np.errstate(over="ignore"):
        if nb_blocks:
            words = np.frombuffer(data, dtype="<u8", count=nb_blocks * BLOCK_LEN // 8).astype(np.uint64)
            per_block = stripe_sums(words.reshape(nb_blocks, STRIPES_PER_BLOCK, 8), npx["stripe_keys"])
            for block in per_block:
                acc = acc + block
                acc = acc ^ (acc >> s47)
                acc = acc ^ npx["scramble_keys"]
                acc = acc * npx["p32"]
        start = nb_blocks * BLOCK_LEN
        stripes = ((n - 1) - start) // STRIPE_LEN
        if stripes:
            words = np.frombuffer(data, dtype="<u8", count=stripes * 8, offset=start).astype(np.uint64)
            acc = acc + stripe_sums(words.reshape(stripes, 8), npx["stripe_keys"][:stripes])
    lanes = [int(value) for value in acc]
    _accumulate_py(lanes, data, n - STRIPE_LEN, SECRET_SIZE - STRIPE_LEN - 7)
    return _merge(lanes, n)


def _long(data: bytes, n: int, use_numpy: bool = True) -> int:
    npx = _numpy() if use_numpy else None
    if npx is None:
        return _long_py(data, n)
    return _long_np(data, n, npx)


def xxh3_64(data) -> int:
    """XXH3_64bits(data, len(data)) with seed 0: the same value as xxHash's C library on any platform."""
    view = bytes(data)
    n = len(view)
    if n <= 240:
        return _short(view, n)
    return _long(view, n)


def xxh3_64_hex(data) -> str:
    """The 16-digit lowercase hex form used in x2 texture keys."""
    return f"{xxh3_64(data):016x}"
