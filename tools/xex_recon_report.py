#!/usr/bin/env python3
"""Create deterministic XEX2/PE reconnaissance reports.

The input PE is the decrypted/decompressed XEX memory image emitted by
tools/xex_extract_pe.cpp.  This script does not decrypt copyrighted data; it
parses headers, import records and selected identifying strings from a local
image supplied by the user.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import struct
import uuid
from pathlib import Path


OPTION_NAMES = {
    0x000002FF: "resource_info",
    0x000003FF: "file_format_info",
    0x00010100: "entry_point",
    0x00010201: "image_base_address",
    0x000103FF: "import_libraries",
    0x00018002: "checksum_timestamp",
    0x000183FF: "original_pe_name",
    0x000200FF: "static_libraries",
    0x00020104: "tls_info",
    0x00020200: "default_stack_size",
    0x00030000: "system_flags",
    0x00040006: "execution_info",
    0x00040310: "game_ratings",
    0x00040404: "lan_key",
    0x000405FF: "xbox360_logo",
}

MODULE_FLAGS = {
    0x00000001: "title",
    0x00000002: "exports_to_title",
    0x00000004: "system_debugger",
    0x00000008: "dll_module",
    0x00000010: "module_patch",
    0x00000020: "patch_full",
    0x00000040: "patch_delta",
    0x00000080: "user_mode",
}

SYSTEM_FLAGS = {
    0x00000001: "no_forced_reboot",
    0x00000002: "foreground_tasks",
    0x00000004: "no_odd_mapping",
    0x00000008: "handle_mce_input",
    0x00000010: "restricted_hud_features",
    0x00000020: "handle_gamepad_disconnect",
    0x00000040: "insecure_sockets",
    0x00000080: "xbox1_interoperability",
    0x00000100: "dash_context",
    0x00000200: "uses_game_voice_channel",
    0x00000400: "pal50_incompatible",
}

IMAGE_FLAGS = {
    0x00000002: "manufacturing_utility",
    0x00000004: "manufacturing_support_tools",
    0x00000008: "xgd2_media_only",
    0x00000100: "cardea_key",
    0x00000200: "xeika_key",
    0x00000400: "usermode_title",
    0x00000800: "usermode_system",
    0x10000000: "page_size_4kb",
    0x20000000: "region_free",
    0x40000000: "revocation_check_optional",
    0x80000000: "revocation_check_required",
}

MEDIA_FLAGS = {
    0x00000001: "harddisk",
    0x00000002: "dvd_x2",
    0x00000004: "dvd_cd",
    0x00000008: "dvd_5",
    0x00000010: "dvd_9",
    0x00000020: "system_flash",
    0x00000080: "memory_unit",
    0x00000100: "usb_mass_storage",
    0x00000200: "network",
    0x00000400: "direct_from_memory",
    0x00000800: "ram_drive",
    0x00001000: "svod",
    0x01000000: "insecure_package",
    0x02000000: "savegame_package",
    0x04000000: "locally_signed_package",
    0x08000000: "live_signed_package",
    0x10000000: "xbox_package",
}

PE_SECTION_FLAGS = {
    0x00000020: "contains_code",
    0x00000040: "initialized_data",
    0x00000080: "uninitialized_data",
    0x20000000: "execute",
    0x40000000: "read",
    0x80000000: "write",
}

TOOLCHAIN_MARKERS = (
    "visual concepts",
    "maincodeline",
    "vcsports",
    "nfl_clean",
    "default.xex.pdb",
    "vclibrary",
    "shaderdumpxe",
    "xbox driver",
    "d3d version",
    "d3d9d.lib",
    "d3d9i.lib",
)

MIDDLEWARE_MARKERS = (
    "renderware",
    "criterion",
    "havok",
    "bink",
    "fmod",
    "wwise",
    "physx",
    "granny",
    "speedtree",
)


def checked_slice(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"{label} is outside the input: {offset:#x}+{size:#x}")
    return data[offset : offset + size]


def be16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def be32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def le16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def le32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def hex32(value: int) -> str:
    return f"0x{value:08X}"


def digest(data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, data).hexdigest()


def flags(value: int, names: dict[int, str]) -> list[str]:
    return [name for bit, name in names.items() if value & bit]


def version(value: int) -> dict[str, object]:
    major = (value >> 28) & 0xF
    minor = (value >> 24) & 0xF
    build = (value >> 8) & 0xFFFF
    qfe = value & 0xFF
    return {
        "raw": hex32(value),
        "major": major,
        "minor": minor,
        "build": build,
        "qfe": qfe,
        "string": f"{major}.{minor}.{build}.{qfe}",
    }


def iso_timestamp(value: int) -> str:
    return dt.datetime.fromtimestamp(value, dt.UTC).isoformat().replace("+00:00", "Z")


def cstring(data: bytes, offset: int, limit: int | None = None) -> str:
    end_limit = len(data) if limit is None else min(len(data), offset + limit)
    end = data.find(b"\0", offset, end_limit)
    if end < 0:
        end = end_limit
    return data[offset:end].decode("ascii", errors="replace")


def parse_optional_headers(data: bytes, count: int) -> tuple[list[dict], dict[int, int]]:
    records = []
    lookup = {}
    for index in range(count):
        position = 24 + index * 8
        key = be32(data, position)
        value = be32(data, position + 4)
        low = key & 0xFF
        if low == 0:
            storage = "immediate_u32"
            byte_length = 4
        elif low == 1:
            storage = "inline_u32"
            byte_length = 4
        elif low == 0xFF:
            storage = "offset_variable"
            byte_length = be32(data, value)
        else:
            storage = "offset_fixed"
            byte_length = low * 4
        records.append(
            {
                "index": index,
                "key": hex32(key),
                "name": OPTION_NAMES.get(key, "unknown"),
                "value_or_offset": hex32(value),
                "storage": storage,
                "byte_length": byte_length,
            }
        )
        lookup[key] = value
    return records, lookup


def parse_static_libraries(data: bytes, offset: int) -> list[dict]:
    size = be32(data, offset)
    if size < 4 or (size - 4) % 16:
        raise ValueError("invalid static-library optional header size")
    result = []
    for position in range(offset + 4, offset + size, 16):
        name = data[position : position + 8].rstrip(b"\0").decode("ascii", "replace")
        major = be16(data, position + 8)
        minor = be16(data, position + 10)
        build = be16(data, position + 12)
        approval = data[position + 14]
        qfe = data[position + 15]
        result.append(
            {
                "name": name,
                "major": major,
                "minor": minor,
                "build": build,
                "qfe": qfe,
                "version": f"{major}.{minor}.{build}.{qfe}",
                "approval_raw": f"0x{approval:02X}",
            }
        )
    return result


def parse_resources(data: bytes, offset: int) -> list[dict]:
    size = be32(data, offset)
    if size < 4 or (size - 4) % 16:
        raise ValueError("invalid resource-info optional header size")
    result = []
    for position in range(offset + 4, offset + size, 16):
        result.append(
            {
                "id": data[position : position + 8].decode("ascii", "replace"),
                "address": hex32(be32(data, position + 8)),
                "size": be32(data, position + 12),
            }
        )
    return result


def parse_pe(data: bytes) -> dict:
    if data[:2] != b"MZ":
        raise ValueError("decompressed image does not have an MZ header")
    nt = le32(data, 0x3C)
    if checked_slice(data, nt, 4, "PE signature") != b"PE\0\0":
        raise ValueError("decompressed image does not have a PE signature")
    file_header = nt + 4
    optional = nt + 24
    section_count = le16(data, file_header + 2)
    optional_size = le16(data, file_header + 16)
    image_base = le32(data, optional + 28)
    entry_rva = le32(data, optional + 16)
    sections = []
    section_by_name = {}
    section_offset = optional + optional_size
    for index in range(section_count):
        position = section_offset + index * 40
        name = data[position : position + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size = le32(data, position + 8)
        virtual_address = le32(data, position + 12)
        raw_size = le32(data, position + 16)
        raw_pointer = le32(data, position + 20)
        characteristics = le32(data, position + 36)
        section = {
            "name": name,
            "virtual_address": hex32(virtual_address),
            "absolute_address": hex32(image_base + virtual_address),
            "virtual_size": virtual_size,
            "virtual_size_hex": hex32(virtual_size),
            "raw_pointer": hex32(raw_pointer),
            "raw_size": raw_size,
            "raw_size_hex": hex32(raw_size),
            "characteristics": hex32(characteristics),
            "flags": flags(characteristics, PE_SECTION_FLAGS),
        }
        sections.append(section)
        section_by_name[name] = section

    timestamp = le32(data, file_header + 4)
    directory_count = min(le32(data, optional + 92), 16)
    directory_names = (
        "export", "import", "resource", "exception", "security", "base_relocation",
        "debug", "architecture", "global_ptr", "tls", "load_config", "bound_import",
        "iat", "delay_import", "com_descriptor", "reserved",
    )
    data_directories = []
    for index in range(directory_count):
        position = optional + 96 + index * 8
        data_directories.append(
            {
                "index": index,
                "name": directory_names[index],
                "virtual_address": hex32(le32(data, position)),
                "size": le32(data, position + 4),
            }
        )
    pe = {
        "dos_lfanew": hex32(nt),
        "machine": hex32(le16(data, file_header)),
        "machine_name": "IMAGE_FILE_MACHINE_POWERPCBE" if le16(data, file_header) == 0x01F2 else "unknown",
        "section_count": section_count,
        "timestamp_raw": hex32(timestamp),
        "timestamp_utc": iso_timestamp(timestamp),
        "characteristics": hex32(le16(data, file_header + 18)),
        "optional_magic": f"0x{le16(data, optional):04X}",
        "linker_version": f"{data[optional + 2]}.{data[optional + 3]}",
        "size_of_code": le32(data, optional + 4),
        "size_of_initialized_data": le32(data, optional + 8),
        "size_of_uninitialized_data": le32(data, optional + 12),
        "entry_rva": hex32(entry_rva),
        "entry_point": hex32(image_base + entry_rva),
        "base_of_code": hex32(le32(data, optional + 20)),
        "base_of_data": hex32(le32(data, optional + 24)),
        "image_base": hex32(image_base),
        "section_alignment": hex32(le32(data, optional + 32)),
        "file_alignment": hex32(le32(data, optional + 36)),
        "os_version": f"{le16(data, optional + 40)}.{le16(data, optional + 42)}",
        "image_version": f"{le16(data, optional + 44)}.{le16(data, optional + 46)}",
        "subsystem_version": f"{le16(data, optional + 48)}.{le16(data, optional + 50)}",
        "size_of_image": le32(data, optional + 56),
        "size_of_headers": le32(data, optional + 60),
        "checksum": hex32(le32(data, optional + 64)),
        "subsystem": le16(data, optional + 68),
        "data_directories": data_directories,
        "sections": sections,
    }

    if directory_count > 6:
        debug_rva = int(data_directories[6]["virtual_address"], 16)
        debug_size = data_directories[6]["size"]
        if debug_rva and debug_size >= 28:
            checked_slice(data, debug_rva, 28, "PE debug directory")
            debug_timestamp = le32(data, debug_rva + 4)
            debug_type = le32(data, debug_rva + 12)
            debug_data_size = le32(data, debug_rva + 16)
            debug_data_rva = le32(data, debug_rva + 20)
            debug = {
                "directory_rva": hex32(debug_rva),
                "timestamp_raw": hex32(debug_timestamp),
                "timestamp_utc": iso_timestamp(debug_timestamp),
                "type": debug_type,
                "size_of_data": debug_data_size,
                "address_of_raw_data": hex32(debug_data_rva),
                "pointer_to_raw_data": hex32(le32(data, debug_rva + 24)),
            }
            if debug_type == 2 and checked_slice(data, debug_data_rva, 4, "CodeView") == b"RSDS":
                checked_slice(data, debug_data_rva, debug_data_size, "CodeView record")
                debug["codeview"] = {
                    "signature": "RSDS",
                    "guid": str(uuid.UUID(bytes_le=data[debug_data_rva + 4 : debug_data_rva + 20])),
                    "age": le32(data, debug_data_rva + 20),
                    "pdb_path": cstring(data, debug_data_rva + 24, debug_data_size - 24),
                }
            pe["debug"] = debug

    pdata = section_by_name.get(".pdata")
    if pdata:
        start = int(pdata["virtual_address"], 16)
        size = pdata["virtual_size"]
        raw = checked_slice(data, start, size, ".pdata virtual bytes")
        entries = []
        for position in range(0, len(raw) - len(raw) % 8, 8):
            entries.append((be32(raw, position), be32(raw, position + 4)))
        pe["pdata"] = {
            "entry_size": 8,
            "entry_count": len(entries),
            "nonzero_start_count": sum(1 for address, _ in entries if address),
            "bytes_sha256": digest(raw, "sha256"),
            "first_entry": {
                "function_start": hex32(entries[0][0]),
                "metadata": hex32(entries[0][1]),
            } if entries else None,
            "last_entry": {
                "function_start": hex32(entries[-1][0]),
                "metadata": hex32(entries[-1][1]),
            } if entries else None,
        }
    return pe


def parse_ghidra_names(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    result = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            result[int(row["address"], 16)] = row["name"].removeprefix("__imp__")
    return result


def parse_imports(
    xex: bytes,
    pe_image: bytes,
    offset: int,
    image_base: int,
    ghidra_names: dict[int, str],
) -> tuple[list[dict], list[dict]]:
    total_size = be32(xex, offset)
    string_size = be32(xex, offset + 4)
    library_count = be32(xex, offset + 8)
    strings_raw = checked_slice(xex, offset + 12, string_size, "import string table")
    strings = []
    string_position = 0
    while string_position < len(strings_raw):
        end = strings_raw.find(b"\0", string_position)
        if end < 0:
            break
        strings.append(strings_raw[string_position:end].decode("ascii", "replace"))
        string_position = (end + 1 + 3) & ~3

    libraries = []
    logical_imports = []
    position = offset + 12 + string_size
    for library_index in range(library_count):
        size = be32(xex, position)
        if size < 40 or position + size > offset + total_size:
            raise ValueError("invalid XEX import-library record")
        name_index = be16(xex, position + 36)
        record_count = be16(xex, position + 38)
        name = strings[name_index]
        library = {
            "index": library_index,
            "name": name,
            "size": size,
            "id": hex32(be32(xex, position + 24)),
            "version": version(be32(xex, position + 28)),
            "minimum_version": version(be32(xex, position + 32)),
            "record_count": record_count,
            "digest": xex[position + 4 : position + 24].hex(),
        }
        libraries.append(library)
        last_import = None
        records = position + 40
        for record_index in range(record_count):
            address = be32(xex, records + record_index * 4)
            image_offset = address - image_base
            word = be32(pe_image, image_offset)
            record_type = (word >> 24) & 0xFF
            ordinal = word & 0xFFFF
            hint = (word >> 16) & 0xFF
            if record_type == 0:
                last_import = {
                    "library": name,
                    "library_version": library["version"]["string"],
                    "reference_address": hex32(address),
                    "thunk_address": None,
                    "raw_word": hex32(word),
                    "hint": hint,
                    "ordinal": ordinal,
                    "name": ghidra_names.get(address),
                }
                logical_imports.append(last_import)
            elif record_type == 1:
                if last_import is None:
                    raise ValueError("function-thunk record has no preceding import")
                last_import["thunk_address"] = hex32(address)
            else:
                raise ValueError(f"unsupported import record type {record_type}")
        position += size
    if position != offset + total_size:
        raise ValueError("XEX import records do not consume their declared size")
    return libraries, logical_imports


def identifying_strings(data: bytes) -> tuple[list[dict], dict[str, list[dict]]]:
    strings = []
    middleware_hits = {marker: [] for marker in MIDDLEWARE_MARKERS}
    matches = []
    for match in re.finditer(rb"[\x20-\x7e]{6,}", data):
        matches.append((match.start(), "ascii", match.group().decode("ascii", "replace")))
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data):
        matches.append((match.start(), "utf-16le", match.group().decode("utf-16le", "replace")))
    for offset, encoding, value in sorted(matches):
        lower = value.lower()
        if any(marker in lower for marker in TOOLCHAIN_MARKERS):
            strings.append({"offset": hex32(offset), "encoding": encoding, "value": value})
        for marker in MIDDLEWARE_MARKERS:
            if marker in lower:
                middleware_hits[marker].append(
                    {"offset": hex32(offset), "encoding": encoding, "value": value}
                )
    return strings, middleware_hits


def write_imports(path: Path, imports: list[dict]) -> None:
    fields = (
        "library",
        "library_version",
        "reference_address",
        "thunk_address",
        "raw_word",
        "hint",
        "ordinal",
        "name",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(imports)


def write_strings(path: Path, strings: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, ("offset", "encoding", "value"), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(strings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xex", type=Path)
    parser.add_argument("pe_image", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--ghidra-imports", type=Path)
    args = parser.parse_args()

    xex = args.xex.read_bytes()
    pe_image = args.pe_image.read_bytes()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    if xex[:4] != b"XEX2":
        raise ValueError("input is not XEX2")

    module_flags = be32(xex, 4)
    payload_offset = be32(xex, 8)
    security_offset = be32(xex, 16)
    optional_count = be32(xex, 20)
    optional_records, optional = parse_optional_headers(xex, optional_count)

    security_header_size = be32(xex, security_offset)
    security_image_size = be32(xex, security_offset + 4)
    page_count = be32(xex, security_offset + 0x180)
    page_descriptors = []
    for index in range(page_count):
        position = security_offset + 0x184 + index * 24
        raw = be32(xex, position)
        page_descriptors.append(
            {
                "index": index,
                "raw": hex32(raw),
                "section_type_low_nibble": raw & 0xF,
                "page_count_high_28_bits": raw >> 4,
                "digest": xex[position + 4 : position + 24].hex(),
            }
        )

    format_offset = optional[0x000003FF]
    format_size = be32(xex, format_offset)
    encryption_type = be16(xex, format_offset + 4)
    compression_type = be16(xex, format_offset + 6)
    file_format = {
        "size": format_size,
        "encryption_type": encryption_type,
        "encryption_name": {0: "none", 1: "normal_aes"}.get(encryption_type, "unknown"),
        "compression_type": compression_type,
        "compression_name": {0: "none", 1: "basic", 2: "normal_lzx", 3: "delta"}.get(compression_type, "unknown"),
    }
    if compression_type == 2:
        file_format["window_size"] = be32(xex, format_offset + 8)
        file_format["first_block_size"] = be32(xex, format_offset + 12)
        file_format["first_block_sha1"] = xex[format_offset + 16 : format_offset + 36].hex()

    checksum_offset = optional[0x00018002]
    checksum = be32(xex, checksum_offset)
    xex_timestamp = be32(xex, checksum_offset + 4)
    pe_name_offset = optional[0x000183FF]
    pe_name_size = be32(xex, pe_name_offset)
    original_pe_name = cstring(xex, pe_name_offset + 4, pe_name_size - 4)

    tls_offset = optional[0x00020104]
    execution_offset = optional[0x00040006]
    execution_version = be32(xex, execution_offset + 4)
    base_version = be32(xex, execution_offset + 8)
    system_value = optional[0x00030000]
    pe = parse_pe(pe_image)
    image_base = int(pe["image_base"], 16)
    ghidra_names = parse_ghidra_names(args.ghidra_imports)
    import_libraries, imports = parse_imports(
        xex, pe_image, optional[0x000103FF], image_base, ghidra_names
    )
    strings, middleware_hits = identifying_strings(pe_image)

    report = {
        "schema": "apf2k8-xex-recon-v1",
        "inputs": {
            "xex_path": str(args.xex),
            "xex_size": len(xex),
            "xex_md5": digest(xex, "md5"),
            "xex_sha256": digest(xex, "sha256"),
            "decompressed_pe_size": len(pe_image),
            "decompressed_pe_md5": digest(pe_image, "md5"),
            "decompressed_pe_sha256": digest(pe_image, "sha256"),
        },
        "xex_header": {
            "magic": xex[:4].decode("ascii"),
            "module_flags_raw": hex32(module_flags),
            "module_flags": flags(module_flags, MODULE_FLAGS),
            "payload_offset": hex32(payload_offset),
            "reserved": hex32(be32(xex, 12)),
            "security_offset": hex32(security_offset),
            "optional_header_count": optional_count,
            "optional_headers": optional_records,
        },
        "file_format": file_format,
        "security_info": {
            "header_size": security_header_size,
            "image_size": security_image_size,
            "unknown_0x108": hex32(be32(xex, security_offset + 0x108)),
            "image_flags_raw": hex32(be32(xex, security_offset + 0x10C)),
            "image_flags": flags(be32(xex, security_offset + 0x10C), IMAGE_FLAGS),
            "load_address": hex32(be32(xex, security_offset + 0x110)),
            "section_digest": xex[security_offset + 0x114 : security_offset + 0x128].hex(),
            "import_table_count": be32(xex, security_offset + 0x128),
            "import_table_digest": xex[security_offset + 0x12C : security_offset + 0x140].hex(),
            "xgd2_media_id": xex[security_offset + 0x140 : security_offset + 0x150].hex(),
            "encrypted_file_key": xex[security_offset + 0x150 : security_offset + 0x160].hex(),
            "export_table": hex32(be32(xex, security_offset + 0x160)),
            "header_digest": xex[security_offset + 0x164 : security_offset + 0x178].hex(),
            "region_raw": hex32(be32(xex, security_offset + 0x178)),
            "allowed_media_types_raw": hex32(be32(xex, security_offset + 0x17C)),
            "allowed_media_types": flags(be32(xex, security_offset + 0x17C), MEDIA_FLAGS),
            "page_descriptor_count": page_count,
            "page_descriptors": page_descriptors,
        },
        "execution": {
            "entry_point": hex32(optional[0x00010100]),
            "image_base": hex32(optional[0x00010201]),
            "default_stack_size": optional[0x00020200],
            "system_flags_raw": hex32(system_value),
            "system_flags": flags(system_value, SYSTEM_FLAGS),
            "media_id": hex32(be32(xex, execution_offset)),
            "version": version(execution_version),
            "base_version": version(base_version),
            "title_id": hex32(be32(xex, execution_offset + 12)),
            "platform": xex[execution_offset + 16],
            "executable_table": xex[execution_offset + 17],
            "disc_number": xex[execution_offset + 18],
            "disc_count": xex[execution_offset + 19],
            "savegame_id": hex32(be32(xex, execution_offset + 20)),
        },
        "resources": parse_resources(xex, optional[0x000002FF]),
        "build_identity": {
            "checksum": hex32(checksum),
            "xex_timestamp_raw": hex32(xex_timestamp),
            "xex_timestamp_utc": iso_timestamp(xex_timestamp),
            "original_pe_name": original_pe_name,
            "static_libraries": parse_static_libraries(xex, optional[0x000200FF]),
        },
        "tls": {
            "slot_count": be32(xex, tls_offset),
            "raw_data_address": hex32(be32(xex, tls_offset + 4)),
            "data_size": be32(xex, tls_offset + 8),
            "raw_data_size": be32(xex, tls_offset + 12),
        },
        "pe": pe,
        "import_libraries": import_libraries,
        "imports": {
            "logical_count": len(imports),
            "thunk_count": sum(1 for item in imports if item["thunk_address"]),
            "items": imports,
        },
        "identifying_strings": strings,
        "middleware_literal_hits": middleware_hits,
    }

    json_path = args.output_directory / "apf2k8_xex_report.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_imports(args.output_directory / "apf2k8_imports.tsv", imports)
    write_strings(args.output_directory / "apf2k8_toolchain_strings.tsv", strings)
    (args.output_directory / "apf2k8_xex_header.bin").write_bytes(
        checked_slice(xex, 0, payload_offset, "XEX header")
    )
    (args.output_directory / "apf2k8_pe_headers.bin").write_bytes(
        checked_slice(pe_image, 0, pe["size_of_headers"], "PE headers")
    )
    pdata_section = next(section for section in pe["sections"] if section["name"] == ".pdata")
    pdata_offset = int(pdata_section["virtual_address"], 16)
    (args.output_directory / "apf2k8_pdata.bin").write_bytes(
        checked_slice(pe_image, pdata_offset, pdata_section["virtual_size"], ".pdata")
    )
    print(f"wrote {json_path}")
    print(f"imports={len(imports)} thunks={report['imports']['thunk_count']}")
    print(f"pdata={report['pe']['pdata']['entry_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
