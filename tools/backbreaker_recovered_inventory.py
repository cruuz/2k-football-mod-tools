#!/usr/bin/env python3
"""Inventory the recovered Backbreaker Ghidra scripts.

The recovered ``Backbreaker*.java`` sources in
``tools/ghidra_scripts/backbreaker/`` embed the proven reverse-engineering
findings as Java literal tables (``Word`` / ``Range`` / ``NamedAddress`` /
``Probe``) plus an ``EXPECTED_MD5`` source-revision guard per script.  This
tool parses those literals into one machine-readable JSON inventory so later
tooling can consume the proven facts without re-reading the Java.

Read-only: it never modifies the scripts and requires no Backbreaker binary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent / "ghidra_scripts" / "backbreaker"

_MD5 = re.compile(r'EXPECTED_MD5\s*=\s*"([0-9a-fA-F]{32})"')
# new Word(2183175296L, 2558724985L, "meaning")
_WORD = re.compile(r'new Word\(\s*(\d+)L\s*,\s*(\d+)L\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')
# new Range(2183175296L, 2183175316L, "name")  OR  new Range("name", 123L, 456L)
_RANGE_AA = re.compile(r'new Range\(\s*(\d+)L\s*,\s*(\d+)L\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')
_RANGE_NA = re.compile(r'new Range\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)L\s*,\s*(\d+)L\s*\)')
# new NamedAddress(2183354896L, "name")
_NAMED = re.compile(r'new NamedAddress\(\s*(\d+)L\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')
# new Probe(2183430960L, "name")
_PROBE = re.compile(r'new Probe\(\s*(\d+)L\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)')
# private static final long NAME = 2181400604L;
_CONST = re.compile(r'private static final long (\w+)\s*=\s*(\d+)L\s*;')
# private static final long[] NAME = new long[]{ ... };
_ARRAY = re.compile(r'private static final long\[\]\s+(\w+)\s*=\s*new long\[\]\s*\{([^}]*)\}\s*;')
# output.write("PIN tackle_type_store 0x823D9B84 ...")
_PIN = re.compile(r'output\.write\("PIN (\w+) (0x[0-9A-Fa-f]+)')


def _hex(value: str) -> str:
    return f"0x{int(value):08X}"


def _hex_literal(token: str) -> str:
    token = token.strip().rstrip("Ll").strip()
    if token.lower().startswith("0x"):
        return f"0x{int(token, 16):08X}"
    return f"0x{int(token):08X}"


def _unquote(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def parse_script(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    md5 = _MD5.search(text)
    words = [
        {"address": _hex(a), "expected": _hex(e), "meaning": _unquote(m)}
        for a, e, m in _WORD.findall(text)
    ]
    ranges = [
        {"first": _hex(a), "last": _hex(b), "name": _unquote(n)}
        for a, b, n in _RANGE_AA.findall(text)
    ]
    ranges += [
        {"first": _hex(a), "last": _hex(b), "name": _unquote(n)}
        for n, a, b in _RANGE_NA.findall(text)
    ]
    named = [
        {"address": _hex(a), "name": _unquote(n)}
        for a, n in _NAMED.findall(text)
    ]
    probes = [
        {"address": _hex(a), "name": _unquote(n)}
        for a, n in _PROBE.findall(text)
    ]
    constants = [
        {"name": name, "value": _hex(value)}
        for name, value in _CONST.findall(text)
    ]
    arrays = [
        {
            "name": name,
            "values": [
                _hex_literal(token)
                for token in body.split(",")
                if token.strip()
            ],
        }
        for name, body in _ARRAY.findall(text)
    ]
    pins = [
        {"name": name, "address": f"0x{int(addr, 16):08X}"}
        for name, addr in _PIN.findall(text)
    ]
    return {
        "script": path.name,
        "expected_md5": md5.group(1).casefold() if md5 else None,
        "word_count": len(words),
        "range_count": len(ranges),
        "named_address_count": len(named),
        "probe_count": len(probes),
        "constant_count": len(constants),
        "array_count": len(arrays),
        "pin_count": len(pins),
        "words": words,
        "ranges": ranges,
        "named_addresses": named,
        "probes": probes,
        "constants": constants,
        "arrays": arrays,
        "pins": pins,
    }


def build_inventory(script_dir: Path = SCRIPT_DIR) -> dict[str, object]:
    scripts = sorted(script_dir.glob("Backbreaker*.java"))
    parsed = [parse_script(path) for path in scripts]
    md5s = sorted({item["expected_md5"] for item in parsed if item["expected_md5"]})
    return {
        "schema": "backbreaker_recovered_inventory/v1",
        "script_count": len(parsed),
        "source_revision_md5s": md5s,
        "totals": {
            "words": sum(item["word_count"] for item in parsed),
            "ranges": sum(item["range_count"] for item in parsed),
            "named_addresses": sum(item["named_address_count"] for item in parsed),
            "probes": sum(item["probe_count"] for item in parsed),
            "constants": sum(item["constant_count"] for item in parsed),
            "arrays": sum(item["array_count"] for item in parsed),
            "pins": sum(item["pin_count"] for item in parsed),
        },
        "scripts": parsed,
    }


def main() -> None:
    inventory = build_inventory()
    print(json.dumps(inventory, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
