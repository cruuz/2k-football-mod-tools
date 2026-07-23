#!/usr/bin/env python3
"""Read-only original-Xbox XBE header and import-table reporter.

The parser follows the packed structures used by XboxDev/ghidra-xbe and
Cxbx-Reloaded/XbSymbolDatabase.  It never decrypts or rewrites the input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


ENTRY_KEYS = {
    "debug": 0x94859D4B,
    "retail": 0xA8FC57AB,
    "sega": 0x40B5C16E,
}

KERNEL_THUNK_KEYS = {
    "debug": 0xEFB1F152,
    "retail": 0x5B6D40B6,
    "sega": 0x2290059D,
}

SECTION_FLAGS = (
    (0x01, "writable"),
    (0x02, "preload"),
    (0x04, "executable"),
    (0x08, "inserted_file"),
    (0x10, "head_page_read_only"),
    (0x20, "tail_page_read_only"),
)

INIT_FLAGS = (
    (0x01, "mount_utility_drive"),
    (0x02, "format_utility_drive"),
    (0x04, "limit_devkit_to_64_mb"),
    (0x08, "do_not_setup_hard_disk"),
)

REGIONS = {
    0: "unknown",
    1: "NTSC North America",
    2: "NTSC Japan",
    3: "NTSC North America + Japan",
    4: "PAL",
    5: "PAL + NTSC North America",
    6: "PAL + NTSC Japan",
    7: "region free",
}

IMAGE_HEADER_FIELDS = (
    (0x104, "image_base"),
    (0x108, "headers_size"),
    (0x10C, "image_size"),
    (0x110, "image_header_size"),
    (0x114, "timestamp"),
    (0x118, "certificate_address"),
    (0x11C, "section_count"),
    (0x120, "section_headers_address"),
    (0x124, "init_flags"),
    (0x128, "encoded_entry_address"),
    (0x12C, "tls_address"),
    (0x130, "pe_stack_commit"),
    (0x134, "pe_heap_reserve"),
    (0x138, "pe_heap_commit"),
    (0x13C, "pe_base_address"),
    (0x140, "pe_image_size"),
    (0x144, "pe_checksum"),
    (0x148, "pe_timestamp"),
    (0x14C, "debug_pathname_address"),
    (0x150, "debug_filename_address"),
    (0x154, "debug_unicode_filename_address"),
    (0x158, "encoded_kernel_thunk_address"),
    (0x15C, "non_kernel_import_directory_address"),
    (0x160, "library_versions_count"),
    (0x164, "library_versions_address"),
    (0x168, "kernel_library_version_address"),
    (0x16C, "xapi_library_version_address"),
    (0x170, "logo_bitmap_address"),
    (0x174, "logo_bitmap_size"),
)


class XbeError(ValueError):
    pass


class Xbe:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        if len(self.data) < 0x178:
            raise XbeError(f"file is too small for an XBE header: {len(self.data)} bytes")
        if self.data[:4] != b"XBEH":
            raise XbeError(f"bad XBE magic: {self.data[:4]!r}")

        self.header = {name: self.u32(offset) for offset, name in IMAGE_HEADER_FIELDS}
        header_size = self.header["image_header_size"]
        if header_size >= 0x180:
            self.header["feature_library_versions_address"] = self.u32(0x178)
            self.header["feature_library_versions_count"] = self.u32(0x17C)
        else:
            self.header["feature_library_versions_address"] = 0
            self.header["feature_library_versions_count"] = 0
        self.header["debug_info"] = self.u32(0x180) if header_size >= 0x184 else 0

        self.sections = self.parse_sections()

    def need(self, offset: int, size: int, what: str) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise XbeError(
                f"{what} is outside the file: offset=0x{offset:x}, "
                f"size=0x{size:x}, file_size=0x{len(self.data):x}"
            )

    def u16(self, offset: int) -> int:
        self.need(offset, 2, "16-bit field")
        return struct.unpack_from("<H", self.data, offset)[0]

    def u32(self, offset: int) -> int:
        self.need(offset, 4, "32-bit field")
        return struct.unpack_from("<I", self.data, offset)[0]

    def va_to_offset(self, address: int, size: int = 1) -> int:
        base = self.header["image_base"]
        headers_size = self.header["headers_size"]
        if base <= address and address + size <= base + headers_size:
            offset = address - base
            self.need(offset, size, f"header virtual address 0x{address:08x}")
            return offset

        for section in self.sections:
            start = section["virtual_address"]
            raw_size = section["raw_size"]
            if start <= address and address + size <= start + raw_size:
                offset = section["raw_address"] + address - start
                self.need(offset, size, f"section virtual address 0x{address:08x}")
                return offset
        raise XbeError(f"virtual address 0x{address:08x} (+0x{size:x}) has no file-backed range")

    def cstring_at_offset(self, offset: int, maximum: int = 4096) -> str:
        self.need(offset, 1, "string")
        end_limit = min(len(self.data), offset + maximum)
        end = self.data.find(b"\0", offset, end_limit)
        if end < 0:
            end = end_limit
        return self.data[offset:end].decode("ascii", errors="replace")

    def cstring_va(self, address: int) -> str | None:
        if address == 0:
            return None
        return self.cstring_at_offset(self.va_to_offset(address))

    def utf16z_va(self, address: int, maximum_code_units: int = 2048) -> str | None:
        if address == 0:
            return None
        offset = self.va_to_offset(address, 2)
        end = offset
        limit = min(len(self.data), offset + maximum_code_units * 2)
        while end + 1 < limit and self.data[end : end + 2] != b"\0\0":
            end += 2
        return self.data[offset:end].decode("utf-16-le", errors="replace")

    def parse_sections(self) -> list[dict[str, Any]]:
        base = self.header["image_base"]
        table_address = self.header["section_headers_address"]
        count = self.header["section_count"]
        if count > 4096:
            raise XbeError(f"unreasonable section count: {count}")
        table_offset = table_address - base
        self.need(table_offset, count * 56, "section table")

        sections: list[dict[str, Any]] = []
        for index in range(count):
            offset = table_offset + index * 56
            values = struct.unpack_from("<9I20s", self.data, offset)
            flags, va, vsize, raw, raw_size, name_va, ref_count, head_ref, tail_ref, digest = values
            name_offset = name_va - base
            name = self.cstring_at_offset(name_offset, 256)
            self.need(raw, raw_size, f"raw bytes for section {name!r}")
            # XBE signs little-endian unpadded section length || section bytes,
            # rather than the section bytes alone.
            digest_input = struct.pack("<I", raw_size) + self.data[raw : raw + raw_size]
            computed_digest = hashlib.sha1(digest_input).hexdigest()  # nosec: XBE field
            sections.append(
                {
                    "index": index,
                    "header_file_offset": offset,
                    "name": name,
                    "flags": flags,
                    "flag_names": [name for mask, name in SECTION_FLAGS if flags & mask],
                    "virtual_address": va,
                    "virtual_size": vsize,
                    "raw_address": raw,
                    "raw_size": raw_size,
                    "name_address": name_va,
                    "reference_count": ref_count,
                    "head_shared_page_reference_count_address": head_ref,
                    "tail_shared_page_reference_count_address": tail_ref,
                    "sha1_digest": digest.hex(),
                    "computed_xbe_section_sha1": computed_digest,
                    "digest_matches": digest.hex() == computed_digest,
                }
            )
        return sections

    def parse_certificate(self) -> dict[str, Any]:
        address = self.header["certificate_address"]
        offset = self.va_to_offset(address, 0x1D0)
        size = self.u32(offset)
        self.need(offset, size, "certificate")
        title_raw = self.data[offset + 0x0C : offset + 0x5C]
        title_name = title_raw.decode("utf-16-le", errors="replace").split("\0", 1)[0]
        alternate_ids = list(struct.unpack_from("<16I", self.data, offset + 0x5C))
        title_id = self.u32(offset + 0x08)
        publisher = title_id.to_bytes(4, "big")[:2].decode("ascii", errors="replace")
        game_number = title_id & 0xFFFF
        region = self.u32(offset + 0xA0)
        result: dict[str, Any] = {
            "address": address,
            "file_offset": offset,
            "size": size,
            "timestamp": self.u32(offset + 0x04),
            "title_id": title_id,
            "formatted_title_id": f"{publisher}-{game_number:03d}",
            "title_name": title_name,
            "alternate_title_ids": alternate_ids,
            "allowed_media": self.u32(offset + 0x9C),
            "game_region": region,
            "region_name": REGIONS.get(region & 0x7, "invalid"),
            "manufacturing_region_flag": bool(region & 0x80000000),
            "game_ratings": self.u32(offset + 0xA4),
            "disc_number": self.u32(offset + 0xA8),
            "version": self.u32(offset + 0xAC),
            "lan_key_sha256": hashlib.sha256(self.data[offset + 0xB0 : offset + 0xC0]).hexdigest(),
            "signature_key_sha256": hashlib.sha256(self.data[offset + 0xC0 : offset + 0xD0]).hexdigest(),
            "alternate_signature_keys_sha256": hashlib.sha256(
                self.data[offset + 0xD0 : offset + 0x1D0]
            ).hexdigest(),
        }
        if size >= 0x1D4:
            result["original_certificate_size"] = self.u32(offset + 0x1D0)
        if size >= 0x1D8:
            result["online_service_id"] = self.u32(offset + 0x1D4)
        if size >= 0x1DC:
            result["security_flags"] = self.u32(offset + 0x1D8)
        if size >= 0x1EC:
            result["code_encryption_key_sha256"] = hashlib.sha256(
                self.data[offset + 0x1DC : offset + 0x1EC]
            ).hexdigest()
        return result

    def parse_library(self, address: int, role: str, index: int | None = None) -> dict[str, Any]:
        offset = self.va_to_offset(address, 16)
        raw_name, major, minor, build, flags = struct.unpack_from("<8s4H", self.data, offset)
        name = raw_name.rstrip(b"\0 ").decode("ascii", errors="replace")
        approved = (flags >> 13) & 0x3
        return {
            "role": role,
            "index": index,
            "address": address,
            "file_offset": offset,
            "name": name,
            "major": major,
            "minor": minor,
            "build": build,
            "flags": flags,
            "qfe": flags & 0x1FFF,
            "approved": approved,
            "approved_name": {0: "no", 1: "possibly", 2: "yes", 3: "reserved"}[approved],
            "debug_build": bool(flags & 0x8000),
            "display_version": f"{major}.{minor}.{build}.{flags & 0x1FFF}",
        }

    def parse_libraries(self) -> list[dict[str, Any]]:
        libraries: list[dict[str, Any]] = []
        address = self.header["library_versions_address"]
        count = self.header["library_versions_count"]
        if count > 4096:
            raise XbeError(f"unreasonable library version count: {count}")
        for index in range(count):
            libraries.append(self.parse_library(address + index * 16, "library_table", index))

        known_addresses = {item["address"] for item in libraries}
        for field, role in (
            ("kernel_library_version_address", "kernel_library_pointer"),
            ("xapi_library_version_address", "xapi_library_pointer"),
        ):
            pointer = self.header[field]
            if pointer and pointer not in known_addresses:
                libraries.append(self.parse_library(pointer, role))

        feature_address = self.header["feature_library_versions_address"]
        feature_count = self.header["feature_library_versions_count"]
        if feature_count > 4096:
            raise XbeError(f"unreasonable feature library count: {feature_count}")
        for index in range(feature_count):
            libraries.append(self.parse_library(feature_address + index * 16, "feature_table", index))
        return libraries

    def executable_kind(self) -> str:
        encoded = self.header["encoded_entry_address"]
        if encoded & 0xF0000000 == 0x40000000:
            return "sega"
        if encoded ^ ENTRY_KEYS["debug"] < 0x04000000:
            return "debug"
        return "retail"

    def parse_tls(self) -> dict[str, int] | None:
        address = self.header["tls_address"]
        if not address:
            return None
        offset = self.va_to_offset(address, 24)
        values = struct.unpack_from("<6I", self.data, offset)
        names = (
            "start_address_of_raw_data",
            "end_address_of_raw_data",
            "address_of_index",
            "address_of_callbacks",
            "size_of_zero_fill",
            "characteristics",
        )
        return {"address": address, "file_offset": offset, **dict(zip(names, values))}

    def load_kernel_export_names(self) -> tuple[dict[int, str], str | None]:
        source = self.path.parent
        candidates = [
            Path(__file__).resolve().parent / "vendor/ghidra-xbe/src/main/java/XbeLoader/XbeLoader.java",
            Path(__file__).resolve().parent
            / "vendor/ghidra_12.1.2_PUBLIC/Ghidra/Extensions/ghidra-xbe/lib/ghidra-xbe-src.zip",
        ]
        del source  # keeps the candidate list intentionally workspace-relative
        java_source = candidates[0]
        if not java_source.is_file():
            return {}, None
        text = java_source.read_text(encoding="utf-8")
        start = text.find("private static String[] kernelExports")
        end = text.find("\n\t\t};", start)
        if start < 0 or end < 0:
            return {}, None
        exports: dict[int, str] = {}
        for name, ordinal in re.findall(r'"([^"]*)",?\s*//\s*(\d+)', text[start:end]):
            exports[int(ordinal)] = name
        return exports, str(java_source)

    def parse_kernel_thunks(self) -> tuple[list[dict[str, Any]], str | None]:
        kind = self.executable_kind()
        address = self.header["encoded_kernel_thunk_address"] ^ KERNEL_THUNK_KEYS[kind]
        if address == 0:
            return [], None
        names, name_source = self.load_kernel_export_names()
        entries: list[dict[str, Any]] = []
        for index in range(4096):
            slot_address = address + index * 4
            value = self.u32(self.va_to_offset(slot_address, 4))
            if value == 0:
                break
            ordinal = value & 0x7FFFFFFF if value & 0x80000000 else None
            entries.append(
                {
                    "index": index,
                    "slot_address": slot_address,
                    "raw_value": value,
                    "is_kernel_ordinal": ordinal is not None,
                    "ordinal": ordinal,
                    "name": names.get(ordinal, "") if ordinal is not None else "",
                }
            )
        else:
            raise XbeError("kernel thunk table did not terminate within 4096 entries")
        return entries, name_source

    def report(self) -> dict[str, Any]:
        kind = self.executable_kind()
        entry = self.header["encoded_entry_address"] ^ ENTRY_KEYS[kind]
        thunk_address = self.header["encoded_kernel_thunk_address"] ^ KERNEL_THUNK_KEYS[kind]
        thunks, export_source = self.parse_kernel_thunks()
        header = dict(self.header)
        header["init_flag_names"] = [name for mask, name in INIT_FLAGS if header["init_flags"] & mask]
        header["decoded_entry_address"] = entry
        header["decoded_kernel_thunk_address"] = thunk_address
        return {
            "format": "XBE",
            "parser": "tools/xbe_info.py",
            "input": str(self.path),
            "file_size": len(self.data),
            "md5": hashlib.md5(self.data).hexdigest(),  # nosec: compatibility identifier
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "digital_signature_sha256": hashlib.sha256(self.data[4:260]).hexdigest(),
            "executable_kind": kind,
            "header": header,
            "header_timestamp_utc": format_timestamp(header["timestamp"]),
            "pe_timestamp_utc": format_timestamp(header["pe_timestamp"]),
            "debug_pathname": self.cstring_va(header["debug_pathname_address"]),
            "debug_filename": self.cstring_va(header["debug_filename_address"]),
            "debug_unicode_filename": self.utf16z_va(header["debug_unicode_filename_address"]),
            "certificate": self.parse_certificate(),
            "sections": self.sections,
            "libraries": self.parse_libraries(),
            "tls": self.parse_tls(),
            "kernel_export_name_source": export_source,
            "kernel_thunks": thunks,
        }


def format_timestamp(value: int) -> str:
    try:
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return "invalid"


def hx(value: int) -> str:
    return f"0x{value:08x}"


def format_text(report: dict[str, Any]) -> str:
    header = report["header"]
    certificate = report["certificate"]
    lines = [
        "Original Xbox XBE reconnaissance report",
        "========================================",
        f"input: {report['input']}",
        f"format: {report['format']}",
        f"file size: {report['file_size']} bytes ({hx(report['file_size'])})",
        f"MD5: {report['md5']}",
        f"SHA-256: {report['sha256']}",
        f"digital-signature SHA-256: {report['digital_signature_sha256']}",
        f"XBE kind/key set: {report['executable_kind']}",
        "",
        "Image header",
        "------------",
    ]
    for _, name in IMAGE_HEADER_FIELDS:
        value = header[name]
        suffix = ""
        if name == "timestamp":
            suffix = f" ({report['header_timestamp_utc']})"
        elif name == "pe_timestamp":
            suffix = f" ({report['pe_timestamp_utc']})"
        lines.append(f"{name}: {hx(value)} ({value}){suffix}")
    for name in (
        "feature_library_versions_address",
        "feature_library_versions_count",
        "debug_info",
        "decoded_entry_address",
        "decoded_kernel_thunk_address",
    ):
        value = header[name]
        lines.append(f"{name}: {hx(value)} ({value})")
    lines.append(f"init flag names: {', '.join(header['init_flag_names']) or '(none)'}")
    lines.extend(
        [
            f"debug pathname: {report['debug_pathname']!r}",
            f"debug filename: {report['debug_filename']!r}",
            f"debug Unicode filename: {report['debug_unicode_filename']!r}",
            "",
            "Certificate",
            "-----------",
        ]
    )
    for name, value in certificate.items():
        if isinstance(value, bool):
            lines.append(f"{name}: {str(value).lower()}")
        elif isinstance(value, int):
            lines.append(f"{name}: {hx(value)} ({value})")
        else:
            lines.append(f"{name}: {value}")
    lines.extend(["", f"Sections ({len(report['sections'])})", "--------"])
    for section in report["sections"]:
        flags = ",".join(section["flag_names"]) or "none"
        lines.append(
            f"[{section['index']:02d}] {section['name']!r} "
            f"flags={hx(section['flags'])} ({flags}) "
            f"VA={hx(section['virtual_address'])} VSize={hx(section['virtual_size'])} "
            f"raw={hx(section['raw_address'])} rawSize={hx(section['raw_size'])} "
            f"digest={section['sha1_digest']} computed={section['computed_xbe_section_sha1']} "
            f"match={str(section['digest_matches']).lower()}"
        )
    lines.extend(["", f"Library version records ({len(report['libraries'])})", "-----------------------"])
    for library in report["libraries"]:
        lines.append(
            f"[{library['role']}:{library['index']}] {library['name']!r} "
            f"version={library['display_version']} build={library['build']} qfe={library['qfe']} "
            f"flags=0x{library['flags']:04x} approved={library['approved_name']} "
            f"debug={str(library['debug_build']).lower()} address={hx(library['address'])}"
        )
    lines.extend(["", "TLS directory", "-------------"])
    if report["tls"] is None:
        lines.append("(absent)")
    else:
        for name, value in report["tls"].items():
            lines.append(f"{name}: {hx(value)} ({value})")
    lines.extend(
        [
            "",
            f"Kernel thunk table ({len(report['kernel_thunks'])} entries)",
            "------------------",
            f"name source: {report['kernel_export_name_source'] or '(ordinal only)'}",
        ]
    )
    for thunk in report["kernel_thunks"]:
        ordinal = "-" if thunk["ordinal"] is None else str(thunk["ordinal"])
        name = thunk["name"] or "(unknown/non-ordinal)"
        lines.append(
            f"[{thunk['index']:03d}] slot={hx(thunk['slot_address'])} "
            f"raw={hx(thunk['raw_value'])} ordinal={ordinal} name={name}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", type=Path, help="XBE file to inspect (read-only)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    try:
        report = Xbe(args.xbe).report()
    except (OSError, XbeError) as exc:
        print(f"xbe_info.py: error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=False)
        print()
    else:
        sys.stdout.write(format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
