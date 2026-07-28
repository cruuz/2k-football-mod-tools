#!/usr/bin/env python3
"""Replace any inventoried NFL 2K5 P8 texture in a layout-identical XISO copy.

The editor already located every TXTR on the disc, but only a curated handful
were replaceable: uniforms, live faces, portraits, the Crib, create-team field
art.  Everything else a modder can see in the inventory -- the goalpost pads,
the real teams' end-zone art, grass and the transparent overlays laid over it,
field lines, helmet reflections, shared equipment like ``shoes_taped`` and
``wristband_qb``, even the tailgate props -- had no way to be edited.  This is
the general lane: name a package and a texture inside it, hand it a PNG, get a
patched copy of your own disc.

Three properties make that safe enough to ship:

* **Fixed span.**  Every replacement is recompressed into the exact byte span
  the original occupied, so archive traversal, every descriptor, and the
  position of every other resource are untouched.  A PNG that cannot be made
  to fit is refused rather than shifting the disc around.
* **Per-extent identity, never the container.**  Image size, the sector a file
  landed on, and therefore its absolute byte offset all describe how a disc was
  dumped, not which game it is -- extract-xiso relocates every file.  Identity
  is the exact size and SHA-256 of ``default.xbe`` and of each pack this plan
  actually touches.
* **Copy only.**  The source is opened read-only, hashed before and after, and
  the output is a fresh file that never aliases it.

Resources reachable from more than one pack segment are refused: such a chunk
would need two writes at two unrelated offsets, and nothing we target does it.
"""

from __future__ import annotations

import argparse
import dataclasses
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import nfl_uniform_color_xiso_direct_patch as common
import nfl_tset_png_import as palette_tools
from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import (HEADER, Chunk, decode_chunk, parse_chunks, parse_texture,
                      rebuild_compressed_chunk_fixed_span, swizzle_2d)


SCHEMA = "nfl2k5_all_texture_xiso_workflow/v1"
PLAN_SCHEMA = "nfl2k5_all_texture_plan/v1"
PACK_ROOT = "vc_53450030"
PALETTE_BYTES = 1024
MAX_PLAN_BYTES = 16 * 1024 * 1024
MAX_EDITS = 512
SUPPORTED_FORMATS = ("P8",)


class TextureWorkflowError(ValueError):
    """Raised when an input, target, or output fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TextureWorkflowError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class ResolvedTarget:
    pack_name: str
    outer_index: int
    chunk_index: int
    texture: str
    width: int
    height: int
    mip_levels: int
    pixel_offset: int
    palette_offset: int
    system_bytes: int
    video_bytes: int
    pack_relative_offset: int
    span_size: int
    span_sha256: str
    decoded: bytes
    template_span: bytes
    chunk: Chunk


def read_plan(path: Path) -> tuple[Path, bytes, list[dict[str, Any]]]:
    plan = path.resolve(strict=True)
    info = plan.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "plan must be a regular, non-symlink file")
    require(info.st_size <= MAX_PLAN_BYTES, "plan file is too large")
    payload = plan.read_bytes()
    document = json.loads(payload.decode("utf-8"))
    require(isinstance(document, dict) and document.get("schema") == PLAN_SCHEMA,
            f"plan schema must be {PLAN_SCHEMA}")
    edits = document.get("edits")
    require(isinstance(edits, list) and 1 <= len(edits) <= MAX_EDITS,
            f"plan must carry 1..{MAX_EDITS} edits")
    fields = {"outer_index", "texture", "png"}
    for edit in edits:
        require(isinstance(edit, dict) and set(edit) == fields,
                f"each edit must carry exactly {sorted(fields)}")
        require(type(edit["outer_index"]) is int and edit["outer_index"] >= 0,
                "edit outer_index must be a non-negative integer")
        require(isinstance(edit["texture"], str) and edit["texture"],
                "edit texture must be a name")
        require(isinstance(edit["png"], str) and edit["png"], "edit png must be a path")
    return plan, payload, edits


def resolve_target(archive: Any, outer_index: int, texture: str) -> ResolvedTarget:
    """Find one named P8 TXTR inside one outer package, fail-closed."""
    require(0 <= outer_index < len(archive.entries),
            f"outer index {outer_index} is outside this archive")
    entry = archive.entries[outer_index]
    require(len(entry.segments) == 1,
            f"outer {outer_index} spans {len(entry.segments)} pack segments; "
            "a straddling resource is not editable through this lane")
    segment = entry.segments[0]
    data = read_entry_bytes(archive, entry)
    matches: list[tuple[int, Chunk, bytes, Any]] = []
    for position, chunk in enumerate(parse_chunks(data, allow_trailing=True)):
        if chunk.kind != "TXTR":
            continue
        try:
            decoded, _info = decode_chunk(data, chunk)
            info = parse_texture(decoded, chunk)
        except Exception:  # noqa: BLE001 - a chunk we cannot read is simply skipped
            continue
        if info.name == texture:
            matches.append((position, chunk, decoded, info))
    require(matches, f"outer {outer_index} has no TXTR named {texture!r}")
    require(len(matches) == 1,
            f"outer {outer_index} has {len(matches)} textures named {texture!r}")
    position, chunk, decoded, info = matches[0]
    require(info.format_name in SUPPORTED_FORMATS,
            f"{texture} is {info.format_name}; this lane replaces "
            f"{'/'.join(SUPPORTED_FORMATS)} textures only")
    require(info.packed_size == 0,
            f"{texture} stores linear pixels; only swizzled P8 is supported")
    require(info.pixel_offset == 0,
            f"{texture} does not begin its index chain at the video buffer start")
    span_size = HEADER.size + chunk.stored_size
    require(chunk.offset + span_size <= len(data),
            f"{texture} span runs past the end of outer {outer_index}")
    expected_chain = sum(
        max(1, info.width >> level) * max(1, info.height >> level)
        for level in range(info.mip_levels)
    )
    require(info.palette_offset == expected_chain,
            f"{texture} palette does not follow its {info.mip_levels}-level chain")
    require(info.palette_offset + PALETTE_BYTES <= chunk.video_bytes,
            f"{texture} palette runs past its video buffer")
    template_span = data[chunk.offset:chunk.offset + span_size]
    return ResolvedTarget(
        pack_name=segment.pack_name,
        outer_index=outer_index,
        chunk_index=position,
        texture=texture,
        width=info.width,
        height=info.height,
        mip_levels=info.mip_levels,
        pixel_offset=info.pixel_offset,
        palette_offset=info.palette_offset,
        system_bytes=chunk.system_bytes,
        video_bytes=chunk.video_bytes,
        pack_relative_offset=segment.pack_offset + chunk.offset,
        span_size=span_size,
        span_sha256=digest(template_span),
        decoded=decoded,
        template_span=template_span,
        chunk=chunk,
    )


def generate_mips(rgba: bytes, width: int, height: int,
                  levels: int) -> list[Any]:
    """Box-filter mip chain for an arbitrary texture size.

    ``palette_tools.generate_mips`` computes exactly this, then asserts the
    result equals the jersey TSET's pinned 512x256 chain -- correct for that
    target, useless for the other 57,000 textures. The arithmetic below is the
    same box filter with the pin replaced by the level count the retail
    descriptor actually declares.
    """
    require(len(rgba) == width * height * 4, "base RGBA size mismatch")
    result = [palette_tools.MipLevel(0, width, height, rgba)]
    current, current_width, current_height = rgba, width, height
    for level in range(1, levels):
        require(current_width % 2 == 0 and current_height % 2 == 0,
                f"{width}x{height} cannot be halved {levels - 1} times exactly")
        next_width, next_height = current_width // 2, current_height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * current_width + x * 2) * 4,
                    ((y * 2) * current_width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * current_width + x * 2) * 4,
                    (((y * 2) + 1) * current_width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    total = sum(current[source + channel] for source in sources)
                    downsampled[target + channel] = (total + 2) // 4
        current = bytes(downsampled)
        current_width, current_height = next_width, next_height
        result.append(palette_tools.MipLevel(level, current_width, current_height, current))
    return result


def build_replacement(target: ResolvedTarget,
                      png_path: Path) -> tuple[bytes, dict[str, Any]]:
    """Quantize a PNG into this target's own palette layout and refit its span."""
    # palette_tools.read_rgba_png is pinned to the jersey TSET's 512x256, so
    # read through the underlying decoder with THIS texture's dimensions.
    resolved_png = png_path.resolve(strict=True)
    png_info = resolved_png.lstat()
    require(stat.S_ISREG(png_info.st_mode) and not stat.S_ISLNK(png_info.st_mode),
            f"PNG must be a regular, non-symlink file: {png_path}")
    require(png_info.st_size <= palette_tools.MAX_PNG_BYTES,
            "PNG exceeds the 32 MiB file bound")
    png_payload = resolved_png.read_bytes()
    png_sha256 = digest(png_payload)
    width, height, rgba = palette_tools.decode_rgba_png(
        png_payload, (target.width, target.height))
    levels = generate_mips(rgba, width, height, target.mip_levels)
    require(len(levels) == target.mip_levels, "mip generation level-count mismatch")
    palette, index_levels, quantization = palette_tools.quantize_levels(levels)
    chain = b"".join(
        swizzle_2d(indices, level.width, level.height, 1)
        for level, indices in zip(levels, index_levels)
    )
    require(len(chain) == target.palette_offset,
            "encoded index chain does not fill the retail chain span")
    rebuilt = bytearray(target.decoded)
    video = target.system_bytes
    rebuilt[video:video + len(chain)] = chain
    encoded_palette = palette_tools.palette_bytes(palette)
    require(len(encoded_palette) == PALETTE_BYTES, "encoded palette size mismatch")
    rebuilt[video + target.palette_offset:
            video + target.palette_offset + PALETTE_BYTES] = encoded_palette
    rebuilt_decoded = bytes(rebuilt)
    require(len(rebuilt_decoded) == len(target.decoded),
            "rebuilt texture payload changed size")
    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        target.template_span, rebuilt_decoded)
    require(len(rebuilt_span) == len(target.template_span),
            "rebuilt span size differs from the retail span")
    # target.chunk.offset points into the whole package; the rebuilt span is
    # standalone, so decode it through a copy anchored at its own byte 0.
    standalone = dataclasses.replace(target.chunk, offset=0)
    roundtrip, _info = decode_chunk(rebuilt_span, standalone)
    require(roundtrip == rebuilt_decoded,
            "rebuilt span does not decode back to the payload it was built from")
    return rebuilt_span, {
        "png_sha256": png_sha256,
        "png_width": width,
        "png_height": height,
        "palette_entries": quantization.get("palette_entries"),
        "mip_levels": target.mip_levels,
        "rebuilt_span_sha256": digest(rebuilt_span),
        "rebuilt_decoded_sha256": digest(rebuilt_decoded),
        "recompressed_bytes": rebuild_info.recompressed_bytes,
        "zero_padding_bytes": rebuild_info.zero_padding_bytes,
    }


def run(source_path: Path, output_path: Path, manifest_path: Path,
        plan_path: Path, index_path: Path) -> dict[str, Any]:
    supplied = source_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    require(not output.exists() and not manifest.exists(),
            "output XISO or manifest already exists")
    plan, plan_payload, edits = read_plan(plan_path)
    index = index_path.resolve(strict=True)

    archive = parse_archive(index)
    resolved: list[tuple[ResolvedTarget, bytes, dict[str, Any]]] = []
    seen: set[tuple[int, str]] = set()
    for edit in edits:
        key = (int(edit["outer_index"]), str(edit["texture"]))
        require(key not in seen, f"plan repeats target {key[0]}:{key[1]}")
        seen.add(key)
        target = resolve_target(archive, key[0], key[1])
        replacement, report = build_replacement(target, Path(str(edit["png"])))
        require(replacement != target.template_span,
                f"replacement equals retail for {key[0]}:{key[1]}")
        resolved.append((target, replacement, report))

    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    success = False
    try:
        info = os.fstat(source_fd)
        source_size = info.st_size
        source_identity = common.fd_identity(source_fd)
        require(common.path_identity(source) == source_identity,
                "source pathname changed while opening")
        source_sha_before = common.sha256_fd(source_fd)
        entries, directory = common.parse_xdvdfs(source_fd, source_size)
        xbe = entries.get("default.xbe")
        require(xbe is not None and xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(source_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail default.xbe identity differs")

        packs: dict[str, Any] = {}
        writes: list[dict[str, Any]] = []
        spans: list[tuple[int, int]] = []
        for target, replacement, report in resolved:
            pack_path = f"{PACK_ROOT}/{target.pack_name}"
            pack = entries.get(pack_path.casefold())
            require(pack is not None, f"source XISO has no {pack_path}")
            if target.pack_name not in packs:
                packs[target.pack_name] = {
                    "path": pack_path,
                    "size": pack.size,
                    "sha256": common.sha256_fd(source_fd, pack.byte_offset, pack.size),
                }
            absolute = pack.byte_offset + target.pack_relative_offset
            require(absolute + target.span_size <= pack.byte_offset + pack.size,
                    f"{target.texture} span does not lie inside {pack_path}")
            actual = common.read_exact(source_fd, absolute, target.span_size)
            require(digest(actual) == target.span_sha256,
                    f"source span for {target.outer_index}:{target.texture} differs "
                    "from the extracted index it was resolved against")
            end = absolute + target.span_size
            require(all(end <= first or absolute >= last for first, last in spans),
                    "plan target spans overlap")
            spans.append((absolute, end))
            writes.append({
                "absolute": absolute, "replacement": replacement,
                "target": target, "report": report, "pack_path": pack_path,
            })

        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output XISO aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_size)
        allowed: set[int] = set()
        for write in writes:
            common.pwrite(output_owned.descriptor, write["replacement"], write["absolute"])
            before = common.read_exact(source_fd, write["absolute"],
                                       write["target"].span_size)
            allowed.update(
                write["absolute"] + position
                for position, (old, new) in enumerate(zip(before, write["replacement"]))
                if old != new
            )
        os.fsync(output_owned.descriptor)
        for write in writes:
            readback = common.read_exact(output_owned.descriptor, write["absolute"],
                                         write["target"].span_size)
            require(readback == write["replacement"],
                    f"output span readback differs for {write['target'].texture}")
        source_sha_after, output_sha, changed = common.compare_and_hash(
            source_fd, output_owned.descriptor, source_size, allowed)
        require(source_sha_after == source_sha_before,
                "source XISO changed during the workflow")
        require(changed == sorted(allowed),
                "output differs from source outside the planned spans")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_size)
        require(output_entries == entries and output_directory == directory,
                "output XISO filesystem tree/layout differs from source")

        record = {
            "schema": SCHEMA,
            "plan": {"path": plan.name, "sha256": digest(plan_payload)},
            "source": {"size": source_size, "sha256_before_and_after": source_sha_before},
            "output": {"size": source_size, "sha256": output_sha,
                       "copy_method": copy_method},
            "packs": packs,
            "identity": {
                "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
                "note": "Identity is per-extent. The container size and hash are "
                        "recorded, never gated: a legally repacked dump differs.",
            },
            "edits": [
                {
                    "outer_index": write["target"].outer_index,
                    "chunk_index": write["target"].chunk_index,
                    "texture": write["target"].texture,
                    "pack_path": write["pack_path"],
                    "width": write["target"].width,
                    "height": write["target"].height,
                    "format": "P8",
                    "absolute_offset": write["absolute"],
                    "span_size": write["target"].span_size,
                    "source_span_sha256": write["target"].span_sha256,
                    **write["report"],
                }
                for write in writes
            ],
            "changed_byte_count": len(changed),
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, record)
        success = True
        return record
    finally:
        os.close(source_fd)
        if output_owned is not None:
            if not success:
                common.unlink_if_owned(output_owned)
            else:
                os.close(output_owned.descriptor)
        if manifest_owned is not None:
            if not success:
                common.unlink_if_owned(manifest_owned)
            else:
                os.close(manifest_owned.descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path,
                        help="extracted vc_53450030/0, used to resolve targets")
    args = parser.parse_args()
    try:
        result = run(args.source_xiso, args.output_xiso, args.manifest,
                     args.plan, args.index)
    except (TextureWorkflowError, common.PatchError) as exc:
        print(f"nfl_all_texture_xiso_workflow: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
