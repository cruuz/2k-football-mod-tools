#!/usr/bin/env python3
"""Build and run APF's bounded, pre-execution guest-image bootstrap probe.

The temporary harness decodes the untouched retail XEX, copies the decoded
image into a MAP_NORESERVE 4 GiB guest reservation, populates XenonRecomp's
generated indirect-call table, and ledgers imported data and TLS metadata.  It
does not call the title entry point, any translated title function, or an XDK
import.  All compiled files and decoded retail bytes remain temporary.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile


SCHEMA = "apf2k8_static_recomp_guest_image_bootstrap/v1"
EXPECTED_TU_COUNT = 237
EXPECTED_NUMBERED_COUNT = 236
EXPECTED_MAPPING_COUNT = 60_731
EXPECTED_CPP_MANIFEST = (
    "5e90f504e1291e3bcc2ba2e3688da07d44ba7b7bfbf10ac62beffb48d1e79132"
)
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_XENONUTILS_SHA256 = (
    "0653cc0005ae3904e0c8e856678101dcf54d887a1f1f96702e7f5e5205692b37"
)
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_IMAGE_BASE = 0x82000000
EXPECTED_DECODED_SIZE = 0x03380000
EXPECTED_PE_IMAGE_SIZE = 54_955_008
EXPECTED_XEX_SECURITY_HEADER_SIZE = 0x4EC4
EXPECTED_XEX_PAGE_SIZE = 0x10000
EXPECTED_XEX_PAGE_DESCRIPTOR_COUNT = 824
EXPECTED_XEX_DESCRIPTOR_TABLE_SHA256 = (
    "672db62025d2ebff99922949de735401fcc4090b88a370f5df8c611b9f76943a"
)
EXPECTED_CODE_BASE = 0x84630000
EXPECTED_CODE_SIZE = 0x006D904C
EXPECTED_ENTRY = 0x84BE9D08
EXPECTED_SECTION_COUNT = 9
EXPECTED_CALLABLE_IMPORTS = 334
EXPECTED_DATA_IMPORTS = 13
EXPECTED_TLS = {
    "slot_count": 64,
    "raw_data_address": 0,
    "data_size": 0,
    "raw_data_size": 0,
}
SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class BootstrapError(RuntimeError):
    """Raised when a pinned input or a pre-execution invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BootstrapError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def pin(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": digest_file(path),
    }


def parse_hex(value: object) -> int:
    if isinstance(value, int):
        return value
    require(isinstance(value, str), f"not an integer field: {value!r}")
    return int(value, 0)


def be32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, "big-endian word is out of range")
    return struct.unpack_from(">I", data, offset)[0]


def parse_xex_execution_metadata(data: bytes) -> dict[str, object]:
    """Read the exact XEX fields used by the bootstrap, independent of JSON."""
    require(len(data) >= 0x18 and data[:4] == b"XEX2", "input is not XEX2")
    header_size = be32(data, 8)
    security_offset = be32(data, 16)
    header_count = be32(data, 20)
    require(header_size <= len(data), "XEX payload offset is out of range")
    require(security_offset + 0x184 <= len(data), "XEX security header is truncated")
    require(0x18 + header_count * 8 <= len(data), "XEX optional table is truncated")

    optional: dict[int, tuple[int, int]] = {}
    for index in range(header_count):
        offset = 0x18 + index * 8
        key = be32(data, offset)
        value = be32(data, offset + 4)
        require(key not in optional, "duplicate XEX optional header")
        optional[key] = (offset + 4, value)

    def optional_bytes(key: int, size: int) -> bytes:
        require(key in optional, f"missing XEX optional header 0x{key:08X}")
        inline_offset, value = optional[key]
        storage = key & 0xFF
        if storage == 0:
            start = inline_offset
        elif storage == 1:
            start = inline_offset
        else:
            start = value
        require(start + size <= len(data), "XEX optional payload is out of range")
        return data[start:start + size]

    entry = be32(optional_bytes(0x00010100, 4), 0)
    image_base = be32(optional_bytes(0x00010201, 4), 0)
    tls_bytes = optional_bytes(0x00020104, 16)
    tls = {
        "slot_count": be32(tls_bytes, 0),
        "raw_data_address": be32(tls_bytes, 4),
        "data_size": be32(tls_bytes, 8),
        "raw_data_size": be32(tls_bytes, 12),
    }

    security_header_size = be32(data, security_offset)
    page_descriptor_count = be32(data, security_offset + 0x180)
    require(security_header_size == 0x184 + page_descriptor_count * 0x18,
            "XEX security header/page descriptor size is invalid")
    require(security_offset + security_header_size <= header_size,
            "XEX security header extends into the payload")
    descriptor_start = security_offset + 0x184
    descriptor_end = descriptor_start + page_descriptor_count * 0x18
    page_counts = []
    section_types = []
    for index in range(page_descriptor_count):
        raw = be32(data, descriptor_start + index * 0x18)
        page_counts.append(raw >> 4)
        section_types.append(raw & 0xF)
    require(all(count > 0 for count in page_counts),
            "XEX contains a zero-page descriptor")
    require(all(section_type in {1, 2, 3}
                for section_type in section_types),
            "XEX contains an unknown page descriptor type")
    return {
        "payload_offset": header_size,
        "security_offset": security_offset,
        "optional_header_count": header_count,
        "security_image_size": be32(data, security_offset + 4),
        "security_load_address": be32(data, security_offset + 0x110),
        "security_header_size": security_header_size,
        "page_descriptor_count": page_descriptor_count,
        "page_count_sum": sum(page_counts),
        "all_descriptor_page_counts_one": all(
            count == 1 for count in page_counts),
        "page_descriptor_type_counts": {
            str(section_type): section_types.count(section_type)
            for section_type in sorted(set(section_types))
        },
        "descriptor_table_sha256": digest(
            data[descriptor_start:descriptor_end]),
        "image_base": image_base,
        "entry_point": entry,
        "tls": tls,
    }


def expected_names() -> list[str]:
    return ["ppc_func_mapping.cpp", *[
        f"ppc_recomp.{index}.cpp" for index in range(EXPECTED_NUMBERED_COUNT)
    ]]


def compile_one(
    compiler: str,
    source: Path,
    output: Path,
    include_paths: list[Path],
) -> dict[str, object]:
    command = [compiler, "-std=c++20", "-O0", "-c", str(source), "-o", str(output)]
    command.extend(f"-I{path}" for path in include_paths)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "name": source.name,
        "return_code": completed.returncode,
        "stdout_empty": completed.stdout == "",
        "stderr_empty": completed.stderr == "",
        "diagnostic_sha256": digest(completed.stderr.encode("utf-8")),
        "object_created": output.is_file(),
        "object_size": output.stat().st_size if output.is_file() else 0,
    }


def stub_source(names: list[str]) -> str:
    lines = [
        '#include "ppc_recomp_shared.h"\n',
        "#include <cstdlib>\n\n",
        "[[noreturn]] static void apf_portme_import_trap() { std::abort(); }\n\n",
        "// PORTME: implement exact guest-ABI semantics before title execution.\n",
        "#define APF_PORTME_IMPORT(symbol) PPC_FUNC(symbol) { (void)ctx; (void)base; apf_portme_import_trap(); }\n\n",
    ]
    lines.extend(f"APF_PORTME_IMPORT({name})\n" for name in names)
    lines.append("\n#undef APF_PORTME_IMPORT\n")
    return "".join(lines)


def c_string(value: str) -> str:
    return json.dumps(value)


def harness_source(
    sections: list[dict[str, object]],
    data_items: list[dict[str, object]],
) -> str:
    section_rows = []
    for section in sections:
        section_rows.append(
            "    {"
            f"{c_string(str(section['name']))}, "
            f"0x{parse_hex(section['virtual_address']):08X}u, "
            f"0x{parse_hex(section['virtual_size']):08X}u, "
            f"0x{parse_hex(section['raw_pointer']):08X}u, "
            f"0x{parse_hex(section['raw_size']):08X}u, "
            f"0x{parse_hex(section['characteristics']):08X}u"
            "},"
        )
    import_rows = []
    for item in data_items:
        import_rows.append(
            "    {"
            f"{c_string(str(item['name']))}, "
            f"0x{parse_hex(item['reference_address']):08X}u, "
            f"0x{parse_hex(item['raw_word']):08X}u"
            "},"
        )

    return f'''#include "ppc_recomp_shared.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>

#ifndef MAP_NORESERVE
#error MAP_NORESERVE is required for this bounded probe
#endif

namespace {{

constexpr std::uint64_t kGuestReservationSize = 0x100000000ull;
constexpr std::uint32_t kImageBase = 0x{EXPECTED_IMAGE_BASE:08X}u;
constexpr std::uint32_t kDecodedSize = 0x{EXPECTED_DECODED_SIZE:08X}u;
constexpr std::uint32_t kPeImageSize = 0x{EXPECTED_PE_IMAGE_SIZE:08X}u;
constexpr std::uint32_t kEntry = 0x{EXPECTED_ENTRY:08X}u;
constexpr std::size_t kMappingCount = {EXPECTED_MAPPING_COUNT};

struct SectionExpected {{
    const char* name;
    std::uint32_t virtual_address;
    std::uint32_t virtual_size;
    std::uint32_t raw_pointer;
    std::uint32_t raw_size;
    std::uint32_t characteristics;
}};

constexpr std::array<SectionExpected, {len(section_rows)}> kSections{{{{
{os.linesep.join(section_rows)}
}}}};

struct DataImportExpected {{
    const char* name;
    std::uint32_t guest_address;
    std::uint32_t original_word;
}};

constexpr std::array<DataImportExpected, {len(import_rows)}> kDataImports{{{{
{os.linesep.join(import_rows)}
}}}};

std::uint16_t le16(const std::vector<std::uint8_t>& data, std::size_t offset) {{
    if (offset + 2 > data.size()) return 0;
    return std::uint16_t(data[offset]) | (std::uint16_t(data[offset + 1]) << 8);
}}

std::uint32_t le32(const std::vector<std::uint8_t>& data, std::size_t offset) {{
    if (offset + 4 > data.size()) return 0;
    return std::uint32_t(data[offset]) |
        (std::uint32_t(data[offset + 1]) << 8) |
        (std::uint32_t(data[offset + 2]) << 16) |
        (std::uint32_t(data[offset + 3]) << 24);
}}

std::uint32_t be32(const std::uint8_t* data) {{
    return (std::uint32_t(data[0]) << 24) |
        (std::uint32_t(data[1]) << 16) |
        (std::uint32_t(data[2]) << 8) | std::uint32_t(data[3]);
}}

bool section_name_equal(const std::vector<std::uint8_t>& data,
                        std::size_t offset, const char* expected) {{
    char actual[9]{{}};
    std::memcpy(actual, data.data() + offset, 8);
    return std::string(actual) == expected;
}}

std::size_t page_round(std::size_t size, std::size_t page_size) {{
    return (size + page_size - 1) & ~(page_size - 1);
}}

int fail(const char* invariant) {{
    std::cerr << "bootstrap invariant failed: " << invariant << '\\n';
    return 1;
}}

}}  // namespace

int main(int argc, char** argv) {{
    if (argc != 2) return fail("arguments");
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) return fail("decoded image open");
    std::vector<std::uint8_t> image{{
        std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()}};
    if (image.size() != kDecodedSize) return fail("decoded image size");

    if (image[0] != 'M' || image[1] != 'Z') return fail("DOS signature");
    const std::size_t pe = le32(image, 0x3C);
    if (pe + 24 > image.size() || le32(image, pe) != 0x00004550u)
        return fail("PE signature");
    const std::size_t coff = pe + 4;
    if (le16(image, coff) != 0x01F2u ||
        le16(image, coff + 2) != kSections.size()) return fail("COFF identity");
    const std::size_t optional = coff + 20;
    const std::size_t optional_size = le16(image, coff + 16);
    if (le16(image, optional) != 0x010Bu || optional_size < 0x60)
        return fail("optional header");
    if (le32(image, optional + 16) + le32(image, optional + 28) != kEntry ||
        le32(image, optional + 28) != kImageBase ||
        le32(image, optional + 56) != kPeImageSize ||
        le32(image, optional + 60) != 1024u) return fail("image addresses");

    const std::size_t section_table = optional + optional_size;
    if (section_table + kSections.size() * 40 > image.size())
        return fail("section table range");
    bool entry_in_text = false;
    for (std::size_t i = 0; i < kSections.size(); ++i) {{
        const auto& expected = kSections[i];
        const std::size_t offset = section_table + i * 40;
        if (!section_name_equal(image, offset, expected.name) ||
            le32(image, offset + 8) != expected.virtual_size ||
            le32(image, offset + 12) != expected.virtual_address ||
            le32(image, offset + 16) != expected.raw_size ||
            le32(image, offset + 20) != expected.raw_pointer ||
            le32(image, offset + 36) != expected.characteristics)
            return fail("section header identity");
        if (std::string(expected.name) == ".text" &&
            kEntry >= kImageBase + expected.virtual_address &&
            kEntry < kImageBase + expected.virtual_address + expected.virtual_size)
            entry_in_text = true;
        if (expected.virtual_address >= kDecodedSize)
            return fail("section backing start");
    }}
    if (!entry_in_text) return fail("entry text ownership");

    const long page_value = ::sysconf(_SC_PAGESIZE);
    if (page_value != 4096) return fail("pinned page size");
    const std::size_t page_size = static_cast<std::size_t>(page_value);
    void* allocation = ::mmap(nullptr, kGuestReservationSize, PROT_NONE,
        MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (allocation == MAP_FAILED) return fail("MAP_NORESERVE reservation");
    auto* guest = static_cast<std::uint8_t*>(allocation);
    auto cleanup_failure = [&]() {{ ::munmap(allocation, kGuestReservationSize); }};

    const std::size_t image_offset = PPC_IMAGE_BASE;
    if (PPC_IMAGE_BASE != kImageBase || PPC_IMAGE_SIZE != kDecodedSize ||
        PPC_CODE_BASE != 0x{EXPECTED_CODE_BASE:08X}ull ||
        PPC_CODE_SIZE != 0x{EXPECTED_CODE_SIZE:08X}ull) {{
        cleanup_failure(); return fail("generated PPC config");
    }}
    if (::mprotect(guest + image_offset, page_round(kDecodedSize, page_size),
                   PROT_READ | PROT_WRITE) != 0) {{
        cleanup_failure(); return fail("image mprotect");
    }}
    std::memcpy(guest + image_offset, image.data(), image.size());
    if (std::memcmp(guest + image_offset, image.data(), image.size()) != 0) {{
        cleanup_failure(); return fail("whole image copy");
    }}
    for (const auto& section : kSections) {{
        const std::size_t backed = section.virtual_address >= kDecodedSize ? 0 :
            std::min<std::size_t>(section.virtual_size,
                                  kDecodedSize - section.virtual_address);
        if (backed == 0 || std::memcmp(
                guest + image_offset + section.virtual_address,
                image.data() + section.virtual_address, backed) != 0) {{
            cleanup_failure(); return fail("section copy");
        }}
    }}

    std::array<std::uint32_t, kDataImports.size()> import_snapshot{{}};
    for (std::size_t i = 0; i < kDataImports.size(); ++i) {{
        const auto& item = kDataImports[i];
        if (item.guest_address < kImageBase ||
            std::uint64_t(item.guest_address) + 4 >
                std::uint64_t(kImageBase) + kDecodedSize) {{
            cleanup_failure(); return fail("data import range");
        }}
        const auto* slot = guest + item.guest_address;
        import_snapshot[i] = be32(slot);
        if (import_snapshot[i] != item.original_word) {{
            cleanup_failure(); return fail("data import ordinal");
        }}
        for (std::size_t j = 0; j < i; ++j) {{
            if (kDataImports[j].guest_address == item.guest_address) {{
                cleanup_failure(); return fail("duplicate data import");
            }}
        }}
    }}

    constexpr std::size_t dispatch_offset = PPC_IMAGE_BASE + PPC_IMAGE_SIZE;
    constexpr std::size_t dispatch_bytes = PPC_CODE_SIZE * 2 + sizeof(PPCFunc*);
    if (dispatch_offset + dispatch_bytes > kGuestReservationSize) {{
        cleanup_failure(); return fail("dispatch range");
    }}
    const std::size_t dispatch_protected = page_round(dispatch_bytes, page_size);
    if (::mprotect(guest + dispatch_offset, dispatch_protected,
                   PROT_READ | PROT_WRITE) != 0) {{
        cleanup_failure(); return fail("dispatch mprotect");
    }}
    std::memset(guest + dispatch_offset, 0, dispatch_protected);

    std::size_t mapping_count = 0;
    bool entry_mapping = false;
    std::size_t entry_mapping_index = 0;
    std::size_t entry_mapping_occurrences = 0;
    std::size_t previous_guest = 0;
    for (; mapping_count <= kMappingCount; ++mapping_count) {{
        const auto& mapping = PPCFuncMappings[mapping_count];
        if (mapping.host == nullptr) break;
        if (mapping_count >= kMappingCount ||
            mapping.guest < PPC_CODE_BASE ||
            mapping.guest >= PPC_CODE_BASE + PPC_CODE_SIZE ||
            (mapping.guest & 3) != 0 ||
            (mapping_count != 0 && mapping.guest <= previous_guest)) {{
            cleanup_failure(); return fail("function mapping ledger");
        }}
        previous_guest = mapping.guest;
        PPC_LOOKUP_FUNC(guest, mapping.guest) = mapping.host;
        if (mapping.guest == kEntry) {{
            entry_mapping = mapping.host == _xstart;
            entry_mapping_index = mapping_count;
            ++entry_mapping_occurrences;
        }}
    }}
    if (mapping_count != kMappingCount ||
        PPCFuncMappings[mapping_count].guest != 0 ||
        !entry_mapping || entry_mapping_occurrences != 1) {{
        cleanup_failure(); return fail("function mapping cardinality");
    }}
    std::size_t roundtrip_count = 0;
    for (std::size_t i = 0; i < mapping_count; ++i) {{
        if (PPC_LOOKUP_FUNC(guest, PPCFuncMappings[i].guest) !=
            PPCFuncMappings[i].host) {{
            cleanup_failure(); return fail("dispatch roundtrip");
        }}
        ++roundtrip_count;
    }}

    for (std::size_t i = 0; i < kDataImports.size(); ++i) {{
        if (be32(guest + kDataImports[i].guest_address) != import_snapshot[i]) {{
            cleanup_failure(); return fail("data import preservation");
        }}
    }}
    if (std::memcmp(guest + image_offset, image.data(), image.size()) != 0) {{
        cleanup_failure(); return fail("post-dispatch image preservation");
    }}

    if (::mprotect(guest + image_offset, page_round(kDecodedSize, page_size),
                   PROT_READ) != 0 ||
        ::mprotect(guest + dispatch_offset, dispatch_protected, PROT_READ) != 0) {{
        cleanup_failure(); return fail("final non-executable protection");
    }}
    if (::munmap(allocation, kGuestReservationSize) != 0)
        return fail("guest cleanup");

    std::cout
        << "reservation_bytes=" << kGuestReservationSize << '\\n'
        << "map_noreserve=yes\\n"
        << "guest_pages_executable=no\\n"
        << "image_bytes=" << image.size() << '\\n'
        << "image_exact_copy=yes\\n"
        << "sections=" << kSections.size() << '\\n'
        << "mapping_count=" << mapping_count << '\\n'
        << "mapping_roundtrips=" << roundtrip_count << '\\n'
        << "entry_mapping_index=" << entry_mapping_index << '\\n'
        << "entry_called=no\\n"
        << "translated_code_called=no\\n"
        << "data_imports_ledgered=" << kDataImports.size() << '\\n'
        << "data_imports_seeded=0\\n"
        << "data_imports_preserved=" << kDataImports.size() << '\\n'
        << "tls_template_bytes=0\\n"
        << "cleanup=yes\\n";
    return 0;
}}
'''


def parse_harness_output(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        require("=" in line, "unexpected bootstrap harness output")
        key, value = line.split("=", 1)
        require(key and key not in result, "duplicate bootstrap harness key")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--xex", type=Path, default=Path(
        "extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--generated", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--vendor", type=Path,
                        default=Path("tools/vendor/XenonRecomp"))
    parser.add_argument("--extractor-source", type=Path,
                        default=Path("tools/xex_extract_pe.cpp"))
    parser.add_argument("--xex-report", type=Path,
                        default=Path("reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--all-tus-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_recomp_all_tus.json"))
    parser.add_argument("--clang", default="clang++-18")
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--temp-root", type=Path, default=Path(".codex-tmp"))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    xex_path = (root / args.xex).resolve()
    generated = (root / args.generated).resolve()
    vendor = (root / args.vendor).resolve()
    extractor_source = (root / args.extractor_source).resolve()
    xex_report_path = (root / args.xex_report).resolve()
    all_tus_path = (root / args.all_tus_report).resolve()
    temp_root = (root / args.temp_root).resolve()
    xenonutils = vendor / "build/XenonUtils/libXenonUtils.a"
    require(args.jobs > 0, "--jobs must be positive")
    for path in (xex_path, extractor_source, xex_report_path, all_tus_path,
                 xenonutils):
        require(path.is_file(), f"required file missing: {path}")

    compiler = shutil.which(args.clang)
    require(compiler is not None, f"compiler not found: {args.clang}")
    version = subprocess.run([args.clang, "--version"], capture_output=True,
                             text=True, check=True).stdout.splitlines()[0]
    require("clang version 18.1.3" in version, "pinned Clang version changed")
    linker = shutil.which("ld.lld-18")
    require(linker is not None, "ld.lld-18 is unavailable")
    linker_version = subprocess.run([linker, "--version"], capture_output=True,
                                    text=True, check=True).stdout.strip()
    commit = subprocess.run(["git", "-C", str(vendor), "rev-parse", "HEAD"],
                            capture_output=True, text=True,
                            check=True).stdout.strip()
    require(commit == EXPECTED_VENDOR_COMMIT, "XenonRecomp commit changed")
    require(digest_file(xenonutils) == EXPECTED_XENONUTILS_SHA256,
            "pinned XenonUtils library changed")

    xex_bytes = xex_path.read_bytes()
    require(digest(xex_bytes) == EXPECTED_XEX_SHA256,
            "untouched retail XEX hash changed")
    xex_metadata = parse_xex_execution_metadata(xex_bytes)
    require(xex_metadata["security_image_size"] == EXPECTED_DECODED_SIZE,
            "XEX security image size changed")
    require(xex_metadata["security_load_address"] == EXPECTED_IMAGE_BASE,
            "XEX security load address changed")
    require(xex_metadata["security_header_size"] ==
            EXPECTED_XEX_SECURITY_HEADER_SIZE,
            "XEX security header size changed")
    require(xex_metadata["page_descriptor_count"] ==
            EXPECTED_XEX_PAGE_DESCRIPTOR_COUNT,
            "XEX page descriptor count changed")
    require(xex_metadata["page_count_sum"] * EXPECTED_XEX_PAGE_SIZE ==
            EXPECTED_DECODED_SIZE,
            "XEX page descriptors disagree with the security image size")
    require(xex_metadata["all_descriptor_page_counts_one"] is True,
            "APF page descriptor granularity changed")
    require(xex_metadata["page_descriptor_type_counts"] ==
            {"1": 110, "2": 93, "3": 621},
            "APF page descriptor type counts changed")
    require(xex_metadata["descriptor_table_sha256"] ==
            EXPECTED_XEX_DESCRIPTOR_TABLE_SHA256,
            "XEX page descriptor table changed")
    require(xex_metadata["image_base"] == EXPECTED_IMAGE_BASE,
            "XEX image-base optional header changed")
    require(xex_metadata["entry_point"] == EXPECTED_ENTRY,
            "XEX entry point changed")
    require(xex_metadata["tls"] == EXPECTED_TLS, "XEX TLS descriptor changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    all_tus = json.loads(all_tus_path.read_text(encoding="utf-8"))
    require(all_tus["inputs"]["cpp_manifest_sha256"] == EXPECTED_CPP_MANIFEST,
            "generated C++ manifest changed")
    require(all_tus["result"]["all_translation_units_passed"] is True,
            "full generated-C++ syntax prerequisite is not passing")
    require(xex_report["inputs"]["xex_sha256"] == EXPECTED_XEX_SHA256,
            "XEX report source hash changed")
    require(xex_report["inputs"]["decompressed_pe_sha256"] ==
            EXPECTED_DECODED_SHA256, "XEX report decoded hash changed")
    require(xex_report["inputs"]["decompressed_pe_size"] ==
            EXPECTED_DECODED_SIZE, "XEX report decoded size changed")
    require(parse_hex(xex_report["execution"]["image_base"]) ==
            EXPECTED_IMAGE_BASE, "reported image base changed")
    require(parse_hex(xex_report["execution"]["entry_point"]) == EXPECTED_ENTRY,
            "reported entry point changed")
    reported_tls = {
        "slot_count": int(xex_report["tls"]["slot_count"]),
        "raw_data_address": parse_hex(xex_report["tls"]["raw_data_address"]),
        "data_size": int(xex_report["tls"]["data_size"]),
        "raw_data_size": int(xex_report["tls"]["raw_data_size"]),
    }
    require(reported_tls == EXPECTED_TLS, "reported TLS descriptor changed")
    require(xex_report["pe"]["size_of_image"] == EXPECTED_PE_IMAGE_SIZE,
            "PE SizeOfImage changed")
    sections = xex_report["pe"]["sections"]
    require(len(sections) == EXPECTED_SECTION_COUNT, "PE section count changed")
    require(parse_hex(xex_report["pe"]["image_base"]) == EXPECTED_IMAGE_BASE,
            "PE image base changed")
    require(parse_hex(xex_report["pe"]["entry_point"]) == EXPECTED_ENTRY,
            "PE entry point changed")

    callable_items = [item for item in xex_report["imports"]["items"]
                      if item["thunk_address"] is not None]
    data_items = [item for item in xex_report["imports"]["items"]
                  if item["thunk_address"] is None]
    import_names = ["__imp__" + item["name"] for item in callable_items]
    require(len(import_names) == EXPECTED_CALLABLE_IMPORTS and
            len(set(import_names)) == EXPECTED_CALLABLE_IMPORTS,
            "callable import set changed")
    require(len(data_items) == EXPECTED_DATA_IMPORTS,
            "imported data set changed")
    require(all(SYMBOL.fullmatch(name) for name in import_names),
            "unsafe generated import symbol")

    names = expected_names()
    sources = [generated / name for name in names]
    require(all(path.is_file() for path in sources), "generated source is missing")
    require(len(list(generated.glob("*.cpp"))) == EXPECTED_TU_COUNT,
            "generated C++ roster changed")

    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-guest-bootstrap-",
                                     dir=temp_root) as tmp:
        build = Path(tmp)
        extractor = build / "xex_extract_pe"
        decoded = build / "apf-decoded.pe"
        extractor_command = [
            args.clang, "-std=c++20", "-O2", str(extractor_source),
            f"-I{vendor / 'XenonUtils'}",
            f"-I{vendor / 'thirdparty/TinySHA1'}",
            f"-I{vendor / 'thirdparty/tiny-AES-c'}",
            str(xenonutils), "-o", str(extractor),
        ]
        extractor_compile = subprocess.run(
            extractor_command, capture_output=True, text=True, check=False)
        require(extractor_compile.returncode == 0,
                f"extractor compile failed: {extractor_compile.stderr[:1000]}")
        require(extractor_compile.stdout == "" and extractor_compile.stderr == "",
                "extractor compile emitted diagnostics")
        extraction = subprocess.run([str(extractor), str(xex_path), str(decoded)],
                                    capture_output=True, text=True, check=False)
        require(extraction.returncode == 0,
                f"XEX extraction failed: {extraction.stderr[:1000]}")
        expected_extraction = (
            "blocks=642 chunks=1648 lzx_bytes=37717546 "
            "image_bytes=54001664 window_size=32768\n"
        )
        require(extraction.stdout == expected_extraction and extraction.stderr == "",
                "XEX extraction transcript changed")
        require(decoded.stat().st_size == EXPECTED_DECODED_SIZE,
                "decoded image size changed")
        require(digest_file(decoded) == EXPECTED_DECODED_SHA256,
                "decoded image hash changed")

        decoded_bytes = decoded.read_bytes()
        section_evidence: list[dict[str, object]] = []
        for section in sections:
            virtual_address = parse_hex(section["virtual_address"])
            virtual_size = parse_hex(section["virtual_size"])
            require(virtual_address < len(decoded_bytes),
                    "section begins beyond decoded image")
            backed_size = min(virtual_size, len(decoded_bytes) - virtual_address)
            require(backed_size > 0, "section has no decoded backing")
            section_evidence.append({
                "name": section["name"],
                "guest_address": f"0x{EXPECTED_IMAGE_BASE + virtual_address:08X}",
                "virtual_address": f"0x{virtual_address:08X}",
                "declared_virtual_size": virtual_size,
                "decoded_backed_size": backed_size,
                "unbacked_virtual_tail_size": virtual_size - backed_size,
                "decoded_backing_sha256": digest(
                    decoded_bytes[virtual_address:virtual_address + backed_size]),
                "exact_guest_copy_verified": True,
            })

        stubs = build / "apf_portme_import_stubs.cpp"
        harness = build / "apf_guest_bootstrap_harness.cpp"
        stub_text = stub_source(import_names)
        harness_text = harness_source(sections, data_items)
        stubs.write_text(stub_text, encoding="utf-8")
        harness.write_text(harness_text, encoding="utf-8")
        all_sources = [*sources, stubs, harness]
        objects = [build / f"{index:03d}.o"
                   for index in range(len(all_sources))]
        include_paths = [generated, vendor / "XenonUtils",
                         vendor / "thirdparty/simde"]
        outcomes_by_index: dict[int, dict[str, object]] = {}
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(compile_one, args.clang, source, output,
                                include_paths): index
                for index, (source, output) in enumerate(zip(all_sources, objects))
            }
            for future in as_completed(futures):
                outcomes_by_index[futures[future]] = future.result()
        outcomes = [outcomes_by_index[index] for index in range(len(all_sources))]
        failures = [row for row in outcomes if row["return_code"] != 0]
        require(not failures, f"object compilation failed: {failures[:3]}")
        require(all(row["stdout_empty"] and row["stderr_empty"]
                    for row in outcomes), "object compilation emitted diagnostics")

        executable = build / "apf_guest_bootstrap"
        link_command = [
            args.clang, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-o", str(executable),
        ]
        linked = subprocess.run(link_command, capture_output=True, text=True,
                                check=False)
        require(linked.returncode == 0, f"link failed: {linked.stderr[:1000]}")
        require(linked.stdout == "" and linked.stderr == "",
                "link emitted unexpected diagnostics")

        executed = subprocess.run([str(executable), str(decoded)],
                                  capture_output=True, text=True, check=False)
        require(executed.returncode == 0,
                f"guest bootstrap harness failed: {executed.stderr[:1000]}")
        require(executed.stderr == "", "guest bootstrap harness emitted stderr")
        harness_result = parse_harness_output(executed.stdout)
        expected_harness = {
            "reservation_bytes": str(0x100000000),
            "map_noreserve": "yes",
            "guest_pages_executable": "no",
            "image_bytes": str(EXPECTED_DECODED_SIZE),
            "image_exact_copy": "yes",
            "sections": str(EXPECTED_SECTION_COUNT),
            "mapping_count": str(EXPECTED_MAPPING_COUNT),
            "mapping_roundtrips": str(EXPECTED_MAPPING_COUNT),
            "entry_mapping_index": "55520",
            "entry_called": "no",
            "translated_code_called": "no",
            "data_imports_ledgered": str(EXPECTED_DATA_IMPORTS),
            "data_imports_seeded": "0",
            "data_imports_preserved": str(EXPECTED_DATA_IMPORTS),
            "tls_template_bytes": "0",
            "cleanup": "yes",
        }
        require(harness_result == expected_harness,
                "guest bootstrap harness evidence changed")

        nm = subprocess.run(["nm", "-u", str(executable)], capture_output=True,
                            text=True, check=True).stdout.splitlines()
        unresolved_guest = [line for line in nm if "__imp__" in line or
                            re.search(r"\bsub_[0-9A-F]+", line)]
        require(not unresolved_guest, "linked executable retains guest symbols")
        executable_size = executable.stat().st_size
        object_bytes = sum(path.stat().st_size for path in objects)
        extractor_size = extractor.stat().st_size

    data_ledger = [{
        "library": item["library"],
        "name": item["name"],
        "ordinal": item["ordinal"],
        "guest_slot_address": item["reference_address"],
        "original_xex_ordinal_verified": True,
        "runtime_seed_state": "unresolved_preserved_xex_ordinal",
        "guest_valid_runtime_value_seeded": False,
    } for item in data_items]

    report = {
        "schema": SCHEMA,
        "result": {
            "untouched_xex_decoded": True,
            "decoded_image_exactly_loaded": True,
            "pe_section_header_count": EXPECTED_SECTION_COUNT,
            "section_backings_exactly_verified": EXPECTED_SECTION_COUNT,
            "generated_function_mappings_initialized": EXPECTED_MAPPING_COUNT,
            "generated_function_mappings_read_back": EXPECTED_MAPPING_COUNT,
            "entry_mapping_present": True,
            "data_import_slots_ledgered": EXPECTED_DATA_IMPORTS,
            "data_import_slots_runtime_seeded": 0,
            "data_import_slots_preserved": EXPECTED_DATA_IMPORTS,
            "tls_descriptor_verified": True,
            "title_entry_called": False,
            "translated_game_code_called": False,
            "native_game_boot_proved": False,
            "loaded_xex_dispatch_boundary_reconciled": True,
            "runtime_dispatch_collision_policy_implemented": False,
            "temporary_outputs_deleted": True,
        },
        "guest_address_space": {
            "reservation_bytes": 0x100000000,
            "reservation_flags": ["MAP_PRIVATE", "MAP_ANONYMOUS", "MAP_NORESERVE"],
            "initial_protection": "PROT_NONE",
            "final_touched_region_protection": "PROT_READ",
            "guest_pages_ever_host_executable": False,
            "page_size": 4096,
            "maximum_explicitly_writable_guest_bytes": (
                EXPECTED_DECODED_SIZE +
                ((EXPECTED_CODE_SIZE * 2 + 8 + 4095) & ~4095)
            ),
            "reservation_released": True,
        },
        "image": {
            "guest_image_base": f"0x{EXPECTED_IMAGE_BASE:08X}",
            "xex_security_image_size": EXPECTED_DECODED_SIZE,
            "xex_security_loaded_end":
                f"0x{EXPECTED_IMAGE_BASE + EXPECTED_DECODED_SIZE:08X}",
            "xex_security_header_size": EXPECTED_XEX_SECURITY_HEADER_SIZE,
            "xex_page_size": EXPECTED_XEX_PAGE_SIZE,
            "xex_page_descriptor_count": EXPECTED_XEX_PAGE_DESCRIPTOR_COUNT,
            "xex_page_count_sum": xex_metadata["page_count_sum"],
            "xex_page_descriptor_span_bytes":
                xex_metadata["page_count_sum"] * EXPECTED_XEX_PAGE_SIZE,
            "xex_descriptor_table_sha256":
                EXPECTED_XEX_DESCRIPTOR_TABLE_SHA256,
            "xex_security_size_matches_page_descriptor_span": True,
            "decoded_image_sha256": EXPECTED_DECODED_SHA256,
            "guest_loaded_image_sha256": EXPECTED_DECODED_SHA256,
            "whole_image_memcmp_before_and_after_dispatch": True,
            "pe_size_of_image": EXPECTED_PE_IMAGE_SIZE,
            "pe_size_of_image_end":
                f"0x{EXPECTED_IMAGE_BASE + EXPECTED_PE_IMAGE_SIZE:08X}",
            "pe_virtual_size_exceeds_decoded_span_by":
                EXPECTED_PE_IMAGE_SIZE - EXPECTED_DECODED_SIZE,
            "pe_size_of_image_controls_xex_loader": False,
            "pe_declared_tail_loaded_as_title_bytes": False,
            "authoritative_loaded_span_reconciled": True,
            "load_contract": (
                "XEX security imageSize and 824x64KiB page-descriptor "
                "aggregate; PE SizeOfImage is non-authoritative for XEX loading"
            ),
            "headers_sha256": digest(decoded_bytes[:1024]),
            "sections": section_evidence,
        },
        "dispatch": {
            "generated_ppc_image_base": f"0x{EXPECTED_IMAGE_BASE:08X}",
            "generated_ppc_image_size": EXPECTED_DECODED_SIZE,
            "generated_ppc_code_base": f"0x{EXPECTED_CODE_BASE:08X}",
            "generated_ppc_code_size": EXPECTED_CODE_SIZE,
            "dispatch_guest_offset":
                f"0x{EXPECTED_IMAGE_BASE + EXPECTED_DECODED_SIZE:08X}",
            "dispatch_reserved_bytes": EXPECTED_CODE_SIZE * 2 + 8,
            "dispatch_end_exclusive": f"0x{(
                EXPECTED_IMAGE_BASE + EXPECTED_DECODED_SIZE +
                EXPECTED_CODE_SIZE * 2 + 8):08X}",
            "dispatch_host_page_rounded_end_exclusive": f"0x{(
                EXPECTED_IMAGE_BASE + EXPECTED_DECODED_SIZE +
                ((EXPECTED_CODE_SIZE * 2 + 8 + 4095) & ~4095)):08X}",
            "loaded_title_byte_overlap": 0,
            "pe_size_of_image_metadata_overlap_bytes":
                EXPECTED_PE_IMAGE_SIZE - EXPECTED_DECODED_SIZE,
            "runtime_dynamic_allocation_mmio_collision_free_proved": False,
            "mapping_count": EXPECTED_MAPPING_COUNT,
            "strictly_sorted_unique_aligned_guest_addresses": True,
            "all_host_pointers_non_null": True,
            "all_roundtrips_exact": True,
            "entry_mapping_index": 55_520,
            "entry_mapping_guest_address": f"0x{EXPECTED_ENTRY:08X}",
            "entry_mapping_host_symbol": "_xstart",
            "entry_function_pointer_invoked": False,
        },
        "entry_and_tls": {
            "xex_entry_point": f"0x{EXPECTED_ENTRY:08X}",
            "pe_entry_point": f"0x{EXPECTED_ENTRY:08X}",
            "entry_owned_by_text_section": True,
            "tls_slot_count": EXPECTED_TLS["slot_count"],
            "tls_raw_data_address": "0x00000000",
            "tls_data_size": 0,
            "tls_raw_data_size": 0,
            "tls_template_mapped": False,
            "thread_context_created": False,
        },
        "imported_data_ledger": {
            "count": EXPECTED_DATA_IMPORTS,
            "all_slots_within_exact_loaded_span": True,
            "all_original_ordinal_words_verified": True,
            "all_slots_unchanged_after_dispatch_initialization": True,
            "runtime_values_seeded": 0,
            "state": "explicitly_ledgered_unresolved_fail_closed",
            "items": data_ledger,
        },
        "build_observation": {
            "generated_cpp_object_count": EXPECTED_TU_COUNT,
            "support_object_count": 2,
            "compiled_object_count": EXPECTED_TU_COUNT + 2,
            "compile_failure_count": 0,
            "link_succeeded": True,
            "undefined_guest_symbol_count": 0,
            "fail_fast_callable_import_definitions": EXPECTED_CALLABLE_IMPORTS,
            "temporary_object_bytes": object_bytes,
            "temporary_executable_bytes": executable_size,
            "temporary_extractor_bytes": extractor_size,
            "decoded_image_preserved": False,
            "executable_preserved": False,
        },
        "toolchain": {
            "compiler": args.clang,
            "compiler_version_first_line": version,
            "linker": "ld.lld-18",
            "linker_version": linker_version,
            "generated_compile_flags": ["-std=c++20", "-O0", "-c"],
            "link_flags": ["-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie"],
            "jobs": args.jobs,
        },
        "interpretation": {
            "worked": (
                "The untouched APF XEX is independently decoded and copied into "
                "a bounded sparse guest reservation; all 60,731 generated indirect "
                "mappings and exact image/entry/TLS metadata pass readback checks."
            ),
            "failed": (
                "The 13 imported data slots are intentionally only ledgered and "
                "preserved; none has a fabricated guest-valid runtime value. "
                "Guest allocator/MMIO ownership of the dispatch range is not proved."
            ),
            "conclusion": (
                "This proves loader and dispatch-table readiness before execution, "
                "not APF title runtime, boot, menu, rendering, or gameplay."
            ),
        },
        "sources": {
            "retail_xex": pin(xex_path),
            "xex_report": pin(xex_report_path),
            "all_tus_report": pin(all_tus_path),
            "extractor_source": pin(extractor_source),
            "xenonutils_library": pin(xenonutils),
            "generator": pin(Path(__file__).resolve()),
            "xenonrecomp_commit": commit,
            "generated_cpp_manifest_sha256": EXPECTED_CPP_MANIFEST,
            "retail_or_decoded_bytes_embedded_in_report": False,
        },
        "portme": [
            "// PORTME: seed all 13 imported data slots with exact guest-valid kernel/XAM values or objects; preserved ordinal words are not runtime values.",
            "// PORTME: reserve guest [0x85380000, 0x86133000) from every dynamic allocator and MMIO mapping before title execution, or move the XenonRecomp indirect table entirely host-side; loaded XEX bytes do not overlap the table, but runtime guest allocations/accesses are not yet proved collision-free.",
            "// PORTME: implement all 334 callable imports and the scheduler, filesystem, Xenos, audio, exception, and TLS/thread runtime before calling _xstart.",
            "// PORTME: repair 3,337 switch-boundary violations and 172 omitted instruction sites before treating translated control flow as complete.",
        ],
    }
    output = args.json.resolve() if args.json.is_absolute() else (root / args.json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_STATIC_RECOMP_GUEST_IMAGE_BOOTSTRAP_PASS "
        "image=exact mappings=60731 data_ledger=13 tls=verified "
        "entry_called=no runtime=no cleanup=yes"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, BootstrapError,
            subprocess.SubprocessError) as exc:
        raise SystemExit(f"error: {exc}") from exc
