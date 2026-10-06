#!/usr/bin/env python3
"""Apply reviewed uniform spans to loose resource files or extracted disc packs.

The manifest and replacement binaries are private, game-derived build evidence.
Only pinned before/after spans are accepted. Unrelated edits compose unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from nfl_outer import PACK_NAMES


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def refuse_links(path: Path) -> Path:
    """Check the path before resolving it, including directory components."""
    absolute = Path(path).absolute()
    require(not any(part.is_symlink() for part in (absolute, *absolute.parents)),
            f"symlink path component is refused: {path}")
    return absolute


def replacement_bytes(base: Path, relative: str) -> bytes:
    require(isinstance(relative, str), "replacement must be a relative file name")
    name = Path(relative)
    require(not name.is_absolute() and name.parts and ".." not in name.parts,
            "replacement path escapes the manifest directory")
    root = refuse_links(base).resolve(strict=True)
    path = refuse_links(root / name)
    require(path.is_file() and path.resolve(strict=True).is_relative_to(root),
            "replacement must be a regular file inside the manifest directory")
    return path.read_bytes()


HELMET_SCOPE_SCHEMA = "b765/u1/helmet-pixel-scope/v1"


def helmet_scope_masks(scope: dict) -> list[bytes]:
    """Validate the optional declaration and bound it to the six helmet mips.

    A coarse texel is owned if its base-level footprint intersects a box.
    Undeclared levels are entirely protected, including mip0 when omitted.
    """
    fields = {"schema", "family", "base_boxes", "mip_levels", "system_sha256",
              "descriptor_sha256", "protected_rgba_sha256"}
    require(isinstance(scope, dict) and len(scope) == len(fields) and set(scope) == fields and
            scope.get("schema") == HELMET_SCOPE_SCHEMA,
            "invalid helmet pixel scope schema/fields")
    require(scope["family"] in ("helmet00", "helmet02"), "invalid helmet scope family")
    hashes = [scope["system_sha256"], scope["descriptor_sha256"]]
    protected = scope["protected_rgba_sha256"]
    require(isinstance(protected, list) and len(protected) == 6,
            "helmet scope requires six protected RGBA hashes")
    hashes += protected
    require(all(isinstance(value, str) and len(value) == 64 and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in hashes), "invalid helmet scope hash")
    levels = scope["mip_levels"]
    require(isinstance(levels, list) and 0 < len(levels) <= 6 and
            all(type(level) is int and 0 <= level < 6 for level in levels) and
            levels == sorted(set(levels)), "invalid helmet scope mip levels")
    boxes = scope["base_boxes"]
    require(isinstance(boxes, list) and 0 < len(boxes) <= 8,
            "helmet scope requires one through eight base boxes")
    for box in boxes:
        require(isinstance(box, list) and len(box) == 4 and
                all(type(value) is int for value in box) and
                0 <= box[0] < box[2] <= 256 and 0 <= box[1] < box[3] <= 256,
                "invalid helmet scope base box")
    require(len({tuple(box) for box in boxes}) == len(boxes),
            "duplicate helmet scope base box")
    masks = []
    for level in range(6):
        scale, width = 1 << level, 256 >> level
        mask = bytearray(width * width)
        if level in levels:
            for x0, y0, x1, y1 in boxes:
                left, right = x0 // scale, (x1 + scale - 1) // scale
                for y in range(y0 // scale, (y1 + scale - 1) // scale):
                    mask[y * width + left:y * width + right] = bytes([1]) * (right - left)
        require(0 in mask, "helmet scope leaves no protected texels")
        masks.append(bytes(mask))
    return masks


def _decode_scoped_helmet(span: bytes, scope: dict) -> tuple[bytes, list]:
    """Bound the allocation before decoding an actual compressed helmet TXTR."""
    from nfl_txtr import (HEADER, COMPRESSED_SENTINEL, Chunk, decode_chunk,
                          minimum_vc_lz_overlap_scratch, parse_texture)
    from nfl_live_helmet_txtr_png_import import decode_levels

    require(HEADER.size <= len(span) <= 1024 * 1024,
            "helmet scope span size exceeds its bound")
    fields = HEADER.unpack_from(span)
    kind, stored, system, video, magic, scratch, reserved0, reserved1 = fields
    require(kind == b"TXTR" and len(span) == HEADER.size + stored and
            system == 128 and video == 88384 and magic == COMPRESSED_SENTINEL and
            reserved0 == reserved1 == 0,
            "helmet scope requires the pinned compressed allocation")
    chunk = Chunk(0, 0, "TXTR", stored, system, video, magic, scratch, reserved0, reserved1)
    decoded, info = decode_chunk(span, chunk)
    require(info is not None and len(decoded) == 88512,
            "helmet scope decoded allocation changed")
    texture = parse_texture(decoded, chunk)
    require(texture.name == scope["family"] and texture.name_offset == 32 and
            texture.descriptor_offset == 52 and texture.pixel_offset == 0 and
            texture.palette_offset == 87360 and texture.packed_format == 0x08860B29 and
            texture.packed_size == 0 and texture.descriptor_flags == 0x80000000 and
            texture.format_name == "P8" and texture.mip_levels == 6 and
            texture.width == texture.height == 256 and texture.depth == 1,
            "helmet scope descriptor/layout changed")
    require(sha(decoded[:128]) == scope["system_sha256"] and
            sha(decoded[52:76]) == scope["descriptor_sha256"],
            "helmet scope system/descriptor hash changed")
    minimum = minimum_vc_lz_overlap_scratch(
        span[HEADER.size:HEADER.size + info.consumed_bytes], stored, len(decoded))
    require(scratch >= minimum, "helmet scope loader scratch is insufficient")
    return decoded, decode_levels(decoded)


def verify_helmet_pixel_scope(before: bytes, replacement: bytes, scope: dict) -> dict:
    """Prove actual decoded RGBA protection, even when a patch is already applied.

    Palette/index permutations are accepted; the protected *pixels* must remain
    exact. Both input and replacement are checked against the declared baseline.
    """
    masks = helmet_scope_masks(scope)
    require(len(before) == len(replacement), "helmet scope stored span size changed")
    old_decoded, old_levels = _decode_scoped_helmet(before, scope)
    new_decoded, new_levels = _decode_scoped_helmet(replacement, scope)
    rows = []
    for old, new, mask, expected in zip(old_levels, new_levels, masks,
                                       scope["protected_rgba_sha256"]):
        require((old.level, old.width, old.height) == (new.level, new.width, new.height),
                "helmet scope mip dimensions changed")
        protected_before, protected_after = bytearray(), bytearray()
        changed, outside_changed = 0, 0
        for index, allowed in enumerate(mask):
            a, b = old.rgba[index * 4:index * 4 + 4], new.rgba[index * 4:index * 4 + 4]
            changed += a != b
            if not allowed:
                protected_before.extend(a)
                protected_after.extend(b)
                outside_changed += a != b
        before_hash, after_hash = sha(protected_before), sha(protected_after)
        require(before_hash == expected, f"helmet scope input protected mip{old.level} changed")
        require(after_hash == expected and outside_changed == 0,
                f"helmet scope replacement protected mip{old.level} changed")
        rows.append({"level": old.level, "dimensions": [old.width, old.height],
                     "allowed_texels": sum(mask), "protected_texels": len(mask) - sum(mask),
                     "protected_before_sha256": before_hash, "protected_after_sha256": after_hash,
                     "protected_changed_texels": outside_changed, "changed_texels": changed})
    return {"schema": HELMET_SCOPE_SCHEMA, "family": scope["family"],
            "base_boxes": scope["base_boxes"], "mip_levels": scope["mip_levels"],
            "system_sha256": sha(new_decoded[:128]), "descriptor_sha256": sha(new_decoded[52:76]),
            "system_identical": old_decoded[:128] == new_decoded[:128],
            "descriptor_identical": old_decoded[52:76] == new_decoded[52:76],
            "allocation_identical": len(old_decoded) == len(new_decoded),
            "palette_identical": old_decoded[-1024:] == new_decoded[-1024:],
            "levels": rows, "changed_texels": sum(row["changed_texels"] for row in rows),
            "protected_changed_texels": sum(row["protected_changed_texels"] for row in rows)}


def apply_spans(original: bytes, patches: list[dict], base: Path) -> tuple[bytes, dict]:
    result = bytearray(original)
    occupied: list[tuple[int, int]] = []
    receipts = []
    for patch in sorted(patches, key=lambda p: p["offset"]):
        offset, length = patch["offset"], patch["length"]
        require(type(offset) is int and type(length) is int and length > 0 and
                0 <= offset <= len(original) - length, "patch span exceeds file")
        require(not occupied or occupied[-1][1] <= offset, "overlapping patch spans")
        replacement = replacement_bytes(base, patch["replacement"])
        require(len(replacement) == length and sha(replacement) == patch["after_sha256"],
                "replacement size/hash changed")
        before = original[offset:offset + length]
        current_sha = sha(before)
        require(current_sha in {patch["before_sha256"], patch["after_sha256"]},
                f"unexpected input span at {offset:#x}")
        pixel_receipt = None
        if "helmet_pixel_scope" in patch:
            pixel_receipt = verify_helmet_pixel_scope(before, replacement, patch["helmet_pixel_scope"])
        result[offset:offset + length] = replacement
        occupied.append((offset, offset + length))
        receipts.append({"offset": offset, "length": length,
                         "before_sha256": current_sha, "after_sha256": sha(replacement),
                         "already_applied": before == replacement})
        if pixel_receipt is not None:
            receipts[-1]["helmet_pixel_scope"] = pixel_receipt
    cursor = 0
    untouched = hashlib.sha256()
    for start, end in occupied + [(len(original), len(original))]:
        require(original[cursor:start] == result[cursor:start], "outside-scope bytes changed")
        untouched.update(original[cursor:start])
        cursor = end
    return bytes(result), {"before_sha256": sha(original), "after_sha256": sha(result),
                           "size": len(original), "outside_scope_sha256": untouched.hexdigest(),
                           "outside_scope_identical": True, "spans": receipts}


def atomic_write(path: Path, data: bytes) -> None:
    publish_batch([(path, data)])


def publish_batch(items: list[tuple[Path, bytes]]) -> None:
    """Stage/read back the complete batch before exposing any new output.

    Existing identical outputs are accepted for idempotence. Differing outputs
    are refused, so an integration directory cannot clobber another job's work.
    New outputs use an exclusive hard-link commit; a commit failure rolls back
    only files created by this invocation.
    """
    pending = []
    require(len({str(path.absolute()) for path, _ in items}) == len(items), "duplicate output path")
    for path, data in items:
        refuse_links(path)
        if path.exists():
            require(path.is_file() and path.read_bytes() == data,
                    f"existing output differs; use a fresh output directory: {path}")
        else:
            temp = path.with_name(path.name + ".u1-tmp")
            require(not temp.exists() and not temp.is_symlink(), f"staging file already exists: {temp}")
            pending.append((path, temp, data))
    staged, committed = [], []
    try:
        for path, temp, data in pending:
            path.parent.mkdir(parents=True, exist_ok=True)
            refuse_links(path)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temp, flags, 0o600)
            staged.append(temp)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            require(temp.read_bytes() == data, f"staged output readback differs: {temp}")
        for path, temp, data in pending:
            refuse_links(path)
            # Exclusive creation refuses a path introduced after validation.
            os.link(temp, path)
            committed.append((path, temp.stat().st_ino, temp.stat().st_dev))
            require(path.read_bytes() == data, f"output readback differs: {path}")
    except BaseException:
        for path, inode, device in reversed(committed):
            try:
                current = path.lstat()
            except FileNotFoundError:
                continue
            require((current.st_ino, current.st_dev) == (inode, device),
                    "output changed during rollback; refusing to remove another writer's file")
            path.unlink()
        raise
    finally:
        for temp in staged:
            temp.unlink(missing_ok=True)


def repair_resources(source: Path, output: Path, manifest: dict, base: Path) -> dict:
    refuse_links(source)
    refuse_links(output)
    require(source.resolve() != output.resolve(), "source/output must differ")
    require(not output.resolve().is_relative_to(source.resolve()),
            "output must not be inside the input directory")
    receipts = {}
    # Validate every resource before publishing any output.
    compiled = []
    for name, patches in manifest["resources"].items():
        require(re.fullmatch(r"[0-9]{2}[HA][0-9]{1,2}\.IFF", name) is not None,
                "invalid uniform resource name")
        path = source / name
        refuse_links(path)
        require(path.is_file() and not path.is_symlink(), "input must be a regular resource")
        data, receipt = apply_spans(path.read_bytes(), patches, base)
        compiled.append((name, data, receipt))
    publish_batch([(output / name, data) for name, data, _receipt in compiled])
    for name, data, receipt in compiled:
        receipts[name] = dict(receipt, readback=True)
    return {"schema": "b765/u1/repair-receipt/v1", "resources": receipts}


def repair_packs(source: Path, output: Path, manifest: dict, base: Path) -> dict:
    """The source can be the v0.4 image or an already stacked extracted set.

    Materialize only the index and affected packs. Full pack before/after hashes
    and comparisons prove that all resources outside the manifest stay exact.
    """
    refuse_links(source)
    refuse_links(output)
    require(source.resolve() != output.resolve(), "source/output must differ")
    require(not (source.is_dir() and output.resolve().is_relative_to(source.resolve())),
            "output must not be inside the input directory")
    pack_patches: dict[int, list[dict]] = {}
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for name, patches in manifest["resources"].items():
            require(re.fullmatch(r"[0-9]{2}[HA][0-9]{1,2}\.IFF", name) is not None,
                    "invalid uniform resource name")
            require(name in by_name, f"resource absent: {name}")
            entry = by_name[name]
            for patch in patches:
                require(type(patch["offset"]) is int and type(patch["length"]) is int and
                        patch["length"] > 0, "invalid resource span coordinates")
                parts = index.sub_extents(entry, patch["offset"], patch["length"])
                # The uniform texture resources in this repair do not cross a pack.
                require(len(parts) == 1, "cross-pack patch needs explicitly segmented handling")
                ordinal, offset, length = parts[0]
                require(length == patch["length"], "patch segment size changed")
                pack_patches.setdefault(ordinal, []).append(dict(patch, offset=offset, resource=name,
                                                                resource_offset=patch["offset"]))
        compiled = []
        for ordinal, patches in sorted(pack_patches.items()):
            # Only each affected archive volume is copied; no full disc copy.
            # Preserve the physical archive in full, including any trailing
            # padding after the virtual allocation declared by the index.
            size = image.pack_size(ordinal)
            require(size >= index.slots[ordinal] * bump.SECTOR_SIZE,
                    "physical archive is shorter than its declared allocation")
            original = image.read_pack(ordinal, 0, size)
            data, receipt = apply_spans(original, patches, base)
            compiled.append((PACK_NAMES[ordinal], data, receipt))
        if 0 not in pack_patches:
            index_bytes = image.read_index_range(0, image.index_size)
        outputs = [(output / name, data) for name, data, _receipt in compiled]
        if 0 not in pack_patches:
            outputs.insert(0, (output / "0", index_bytes))
        publish_batch(outputs)
        receipts = {}
        for name, data, receipt in compiled:
            receipts[f"vc_53450030/{name}"] = dict(receipt, readback=True)
    return {"schema": "b765/u1/repair-receipt/v1", "disc_files": receipts,
            "index_copied_unchanged": 0 not in pack_patches}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--resource-files", action="store_true")
    args = p.parse_args()
    receipt_path = refuse_links(args.receipt).resolve()
    source_path = refuse_links(args.input).resolve()
    require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
            "receipt must not overwrite any input file")
    require(receipt_path != args.manifest.resolve(), "receipt must not overwrite the repair manifest")
    manifest = json.loads(args.manifest.read_text())
    require(manifest.get("schema") == "b765/u1/texture-repair/v1", "unsupported manifest")
    output_names = manifest["resources"] if args.resource_files else PACK_NAMES
    require(receipt_path not in {(args.output / name).resolve() for name in output_names},
            "receipt must not overwrite a repaired game file")
    fn = repair_resources if args.resource_files else repair_packs
    receipt = fn(args.input, args.output, manifest, args.manifest.parent)
    receipt["manifest_sha256"] = sha(args.manifest.read_bytes())
    atomic_write(args.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(args.receipt), "scope_verified": True}))


if __name__ == "__main__":
    main()
