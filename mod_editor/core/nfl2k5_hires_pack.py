"""Opt-in resource-only 2x pack. EXPERIMENTAL / UNWITNESSED.

Explicit artwork names select pinned current-team helmets, numbers, paired
jerseys, midfield logos and the scorebug atlas/strip. Run catalog for the full
list. Keep the folder for exact replay and native-size output. Whole-game
memory fit is unproved; no 128 MiB target or executable patch is installed.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import time
import zipfile

from PIL import Image
from . import nfl2k5_hires_texture as texture
from . import nfl2k5_music_archive as archive
from . import nfl2k5_music_banks as transport
from . import texture_master
from . import nfl2k5_hires_budget as budget
from .nfl2k5_hires_evidence import RANGES as FAMILY_RANGES
from . import nfl2k5_bump_strength
from .json_stream import read_bounded_regular_file
from .errors import ValidationError

SCHEMA = "nfl2k5_hires_pack/v2"
ASSETS = texture.ASSETS
require = texture.require
sha = texture.sha

# Pinned static paths are a bounded consumer proof, not a complete runtime
# call-graph or RAM-residency proof. Other XBE owners may compose outside these.
CONSUMER_RANGES = {
    "common": (
        (0x000245B9, 68, "abe638e241bbe159e2479f35734bde2c50b6eeeb84444cfb3a701b25b81a14e7"),
        (0x00031FA0, 429, "a6ab3005c6df3a0283c15d2960a1eb7693540c33a5757701134ae7a1fead02da"),
        (0x000323D0, 351, "ff46a3686f87aa848f3b6f5109c309953048f486f48284d05e4a9bf46dede5d4"),
        (0x00034DF0, 108, "f84f040777759d3417fb8bee34ab8e046cf40255e18c467530417ae504aad29c"),
        (0x00044E60, 165, "611be14e0a1ab465f6c31533ae44a0fa10f59f888675b2bd2983f97137f896e6")),
    "scorebug": (
        (0x000FC1A0, 96, "62c0cbdf5b808560c0abe4b4cab47cb6cd16cec383a5200bd672e35f9eb6ef14"),
        (0x00A95C60, 88, "9561e949a57006c87d44b9e8e4ce6094584724e0f15394cea2f3e5145384047b")),
    "field_logo": (
        (0x0009C5DE, 142, "f88e2a96382b2347d27e10ee36d6c0e05739264b980b2366199a4748ee910e54"),
        (0x004F0090, 56, "5a73c30d0eb969ec00e0a5bd24b9035c7e65e53ed29bd276beff5d26b020f80d")),
    "helmet": (
        (0x0008E3F0, 56, "7a49b3a41f69c48ed28444a005aa33cb2f44eb1551b7613b8286836dbb8a7fb4"),
        (0x0008E9E0, 449, "8451525d8c43398801f41e51a5a0012fb530aec1c3eedb2b4a1a33af361ea33d"),
        (0x004EEAF8, 16, "0fbb2ff7e5e09eb4d2a7fbf40bd24d4f8c617844e9b31156cfe2bc029f18ffa2"),
        (0x004EF390, 64, "9b618fe07ebd9011bfa6a2f5d432ff9bd404fcb60fcb32aaaf897e0c62a3a92a")),
}
CONSUMER_RANGES.update(FAMILY_RANGES)


def validate_consumer_xbe(payload, keys):
    """Refuse changed code/table bytes at the audited asset binding paths."""
    keys = tuple(a.key for a in _selection(keys))
    require(len(payload) <= 16*archive.BLOCK, "Executable exceeds 16 MiB")
    sections = nfl2k5_bump_strength._sections(payload)
    result = []
    for family in dict.fromkeys(("common", "memory", *(texture.BY_KEY[k].consumer for k in keys))):
        for address, size, digest in CONSUMER_RANGES[family]:
            matches = [s for s in sections if s.virtual_address <= address
                       and address+size <= s.virtual_address+s.raw_size]
            require(len(matches) == 1, "Consumer address is unmapped or ambiguous")
            s = matches[0]
            at = s.raw_offset+address-s.virtual_address
            require(sha(payload[at:at+size]) == digest, f"Foreign {family} consumer at 0x{address:08x}")
            result.append(dict(family=family, address=address, offset=at, size=size, sha256=digest))
    return dict(xbe_sha256=sha(payload), ranges=result, pixel_consumer_in_audited_binders=False,
                exhaustive_runtime_consumers_proved=False, runtime_witnessed=False)


def _consumer_check(disc, keys):
    entry = disc.entries.get("default.xbe")
    require(entry is not None and entry.size <= 16*archive.BLOCK, "Missing or oversized default.xbe")
    return validate_consumer_xbe(disc.read(entry.size,entry.byte_offset),keys)


def _selection(keys):
    keys = tuple(keys)
    require(keys and len(keys) == len(set(keys)) and set(keys) <= set(texture.BY_KEY),
            "Select one or more known Hi-res assets")
    return tuple(a for a in ASSETS if a.key in keys)


FAMILIES = ("helmets", "field_logos", "stock_fields", "scorebug", "numbers", "jerseys")


def asset_family(asset):
    return asset.family or {"helmet": "helmets", "field_logo": "field_logos", "scorebug": "scorebug"}[asset.key]


def _load_artwork(asset, path):
    _, payload = read_bounded_regular_file(path, "Hi-res artwork", maximum=32*1024**2)
    detail = dict(path=str(path), file_sha256=sha(payload), kind=path.suffix[1:])
    if path.suffix == ".png":
        rgba = texture.png_rgba(payload, asset)
        detail["authored_png_sha256"] = sha(payload)
    else:
        # Bound expanded work before the general master loader renders it.
        # In particular, a tiny ZIP must not summon three 64-Mpixel canvases.
        with zipfile.ZipFile(io.BytesIO(payload)) as zipped:
            infos = zipped.infolist()
            require(len(infos) in (4, 5) and sum(i.file_size for i in infos) <= 64*archive.BLOCK,
                    "Hi-res master exceeds the 64 MiB expanded bound")
            manifest = zipped.getinfo("manifest.json")
            require(manifest.file_size <= 256*1024, "Master manifest exceeds bound")
            doc = json.loads(zipped.read(manifest))
            require(isinstance(doc, dict) and isinstance(doc.get("native"), dict)
                    and isinstance(doc.get("source"), dict), "Malformed master manifest")
            require((doc["native"].get("width"),doc["native"].get("height")) == (asset.native,asset.height),
                    f"{asset.key}: master native canvas differs")
            w, h = doc["source"].get("width"),doc["source"].get("height")
            require(type(w) is int and type(h) is int and w > 0 and h > 0 and w*h <= 16*1024**2,
                    "Hi-res master source exceeds 16 megapixels")
        bundle = texture_master.load_texture_master_bundle(path)
        doc = bundle.manifest
        require(doc["editor_target"] == "nfl2k5_xbox", "Only NFL 2K5 literal-color masters are supported")
        require((doc["native"]["width"], doc["native"]["height"]) == (asset.native, asset.height),
                f"{asset.key}: master native canvas differs")
        # The loader re-renders and authenticates this preview including any
        # native paint overlay. A 4x preview is reduced once to the 2x pilot.
        with Image.open(io.BytesIO(bundle.high_resolution_png)) as image:
            raster = image.convert("RGBA")
            if bundle.high_resolution_scale != 2:
                raster = raster.resize((asset.native*2, asset.height*2), Image.Resampling.LANCZOS)
            rgba = raster.tobytes()
        detail.update(master_source_sha256=sha(bundle.source_bytes), master_asset_id=bundle.asset_id,
            authored_png_sha256=sha(bundle.high_resolution_png), transform=doc["transform"],
            native_raster_edit=doc["native_raster_edit"], preview_scale=bundle.high_resolution_scale,
            conversion="validated master preview to 2x, Lanczos only when 4x")
        require(archive.file_hash(path) == detail["file_sha256"], "Master changed while reading")
    detail["rgba_sha256"] = sha(rgba)
    return rgba, detail


class FolderSources(Mapping):
    """Validate every file first, then decode one selected raster at a time."""
    def __init__(self, entries):
        self.entries = entries

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __getitem__(self, key):
        asset = texture.BY_KEY[key]
        expected = self.entries[key]
        rasters, details = [], []
        for info in expected:
            rgba, detail = _load_artwork(asset, Path(info["path"]))
            require(detail == info, "Authored input changed after preflight")
            rasters.append(rgba)
            details.append(detail)
        detail = dict(details[0], inputs=details)
        return (tuple(rasters) if asset.kind == "TSET" else rasters[0]), detail

    def input_details(self):
        return [info for entries in self.entries.values() for info in entries]


def load_folder(folder, *, families=None):
    """Explicit filenames; optional family filters. Unknown artwork refuses."""
    folder = Path(folder).resolve()
    require(folder.is_dir(), "Choose an existing Hi-res folder")
    if families is None:
        families = FAMILIES
    require(not isinstance(families, str), "Families must be a sequence")
    families = tuple(families)
    require(families and len(set(families)) == len(families) and set(families) <= set(FAMILIES), "Unknown or empty Hi-res family selection")
    known = {a.key+suffix+ext for a in ASSETS for suffix in (("", ".mud") if a.kind == "TSET" else ("",))
             for ext in (".png", ".2ktexmaster")}
    for path in folder.iterdir():
        if path.suffix.lower() in (".png", ".2ktexmaster"):
            require(path.name in known, f"Unknown Hi-res artwork: {path.name}")
    result = {}
    for asset in ASSETS:
        if asset_family(asset) not in families:
            continue
        entries = []
        suffixes = ("", ".mud") if asset.kind == "TSET" else ("",)
        for suffix in suffixes:
            paths = [folder/(asset.key+suffix+ext) for ext in (".png", ".2ktexmaster")]
            paths = [p for p in paths if p.exists() or p.is_symlink()]
            require(len(paths) <= 1, f"{asset.key}: choose either PNG or master, not both")
            if paths:
                _, detail = _load_artwork(asset, paths[0])
                entries.append(detail)
        require(not entries or len(entries) == len(suffixes), f"{asset.key}: supply both clean and .mud artwork")
        if entries:
            result[asset.key] = entries
    _selection(result)
    return FolderSources(result)


def preflight_budget(folder, *, scale=2, target="xemu-64", families=None):
    """Build-tab budget before texture encoding or creating an output copy."""
    require(target == "xemu-64", "128 MiB target unavailable: the guest memory and GPU address path is unproved")
    sources = load_folder(folder, families=families)
    report = budget.model(_selection(sources), scale)
    budget.enforce(report)
    return report


def _compile(payload, sources, scale, target):
    require(type(scale) is int and scale in (1, 2), "Only native or 2x output is supported")
    require(target == "xemu-64", "128 MiB target unavailable: the guest memory and GPU address path is unproved")
    assets = _selection(sources)
    require(set(payload) == set(sources), "Resource and selected artwork identities differ")
    # Validate every wrapper/system before any encoding or proposed mutation.
    require(sum(len(raw) for raw in payload.values()) <= 256*archive.BLOCK, "Selected resources exceed 256 MiB host bound")
    inspected = {a.key: texture.inspect_span(payload[a.key], a)[0] for a in assets}
    budget.enforce(budget.model(assets, scale))
    output, rows, states = {}, [], set()
    for asset in assets:
        key = asset.key
        before = inspected[key]
        _, system = texture.inspect_span(payload[key], asset)
        rgba, source = sources[key]
        raw, compiled = texture.compile_texture(system, rgba, asset, scale)
        if sha(payload[key]) == asset.retail_sha256:
            state = "retail"
        else:
            expected = raw if before["scale"] == scale else texture.compile_texture(system, rgba, asset, before["scale"])[0]
            require(payload[key] == expected, f"{key}: foreign artwork or partial texture install; rebuild from retail")
            state = f"authored-{before['scale']}x"
        states.add(state)
        output[key] = raw
        require(sum(map(len, output.values())) <= 256*archive.BLOCK, "Compiled resources exceed 256 MiB host bound")
        rows.append(dict(key=key, outer=asset.outer, chunk=asset.chunk, name_id=asset.name_id,
                         texture=asset.name, family=asset_family(asset), input=source, before=before, after=compiled["decoded"],
                         compiler=compiled, prior_state=state, changed=raw != payload[key]))
    require(len(states) == 1, "Mixed retail/authored or mixed-scale selection; rebuild the selected set from retail")
    live_budget = budget.model(assets, scale, rows=rows)
    budget.enforce(live_budget)
    video = sum(row["after"]["video_bytes"] for row in rows)
    native_video = sum(a.original_video if a.kind == "SCNE" else a.video_size(1) for a in assets)
    return output, dict(schema=SCHEMA, experimental=True, runtime_witnessed=False, target=target, scale=scale,
        status="applied" if all(not r["changed"] for r in rows) else next(iter(states)), assets=rows,
        already_applied=all(not r["changed"] for r in rows),
        memory=dict(live_budget, selected_video_bytes=video, native_video_bytes=native_video, video_delta=video-native_video,
                    selected_load_allocation_bytes=sum(r["after"]["load_allocation_bytes"] for r in rows),
                    nominal_64_mib_fraction=video/(64*1024**2), nominal_128_mib_fraction=video/(128*1024**2),
                    peak_scene_measured=False, target_128_available=False,
                    exclusions="See unknowns; host texture caches and framebuffers are separate from guest RAM"))


def apply(payload, folder, *, scale=2, target="xemu-64", families=None):
    """Pure apply of selected key -> complete TXTR/TSET/SCNE span, plus receipt."""
    return _compile(payload, load_folder(folder, families=families), scale, target)


def status(payload, folder, *, scale=2, target="xemu-64", families=None):
    """Exact recipe-relative state, including foreign/mixed refusal without mutation."""
    try:
        return apply(payload, folder, scale=scale, target=target, families=families)[1]["status"]
    except (ValueError, OSError, ValidationError, zipfile.BadZipFile, KeyError):
        return "foreign"


def _read(disc, keys):
    assets = _selection(keys)
    spans, positions = {}, {}
    groups = {}
    for asset in assets:
        groups.setdefault(asset.outer, []).append(asset)
    for outer, group in groups.items():
        require(0 <= outer < len(disc.archive_entries), "Selected outer is missing")
        entry = disc.archive_entries[outer]
        require(all(entry.name_id == a.name_id for a in group) and entry.size <= 32*archive.BLOCK, "Foreign selected outer identity/size")
        container = disc.read_entry_range(entry, 0, entry.size)
        wanted = {a.chunk: a for a in group}
        found = set()
        for index, at, raw in archive.chunks(container):
            if index not in wanted:
                continue
            asset = wanted[index]
            found.add(index)
            spans[asset.key] = raw
            positions[asset.key] = dict(outer_offset=entry.virtual_offset, outer_size=entry.size, chunk_offset=at,
                virtual_offset=entry.virtual_offset+at, outer_sha256=sha(container),
                segments=[dict(pack=s.pack_name, offset=s.pack_offset, size=s.size) for s in entry.segments])
        require(found == set(wanted), "Selected chunk is missing")
        require(sum(map(len, spans.values())) <= 256*archive.BLOCK, "Selected resources exceed 256 MiB host bound")
    return spans, positions


def _rewrite(disc, replacements):
    containers = {}
    by_chunk = {(texture.BY_KEY[k].outer, texture.BY_KEY[k].chunk): raw for k, raw in replacements.items()}
    for outer in sorted({o for o, _ in by_chunk}):
        entry = disc.archive_entries[outer]
        require(entry.size <= 32*archive.BLOCK, "Outer exceeds bound")
        disc.containers = {outer: disc.read_entry_range(entry, 0, entry.size)}
        containers.update(archive.rewrite_containers(disc, by_chunk))
        require(sum(map(len, containers.values())) <= 768*archive.BLOCK, "Rewritten containers exceed 768 MiB host bound")
    disc.containers.clear()
    return containers


def inspect_image(source, folder=None, *, scale=2, target="xemu-64", families=None):
    """Fresh XDVDFS/archive inspection. Without artwork, nonretail bytes are unverified."""
    require(type(scale) is int and scale in (1, 2), "Only native or 2x output is supported")
    require(target == "xemu-64", "128 MiB target unavailable: the guest memory and GPU address path is unproved")
    sources = load_folder(folder, families=families) if folder is not None else None
    with archive.Disc(source, descriptors=()) as disc:
        spans, positions = _read(disc, sources if sources is not None else (a.key for a in texture.PILOT_ASSETS))
        consumers = _consumer_check(disc, tuple(spans))
        if sources is not None:
            _, receipt = _compile(spans, sources, scale, target)
        else:
            rows = []
            for key, raw in spans.items():
                asset = texture.BY_KEY[key]
                try:
                    item, _ = texture.inspect_span(raw, asset)
                    item["status"] = "retail" if sha(raw) == asset.retail_sha256 else "authored-unverified"
                except ValueError as exc:
                    item = dict(key=key, status="foreign", reason=str(exc))
                rows.append(item)
            states = {r["status"] for r in rows}
            receipt = dict(schema=SCHEMA, experimental=True, runtime_witnessed=False, assets=rows,
                           inspection_scope="legacy pilot probes; supply a folder to inspect selected families",
                           status=next(iter(states)) if len(states) == 1 else "mixed")
        return dict(receipt, image_size=disc.image_size, locations=positions, consumer_xbe=consumers)


def _verify(source, output, geometry, containers, expected, progress):
    """Independent fresh readers: every outer, every file, and every selected mip."""
    with archive.Disc(source, descriptors=()) as old, archive.Disc(output, descriptors=()) as new:
        require(new.image_size == geometry["image_size"], "Output image size differs")
        require(len(new.archive_entries) == len(geometry["entries"]), "Outer count changed")
        hashes = {}
        for entry, projection in zip(new.archive_entries, geometry["entries"]):
            i = entry.table_index
            progress("verify", i, len(new.archive_entries))
            require((entry.name_id, entry.virtual_offset, entry.size) ==
                    (projection["name_id"], projection["offset"], projection["size"]), "Outer geometry differs")
            actual = new.outer_hash(i)
            require(actual == (sha(containers[i]) if i in containers else old.outer_hash(i)), f"Outer {i} hash differs")
            hashes[str(i)] = actual
        nodes = []
        for p in geometry["packs"]:
            extent = new.pack_extents[p["name"]]
            require((extent.byte_offset, extent.size) == (p["offset"], p["size"]), "Pack extent differs")
            nodes.append(dict(pack=p["name"], offset=p["node"], before=old.read(8, p["node"]).hex(),
                              after=new.read(8, p["node"]).hex()))
        require(set(old.entries) == set(new.entries), "Named files changed")
        unrelated = 0
        for name, e in old.entries.items():
            if name.startswith("vc_53450030/") or e.attributes & 0x10:
                continue
            n = new.entries[name]
            require((n.byte_offset, n.size) == (e.byte_offset, e.size), "Unrelated extent changed")
            require(archive.digest(lambda count, at: old.read(count, e.byte_offset+at), e.size) ==
                    archive.digest(lambda count, at: new.read(count, n.byte_offset+at), n.size), "Unrelated file changed")
            unrelated += 1
        actual, positions = _read(new, expected)
        require(actual == expected, "Texture output read-back differs")
        mips = {key: texture.inspect_span(raw, texture.BY_KEY[key])[0] for key, raw in actual.items()}
        return dict(status="verified", unchanged_outers=len(hashes)-len(containers), outer_sha256=hashes,
                    unchanged_named_files=unrelated, xdvdfs_nodes=nodes, locations=positions, decoded=mips,
                    output_sha256=archive.digest(new.read, new.image_size))


def build_image(source, output, folder, *, scale=2, target="xemu-64", families=None, overwrite=False, progress=None):
    """Compile first, then reuse the music grow/shrink writer and publication transaction."""
    start = time.monotonic()
    progress = progress or (lambda *_: None)
    source = Path(source).resolve()
    sources = load_folder(folder, families=families)
    before_identity = archive.identity(source)
    with archive.Disc(source, descriptors=()) as disc:
        spans, positions = _read(disc, sources)
        consumers = _consumer_check(disc, tuple(sources))
        replacements, receipt = _compile(spans, sources, scale, target)
        containers = _rewrite(disc, replacements)
        geometry = archive.layout(disc, {i: len(b) for i, b in containers.items()})
        source_hash = archive.digest(disc.read, disc.image_size)
        require(archive.identity(source) == before_identity, "Source changed while compiling")
        receipt.update(source_sha256=source_hash, source_size=disc.image_size, before_locations=positions,
                       consumer_xbe=consumers,
                       layout=geometry, logical_growth=geometry["virtual_size"]-disc.packs[-1].virtual_end,
                       physical_growth=geometry["image_size"]-disc.image_size,
                       planning_seconds=time.monotonic()-start)
    input_details = sources.input_details()
    input_paths = [detail["path"] for detail in input_details]
    require(all(archive.file_hash(detail["path"]) == detail["file_sha256"]
                for detail in input_details), "Artwork changed while compiling")

    def build(_directory, staged):
        require(all(archive.file_hash(detail["path"]) == detail["file_sha256"]
                    for detail in input_details), "Artwork changed before write")
        with archive.Disc(source, descriptors=()) as disc:
            current, _ = _read(disc, sources)
            require(current == spans and archive.layout(disc, {i: len(b) for i, b in containers.items()}) == geometry,
                    "Source resources or geometry changed before write")
            fd = os.open(staged, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                transport._write_archive(fd, disc, geometry, containers, {}, progress)
                os.fsync(fd)
            finally:
                os.close(fd)

    _, checked = archive.transactional_copy(source, output, source_sha256=source_hash,
        scratch_bytes=geometry["image_size"]+64*archive.BLOCK, build=build,
        verify=lambda staged, _: _verify(source, staged, geometry, containers, replacements, progress),
        overwrite=overwrite, inputs=input_paths, progress=progress)
    return dict(receipt, verification=checked, source_unchanged_verified=True,
                output=str(Path(output).resolve()), elapsed_seconds=time.monotonic()-start)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("catalog", "budget", "status", "inspect_image", "apply"))
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scale", type=int, choices=(1, 2), default=2)
    parser.add_argument("--target", choices=("xemu-64", "xemu-128"), default="xemu-64")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--family", choices=FAMILIES, action="append", dest="families")
    args = parser.parse_args(argv)
    if args.command == "catalog":
        result = dict(schema=SCHEMA, experimental=True, runtime_witnessed=False,
                      families=FAMILIES, assets=[dict(asdict(a), family=asset_family(a),
                          input_width=a.native*2, input_height=a.height*2, mud_pair_required=a.kind == "TSET")
                          for a in ASSETS if args.families is None or asset_family(a) in args.families])
    elif args.command == "budget":
        if args.folder is None:
            parser.error("budget requires --folder")
        result = preflight_budget(args.folder, scale=args.scale, target=args.target, families=args.families)
    elif args.command == "apply":
        if args.source is None or args.folder is None or args.output is None:
            parser.error("apply requires source, --folder and --output")
        result = build_image(args.source, args.output, args.folder, scale=args.scale,
                             target=args.target, families=args.families, overwrite=args.overwrite)
    else:
        if args.source is None:
            parser.error("inspection requires source")
        result = inspect_image(args.source, args.folder, scale=args.scale, target=args.target, families=args.families)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
