#!/usr/bin/env python3
"""Prove APF's loaded-XEX / XenonRecomp dispatch-table boundary.

This is a metadata-only, pre-execution probe.  It parses the untouched retail
XEX security header and page descriptors, a transient decoded PE image, the
generated XenonRecomp configuration/mapping table, and pinned local primary
source.  It never calls translated title code or retains decoded retail bytes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


SCHEMA = "apf2k8_xex_dispatch_boundary/v1"

EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_XENONRECOMP_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"

EXPECTED_IMAGE_BASE = 0x82000000
EXPECTED_IMAGE_SIZE = 0x03380000
EXPECTED_IMAGE_END = EXPECTED_IMAGE_BASE + EXPECTED_IMAGE_SIZE
EXPECTED_SECURITY_OFFSET = 0x90
EXPECTED_SECURITY_HEADER_SIZE = 0x4EC4
EXPECTED_DESCRIPTOR_COUNT = 824
EXPECTED_DESCRIPTOR_TABLE_SHA256 = (
    "672db62025d2ebff99922949de735401fcc4090b88a370f5df8c611b9f76943a"
)
EXPECTED_SECURITY_HEADER_SHA256 = (
    "7b34cf71c6c246b7a804f1d878f6611bf7cdaca5c4bf0bb3b65ecb5f57b12d21"
)
EXPECTED_PAGE_SIZE = 0x10000

EXPECTED_PE_SIZE_OF_IMAGE = 0x03468C00
EXPECTED_PE_SECTION_ALIGNMENT = 0x10000
EXPECTED_RELOC_RVA = 0x032F0200
EXPECTED_RELOC_VIRTUAL_SIZE = 0x000E9410

EXPECTED_CODE_BASE = 0x84630000
EXPECTED_CODE_SIZE = 0x006D904C
EXPECTED_MAPPING_COUNT = 60_731
EXPECTED_MAPPING_MIN = 0x84630000
EXPECTED_MAPPING_MAX = 0x84D0903C
EXPECTED_CONFIG_SHA256 = (
    "a8c820b2efb2426c097be73ef7024fc7422b76150c26c3f12ff9a1074a62fc84"
)
EXPECTED_MAPPING_SHA256 = (
    "9050c9a14781b40e0329ed9abca512f780cfba6ca709c8e8326397a66de6b5bd"
)
EXPECTED_EXTRACTOR_SHA256 = (
    "26587b2c040efa6c92eda382d30fb8f050c0be0ce173b799442bd4517e3b2f73"
)
EXPECTED_XENONUTILS_LIBRARY_SHA256 = (
    "0653cc0005ae3904e0c8e856678101dcf54d887a1f1f96702e7f5e5205692b37"
)

XENON_SOURCE_HASHES = {
    "XenonUtils/xex.h":
        "d75db078add62416cb465f06550c89e470382895d098ee8e95ad49b6901fc9b8",
    "XenonUtils/xex.cpp":
        "7ac994d7c12aa05842d2b3f8df930eac6d5bc92d83c48cc853d453f15bb526f7",
    "XenonUtils/image.h":
        "6d37785a83a9ca42628c26adbf9c748e4f506dddd10b7653c9acf4178768e28d",
    "XenonRecomp/recompiler.cpp":
        "30e7ea5b4d8a225bc3e0ac71aebd1a0af7bcde5aaf5679517719b559c9cd777a",
    "XenonUtils/ppc_context.h":
        "369acaf639c52bb25ee8a2c6a555c7875912f0692b1e8220ea8dab0384e42263",
}

XENIA_SOURCE_HASHES = {
    "src/xenia/kernel/util/xex2_info.h":
        "3df4a38e4a05f5d6e2a55be566727380dafeea683b2564093915ba515f89b9a9",
    "src/xenia/cpu/xex_module.h":
        "49a26f2fee8a48f640f3b816c9b4ede07c1426d0c28bc749a838de6264597fd2",
    "src/xenia/cpu/xex_module.cc":
        "36a30e1bc54b9854cbd2572b74e366e733460c5df6edf2b29542de36575858f2",
    "src/xenia/kernel/user_module.cc":
        "fcc297e2d1a77a8f3dbb1901721ed06a9ce1865bfcce7779409a3cc0c1258582",
    "src/xenia/memory.cc":
        "f29ceea394bda0910eab039d06e3f2142339b0a9c3cb8b703666cc399e70afb8",
}

SECTION_TYPES = {
    1: "code",
    2: "read_write_data",
    3: "read_only_data",
}


class BoundaryError(RuntimeError):
    """Raised when pinned boundary evidence changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BoundaryError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def file_pin(path: Path) -> dict[str, object]:
    actual = sha256_file(path)
    return {"path": str(path), "size": path.stat().st_size, "sha256": actual}


def source_pin(path: Path, expected: str) -> dict[str, object]:
    pin = file_pin(path)
    actual = str(pin["sha256"])
    require(actual == expected, f"pinned source changed: {path}")
    return pin


def git_output(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        check=False,
    )
    require(completed.returncode == 0,
            f"git {' '.join(args)} failed for {repo}: {completed.stderr.strip()}")
    return completed.stdout.strip()


def assert_tracked_clean(repo: Path) -> None:
    for args in (("diff", "--quiet", "HEAD", "--"),
                 ("diff", "--cached", "--quiet", "HEAD", "--")):
        completed = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
            check=False,
        )
        require(completed.returncode == 0,
                f"tracked changes present in pinned source: {repo}")


def be32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, "big-endian u32 is out of range")
    return struct.unpack_from(">I", data, offset)[0]


def le16(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 2, "little-endian u16 is out of range")
    return struct.unpack_from("<H", data, offset)[0]


def le32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, "little-endian u32 is out of range")
    return struct.unpack_from("<I", data, offset)[0]


def hx(value: int) -> str:
    return f"0x{value:08X}"


def overlap_size(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def parse_xex(data: bytes) -> dict[str, object]:
    require(sha256(data) == EXPECTED_XEX_SHA256, "retail XEX hash changed")
    require(data[:4] == b"XEX2", "input is not XEX2")
    payload_offset = be32(data, 0x08)
    security_offset = be32(data, 0x10)
    require(security_offset == EXPECTED_SECURITY_OFFSET,
            "XEX security offset changed")
    security_size = be32(data, security_offset)
    image_size = be32(data, security_offset + 0x04)
    load_address = be32(data, security_offset + 0x110)
    descriptor_count = be32(data, security_offset + 0x180)
    require(security_size == EXPECTED_SECURITY_HEADER_SIZE,
            "XEX security header size changed")
    require(image_size == EXPECTED_IMAGE_SIZE, "XEX image size changed")
    require(load_address == EXPECTED_IMAGE_BASE, "XEX load address changed")
    require(descriptor_count == EXPECTED_DESCRIPTOR_COUNT,
            "XEX page descriptor count changed")
    require(security_size == 0x184 + descriptor_count * 0x18,
            "security header does not end after its page descriptors")
    require(security_offset + security_size <= payload_offset,
            "security header overlaps encrypted/compressed payload")

    descriptor_start = security_offset + 0x184
    descriptor_end = descriptor_start + descriptor_count * 0x18
    descriptors: list[dict[str, int]] = []
    for index in range(descriptor_count):
        offset = descriptor_start + index * 0x18
        raw = be32(data, offset)
        page_count = raw >> 4
        section_type = raw & 0xF
        require(page_count > 0, "zero-page XEX descriptor")
        require(section_type in SECTION_TYPES, "unknown XEX section type")
        descriptors.append({
            "index": index,
            "raw": raw,
            "page_count": page_count,
            "section_type": section_type,
        })

    page_count_sum = sum(row["page_count"] for row in descriptors)
    descriptor_span = page_count_sum * EXPECTED_PAGE_SIZE
    require(descriptor_span == image_size,
            "XEX page descriptors disagree with security image size")
    require(all(row["page_count"] == 1 for row in descriptors),
            "APF no longer has one digest descriptor per image page")
    require(sha256(data[descriptor_start:descriptor_end]) ==
            EXPECTED_DESCRIPTOR_TABLE_SHA256,
            "XEX descriptor table hash changed")
    require(sha256(data[security_offset:security_offset + security_size]) ==
            EXPECTED_SECURITY_HEADER_SHA256,
            "XEX security header hash changed")

    runs: list[dict[str, object]] = []
    run_start_index = 0
    run_start_page = 0
    current_type = descriptors[0]["section_type"]
    page_cursor = 0
    for index, descriptor in enumerate(descriptors):
        if descriptor["section_type"] != current_type:
            runs.append(make_run(
                run_start_index, index, run_start_page, page_cursor,
                current_type, load_address,
            ))
            run_start_index = index
            run_start_page = page_cursor
            current_type = descriptor["section_type"]
        page_cursor += descriptor["page_count"]
    runs.append(make_run(
        run_start_index, descriptor_count, run_start_page, page_cursor,
        current_type, load_address,
    ))

    expected_runs = [
        (0, 611, 3, 0x00000000, 0x02630000),
        (611, 721, 1, 0x02630000, 0x02D10000),
        (721, 814, 2, 0x02D10000, 0x032E0000),
        (814, 824, 3, 0x032E0000, 0x03380000),
    ]
    observed_runs = [(
        row["descriptor_start_index"], row["descriptor_end_index_exclusive"],
        row["section_type"], int(str(row["rva_start"]), 0),
        int(str(row["rva_end_exclusive"]), 0),
    ) for row in runs]
    require(observed_runs == expected_runs, "XEX descriptor runs changed")

    counts = Counter(row["section_type"] for row in descriptors)
    return {
        "main_header_payload_offset": hx(payload_offset),
        "security_offset": hx(security_offset),
        "security_header_size": security_size,
        "security_header_end": hx(security_offset + security_size),
        "security_header_sha256": EXPECTED_SECURITY_HEADER_SHA256,
        "load_address": hx(load_address),
        "security_image_size": image_size,
        "security_image_end_exclusive": hx(load_address + image_size),
        "page_size_for_0x80000000_xex_heap": EXPECTED_PAGE_SIZE,
        "page_descriptor_count": descriptor_count,
        "page_descriptor_count_by_type": {
            SECTION_TYPES[key]: counts[key] for key in sorted(counts)
        },
        "all_descriptor_page_counts": 1,
        "page_count_sum": page_count_sum,
        "descriptor_span_bytes": descriptor_span,
        "descriptor_table_sha256": EXPECTED_DESCRIPTOR_TABLE_SHA256,
        "security_size_equals_descriptor_span": image_size == descriptor_span,
        "descriptor_runs": runs,
    }


def make_run(
    descriptor_start: int,
    descriptor_end: int,
    page_start: int,
    page_end: int,
    section_type: int,
    image_base: int,
) -> dict[str, object]:
    rva_start = page_start * EXPECTED_PAGE_SIZE
    rva_end = page_end * EXPECTED_PAGE_SIZE
    return {
        "descriptor_start_index": descriptor_start,
        "descriptor_end_index_exclusive": descriptor_end,
        "section_type": section_type,
        "section_type_name": SECTION_TYPES[section_type],
        "page_count": page_end - page_start,
        "byte_count": rva_end - rva_start,
        "rva_start": hx(rva_start),
        "rva_end_exclusive": hx(rva_end),
        "guest_start": hx(image_base + rva_start),
        "guest_end_exclusive": hx(image_base + rva_end),
    }


def parse_pe(data: bytes) -> dict[str, object]:
    require(len(data) == EXPECTED_IMAGE_SIZE, "decoded PE length changed")
    require(sha256(data) == EXPECTED_DECODED_SHA256,
            "decoded PE hash changed")
    require(data[:2] == b"MZ", "decoded image has no MZ header")
    pe_offset = le32(data, 0x3C)
    require(data[pe_offset:pe_offset + 4] == b"PE\0\0",
            "decoded image has no PE signature")
    coff = pe_offset + 4
    section_count = le16(data, coff + 2)
    optional_size = le16(data, coff + 16)
    optional = coff + 20
    require(le16(data, optional) == 0x10B, "decoded image is not PE32")
    entry_rva = le32(data, optional + 16)
    image_base = le32(data, optional + 28)
    section_alignment = le32(data, optional + 32)
    size_of_image = le32(data, optional + 56)
    require(image_base == EXPECTED_IMAGE_BASE, "PE image base changed")
    require(section_alignment == EXPECTED_PE_SECTION_ALIGNMENT,
            "PE section alignment changed")
    require(size_of_image == EXPECTED_PE_SIZE_OF_IMAGE,
            "PE SizeOfImage changed")

    sections = []
    section_table = optional + optional_size
    for index in range(section_count):
        offset = section_table + index * 40
        require(offset + 40 <= len(data), "PE section header is truncated")
        name = data[offset:offset + 8].split(b"\0", 1)[0].decode("ascii")
        virtual_size = le32(data, offset + 8)
        virtual_address = le32(data, offset + 12)
        sections.append({
            "name": name,
            "virtual_address": virtual_address,
            "virtual_size": virtual_size,
            "declared_end": virtual_address + virtual_size,
        })
    reloc = next((row for row in sections if row["name"] == ".reloc"), None)
    require(reloc is not None, "PE .reloc section is missing")
    require(reloc["virtual_address"] == EXPECTED_RELOC_RVA and
            reloc["virtual_size"] == EXPECTED_RELOC_VIRTUAL_SIZE,
            "PE .reloc declaration changed")
    highest = max(sections, key=lambda row: row["declared_end"])
    highest_end = int(highest["declared_end"])
    require(highest["name"] == ".reloc", "PE highest section changed")
    require(highest_end == EXPECTED_RELOC_RVA + EXPECTED_RELOC_VIRTUAL_SIZE,
            "PE highest declared section end changed")

    return {
        "decoded_file_size": len(data),
        "decoded_sha256": EXPECTED_DECODED_SHA256,
        "image_base": hx(image_base),
        "entry_rva": hx(entry_rva),
        "section_count": section_count,
        "section_alignment": section_alignment,
        "size_of_image": size_of_image,
        "size_of_image_end_exclusive": hx(image_base + size_of_image),
        "size_of_image_exceeds_xex_span_by": size_of_image - len(data),
        "size_of_image_alignment_remainder": size_of_image % section_alignment,
        "size_of_image_is_section_aligned":
            size_of_image % section_alignment == 0,
        "highest_declared_section": str(highest["name"]),
        "highest_declared_section_end_rva_exclusive": hx(highest_end),
        "highest_section_exceeds_xex_span_by": highest_end - len(data),
        "size_of_image_exceeds_highest_section_by": size_of_image - highest_end,
        "classification": (
            "larger_stale_or_non_authoritative_PE_metadata_for_XEX_loading"
        ),
    }


def macro(text: str, name: str) -> int:
    match = re.search(
        rf"^#define\s+{re.escape(name)}\s+(0x[0-9A-Fa-f]+)(?:ull)?\s*$",
        text, re.MULTILINE,
    )
    require(match is not None, f"generated macro missing: {name}")
    return int(match.group(1), 16)


def line_of(text: str, needle: str) -> int:
    require(needle in text, f"pinned source statement missing: {needle}")
    return text[:text.index(needle)].count("\n") + 1


def inspect_sources(xenon: Path, xenia: Path) -> tuple[dict[str, object],
                                                        dict[str, object]]:
    xenon_commit = git_output(xenon, "rev-parse", "HEAD")
    xenia_commit = git_output(xenia, "rev-parse", "HEAD")
    require(xenon_commit == EXPECTED_XENONRECOMP_COMMIT,
            "XenonRecomp commit changed")
    require(xenia_commit == EXPECTED_XENIA_COMMIT, "Xenia commit changed")
    assert_tracked_clean(xenon)
    assert_tracked_clean(xenia)

    xenon_pins = {}
    for relative, expected in XENON_SOURCE_HASHES.items():
        xenon_pins[relative] = source_pin(xenon / relative, expected)
    xenia_pins = {}
    for relative, expected in XENIA_SOURCE_HASHES.items():
        xenia_pins[relative] = source_pin(xenia / relative, expected)

    xex_h = (xenon / "XenonUtils/xex.h").read_text(encoding="utf-8")
    xex_cpp = (xenon / "XenonUtils/xex.cpp").read_text(encoding="utf-8")
    recompiler = (xenon / "XenonRecomp/recompiler.cpp").read_text(
        encoding="utf-8")
    context = (xenon / "XenonUtils/ppc_context.h").read_text(encoding="utf-8")
    require("uint32_t info : 4;" in xex_h and
            "uint32_t pageCount : 28;" in xex_h and
            "be<uint32_t> imageSize;" in xex_h,
            "XenonRecomp XEX structure contract changed")
    require("size_t imageSize = security->imageSize;" in xex_cpp,
            "XenonRecomp initial image size source changed")
    require("uint32_t uncompressedSize = security->imageSize;" in xex_cpp,
            "XenonRecomp LZX output size source changed")
    require("image.size = security->imageSize;" in xex_cpp,
            "XenonRecomp Image.size source changed")
    require('println("#define PPC_IMAGE_SIZE 0x{:X}ull", image.size);' in
            recompiler, "PPC_IMAGE_SIZE emission changed")
    lookup_needle = (
        "#define PPC_LOOKUP_FUNC(x, y) *(PPCFunc**)(x + PPC_IMAGE_BASE + "
        "PPC_IMAGE_SIZE + (uint64_t(uint32_t(y) - PPC_CODE_BASE) * 2))"
    )
    require(lookup_needle in context, "XenonRecomp dispatch lookup changed")
    require(len(re.findall(r"(?:->|\.)\s*SizeOfImage", xex_cpp)) == 0,
            "XenonRecomp loader began consuming PE SizeOfImage")

    xenia_info = (xenia / "src/xenia/kernel/util/xex2_info.h").read_text(
        encoding="utf-8")
    xenia_header = (xenia / "src/xenia/cpu/xex_module.h").read_text(
        encoding="utf-8")
    xenia_module = (xenia / "src/xenia/cpu/xex_module.cc").read_text(
        encoding="utf-8")
    xenia_user = (xenia / "src/xenia/kernel/user_module.cc").read_text(
        encoding="utf-8")
    xenia_memory = (xenia / "src/xenia/memory.cc").read_text(encoding="utf-8")
    require("xe::be<uint32_t> image_size;" in xenia_info and
            "uint32_t page_count : 28;" in xenia_info,
            "Xenia XEX security structures changed")
    sum_needle = "total_size += desc.page_count * heap->page_size();"
    require(sum_needle in xenia_header, "Xenia image_size() contract changed")
    require("uint32_t uncompressed_size = image_size();" in xenia_module,
            "Xenia normal-LZX output size source changed")
    require("->AllocFixed(" in xenia_module and
            "std::memset(buffer, 0, uncompressed_size);" in xenia_module and
            "buffer, uncompressed_size," in xenia_module,
            "Xenia allocation/decompression contract changed")
    require("ldr_data->full_image_size = security_header->image_size;" in
            xenia_user, "Xenia loader-data image size source changed")
    require("0x80000000, 0x10000000, 64 * 1024" in xenia_memory and
            "} else if (address < 0x90000000) {" in xenia_memory and
            "return &heaps_.v80000000;" in xenia_memory,
            "Xenia 0x80000000 XEX heap page-size contract changed")

    pe_size_token_count = 0
    for path in (xenia / "src/xenia").rglob("*"):
        if path.suffix not in {".cc", ".h"} or not path.is_file():
            continue
        pe_size_token_count += path.read_text(
            encoding="utf-8", errors="replace").count("SizeOfImage")
    require(pe_size_token_count == 0,
            "pinned Xenia source now references PE SizeOfImage")

    xenon_evidence = {
        "commit": xenon_commit,
        "tracked_sources_unchanged": True,
        "xex_security_image_size_struct": {
            "path": "XenonUtils/xex.h",
            "line": line_of(xex_h, "be<uint32_t> imageSize;"),
        },
        "normal_lzx_output_size_from_security_image_size": {
            "path": "XenonUtils/xex.cpp",
            "line": line_of(
                xex_cpp, "uint32_t uncompressedSize = security->imageSize;"),
        },
        "image_size_stored_from_security_image_size": {
            "path": "XenonUtils/xex.cpp",
            "line": line_of(xex_cpp, "image.size = security->imageSize;"),
        },
        "generated_ppc_image_size_from_image_size": {
            "path": "XenonRecomp/recompiler.cpp",
            "line": line_of(
                recompiler,
                'println("#define PPC_IMAGE_SIZE 0x{:X}ull", image.size);'),
        },
        "dispatch_lookup_after_image_span": {
            "path": "XenonUtils/ppc_context.h",
            "line": line_of(context, lookup_needle),
        },
        "pe_size_of_image_member_accesses_in_loader": 0,
        "source_files": xenon_pins,
    }
    xenia_evidence = {
        "commit": xenia_commit,
        "tracked_sources_unchanged": True,
        "xex_heap_for_apf_base": "v80000000",
        "xex_heap_page_size": EXPECTED_PAGE_SIZE,
        "heap_definition": {
            "path": "src/xenia/memory.cc",
            "line": line_of(
                xenia_memory,
                "0x80000000, 0x10000000, 64 * 1024"),
        },
        "image_size_sums_descriptor_pages": {
            "path": "src/xenia/cpu/xex_module.h",
            "line": line_of(xenia_header, sum_needle),
        },
        "normal_lzx_allocation_and_output_size_from_descriptor_sum": {
            "path": "src/xenia/cpu/xex_module.cc",
            "line": line_of(
                xenia_module, "uint32_t uncompressed_size = image_size();"),
        },
        "guest_loader_full_image_size_from_security_header": {
            "path": "src/xenia/kernel/user_module.cc",
            "line": line_of(
                xenia_user,
                "ldr_data->full_image_size = security_header->image_size;"),
        },
        "pe_size_of_image_token_occurrences_in_src_xenia_cc_h": 0,
        "source_files": xenia_pins,
    }
    return xenon_evidence, xenia_evidence


def inspect_generated(config_path: Path,
                      mapping_path: Path) -> dict[str, object]:
    require(sha256_file(config_path) == EXPECTED_CONFIG_SHA256,
            "generated ppc_config.h changed")
    require(sha256_file(mapping_path) == EXPECTED_MAPPING_SHA256,
            "generated ppc_func_mapping.cpp changed")
    config = config_path.read_text(encoding="utf-8")
    image_base = macro(config, "PPC_IMAGE_BASE")
    image_size = macro(config, "PPC_IMAGE_SIZE")
    code_base = macro(config, "PPC_CODE_BASE")
    code_size = macro(config, "PPC_CODE_SIZE")
    require((image_base, image_size, code_base, code_size) == (
        EXPECTED_IMAGE_BASE, EXPECTED_IMAGE_SIZE,
        EXPECTED_CODE_BASE, EXPECTED_CODE_SIZE,
    ), "generated PPC span macros changed")

    mapping_text = mapping_path.read_text(encoding="utf-8")
    addresses = [
        int(match.group(1), 16)
        for match in re.finditer(
            r"^\s*\{\s*(0x[0-9A-Fa-f]+),\s*[^}]+\},\s*$",
            mapping_text, re.MULTILINE,
        )
        if int(match.group(1), 16) != 0
    ]
    require(len(addresses) == EXPECTED_MAPPING_COUNT,
            "generated mapping count changed")
    require(addresses == sorted(set(addresses)),
            "generated mappings are not sorted and unique")
    require(min(addresses) == EXPECTED_MAPPING_MIN and
            max(addresses) == EXPECTED_MAPPING_MAX,
            "generated mapping address range changed")
    require(all(address % 4 == 0 for address in addresses),
            "unaligned generated mapping")

    dispatch_start = image_base + image_size
    pointer_size = 8
    logical_bytes = code_size * 2 + pointer_size
    dispatch_end = dispatch_start + logical_bytes
    last_slot_start = dispatch_start + (max(addresses) - code_base) * 2
    last_slot_end = last_slot_start + pointer_size
    require(last_slot_end <= dispatch_end, "last mapping exceeds dispatch range")
    page_rounded_bytes = (logical_bytes + 4095) & ~4095
    return {
        "ppc_image_base": hx(image_base),
        "ppc_image_size": image_size,
        "ppc_code_base": hx(code_base),
        "ppc_code_size": code_size,
        "host_function_pointer_size": pointer_size,
        "lookup_formula": (
            "base + PPC_IMAGE_BASE + PPC_IMAGE_SIZE + "
            "((uint32_t(target) - PPC_CODE_BASE) * 2)"
        ),
        "dispatch_start": hx(dispatch_start),
        "dispatch_logical_bytes": logical_bytes,
        "dispatch_end_exclusive": hx(dispatch_end),
        "dispatch_host_page_rounded_bytes": page_rounded_bytes,
        "dispatch_host_page_rounded_end_exclusive":
            hx(dispatch_start + page_rounded_bytes),
        "mapping_count": len(addresses),
        "minimum_mapped_guest_function": hx(min(addresses)),
        "maximum_mapped_guest_function": hx(max(addresses)),
        "last_populated_slot_start": hx(last_slot_start),
        "last_populated_slot_end_exclusive": hx(last_slot_end),
        "all_mapping_slots_inside_logical_range": True,
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xex", type=Path,
        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--pe", type=Path, required=True,
                        help="transient decoded PE from tools/xex_extract_pe.cpp")
    parser.add_argument("--xenonrecomp", type=Path,
                        default=Path("tools/vendor/XenonRecomp"))
    parser.add_argument(
        "--xenia", type=Path,
        default=Path("/media/noah/Storage/.codex-tmp/xenia-source"))
    parser.add_argument("--config", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered/ppc_config.h"))
    parser.add_argument(
        "--mapping", type=Path,
        default=Path("build-static-recomp-apf/ppc-filtered/ppc_func_mapping.cpp"))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    xex_path = resolve(args.xex)
    pe_path = resolve(args.pe)
    xenon_path = resolve(args.xenonrecomp)
    xenia_path = resolve(args.xenia)
    config_path = resolve(args.config)
    mapping_path = resolve(args.mapping)
    output_path = resolve(args.json)
    extractor_path = root / "tools/xex_extract_pe.cpp"
    xenonutils_library_path = (
        xenon_path / "build/XenonUtils/libXenonUtils.a")
    for path in (xex_path, pe_path, config_path, mapping_path):
        require(path.is_file(), f"required file is missing: {path}")
    for path in (xenon_path, xenia_path):
        require(path.is_dir(), f"required source tree is missing: {path}")
    require(sha256_file(extractor_path) == EXPECTED_EXTRACTOR_SHA256,
            "bounded XEX extractor source changed")
    require(sha256_file(xenonutils_library_path) ==
            EXPECTED_XENONUTILS_LIBRARY_SHA256,
            "pinned XenonUtils library changed")

    xex_bytes = xex_path.read_bytes()
    pe_bytes = pe_path.read_bytes()
    xex = parse_xex(xex_bytes)
    pe = parse_pe(pe_bytes)
    xenon, xenia = inspect_sources(xenon_path, xenia_path)
    dispatch = inspect_generated(config_path, mapping_path)

    loaded_start = EXPECTED_IMAGE_BASE
    loaded_end = EXPECTED_IMAGE_END
    dispatch_start = int(str(dispatch["dispatch_start"]), 0)
    dispatch_end = int(str(dispatch["dispatch_end_exclusive"]), 0)
    pe_end = EXPECTED_IMAGE_BASE + EXPECTED_PE_SIZE_OF_IMAGE
    reloc_end = EXPECTED_IMAGE_BASE + EXPECTED_RELOC_RVA + EXPECTED_RELOC_VIRTUAL_SIZE
    loaded_overlap = overlap_size(
        loaded_start, loaded_end, dispatch_start, dispatch_end)
    pe_metadata_overlap = overlap_size(
        EXPECTED_IMAGE_BASE, pe_end, dispatch_start, dispatch_end)
    reloc_metadata_overlap = overlap_size(
        EXPECTED_IMAGE_BASE + EXPECTED_RELOC_RVA, reloc_end,
        dispatch_start, dispatch_end)
    require(loaded_end == dispatch_start, "dispatch is not at loaded end")
    require(loaded_overlap == 0, "dispatch overlaps loaded title bytes")
    require(pe_metadata_overlap == EXPECTED_PE_SIZE_OF_IMAGE - EXPECTED_IMAGE_SIZE,
            "PE metadata overlap changed")

    portme = (
        "// PORTME: reserve guest [0x85380000, 0x86133000) from every "
        "dynamic allocator and MMIO mapping before title execution, or move "
        "the XenonRecomp indirect table entirely host-side; loaded XEX bytes "
        "do not overlap the table, but runtime guest allocations/accesses are "
        "not yet proved collision-free."
    )
    report = {
        "schema": SCHEMA,
        "result": {
            "authoritative_loaded_xex_span_proved": True,
            "security_image_size_equals_page_descriptor_span": True,
            "xenonrecomp_uses_security_span_for_decode_and_ppc_image_size": True,
            "xenia_primary_source_independently_corroborates_span": True,
            "dispatch_starts_at_loaded_span_exclusive_end": True,
            "loaded_title_byte_overlap_with_dispatch": loaded_overlap,
            "pe_size_of_image_controls_xex_loader": False,
            "pe_declared_tail_is_loaded_title_bytes": False,
            "runtime_dynamic_allocation_mmio_collision_free_proved": False,
            "title_code_executed": False,
            "original_or_vendor_files_modified": False,
        },
        "xex_security_and_pages": xex,
        "pe_metadata": pe,
        "xenonrecomp_loader_contract": xenon,
        "xenia_primary_source_corroboration": xenia,
        "dispatch": {
            **dispatch,
            "loaded_xex_span": "[0x82000000, 0x85380000)",
            "loaded_title_byte_overlap": loaded_overlap,
            "pe_size_of_image_metadata_overlap_bytes": pe_metadata_overlap,
            "reloc_virtual_metadata_overlap_bytes": reloc_metadata_overlap,
            "runtime_collision_policy": (
                "move_table_host_side_preferred; otherwise reserve the "
                "4KiB-rounded guest range before allocators/MMIO"
            ),
            "runtime_collision_policy_implemented": False,
        },
        "interpretation": {
            "authoritative_boundary": (
                "APF's XEX security image size and 824 security page descriptors "
                "independently end at 0x85380000; XenonRecomp and Xenia both "
                "load/decompress this XEX span rather than PE SizeOfImage."
            ),
            "pe_mismatch": (
                "PE SizeOfImage 0x03468C00 is larger, unaligned to its own "
                "0x10000 SectionAlignment, and non-authoritative for these XEX "
                "loaders. Its overlap is metadata, not loaded title bytes."
            ),
            "remaining_risk": (
                "The in-guest dispatch table consumes about 13.7 MiB after the "
                "image. Static bytes do not collide, but future guest heaps or "
                "MMIO may unless the range is reserved or the table moves "
                "host-side."
            ),
            "scope": (
                "Metadata/source reconciliation only; no translated function, "
                "entry point, import, or title instruction was executed."
            ),
        },
        "sources": {
            "retail_xex": {
                "path": str(xex_path),
                "size": len(xex_bytes),
                "sha256": EXPECTED_XEX_SHA256,
            },
            "transient_decoded_pe": {
                "preserved": False,
                "size": len(pe_bytes),
                "sha256": EXPECTED_DECODED_SHA256,
            },
            "generated_config": source_pin(config_path, EXPECTED_CONFIG_SHA256),
            "generated_mapping": source_pin(
                mapping_path, EXPECTED_MAPPING_SHA256),
            "extractor_source": source_pin(
                extractor_path, EXPECTED_EXTRACTOR_SHA256),
            "xenonutils_library": source_pin(
                xenonutils_library_path,
                EXPECTED_XENONUTILS_LIBRARY_SHA256),
            "generator": file_pin(Path(__file__).resolve()),
            "retail_or_decoded_bytes_embedded_in_report": False,
        },
        "portme": [portme],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_XEX_DISPATCH_BOUNDARY_PASS "
        "xex_span=0x03380000 descriptors=824 dispatch=0x85380000 "
        "loaded_overlap=0 pe_loader_authority=no runtime_collision=PORTME "
        "title_executed=no"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BoundaryError, OSError, ValueError, struct.error,
            subprocess.SubprocessError) as exc:
        raise SystemExit(f"error: {exc}") from exc
