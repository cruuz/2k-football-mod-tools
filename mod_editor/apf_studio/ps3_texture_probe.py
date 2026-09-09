"""Stream the nested 1993 PS3 package and compare TXTR pixels with Xbox 360.

The outer ZIP's nested game ZIP must be STORED. Compressed volume members
are consumed in physical order with forward seeks only; nothing is extracted.
The largest resident units are one IFF entry and its decoded texture blocks.
Cross-platform differences are candidates, not proof of a modder's changes:
the base PS3 game is unavailable and codecs/platform artwork can differ.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import struct
from typing import BinaryIO
import zipfile

from .backend import ensure_tools_importable
from .ps3_texture_codec import decode_gcm, parse_gcm_descriptor

ensure_tools_importable()
import apf_inner
import apf_outer
import apf_logo_patch

SCHEMA = "apf2k8_ps3_texture_comparison/v1"
MAX_ENTRY_BYTES = 256 * 1024 * 1024


class ProbeError(ValueError):
    pass


def _exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise ProbeError(f"Truncated stream: expected {size}, got {len(data)}")
    return data


class NestedPs3Archive:
    """Bounded, forward-only ArchiveReader adapter for the ZIP-owned volumes."""
    def __init__(self, path: Path):
        self.path = path
        self._stack = ExitStack()
        self.streams = {}

    def __enter__(self):
        try:
            outer = self._stack.enter_context(zipfile.ZipFile(self.path))
            matches = [i for i in outer.infolist() if i.filename.endswith("/Modify APF game File.zip") or i.filename == "Modify APF game File.zip"]
            if len(matches) != 1 or matches[0].compress_type != zipfile.ZIP_STORED:
                raise ProbeError("Expected one STORED Modify APF game File.zip")
            member = self._stack.enter_context(outer.open(matches[0]))
            inner = self._stack.enter_context(zipfile.ZipFile(member))
            names = [i for i in inner.infolist() if i.filename.endswith("/USRDIR/0A")]
            if len(names) != 1:
                raise ProbeError("Expected exactly one USRDIR/0A index")
            prefix = names[0].filename[:-2]
            index = self._stack.enter_context(inner.open(names[0]))
            magic, alignment, pack_count, reserved, entry_count, reserved2 = struct.unpack(">6I", _exact(index, 24))
            if magic != apf_outer.MAGIC or not 1 <= pack_count <= 16 or not 1 <= entry_count <= 10000:
                raise ProbeError("Invalid PS3 outer directory")
            if not 0 < alignment <= apf_outer.MAX_ALIGNMENT or alignment & (alignment - 1):
                raise ProbeError("Invalid PS3 archive alignment")
            packs, cursor, seen = [], 0, set()
            for ordinal in range(pack_count):
                size_blocks, zero, raw_name = struct.unpack(">II8s", _exact(index, 16))
                name = apf_outer._decode_pack_name(raw_name, ordinal)
                if zero or name in seen or not size_blocks:
                    raise ProbeError("Invalid/duplicate PS3 volume descriptor")
                seen.add(name)
                infos = [i for i in inner.infolist() if i.filename == prefix + name]
                if len(infos) != 1 or infos[0].file_size != size_blocks * alignment:
                    raise ProbeError(f"Missing/duplicate/wrong-size PS3 volume {name}")
                size = infos[0].file_size
                packs.append(apf_outer.Pack(ordinal, name, size_blocks, size, size, cursor, Path(name)))
                self.streams[ordinal] = index if ordinal == 0 else self._stack.enter_context(inner.open(infos[0]))
                cursor += size
            if packs[0].name != "0A":
                raise ProbeError("Index is not first volume")
            entries = []
            starts = [p.virtual_start for p in packs]
            for ordinal in range(entry_count):
                name_hash, offset, size = struct.unpack(">III", _exact(index, 12))
                if not size:
                    raise ProbeError("Empty PS3 archive entry")
                segments = apf_outer._segments_for_range(tuple(packs), starts, offset * alignment, size * alignment)
                entries.append(apf_outer.Entry(ordinal, name_hash, offset, size, offset * alignment, size * alignment, "", segments))
            ordered = sorted(entries, key=lambda e: e.virtual_offset)
            if ordered[0].virtual_offset < index.tell() or any(a.virtual_end > b.virtual_offset for a, b in zip(ordered, ordered[1:])):
                raise ProbeError("Overlapping PS3 entries/directory")
            self.entries, self.packs = tuple(ordered), tuple(packs)
            self.nested_member = matches[0].filename
            return self
        except BaseException:
            self._stack.close()
            raise

    def __exit__(self, *args):
        self._stack.close()

    def read_entry(self, entry) -> bytes:
        return self.read_entry_range(entry, 0, entry.size)

    def read_entry_range(self, entry, offset: int, size: int) -> bytes:
        """Read a bounded forward range, including across a volume boundary."""
        if offset < 0 or size < 0 or offset + size > entry.size:
            raise ProbeError("Read outside PS3 entry")
        if size > MAX_ENTRY_BYTES:
            raise ProbeError(f"Entry exceeds {MAX_ENTRY_BYTES}-byte bound")
        pieces, cursor = [], 0
        for segment in entry.segments:
            start, end = max(offset, cursor), min(offset + size, cursor + segment.size)
            if end <= start:
                cursor += segment.size
                continue
            stream = self.streams[segment.pack_ordinal]
            position = segment.pack_offset + start - cursor
            if stream.tell() > position:
                raise ProbeError("Backward volume seek refused; visit entries in physical order")
            stream.seek(position)
            pieces.append(_exact(stream, end - start))
            cursor += segment.size
        return b"".join(pieces)


def texture_kind(name: str) -> str:
    name = name.casefold()
    for kind, tokens in (
        ("endzones", ("endzone",)), ("logos", ("logo",)), ("helmets", ("helmet",)),
        ("numbers", ("number", "namefont")), ("uniforms", ("jersey", "pants", "shoulder", "sock", "shoe", "glove", "weave", "dirtmap")),
        ("field", ("field", "grass", "turf", "divot")), ("banners", ("banner", "flag", "sign", "ad_")),
        ("presentation", ("score", "font", "title", "legal", "menu")),
    ):
        if any(t in name for t in tokens):
            return kind
    return "other"


def _parts(reader, record, file, blocks: dict) -> list[bytes]:
    result = []
    for part in file.parts:
        if part.block_index not in blocks:
            blocks[part.block_index] = apf_inner.decode_block(reader, record, part.block_index, MAX_ENTRY_BYTES)
        result.append(blocks[part.block_index][part.offset:part.offset + part.length])
    return result


def _ps3_image(parts):
    if not parts or len(parts[0]) < 0x70:
        raise ProbeError("PS3 TXTR descriptor missing")
    # The VC PS3 TXTR embeds CellGcmTexture at 0x58. The remaining VC
    # descriptor is 0xB0 bytes; split-part exports keep VRAM separately.
    descriptor = parse_gcm_descriptor(parts[0][0x58:0x70])
    if len(parts) == 1:
        # Inline textures use a one-based self-relative pixel pointer at
        # 0xA4. Observed 0x5D resolves to 0x100, after the padded descriptor;
        # do not confuse the GPU descriptor's offset with this file pointer.
        if len(parts[0]) < 0xB0:
            raise ProbeError("Truncated inline PS3 TXTR header")
        offset = 0xA4 + struct.unpack_from(">i", parts[0], 0xA4)[0] - 1
        if not 0xB0 <= offset < len(parts[0]) or any(parts[0][0xB0:offset]):
            raise ProbeError("Invalid inline PS3 TXTR pixel pointer/padding")
        pixels = parts[0][offset:]
    else:
        pixels = parts[-1]
    return decode_gcm(pixels, descriptor), descriptor


def _xbox_image(parts):
    meta = apf_inner.parse_txtr_metadata(parts[0])
    pixels = parts[-1]
    base, mip = int(meta["vc_base_data_length"]), int(meta["vc_mip_data_length"])
    if len(parts) == 1:
        head = len(pixels) - base - mip
        if head < 0xAC:
            raise ProbeError("Invalid single-part Xbox texture allocation")
        pixels = pixels[head:head + base]
    if meta["dimension"] != 1 or meta["stacked"]:
        raise ProbeError("Full cubemap/volume pixel comparison is not supported")
    if meta["format"] == 49:
        import apf_xenos_dxn_mip_layout
        import apf_helmet_color_transport
        locations = apf_xenos_dxn_mip_layout.derive_layout(meta)
        linear = apf_xenos_dxn_mip_layout.extract_linear_dxn(pixels, locations[0])
        rgba = apf_helmet_color_transport.decode_linear_dxn(linear, locations[0])
        width, height = locations[0].width, locations[0].height
    elif meta["format"] == 59:
        import apf_xenos_dxt5a
        width, height = int(meta["width"]), int(meta["height"])
        if not meta["tiled"]:
            raise ProbeError("Linear DXT5A comparison is unverified")
        linear = apf_xenos_dxt5a.extract_linear_general(pixels, width, height, int(meta["pitch_pixels"]), endian_mode=int(meta["endianness"]))
        alpha = apf_xenos_dxt5a.decode_linear_alpha_general(linear, width, height)
        rgba = apf_xenos_dxt5a.alpha_to_rgba_general(alpha, width, height)
    else:
        from .ps3_texture_probe_fast import decode_xbox_base
        width, height, rgba = decode_xbox_base(meta, pixels)
    return (width, height), rgba, meta


def compare_package(package: Path, xbox_index: Path, *, progress=None, journal: Path | None = None) -> dict:
    """Exhaustively index TXTRs; undecodable resources remain explicit rows."""
    from .ps3_texture_bundle import destination_slots
    from .uniform_targets import load_targets
    slots = destination_slots(xbox_index)
    owned = {(s.outer_index, i): "Team Logo" if s.kind == "logo" else "Field Art"
             for s in slots if s.writable for i in s.inner_indices}
    for family, targets in load_targets().items():
        for target in targets:
            owned[(target["outer_table_index"], target["inner_file"]["index"])] = f"Uniforms: {family}"
    archive = apf_outer.parse_archive(xbox_index)
    by_hash = defaultdict(list)
    for entry in archive.entries:
        by_hash[entry.name_id].append(entry)
    rows, entry_errors = [], []
    compressed, uncompressed, non_iff = 0, 0, 0
    with ExitStack() as stack:
        ps3 = stack.enter_context(NestedPs3Archive(package))
        xbox = stack.enter_context(apf_inner.ArchiveReader(archive))
        log = stack.enter_context(journal.open("x", encoding="utf-8")) if journal else None
        for number, entry in enumerate(ps3.entries):
            try:
                prefix = ps3.read_entry_range(entry, 0, 4)
                if prefix != bytes.fromhex("ff3bef94"):
                    non_iff += 1
                    continue
                if entry.size > MAX_ENTRY_BYTES:
                    raise ProbeError(f"IFF entry exceeds {MAX_ENTRY_BYTES}-byte bound")
                raw = prefix + ps3.read_entry_range(entry, 4, entry.size - 4)
                reader = apf_logo_patch.BytesReader(raw)
                record = apf_inner.parse_iff(reader, entry)
                txtrs = [f for f in record.files if f.type_name == "TXTR"]
                if not txtrs:
                    continue
                compressed += sum(b.is_compressed for b in record.blocks)
                uncompressed += sum(not b.is_compressed for b in record.blocks)
                counterparts = by_hash.get(entry.name_id, [])
                xr, xentry, xfiles, xblocks = None, None, {}, {}
                if len(counterparts) == 1 and counterparts[0].head_hex == "ff3bef94":
                    xentry = counterparts[0]
                    xr = apf_inner.parse_iff(xbox, xentry)
                    for f in xr.files:
                        if f.type_name == "TXTR":
                            xfiles.setdefault((f.file_id, f.name), []).append(f)
                blocks = {}
                for file in txtrs:
                    row = {"entry_hash": f"0x{entry.name_id:08x}", "ps3_outer": entry.table_index,
                           "ps3_inner": file.index, "ps3_volume": entry.segments[0].pack_name,
                           "ps3_virtual_offset": entry.virtual_offset,
                           "inner_hash": f"0x{file.file_id:08x}", "name": file.name,
                           "kind": texture_kind(file.name or ""), "status": "uncompared"}
                    try:
                        image, descriptor = _ps3_image(_parts(reader, record, file, blocks))
                        rgba = image.tobytes()
                        row.update(ps3_dimensions=list(image.size), ps3_format=descriptor["format"],
                                   ps3_pixels_sha256=hashlib.sha256(rgba).hexdigest())
                    except (ValueError, RuntimeError, OSError) as exc:
                        row["ps3_decode_error"] = str(exc)
                        rgba = None
                    matches = xfiles.get((file.file_id, file.name), [])
                    if len(matches) == 1:
                        target = matches[0]
                        row.update(xbox_outer=xentry.table_index, xbox_inner=target.index,
                                   destination_asset_id=f"apf:outer:{xentry.table_index}:inner:{target.index}",
                                   writer=owned.get((xentry.table_index, target.index), "candidate: inspect existing workspace owner"))
                        try:
                            dims, xrgba, meta = _xbox_image(_parts(xbox, xr, target, xblocks))
                            row.update(xbox_dimensions=list(dims), xbox_format=meta["format"],
                                       xbox_pixels_sha256=hashlib.sha256(xrgba).hexdigest())
                            if rgba is not None:
                                same = image.size == dims and rgba == xrgba
                                row["status"] = "same_pixels" if same else "different_pixels"
                                if image.size == dims:
                                    row["different_pixel_count"] = sum(a != b for a, b in zip(
                                        struct.iter_unpack("4s", rgba), struct.iter_unpack("4s", xrgba)))
                        except (ValueError, RuntimeError, OSError) as exc:
                            row["xbox_decode_error"] = str(exc)
                    else:
                        row["counterpart_error"] = f"Expected unique outer hash + inner hash/name, got {len(matches)} matches"
                    rows.append(row)
                    if log:
                        log.write(json.dumps(row, sort_keys=True) + "\n")
                if log:
                    log.flush()
            except (ValueError, RuntimeError, OSError) as exc:
                entry_errors.append({"ps3_outer": entry.table_index, "entry_hash": f"0x{entry.name_id:08x}", "error": str(exc)})
            finally:
                if progress and (number % 10 == 0 or number + 1 == len(ps3.entries)):
                    progress(number + 1, len(ps3.entries), len(rows))
        totals = Counter(row["status"] for row in rows)
        per_kind = defaultdict(Counter)
        for row in rows:
            per_kind[row["kind"]][row["status"]] += 1
        return {"schema": SCHEMA, "ps3_package": str(package), "nested_member": ps3.nested_member,
                "xbox_index": str(xbox_index), "ps3_entry_count": len(ps3.entries), "xbox_entry_count": len(archive.entries),
                "ps3_volume_bytes": {p.name: p.actual_size for p in ps3.packs}, "non_iff_entries": non_iff,
                "txtr_containing_package_blocks": {"compressed": compressed, "uncompressed": uncompressed},
                "texture_count": len(rows), "counts": dict(totals), "counts_per_kind": {k: dict(v) for k, v in sorted(per_kind.items())},
                "entry_errors": entry_errors, "textures": rows,
                "interpretation": "Different decoded base pixels are cross-platform candidates, not a proven modder-change set. Base PS3 disc absent. Uncompared rows are not equal rows. Mips and runtime consumption are not compared.",
                "runtime": "UNWITNESSED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("xbox_index", type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args(argv)
    if args.receipt.exists() or (args.journal and args.journal.exists()):
        parser.error("Choose new receipt/journal paths")
    report = compare_package(args.package, args.xbox_index, journal=args.journal,
                             progress=lambda n, total, count: print(f"Indexed {n}/{total} packages; {count} TXTRs", flush=True))
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report["counts_per_kind"], sort_keys=True))


if __name__ == "__main__":
    main()
