"""Pinned native collection accessors for the library-owned collection table.

No new executable storage: only table displacements and the retail/OS
soundtrack boundary change. Collection-entry playback/freeze is UNWITNESSED.
"""
import struct
from .nfl2k5_cave_oracle import XbeImage

RETAIL_TABLE = 0xAC9C80
# Full instructions, field offsets, and meaning; not a scan-and-replace writer.
SITES = (
    (0x27F410, "b812000000", 1, "count"),  # mov eax, 0x12
    (0x27F425, "83c012", 2, "count"),  # add eax, 0x12
    (0x27F430, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F438, "8b81989cac00", 2, "table"),  # mov eax, dword ptr [ecx + 0xac9c98]
    (0x27F440, "8d71ee", 2, "negative_count"),  # lea esi, [ecx - 0x12]
    (0x27F460, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F468, "8b81809cac00", 2, "table"),  # mov eax, dword ptr [ecx + 0xac9c80]
    (0x27F470, "8d71ee", 2, "negative_count"),  # lea esi, [ecx - 0x12]
    (0x27F490, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F49F, "8b818c9cac00", 2, "table"),  # mov eax, dword ptr [ecx + 0xac9c8c]
    (0x27F4A6, "8b81889cac00", 2, "table"),  # mov eax, dword ptr [ecx + 0xac9c88]
    (0x27F4B4, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F4C3, "8b86989cac00", 2, "table"),  # mov eax, dword ptr [esi + 0xac9c98]
    (0x27F4D1, "8b869c9cac00", 2, "table"),  # mov eax, dword ptr [esi + 0xac9c9c]
    (0x27F4E6, "8b86989cac00", 2, "table"),  # mov eax, dword ptr [esi + 0xac9c98]
    (0x27F502, "8d71ee", 2, "negative_count"),  # lea esi, [ecx - 0x12]
    (0x27F520, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F528, "8b81909cac00", 2, "table"),  # mov eax, dword ptr [ecx + 0xac9c90]
    (0x27F535, "8b89949cac00", 2, "table"),  # mov ecx, dword ptr [ecx + 0xac9c94]
    (0x27F551, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F55F, "8b879c9cac00", 2, "table"),  # mov eax, dword ptr [edi + 0xac9c9c]
    (0x27F571, "8b8f809cac00", 2, "table"),  # mov ecx, dword ptr [edi + 0xac9c80]
    (0x27F587, "8d79ee", 2, "negative_count"),  # lea edi, [ecx - 0x12]
    (0x27F5D0, "83f912", 2, "count"),  # cmp ecx, 0x12
    (0x27F5D8, "8b81849cac00", 2, "table"),  # mov eax, dword ptr [ecx + 0xac9c84]
    (0x27F95B, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x27F963, "8b80809cac00", 2, "table"),  # mov eax, dword ptr [eax + 0xac9c80]
    (0x27F96B, "8d48ee", 2, "negative_count"),  # lea ecx, [eax - 0x12]
    (0x27F984, "83fa12", 2, "count"),  # cmp edx, 0x12
    (0x27F9BD, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x27F9C8, "8b909c9cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c9c]
    (0x27F9E0, "8d48ee", 2, "negative_count"),  # lea ecx, [eax - 0x12]
    (0x27FA0D, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x27FA18, "8b909c9cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c9c]
    (0x27FA30, "8d48ee", 2, "negative_count"),  # lea ecx, [eax - 0x12]
    (0x27FA42, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x27FA4D, "8b909c9cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c9c]
    (0x27FC9A, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x27FCA5, "8b909c9cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c9c]
    (0x27FCC4, "8d48ee", 2, "negative_count"),  # lea ecx, [eax - 0x12]
    (0x27FD5C, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x27FD67, "8b909c9cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c9c]
    (0x27FF24, "83fe12", 2, "count"),  # cmp esi, 0x12
    (0x27FF31, "3bb8989cac00", 2, "table"),  # cmp edi, dword ptr [eax + 0xac9c98]
    (0x27FF39, "8d5eee", 2, "negative_count"),  # lea ebx, [esi - 0x12]
    (0x280028, "83f812", 2, "count"),  # cmp eax, 0x12
    (0x280034, "8b90889cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c88]
    (0x280097, "8b909c9cac00", 2, "table"),  # mov edx, dword ptr [eax + 0xac9c9c]
    (0x280104, "8b80809cac00", 2, "table"),  # mov eax, dword ptr [eax + 0xac9c80]
    (0x280141, "83e912", 2, "count"),  # sub ecx, 0x12
    (0x280186, "83ea12", 2, "count"),  # sub edx, 0x12
)


def instructions(table, count):
    if not 18 <= count <= 20:
        raise ValueError("Collection table must have 18..20 rows")
    for va, encoded, offset, kind in SITES:
        before = bytes.fromhex(encoded)
        after = bytearray(before)
        if kind == "table":
            old = struct.unpack_from("<I", before, offset)[0]
            struct.pack_into("<I", after, offset, table + old - RETAIL_TABLE)
        elif kind == "negative_count":
            after[offset] = (-count) & 255
        elif len(before) == 5:  # mov eax, imm32: number of on-disc collections
            struct.pack_into("<I", after, offset, count)
        else:
            after[offset] = count
        yield va, before, bytes(after)


def matches(payload, table=RETAIL_TABLE, count=18):
    image = XbeImage(payload)
    return all(image.read(va, len(after)) == after for va, before, after in instructions(table, count))


def apply(payload, table, count, *, previous_table=RETAIL_TABLE, previous_count=18):
    image = XbeImage(payload)
    if not matches(payload, previous_table, previous_count):
        raise ValueError("Mixed/foreign native collection accessors; rebuild from the original disc")
    result = bytearray(payload)
    edits = []
    for va, before, after in instructions(table, count):
        at = image.offset(va, len(after))
        result[at:at+len(after)] = after
        edits.append(dict(label="collection_accessor", va=hex(va), size=len(after)))
    return bytes(result), edits
