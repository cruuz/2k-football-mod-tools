"""Versioned, fixed-span mode text. EXPERIMENTAL / UNWITNESSED.

Pure status/apply accepts default.xbe or the complete Crib STRG resource.
Image adapters read bounded resources through existing XDVDFS/pack readers.
No runtime code, menu descriptor, save type, pointer or allocation is changed.
Only desired/fallbacks in the JSON are user-editable; source bindings are pinned.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import struct
from typing import Any, Callable, Mapping

from . import nfl2k5_rdata_sites as rdata
from . import platform_compat as io
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_safe_text_banks import encode_fixed_utf16le

MANIFEST = Path(__file__).resolve().parents[2] / "data/nfl2k5_modern_naming_2k.json"
STRUCTURE_SHA256 = "0c66d7297654e5e2df87710400f390d9679e6c8b4c236a45ed3cc14d803397f3"
SCHEMA = "nfl2k5_modern_naming_receipt/v1"
OWNER = "nfl2k5_modern_naming"
REQUESTS: tuple = ()  # Existing literal allocations only; no allocator owner.
OPTION_CAPTION = "Modern 2K mode names (MyNFL, MyPlayer, Play Now)"
HELP_TEXT = ("Retail uses Quick Game, Franchise and Create Player. Patch uses Play Now, "
             "MyNFL and MyPlayer. Coach's Desk and The Crib keep their names. "
             "Experimental / Unwitnessed. Preview every change in Text & Team Identity.")
MAX_XBE_BYTES = 32 * 1024 * 1024
_TOKEN = re.compile(r"\|[^|]+\||\[[A-Z0-9_]+\]|%(?:[-+0 #]*\d*(?:\.\d+)?[a-zA-Z%])")


class ModernNamingError(ValueError):
    pass


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ModernNamingError(message)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _bindings(data: dict) -> dict:
    return {key: ([{k: v for k, v in row.items() if k not in ("desired", "fallbacks")}
                   for row in value] if key in ("cells", "career_labels") else value)
            for key, value in data.items()}


def _choice(cell: dict, size: int | None = None) -> str:
    size = cell["allocation_bytes"] if size is None else size
    _require(type(size) is int and size >= 2 and size % 2 == 0, "Invalid text allocation")
    wanted, alternatives = cell.get("desired"), cell.get("fallbacks")
    _require(isinstance(wanted, str) and isinstance(alternatives, list),
             "Each name needs desired text and a list of fallback strings")
    candidates = [wanted, *alternatives]
    for value in candidates:
        _require(isinstance(value, str) and bool(value) and "\0" not in value,
                 "Names must be nonempty strings without NUL characters")
        _require(_TOKEN.findall(value) == _TOKEN.findall(cell["retail"]),
                 "Replacement changes a game placeholder or controller/link token")
        try:
            value.encode("utf-16le")
        except UnicodeError as exc:
            raise ModernNamingError("Name contains invalid Unicode") from exc
    for value in candidates:
        if len(value.encode("utf-16le")) + 2 <= size:
            return value
    raise ModernNamingError(f"No name fits {cell.get('asset_id', cell.get('role'))}: "
                            f"{size // 2 - 1} UTF-16 units available")


def manifest(path: Path | str | None = None) -> dict[str, Any]:
    """Read each time so edited labels take effect; refuse edited source locators."""
    source = Path(path) if path is not None else MANIFEST
    _require(source.stat().st_size <= 1024 * 1024, "Naming manifest exceeds 1 MiB")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        _require(isinstance(data, dict) and _hash(_canonical(_bindings(data))) == STRUCTURE_SHA256,
                 "Naming manifest source bindings/version changed; edit only desired and fallbacks")
        for cell in [*data["cells"], *data["career_labels"]]:
            _choice(cell)
        return data
    except (KeyError, TypeError, AttributeError) as exc:
        raise ModernNamingError("Malformed naming manifest") from exc


def all_strings_fit(manifest_path: Path | str | None = None) -> bool:
    """Experimental preset admission. Source compatibility is checked separately."""
    try:
        manifest(manifest_path)
        return True
    except (OSError, ValueError):
        return False


def preset_enabled(preset: str, manifest_path: Path | str | None = None) -> bool:
    _require(preset in ("basic", "advanced", "experimental"), "Unknown Build preset")
    return preset == "experimental" and all_strings_fit(manifest_path)


def career_text(role: str, allocation_bytes: int = 20, *,
                manifest_path: Path | str | None = None) -> bytes:
    """MyCareer owner calls this when installing its own menu/title descriptors.

    The proposed source spelling is a contract, not a claimed retail menu slot.
    The owner must reserve the passed size and pin/install its own descriptors.
    """
    data = manifest(manifest_path)
    cell = next((c for c in data["career_labels"] if c["role"] == role), None)
    _require(cell is not None, "Unknown MyCareer text role")
    return encode_fixed_utf16le(_choice(cell, allocation_bytes), allocation_bytes, role)


def _rows(data: dict, domain: str) -> list[dict]:
    return [c for c in data["cells"] if c["domain"] == domain]


def _domain(payload: bytes) -> str:
    if payload[:4] == b"XBEH":
        _require(len(payload) <= MAX_XBE_BYTES, "XBE exceeds naming reader bound")
        return "xbe"
    if payload[:4] == b"STRG":
        return "strg"
    raise ModernNamingError("Expected default.xbe or the complete Crib STRG resource")


def _offset(payload: bytes, cell: dict) -> int:
    return rdata.offset_of(payload, cell["va"]) if cell["domain"] == "xbe" else cell["resource_offset"]


def _encoded(cell: dict, modern: bool) -> bytes:
    return encode_fixed_utf16le(_choice(cell) if modern else cell["retail"],
                               cell["allocation_bytes"], cell["asset_id"])


def _structure(payload: bytes, domain: str, data: dict) -> None:
    if domain == "xbe":
        from . import nfl2k5_depth_chart_storage as storage, nfl2k5_xbe_space as space
        _require(len(payload) in (11_948_032, storage.FILE_SIZE, *space.accepted_file_sizes()),
                 "XBE length is not retail or a recognized grown size")
        pin = data["xbe_section"]
        sections = _sections(payload)
        section = sections[pin["index"]]
        header = section.header_offset
        flags, va, vsize, raw, size, name_va = struct.unpack_from("<6I", payload, header)
        name_off = rdata.offset_of(payload, name_va)
        _require((flags, va, vsize, raw, size) == (pin["flags"], pin["virtual_address"],
                 pin["virtual_size"], pin["raw_offset"], pin["raw_size"]) and
                 payload[name_off:name_off + 9] == b".string_\0" and raw + size <= len(payload),
                 "Foreign XBE string section geometry")
        _require(section_digest(payload, section) == section.stored_digest,
                 "XBE string section digest differs; reload a verified source")
        for cell in _rows(data, domain):
            _require(va <= cell["va"] and cell["va"] + cell["allocation_bytes"] <= va + size,
                     "Name is outside the pinned string section")
    else:
        pin = data["resource"]
        _require(len(payload) == pin["resource_size"] and
                 payload[:32].hex() == pin["wrapper_hex"] and
                 _hash(payload[:pin["structure_size"]]) == pin["structure_sha256"],
                 "Foreign STRG wrapper, lookup IDs or allocation pointers")
        from nfl_scene_probe import ResourceRecord
        from string_table_inventory import parse_nfl_body, rebuild_table
        record = ResourceRecord(pin["outer_index"], pin["outer_id"], pin["outer_size"],
                                pin["chunk_index"], pin["chunk_offset"], "STRG",
                                len(payload) - 32, *struct.unpack_from("<4I", payload, 8))
        table = parse_nfl_body(payload[32:], record)
        _require(rebuild_table(table) == payload[32:], "STRG codec round-trip differs")
        for cell in _rows(data, domain):
            item = table.pool[cell["pool_index"]]
            _require(item.offset + 32 == cell["resource_offset"] and
                     item.end_offset - item.offset == cell["allocation_bytes"],
                     "STRG allocation moved or changed size")


def _inspect(payload: bytes, data: dict) -> str:
    domain = _domain(payload)
    _structure(payload, domain, data)
    states = set()
    for cell in _rows(data, domain):
        offset = _offset(payload, cell)
        raw = payload[offset:offset + cell["allocation_bytes"]]
        before, after = _encoded(cell, False), _encoded(cell, True)
        _require(raw in (before, after), f"Foreign or manually edited name: {cell['asset_id']}")
        if before != after:
            states.add("retail" if raw == before else "applied")
    _require(len(states) <= 1, "Mixed retail and modern names; rebuild from the original source")
    return next(iter(states), "retail")


def status(payload: bytes, *, manifest_path: Path | str | None = None) -> str:
    try:
        return _inspect(payload, manifest(manifest_path))
    except (OSError, ValueError, IndexError, struct.error):
        return "foreign"


def preview_rows(*, enabled: bool = True, manifest_path: Path | str | None = None) -> list[dict]:
    """Complete review table; static rows are explicitly not source-verified."""
    return _preview_rows(manifest(manifest_path), enabled)


def _preview_rows(data: dict, enabled: bool) -> list[dict]:
    _require(type(enabled) is bool, "enabled must be boolean")
    return [{**cell, "before": cell["retail"], "after": _choice(cell) if enabled else cell["retail"],
             "character_limit": cell["allocation_bytes"] // 2 - 1,
             "fallback": _choice(cell) != cell["desired"], "source_verified": False,
             "enabled": enabled} for cell in data["cells"]]


def _receipt(payload: bytes, result: bytes, data: dict, enabled: bool, state: str) -> dict:
    domain = _domain(payload)
    writes = []
    for cell in _rows(data, domain):
        off, size = _offset(payload, cell), cell["allocation_bytes"]
        a, b = payload[off:off + size], result[off:off + size]
        if a != b:
            writes.append({"asset_id": cell["asset_id"], "bank_id": cell["bank_id"],
                           "offset": off, "allocation_bytes": size,
                           "before": a.decode("utf-16le").split("\0", 1)[0],
                           "after": b.decode("utf-16le").split("\0", 1)[0],
                           "before_sha256": _hash(a), "after_sha256": _hash(b),
                           "fallback": _choice(cell) != cell["desired"]})
    return {"schema": SCHEMA, "mapping_version": data["version"], "manifest_sha256": _hash(_canonical(data)),
            "experimental": True, "witnessed": False, "domain": domain,
            "status": _inspect(result, data), "enabled": enabled, "input_status": state,
            "already_applied": enabled and not writes, "changed_spans": len(writes),
            "changed_bytes": sum(a != b for a, b in zip(payload, result)),
            "before_sha256": _hash(payload), "after_sha256": _hash(result),
            "growth_bytes": 0, "writes": writes}


def _apply(payload: bytes, data: dict, enabled: bool, original: bytes | None) -> tuple[bytes, dict]:
    state = _inspect(payload, data)
    domain = _domain(payload)
    if not enabled:
        _require(original is not None, "Disabling needs the original source payload")
        _require(_domain(original) == domain and _inspect(original, data) == "retail",
                 "Restore source must contain verified retail names")
    out = bytearray(payload)
    for cell in _rows(data, domain):
        off, size = _offset(payload, cell), cell["allocation_bytes"]
        out[off:off + size] = (_encoded(cell, True) if enabled else
                             original[_offset(original, cell):_offset(original, cell) + size])
    if domain == "xbe" and out != payload:
        section = _sections(payload)[data["xbe_section"]["index"]]
        off = section.header_offset + 36
        out[off:off + 20] = section_digest(bytes(out), section)
    result = bytes(out)
    return result, _receipt(payload, result, data, enabled, state)


def apply(payload: bytes, *, enabled: bool = True, original: bytes | None = None,
          manifest_path: Path | str | None = None) -> tuple[bytes, dict]:
    """Refuse partial/foreign states before mutation. Disable restores only owned spans."""
    _require(type(enabled) is bool, "enabled must be boolean")
    return _apply(payload, manifest(manifest_path), enabled, original)


def catalog_overrides(catalog, *, enabled: bool = False, value_lookup=None,
                      manifest_path: Path | str | None = None) -> dict[str, str]:
    """Text facade preview; no staged edit survives disabling the Build option."""
    if not enabled:
        return {}
    assets = {a.asset_id: a for a in catalog.assets}
    result = {}
    for cell in _rows(manifest(manifest_path), "strg"):
        asset = assets.get(cell["asset_id"])
        _require(asset is not None and asset.editable and
                 asset.allocation_bytes == cell["allocation_bytes"], "Modern naming text bank is unavailable")
        value = value_lookup(asset) if value_lookup else asset.value
        _require(value in (cell["retail"], _choice(cell)),
                 f"Modern naming conflicts with a manual edit to {asset.label}")
        result[cell["asset_id"]] = _choice(cell)
    return result


def _outer_image():
    from .nfl2k5_roster_records import _outer_image as factory
    return factory()


@contextmanager
def _open(path, *, writable=False):
    # This Build adapter admits image files only; extracted research uses
    # nfl_outer's separate bounded API instead of image-specific descriptors.
    _require(Path(path).is_file(), "Modern naming needs a disc image file")
    with _outer_image()(path, writable=writable) as archive:
        yield archive


def _read_image(archive, data: dict, include_xbe: bool) -> tuple[dict[str, bytes], dict[str, int]]:
    pin = data["resource"]
    entry = archive.entries[pin["outer_index"]]
    _require(entry.name_id == int(pin["outer_id"], 0) and entry.size == pin["outer_size"],
             "Foreign Crib archive directory entry")
    pos = entry.virtual_offset + pin["chunk_offset"]
    payloads = {"strg": archive.read(pos, pin["resource_size"])}
    offsets = {"strg": pos}
    if include_xbe:
        from .nfl2k5_throw_tuning import image_xbe_extent
        fd = archive._fd
        off, size = image_xbe_extent(fd, os.fstat(fd).st_size)
        _require(0 < size <= MAX_XBE_BYTES, "XBE exceeds naming reader bound")
        payloads["xbe"] = io.pread(fd, size, off)
        _require(len(payloads["xbe"]) == size, "Short XBE read")
        offsets["xbe"] = off
    return payloads, offsets


def _union_status(payloads: Mapping[str, bytes], data: dict) -> str:
    states = {_inspect(payload, data) for payload in payloads.values()}
    _require(len(states) == 1, "Mixed retail and modern name resources")
    return states.pop()


def image_status(path: Path | str, *, include_xbe: bool = True,
                 manifest_path: Path | str | None = None) -> str:
    try:
        data = manifest(manifest_path)
        with _open(path) as archive:
            payloads, _ = _read_image(archive, data, include_xbe)
            return _union_status(payloads, data)
    except (OSError, ValueError, IndexError, struct.error):
        return "foreign"


def image_preview(path: Path | str, *, enabled: bool = True,
                  manifest_path: Path | str | None = None) -> list[dict]:
    data = manifest(manifest_path)
    with _open(path) as archive:
        payloads, _ = _read_image(archive, data, True)
        _union_status(payloads, data)
    rows = _preview_rows(data, enabled)
    for row in rows:
        payload = payloads[row["domain"]]
        off = _offset(payload, row)
        row["before"] = payload[off:off + row["allocation_bytes"]].decode("utf-16le").split("\0", 1)[0]
        row["source_verified"] = True
    return rows


def apply_to_image(path: Path | str, *, enabled: bool = True, original_source: Path | str | None = None,
                   include_xbe: bool = True, manifest_path: Path | str | None = None,
                   progress: Callable[[str], None] | None = None) -> dict:
    """Caller supplies a disposable Build copy. Preflight all writes, read back, roll back on error.

    include_xbe=False is the final DATA pass when _apply_all already owns XBE
    application. Full standalone transactions require both halves to agree.
    Ordinary I/O failures roll back; power-loss atomicity belongs to Build's
    copy/publish transaction. No image or archive pack is loaded wholesale.
    """
    _require(type(enabled) is bool, "enabled must be boolean")
    data = manifest(manifest_path)
    originals = {}
    if not enabled:
        _require(original_source is not None and not os.path.samefile(original_source, path),
                 "Disabling needs a separate original source image")
        with _open(original_source) as source:
            originals, _ = _read_image(source, data, include_xbe)
            _require(_union_status(originals, data) == "retail", "Original source is not retail naming")
    with _open(path, writable=True) as archive:
        before, offsets = _read_image(archive, data, include_xbe)
        _union_status(before, data)
        results = {key: _apply(value, data, enabled, originals.get(key)) for key, value in before.items()}
        changes = [key for key in before if before[key] != results[key][0]]
        if progress:
            progress("Writing modern 2K mode names" if enabled else "Restoring original mode names")
        current, current_offsets = _read_image(archive, data, include_xbe)
        _require(current == before and offsets == current_offsets, "Image changed after naming preview")
        attempted = []
        def write(key, value):
            if key == "strg":
                count = archive.write(offsets[key], value)
            else:
                count = io.pwrite(archive._fd, value, offsets[key])
            _require(count == len(value), "Short modern naming write")
        try:
            for key in changes:
                attempted.append(key)
                write(key, results[key][0])
            actual, _ = _read_image(archive, data, include_xbe)
            _require(actual == {key: value[0] for key, value in results.items()}, "Modern naming readback differs")
            os.fsync(archive._fd)
        except BaseException:
            for key in reversed(attempted):
                write(key, before[key])
            restored, _ = _read_image(archive, data, include_xbe)
            _require(restored == before, "Naming rollback failed; discard the disposable Build copy")
            raise
    receipts = [receipt for _, receipt in results.values()]
    return {"schema": SCHEMA, "status": _union_status(actual, data), "enabled": enabled,
            "experimental": True, "witnessed": False, "growth_bytes": 0,
            "changed_spans": sum(r["changed_spans"] for r in receipts),
            "already_applied": enabled and not changes, "resources": receipts}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "preview", "status", "apply"))
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--original", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.receipt:
            for source in (args.source, args.original, args.manifest or MANIFEST):
                if source is not None:
                    _require(args.receipt.resolve() != source.resolve() and
                             not (args.receipt.exists() and source.exists() and
                                  os.path.samefile(args.receipt, source)),
                             "Receipt must not overwrite the image, original source or manifest")
        if args.action == "check":
            data = manifest(args.manifest)
            result = {"all_strings_fit": True, "changed_strings": len(data["cells"]),
                      "mycareer_labels": len(data["career_labels"]), "experimental": True, "witnessed": False}
        elif args.action == "preview":
            result = (image_preview(args.source, enabled=not args.disable, manifest_path=args.manifest)
                      if args.source else preview_rows(enabled=not args.disable, manifest_path=args.manifest))
        else:
            _require(args.source is not None, "This action requires a disposable image path")
            if args.action == "status":
                result = {"status": image_status(args.source, manifest_path=args.manifest)}
            else:
                result = apply_to_image(args.source, enabled=not args.disable, original_source=args.original,
                                        manifest_path=args.manifest)
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.receipt:
            args.receipt.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 1 if isinstance(result, dict) and result.get("status") == "foreign" else 0
    except (OSError, ValueError, IndexError, struct.error) as exc:
        parser.exit(2, f"Modern naming refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
