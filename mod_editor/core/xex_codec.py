"""Bounded, standard-library AES-128-CBC and Xbox XEX LZX decoding.

These are file-format decoders, not general-purpose cryptographic APIs. AES
uses data-dependent tables and is only for reading public retail executables.
LZX uses little-endian 16-bit words, MSB-first codes, persistent trees and
32 KiB frames. XEX patch records use ordinary LZX with a reference window,
not the extended MS-PATCH LZX DELTA stream format.
"""
from __future__ import annotations

import struct

from .errors import ValidationError


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def _mul(a, b):
    value = 0
    while b:
        if b & 1:
            value ^= a
        a = ((a << 1) ^ (0x11B if a & 128 else 0)) & 255
        b >>= 1
    return value


def _aes_tables():
    sbox = []
    for value in range(256):
        inverse, power, exponent = 1, value, 254
        while exponent:
            if exponent & 1:
                inverse = _mul(inverse, power)
            power = _mul(power, power)
            exponent >>= 1
        sbox.append(inverse ^ ((inverse << 1 | inverse >> 7) & 255)
                    ^ ((inverse << 2 | inverse >> 6) & 255)
                    ^ ((inverse << 3 | inverse >> 5) & 255)
                    ^ ((inverse << 4 | inverse >> 4) & 255) ^ 0x63)
    inverse = [0] * 256
    for i, value in enumerate(sbox):
        inverse[value] = i
    tables = [[] for _ in range(4)]
    for value in inverse:
        word = (_mul(value, 14) << 24 | _mul(value, 9) << 16
                | _mul(value, 13) << 8 | _mul(value, 11))
        for table in tables:
            table.append(word)
            word = (word >> 8 | word << 24) & 0xFFFFFFFF
    return sbox, inverse, tables


_SBOX, _INVERSE, _TABLES = _aes_tables()


def aes_cbc_decrypt(key: bytes, data: bytes, progress=None) -> bytes:
    """AES-128 CBC, zero IV, no padding removal (the XEX loader convention)."""
    require(len(key) == 16 and len(data) % 16 == 0,
            "XEX AES key or encrypted payload is not block-aligned")
    words = list(struct.unpack(">4I", key))
    rcon = 1
    for i in range(4, 44):
        word = words[-1]
        if i % 4 == 0:
            word = ((_SBOX[word >> 16 & 255] << 24)
                    | (_SBOX[word >> 8 & 255] << 16)
                    | (_SBOX[word & 255] << 8) | _SBOX[word >> 24]) ^ (rcon << 24)
            rcon = _mul(rcon, 2)
        words.append(words[i - 4] ^ word)
    t0, t1, t2, t3 = _TABLES
    rounds = []
    for round_index in range(9, 0, -1):
        row = []
        for word in words[round_index * 4:round_index * 4 + 4]:
            row.append(t0[_SBOX[word >> 24]] ^ t1[_SBOX[word >> 16 & 255]]
                       ^ t2[_SBOX[word >> 8 & 255]] ^ t3[_SBOX[word & 255]])
        rounds.append(row)
    inv = _INVERSE
    output = bytearray(len(data))
    previous = (0, 0, 0, 0)
    for offset in range(0, len(data), 16):
        block = struct.unpack_from(">4I", data, offset)
        a, b, c, d = (block[i] ^ words[40 + i] for i in range(4))
        for k0, k1, k2, k3 in rounds:
            a, b, c, d = (
                t0[a >> 24] ^ t1[d >> 16 & 255] ^ t2[c >> 8 & 255] ^ t3[b & 255] ^ k0,
                t0[b >> 24] ^ t1[a >> 16 & 255] ^ t2[d >> 8 & 255] ^ t3[c & 255] ^ k1,
                t0[c >> 24] ^ t1[b >> 16 & 255] ^ t2[a >> 8 & 255] ^ t3[d & 255] ^ k2,
                t0[d >> 24] ^ t1[c >> 16 & 255] ^ t2[b >> 8 & 255] ^ t3[a & 255] ^ k3)
        struct.pack_into(">4I", output, offset,
            ((inv[a >> 24] << 24 | inv[d >> 16 & 255] << 16 | inv[c >> 8 & 255] << 8 | inv[b & 255]) ^ words[0] ^ previous[0]),
            ((inv[b >> 24] << 24 | inv[a >> 16 & 255] << 16 | inv[d >> 8 & 255] << 8 | inv[c & 255]) ^ words[1] ^ previous[1]),
            ((inv[c >> 24] << 24 | inv[b >> 16 & 255] << 16 | inv[a >> 8 & 255] << 8 | inv[d & 255]) ^ words[2] ^ previous[2]),
            ((inv[d >> 24] << 24 | inv[c >> 16 & 255] << 16 | inv[b >> 8 & 255] << 8 | inv[a & 255]) ^ words[3] ^ previous[3]))
        previous = block
        if progress is not None and offset % 0x100000 == 0:
            progress("Reading your game's encrypted executable", offset, len(data))
    return bytes(output)


class _Bits:
    def __init__(self, data):
        self.limit = len(data)
        self.data = data + bytes(2)  # lookahead only; drop() checks real EOF
        self.pos = self.buffer = self.count = 0

    def peek(self, n):
        while self.count < n:
            require(self.pos + 2 <= len(self.data), "Truncated XEX LZX bitstream")
            self.buffer = (self.buffer << 16) | self.data[self.pos] | self.data[self.pos + 1] << 8
            self.pos += 2
            self.count += 16
        return (self.buffer >> (self.count - n)) & ((1 << n) - 1)

    def drop(self, n):
        require(self.pos * 8 - self.count + n <= self.limit * 8,
                "Truncated XEX LZX code")
        self.count -= n
        self.buffer &= (1 << self.count) - 1

    def read(self, n):
        value = self.peek(n)
        self.drop(n)
        return value

    def align(self, force=False):
        # Uncompressed headers consume 1..16 bits; frames consume 0..15.
        n = self.count % 16
        self.read(n or (16 if force else 0))

    def raw(self, n):
        require(self.count % 16 == 0, "Unaligned XEX LZX raw block")
        offset = self.pos - self.count // 8
        require(offset + n <= self.limit, "Truncated XEX LZX raw block")
        result = self.data[offset:offset + n]
        self.pos, self.buffer, self.count = offset + n, 0, 0
        return result


class _Huffman:
    def __init__(self, lengths, allow_empty=False):
        self.width = max(lengths, default=0)
        require(self.width <= 16, "Invalid XEX LZX Huffman length")
        if not self.width:
            require(allow_empty, "Empty XEX LZX Huffman tree")
            self.table = []
            return
        counts = [lengths.count(n) for n in range(self.width + 1)]
        counts[0] = 0
        starts, code = [0] * (self.width + 1), 0
        for n in range(1, self.width + 1):
            code = (code + counts[n - 1]) << 1
            starts[n] = code
        require(code + counts[self.width] == 1 << self.width,
                "Incomplete or oversubscribed XEX LZX Huffman tree")
        self.table = [None] * (1 << self.width)
        for symbol, n in enumerate(lengths):
            if n:
                start = starts[n] << (self.width - n)
                size = 1 << (self.width - n)
                self.table[start:start + size] = [(n, symbol)] * size
                starts[n] += 1

    def read(self, bits):
        require(bool(self.table), "XEX LZX match uses an empty length tree")
        n, symbol = self.table[bits.peek(self.width)]
        bits.drop(n)
        return symbol


def _lengths(bits, lengths, start, end):
    tree = _Huffman([bits.read(4) for _ in range(20)])
    while start < end:
        symbol = tree.read(bits)
        count = 1
        if symbol == 17:
            count, value = bits.read(4) + 4, 0
        elif symbol == 18:
            count, value = bits.read(5) + 20, 0
        elif symbol == 19:
            count = bits.read(1) + 4
            value = (lengths[start] - tree.read(bits)) % 17
        else:
            value = (lengths[start] - symbol) % 17
        require(start + count <= end, "XEX LZX tree run exceeds its alphabet")
        lengths[start:start + count] = [value] * count
        start += count


def lzx_decompress(data: bytes, size: int, window_bits: int, *, reference=None,
                   progress=None) -> bytes:
    """Decode XEX normal LZX; a patch record may seed a full 32 KiB window."""
    require(15 <= window_bits <= 21 and 0 < size <= 64 * 1024 * 1024,
            "Unsupported XEX LZX window or image size")
    window_size = 1 << window_bits
    require(reference is None or len(reference) == window_size,
            "XEX LZX reference must fill its window")
    slots = (30, 32, 34, 36, 38, 42, 50)[window_bits - 15]
    extras = [0 if i < 4 else min(17, i // 2 - 1) for i in range(slots)]
    bases = [0]
    for extra in extras[:-1]:
        bases.append(bases[-1] + (1 << extra))
    main_lengths, secondary_lengths = [0] * (256 + slots * 8), [0] * 249
    bits = _Bits(data)
    intel_size = (bits.read(16) << 16 | bits.read(16)) if bits.read(1) else 0
    require(intel_size < 1 << 31, "Unsupported XEX LZX Intel file size")
    # Retain raw history; the optional E8 output transform must not alter it.
    history = bytearray(reference or b"")
    prefix = len(history)
    output = bytearray()
    r0 = r1 = r2 = 1
    remaining = block_type = block_size = 0
    main = secondary = aligned = None
    while len(output) < size:
        frame_start = len(history)
        frame_end = frame_start + min(32768, size - len(output))
        while len(history) < frame_end:
            if not remaining:
                block_type = bits.read(3)
                block_size = remaining = (bits.read(16) << 8) | bits.read(8)
                require(remaining > 0, "Empty XEX LZX block")
                if block_type in (1, 2):
                    if block_type == 2:
                        aligned = _Huffman([bits.read(3) for _ in range(8)])
                    _lengths(bits, main_lengths, 0, 256)
                    _lengths(bits, main_lengths, 256, len(main_lengths))
                    main = _Huffman(main_lengths)
                    _lengths(bits, secondary_lengths, 0, 249)
                    secondary = _Huffman(secondary_lengths, allow_empty=True)
                elif block_type == 3:
                    bits.align(force=True)
                    r0, r1, r2 = struct.unpack("<3I", bits.raw(12))
                else:
                    raise ValidationError(f"Unsupported XEX LZX block type {block_type}")
            run = min(remaining, frame_end - len(history))
            if block_type == 3:
                pad = int(run == remaining and block_size % 2 != 0)
                raw = bits.raw(run + pad)
                history.extend(raw[:run])
                remaining -= run
                continue
            symbol = main.read(bits)
            if symbol < 256:
                history.append(symbol)
                remaining -= 1
                continue
            symbol -= 256
            length = symbol & 7
            if length == 7:
                length += secondary.read(bits)
            length += 2
            slot = symbol >> 3
            if slot == 0:
                distance = r0
            elif slot == 1:
                distance, r1 = r1, r0
                r0 = distance
            elif slot == 2:
                distance, r2 = r2, r0
                r0 = distance
            else:
                extra = extras[slot]
                distance = bases[slot] - 2
                if block_type == 2 and extra >= 3:
                    distance += (bits.read(extra - 3) << 3) + aligned.read(bits)
                else:
                    distance += bits.read(extra)
                r2, r1, r0 = r1, r0, distance
            require(0 < distance <= min(window_size, len(history)),
                    "XEX LZX match exceeds available history")
            require(length <= remaining and len(history) + length <= frame_end,
                    "XEX LZX match exceeds block or frame")
            start = len(history) - distance
            chunk = history[start:start + min(distance, length)]
            history.extend((chunk * ((length + len(chunk) - 1) // len(chunk)))[:length])
            remaining -= length
        bits.align()
        frame = history[frame_start:frame_end]
        if intel_size and len(output) // 32768 <= 32768:
            pos = 0
            while pos < len(frame) - 10:
                if frame[pos] == 0xE8:
                    absolute = struct.unpack_from("<i", frame, pos + 1)[0]
                    current = len(output) + pos
                    if -current <= absolute < intel_size:
                        relative = absolute - current if absolute >= 0 else absolute + intel_size
                        struct.pack_into("<i", frame, pos + 1, relative)
                    pos += 5
                else:
                    pos += 1
        output.extend(frame)
        if progress is not None and len(output) % 0x100000 == 0:
            progress("Unpacking your game's executable", len(output), size)
    require(len(history) - prefix == size, "XEX LZX output size differs")
    return bytes(output)
