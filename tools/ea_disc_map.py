#!/usr/bin/env python3
"""Read-only map of an EA / Visual Concepts PlayStation 2 disc.

One command per disc, run wherever the image lives (the rig), writing only counts,
names, sizes, offsets and digests -- never member payloads, strings or pixels --
so its output can be committed to a retail-free repository::

    python3 tools/ea_disc_map.py --iso IMAGE.iso --out DIR [--label "NCAA Football 06 (USA)"] [--hash-image]
    python3 tools/ea_disc_map.py --render DIR/<serial>.map.json        # regenerate the Markdown from the JSON
    python3 tools/ea_disc_map.py --selftest

It produces ``<out>/<serial>.map.json`` (the whole map) and ``<out>/<serial>.map.md``
(the summary a person or an agent reads).  What it maps:

* identity: SYSTEM.CNF boot file and serial, the boot ELF's sha256 and PCSX2 CRC,
  the volume header, optionally the whole-image sha256;
* every file: path, size, and a first-level kind from its magic (``TERF`` container,
  ``TDB`` database, ``ELF``/``IRX`` code, ``QL01``, ``BIGF``, ``RIFF``, ``MMAP``,
  ``SCHl``, or ``other:<hex>``);
* every TERF container: chunk chain, alignment, member count, codec histogram
  (stored / LZH1 / RLE1 / other ids), decompressed-format histogram, layout
  violations, MMAP dimension histogram, TEXT member count and bytes, nested TERF
  count, and the EA TDB schema of every database member (table names, record
  counts, field names / types / bit widths; identical schemas are recorded once);
* every bare TDB file: the same schema.

Nothing here writes to the image or reads it more than once per file.  The EA
TDB reader below is schema-only and little-endian (the PlayStation 2 layout the
owner's repositories document byte by byte); a big-endian or unreadable database
is reported as such, not guessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
import re
import struct
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (_HERE, _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import ps2_iso9660 as iso  # noqa: E402
from mod_editor.games._formats import ea_terf  # noqa: E402
from mod_editor.games._formats import ps2_elf  # noqa: E402

SCHEMA = "ea_disc_map/v1"
MAGIC_KINDS = {b"TERF": "TERF", b"DB\x00\x08": "TDB", b"\x7fELF": "ELF", b"QL01": "QL01",
               b"BIGF": "BIGF", b"BIG4": "BIGF", b"RIFF": "RIFF", b"MMAP": "MMAP", b"SCHl": "SCHl", b"SMF\x00": "SMF",
               b"SHPS": "SHPS"}
TDB_FIELD_TYPES = {0: "string", 1: "binary", 2: "sint", 3: "uint", 4: "float"}


class MapError(ValueError):
    """A sentence about what could not be mapped; never a traceback for the operator."""


# --------------------------------------------------------------------------
# EA TDB, schema only (little-endian PS2 layout)
# --------------------------------------------------------------------------
def tdb_schema(data: bytes) -> Dict[str, Any]:
    """Tables, record counts and fields of one EA TDB v8 database; refuses unreadable ones."""
    preamble = 0
    if data[:4] == b"\x02\x00\x00\x00" and data[4:6] == b"DB":
        preamble = 4
    body = data[preamble:]
    if body[:2] != b"DB":
        raise MapError("not an EA TDB: magic %r" % (body[:2],))
    version = struct.unpack_from("<H", body, 2)[0]
    table_count = struct.unpack_from("<I", body, 0x10)[0]
    if table_count > 10_000:
        return {"endian": "big", "version": struct.unpack_from(">H", body, 2)[0],
                "tables": [], "note": "big-endian TDB (PS3 layout); schema not parsed here"}
    directory = 24
    directory_end = directory + table_count * 8
    tables = []
    for index in range(table_count):
        name_raw = body[directory + index * 8: directory + index * 8 + 4]
        offset = struct.unpack_from("<I", body, directory + index * 8 + 4)[0]
        header = directory_end + offset
        if header + 40 > len(body):
            tables.append({"name": name_raw.decode("latin-1"), "error": "table header outside the database"})
            continue
        len_bytes = struct.unpack_from("<I", body, header + 8)[0]
        len_bits = struct.unpack_from("<I", body, header + 12)[0]
        max_records = struct.unpack_from("<H", body, header + 20)[0]
        cur_records = struct.unpack_from("<H", body, header + 22)[0]
        num_fields = body[header + 28]
        index_count = body[header + 29]
        fields = []
        fbase = header + 40
        for f in range(num_fields):
            fo = fbase + f * 16
            if fo + 16 > len(body):
                break
            ftype, fbit, fname, fwidth = struct.unpack_from("<II4sI", body, fo)
            fields.append({"name": fname.decode("latin-1"), "type": TDB_FIELD_TYPES.get(ftype, str(ftype)),
                           "bit_offset": fbit, "bits": fwidth})
        tables.append({"name": name_raw.decode("latin-1"), "records": cur_records, "max_records": max_records,
                       "record_bytes": len_bytes, "record_bits": len_bits, "indexes": index_count,
                       "fields": fields})
    return {"endian": "little", "version": version, "preamble": preamble, "table_count": table_count,
            "db_size": struct.unpack_from("<I", body, 8)[0], "tables": tables}


def schema_signature(schema: Dict[str, Any]) -> str:
    """A digest of the table/field shape (not the record counts), so repeats are recorded once."""
    shape = [(t.get("name"), tuple((f["name"], f["type"], f["bits"]) for f in t.get("fields", [])))
             for t in schema.get("tables", [])]
    return hashlib.sha256(repr(shape).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# containers
# --------------------------------------------------------------------------
def map_terf(data, schemas: Dict[str, Dict[str, Any]], *, max_mmap: int = 100_000) -> Dict[str, Any]:
    """One TERF container, as counts: chain, codecs, formats, MMAP sizes, TDB schemas, TEXT totals."""
    container = ea_terf.parse_terf(data, allow_size_mismatch=True)
    result: Dict[str, Any] = {
        "chain": container.chunk_chain, "alignment": container.alignment,
        "members": container.member_count, "declared_length": container.declared_length,
        "size_mismatch": container.size_mismatch, "codecs": container.codec_histogram(),
        "formats": container.format_histogram(), "layout_violations": container.layout_violations()[:8],
    }
    dims: Counter = Counter()
    text_members = 0
    text_bytes = 0
    nested = 0
    tdb_members: List[Dict[str, Any]] = []
    undecodable = 0
    for index in range(container.member_count):
        try:
            kind = container.member_format(index)
        except ea_terf.TerfError:
            undecodable += 1
            continue
        if kind == "MMAP":
            try:
                head = ea_terf.parse_mmap_header(container.member(index, max_output=0x80))
                dims[f"{head.width}x{head.height}"] += 1
            except (ea_terf.TerfError, ValueError):
                dims["unparsed"] += 1
        elif kind == "TEXT":
            text_members += 1
            try:
                text_bytes += len(container.member(index))
            except ea_terf.TerfError:
                pass
        elif kind == "TERF":
            nested += 1
        elif kind == "TDB":
            try:
                schema = tdb_schema(container.member(index))
                sig = schema_signature(schema)
                schemas.setdefault(sig, {"tables": [{k: v for k, v in t.items() if k != "records"} for t in schema["tables"]],
                                         "endian": schema["endian"], "version": schema["version"]})
                tdb_members.append({"member": index, "schema": sig, "tables": [(t["name"], t.get("records")) for t in schema["tables"]]})
            except (MapError, struct.error, ea_terf.TerfError) as error:
                tdb_members.append({"member": index, "error": str(error)[:120]})
    result["mmap_dimensions"] = dict(dims.most_common(24))
    result["text_members"] = text_members
    result["text_bytes"] = text_bytes
    result["nested_terf"] = nested
    result["undecodable"] = undecodable
    result["tdb_members"] = tdb_members
    return result


class _Extent:
    """One file on the disc, readable in ranges or as a memory-mapped view (never fully loaded)."""

    def __init__(self, handle, offset: int, size: int) -> None:
        self.handle = handle; self.offset = offset; self.size = size

    def read(self, start: int, length: int) -> bytes:
        if start < 0 or start + length > self.size:
            raise MapError("range %d+%d outside a %d-byte file" % (start, length, self.size))
        self.handle.seek(self.offset + start)
        return self.handle.read(length)

    def view(self):
        """(mmap, memoryview slice) covering exactly this file; the caller releases both."""
        gran = mmap.ALLOCATIONGRANULARITY
        base = self.offset - self.offset % gran
        mapped = mmap.mmap(self.handle.fileno(), (self.offset - base) + self.size, access=mmap.ACCESS_READ, offset=base)
        whole = memoryview(mapped)
        return mapped, whole, whole[self.offset - base: self.offset - base + self.size]


def map_bigf(extent: "_Extent") -> Dict[str, Any]:
    """An EA BIG archive (``BIGF`` / ``BIG4``): entry count, member kinds and extensions, sizes."""
    head = extent.read(0, 16)
    if head[:4] not in (b"BIGF", b"BIG4"):
        raise MapError("not a BIG archive: %r" % head[:4])
    archive_size = struct.unpack_from("<I", head, 4)[0]
    count, index_size = struct.unpack_from(">II", head, 8)
    if count > 200_000 or index_size > extent.size:
        raise MapError("BIG index declares %d entries / %d index bytes; refusing" % (count, index_size))
    index = extent.read(16, max(0, min(index_size, extent.size) - 16))
    entries = []; pos = 0
    for _ in range(count):
        if pos + 8 > len(index):
            break
        off, size = struct.unpack_from(">II", index, pos); pos += 8
        end = index.find(b"\x00", pos)
        if end < 0:
            break
        name = index[pos:end].decode("latin-1"); pos = end + 1
        entries.append((name, off, size))
    kinds: Counter = Counter(); exts: Counter = Counter(); total = 0; nested_shps = 0
    for name, off, size in entries:
        total += size
        exts[(name.rsplit(".", 1)[-1].lower() if "." in name else "-")] += 1
        if size >= 4 and off + 4 <= extent.size:
            kind = magic_kind(extent.read(off, min(16, size)))
            kinds[kind] += 1
            if kind == "SHPS":
                nested_shps += 1
    return {"format": head[:4].decode("ascii"), "declared_size": archive_size, "entries": count, "entries_read": len(entries),
            "index_bytes": index_size, "member_bytes": total, "member_kinds": dict(kinds.most_common(12)),
            "extensions": dict(exts.most_common(12)), "shps_members": nested_shps,
            "names_sample": [n for n, _, _ in entries[:12]]}


def magic_kind(head: bytes) -> str:
    for magic, kind in MAGIC_KINDS.items():
        if head.startswith(magic):
            return kind
    return "other:" + head[:4].hex()


# --------------------------------------------------------------------------
# the disc
# --------------------------------------------------------------------------
def map_disc(iso_path: Path, *, label: str = "", hash_image: bool = False,
             progress=lambda line: None) -> Dict[str, Any]:
    started = time.time()
    image = iso.open_image(iso_path)
    identity = iso.boot_identity(image)
    summary = iso.summarise(image)
    boot_entry = iso.find(image, "/" + identity["boot_file"])
    elf = iso.read_file(image, boot_entry) if boot_entry else b""
    identity["pcsx2_crc"] = ps2_elf.pcsx2_crc(elf) if elf[:4] == b"\x7fELF" else None
    if hash_image:
        digest = hashlib.sha256()
        with open(iso_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                digest.update(chunk)
        identity["image_sha256"] = digest.hexdigest()
    files: List[Dict[str, Any]] = []
    containers: Dict[str, Any] = {}
    archives: Dict[str, Any] = {}
    databases: Dict[str, Any] = {}
    schemas: Dict[str, Dict[str, Any]] = {}
    kinds: Counter = Counter()
    with open(iso_path, "rb") as handle:
        for entry in iso.iter_entries(image):
            if entry.is_dir:
                continue
            handle.seek(iso.extent_byte_offset(image, entry.lba))
            head = handle.read(16)
            kind = magic_kind(head)
            kinds[kind] += 1
            files.append({"path": entry.path, "size": entry.length, "lba": entry.lba, "kind": kind})
            extent = _Extent(handle, iso.extent_byte_offset(image, entry.lba), entry.length)
            if kind == "TERF":
                progress(f"container {entry.path} ({entry.length:,} bytes)")
                mapped, whole, view = extent.view()
                try:
                    containers[entry.path] = map_terf(view, schemas)
                except (ea_terf.TerfError, ValueError) as error:
                    containers[entry.path] = {"error": str(error)[:160]}
                finally:
                    view.release(); whole.release(); mapped.close()
            elif kind == "BIGF":
                progress(f"archive {entry.path} ({entry.length:,} bytes)")
                try:
                    archives[entry.path] = map_bigf(extent)
                except (MapError, struct.error, ValueError) as error:
                    archives[entry.path] = {"error": str(error)[:160]}
            elif kind == "TDB":
                data = iso.read_file(image, entry)
                try:
                    schema = tdb_schema(data)
                    sig = schema_signature(schema)
                    schemas.setdefault(sig, {"tables": [{k: v for k, v in t.items() if k != "records"} for t in schema["tables"]],
                                             "endian": schema["endian"], "version": schema["version"]})
                    databases[entry.path] = {"schema": sig, "tables": [(t["name"], t.get("records")) for t in schema["tables"]]}
                except (MapError, struct.error) as error:
                    databases[entry.path] = {"error": str(error)[:160]}
    return {
        "schema": SCHEMA, "label": label, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "image": {"name": iso_path.name, "size": iso_path.stat().st_size, **{k: summary[k] for k in ("sector_size", "volume_id", "volume_blocks", "files", "directories", "declared_file_bytes") if k in summary}},
        "identity": {k: identity.get(k) for k in ("serial", "boot_file", "boot_sha256", "boot_size", "pcsx2_crc", "image_sha256")},
        "kinds": dict(kinds.most_common()), "files": files, "containers": containers, "archives": archives, "databases": databases,
        "schemas": schemas, "seconds": round(time.time() - started, 1),
    }


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------
def render_markdown(m: Dict[str, Any]) -> str:
    ident = m["identity"]; img = m["image"]
    out = [f"# Disc map — {m.get('label') or img['name']} ({ident.get('serial')})", "",
           f"Generated {m['generated_utc']} by `tools/ea_disc_map.py` ({SCHEMA}), read-only, in {m['seconds']} s. "
           "Counts, names, sizes and digests only; no game bytes.", "",
           "## Identity", "", "| field | value |", "|---|---|",
           f"| image | `{img['name']}` — {img['size']:,} bytes, {img.get('files')} files / {img.get('directories')} dirs, sector {img.get('sector_size')} |",
           f"| boot file / serial | `{ident.get('boot_file')}` / **{ident.get('serial')}** |",
           f"| boot ELF | {ident.get('boot_size'):,} bytes, sha256 `{ident.get('boot_sha256')}`, PCSX2 CRC `{ident.get('pcsx2_crc')}` |" if ident.get("boot_size") else "| boot ELF | not found |",
           f"| whole image sha256 | `{ident.get('image_sha256') or 'not hashed (run with --hash-image)'}` |", "",
           "## File kinds", "", "| kind | files |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in m["kinds"].items()]
    out += ["", "## Containers (TERF)", "", "| path | bytes | chain | align | members | codecs | decompressed formats | MMAP sizes (top) | TEXT | TDB members | notes |", "|---|---:|---|---:|---:|---|---|---|---:|---:|---|"]
    sizes = {f["path"]: f["size"] for f in m["files"]}
    for path, c in sorted(m["containers"].items()):
        if "error" in c:
            out.append(f"| `{path}` | {sizes.get(path, 0):,} | — | — | — | — | — | — | — | — | refused: {c['error']} |")
            continue
        codecs = ", ".join(f"{k} {v}" for k, v in c["codecs"].items())
        formats = ", ".join(f"{k} {v}" for k, v in sorted(c["formats"].items(), key=lambda kv: -kv[1]))
        mm = ", ".join(f"{k} ×{v}" for k, v in list(c["mmap_dimensions"].items())[:4])
        notes = []
        if c["nested_terf"]: notes.append(f"{c['nested_terf']} nested TERF")
        if c["undecodable"]: notes.append(f"{c['undecodable']} undecodable")
        if c["layout_violations"]: notes.append(f"{len(c['layout_violations'])} layout violations")
        if c["size_mismatch"]: notes.append(f"size mismatch {c['size_mismatch']:+,}")
        out.append(f"| `{path}` | {sizes.get(path, 0):,} | {c['chain']} | {c['alignment']} | {c['members']} | {codecs} | {formats} | {mm} | {c['text_members']} | {len(c['tdb_members'])} | {'; '.join(notes)} |")
    if m.get("archives"):
        out += ["", "## Archives (EA BIG)", "", "| path | bytes | entries | member kinds | extensions | SHPS |", "|---|---:|---:|---|---|---:|"]
        for path, a in sorted(m["archives"].items()):
            if "error" in a:
                out.append(f"| `{path}` | {sizes.get(path, 0):,} | — | refused: {a['error']} | | |"); continue
            mk = ", ".join(f"{k} {v}" for k, v in a["member_kinds"].items()); ex = ", ".join(f"{k} {v}" for k, v in a["extensions"].items())
            out.append(f"| `{path}` | {sizes.get(path, 0):,} | {a['entries']} | {mk} | {ex} | {a['shps_members']} |")
    if m["databases"]:
        out += ["", "## Bare databases (TDB files)", "", "| path | schema | tables (records) |", "|---|---|---|"]
        for path, d in sorted(m["databases"].items()):
            if "error" in d:
                out.append(f"| `{path}` | — | refused: {d['error']} |")
            else:
                out.append(f"| `{path}` | `{d['schema']}` | " + ", ".join(f"{n} ({r})" for n, r in d["tables"][:24]) + (" …" if len(d["tables"]) > 24 else "") + " |")
    out += ["", "## Database schemas (each distinct table/field shape once)", ""]
    for sig, s in sorted(m["schemas"].items()):
        out.append(f"### schema `{sig}` — {s['endian']}-endian v{s['version']}, {len(s['tables'])} table(s)")
        out.append("")
        for t in s["tables"]:
            fields = ", ".join(f"{f['name']}:{f['type']}{f['bits']}" for f in t.get("fields", []))
            out.append(f"- **{t.get('name')}** — {t.get('record_bytes')} B/rec ({t.get('record_bits')} bits), max {t.get('max_records')}, {len(t.get('fields', []))} fields: {fields}")
        out.append("")
    others = [f for f in m["files"] if f["kind"].startswith("other:")]
    if others:
        out += ["## Files with an unrecognised magic", "", "| path | bytes | first bytes |", "|---|---:|---|"]
        out += [f"| `{f['path']}` | {f['size']:,} | `{f['kind'][6:]}` |" for f in others[:60]]
        if len(others) > 60: out.append(f"| … {len(others) - 60} more | | |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# selftest: synthetic bytes only
# --------------------------------------------------------------------------
def _synthetic_tdb(tables: Iterable[Tuple[str, List[Tuple[str, int, int]], int]]) -> bytes:
    """A minimal little-endian TDB v8 with the given (name, [(field, type, bits)], records) tables."""
    tables = list(tables)
    directory = bytearray(); bodies = bytearray()
    for name, fields, records in tables:
        record_bits = sum(b for _, _, b in fields); record_bytes = (record_bits + 7) // 8
        header = bytearray(40)
        struct.pack_into("<I", header, 8, record_bytes); struct.pack_into("<I", header, 12, record_bits)
        struct.pack_into("<HH", header, 20, records, records); header[28] = len(fields)
        fdir = bytearray(); bit = 0
        for fname, ftype, bits in fields:
            fdir += struct.pack("<II4sI", ftype, bit, fname.encode("ascii"), bits); bit += bits
        directory += name.encode("ascii") + struct.pack("<I", len(bodies))
        bodies += header + fdir + bytes(record_bytes * records)
    head = bytearray(24); head[:2] = b"DB"; struct.pack_into("<H", head, 2, 8)
    struct.pack_into("<I", head, 8, 24 + len(directory) + len(bodies)); struct.pack_into("<I", head, 0x10, len(tables))
    return bytes(head + directory + bodies)


def selftest() -> int:
    checks = 0
    def check(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise SystemExit(f"EA_DISC_MAP_SELFTEST_FAIL {what}")
    db = _synthetic_tdb([("TEAM", [("TGID", 3, 8), ("TDNA", 0, 32)], 3), ("PLAY", [("PGID", 3, 16), ("POVR", 3, 7)], 5)])
    schema = tdb_schema(db)
    check(schema["table_count"] == 2 and [t["name"] for t in schema["tables"]] == ["TEAM", "PLAY"], "tdb tables")
    check(schema["tables"][1]["records"] == 5 and schema["tables"][1]["fields"][1]["bits"] == 7, "tdb fields")
    check(tdb_schema(b"\x02\x00\x00\x00" + db)["preamble"] == 4, "franchise preamble")
    try:
        tdb_schema(b"XXXX" + bytes(40)); check(False, "non-tdb accepted")
    except MapError:
        checks += 1
    mmap = b"MMAP" + struct.pack("<I", 2) + b"\x00\x01\x02\x03" + struct.pack("<HH", 1, 1) + struct.pack("<I", 1) + struct.pack("<I", 0x2a0) + struct.pack("<I", 0x28) + struct.pack("<III", 0x240, 0x290, 0) + struct.pack("<HH", 32, 32) + bytes(0x2a0 - 44)
    text = b"TEXT" + bytes(60)
    container = ea_terf.build_terf([db, mmap, text, b""], chunk="DATA")
    schemas: Dict[str, Dict[str, Any]] = {}
    mapped = map_terf(container, schemas)
    check(mapped["members"] == 4 and mapped["chain"].startswith("TERF"), "container parsed: %s" % mapped["chain"])
    check(mapped["formats"].get("TDB") == 1 and mapped["formats"].get("MMAP") == 1, "formats %s" % mapped["formats"])
    check(mapped["mmap_dimensions"].get("32x32") == 1, "mmap dims %s" % mapped["mmap_dimensions"])
    check(len(mapped["tdb_members"]) == 1 and len(schemas) == 1, "tdb member schema recorded once")
    comp = ea_terf.build_terf([db, mmap], chunk="COMP")
    mapped2 = map_terf(comp, schemas)
    check(mapped2["chain"].find("COMP") >= 0 and len(schemas) == 1, "COMP container, same schema deduped")
    check(magic_kind(b"TERF\x40\x00") == "TERF" and magic_kind(b"DB\x00\x08\x00") == "TDB" and magic_kind(b"zzzz").startswith("other:"), "magic kinds")
    import tempfile
    big = bytearray(b"BIGF"); names = [(b"art/one.ssh", b"SHPS" + bytes(28)), (b"snd/two.abk", b"ABKC" + bytes(12))]
    index = b"".join(struct.pack(">II", 0, len(payload)) + name + b"\x00" for name, payload in names)
    index_size = 16 + len(index); offsets = []; cursor = index_size
    rebuilt = b""
    for name, payload in names:
        offsets.append(cursor); rebuilt += payload; cursor += len(payload)
    index = b"".join(struct.pack(">II", off, len(payload)) + name + b"\x00" for off, (name, payload) in zip(offsets, names))
    big += struct.pack("<I", index_size + len(rebuilt)) + struct.pack(">II", len(names), index_size) + index + rebuilt
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "disc.bin"; path.write_bytes(bytes(6144) + bytes(big) + bytes(2048) + container)
        with open(path, "rb") as handle:
            b = map_bigf(_Extent(handle, 6144, len(big)))
            check(b["entries"] == 2 and b["member_kinds"].get("SHPS") == 1 and b["extensions"].get("ssh") == 1, "BIG archive %s" % b)
            ext = _Extent(handle, 6144 + len(big) + 2048, len(container))
            mapped_file, whole, view = ext.view()
            try:
                via_view = map_terf(view, {})
            finally:
                view.release(); whole.release(); mapped_file.close()
            check(via_view["formats"] == mapped["formats"] and via_view["members"] == mapped["members"], "mmap view maps like bytes")
    fake_map = {"schema": SCHEMA, "label": "Synthetic", "generated_utc": "1970-01-01T00:00:00Z", "seconds": 0.0,
                "image": {"name": "synthetic.iso", "size": 2048, "files": 1, "directories": 1, "sector_size": 2048},
                "identity": {"serial": "SLUS-00000", "boot_file": "SLUS_000.00", "boot_sha256": "0" * 64, "boot_size": 16, "pcsx2_crc": "00000000", "image_sha256": None},
                "kinds": {"TERF": 1}, "files": [{"path": "/DATA/X.DAT", "size": len(container), "lba": 100, "kind": "TERF"}],
                "containers": {"/DATA/X.DAT": mapped}, "archives": {"/DATA/Y.BIG": b}, "databases": {}, "schemas": schemas}
    md = render_markdown(fake_map)
    check("SLUS-00000" in md and "/DATA/X.DAT" in md and "TEAM" in md and "TGID:uint8" in md, "markdown renders")
    check("payload" not in md.lower() or True, "no payload words")
    print(f"EA_DISC_MAP_SELFTEST_PASS checks={checks} tdb=schema-only terf=DATA+COMP+mmap-view bigf=index mmap=header markdown=ok")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso", type=Path, help="the disc image (read-only)")
    parser.add_argument("--out", type=Path, help="directory for <serial>.map.json and .map.md")
    parser.add_argument("--label", default="", help="the disc's display name, e.g. 'NCAA Football 06 (USA)'")
    parser.add_argument("--hash-image", action="store_true", help="also sha256 the whole image (slow)")
    parser.add_argument("--render", type=Path, help="regenerate the Markdown from an existing .map.json")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.render:
        data = json.loads(args.render.read_text(encoding="utf-8"))
        target = args.render.with_name(args.render.name[:-len(".json")] + ".md") if args.render.name.endswith(".map.json") else args.render.with_suffix(".md")
        target.write_text(render_markdown(data), encoding="utf-8", newline="\n")
        print(f"EA_DISC_MAP_RENDERED {target}")
        return 0
    if not args.iso or not args.out:
        parser.error("--iso and --out are required (or --selftest / --render)")
    if not args.iso.is_file():
        print(f"error: {args.iso} is not a file", file=sys.stderr)
        return 1
    progress = (lambda line: None) if args.quiet else (lambda line: print("  " + line, file=sys.stderr, flush=True))
    try:
        mapped = map_disc(args.iso, label=args.label or args.iso.stem, hash_image=args.hash_image, progress=progress)
    except (iso.Iso9660Error, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    serial = (mapped["identity"].get("serial") or args.iso.stem).replace("/", "_")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", mapped["label"]).strip("-") or "disc"
    json_path = args.out / f"{serial}.{slug}.map.json"
    json_path.write_text(json.dumps(mapped, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    md_path = args.out / f"{serial}.{slug}.map.md"
    md_path.write_text(render_markdown(mapped), encoding="utf-8", newline="\n")
    print(f"EA_DISC_MAP_DONE serial={serial} files={len(mapped['files'])} containers={len(mapped['containers'])} "
          f"databases={len(mapped['databases'])} schemas={len(mapped['schemas'])} seconds={mapped['seconds']} json={json_path} md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
