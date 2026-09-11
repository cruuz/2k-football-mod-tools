"""Package-first Team Art inventory, private thumbnails and paired staging.

Inventory is metadata-only. Names resolve by uppercase filename CRC32 against
the selected archive; layer order resolves by semantic name, never inner index.
The ordinary project builders own compression, mip regeneration, linked logo
cache writes and decode-back verification. No second game writer lives here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping
import zlib

from PIL import Image, ImageOps

from .backend import PRODUCT_ROOT, ensure_tools_importable
from .helmet_crest_design import RETAIL_CREST_PROFILE

ensure_tools_importable()
import apf_field_art_patch as field_writer
import apf_number_texture_patch as number_writer
import apf_outer
import apf_uniform_inventory

THUMBNAIL_VERSION = "team-art-v1"
FAMILIES = (("logo", "Crests"), ("endzone", "Endzones"), ("textlogo", "Wordmarks"),
            ("jersey", "Jerseys"), ("shoulder", "Shoulders"), ("pants", "Pants"), ("number", "Digits"))
STATUS = "Paired PNG staging verified offline; build allocation checks required; in-game UNWITNESSED."


@dataclass(frozen=True)
class ArtLayer:
    name: str
    asset_id: str
    inner_index: int
    width: int
    height: int
    codec: str
    writable: bool
    writer_asset_id: str | None = None


@dataclass(frozen=True)
class ArtPackage:
    family: str
    outer_index: int
    package_name: str
    catalog_index: int | None
    label: str
    retail_teams: tuple[str, ...]
    layers: tuple[ArtLayer, ...]

    @property
    def key(self):
        return f"{self.family}:{self.outer_index}"

    @property
    def writable(self):
        return bool(self.layers) and all(layer.writable for layer in self.layers)

    @property
    def search_text(self):
        return " ".join((self.label, str(self.outer_index), self.package_name, *self.retail_teams)).casefold()


def labels(family):
    path = PRODUCT_ROOT / "mod_editor" / "data" / f"apf2k8_{family}_labels.v1.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    return {int(row["outer_index"]): str(row["team"]) for row in document["labels"]}


def inventory(source, catalog):
    archive = apf_outer.parse_archive(source.index_0a)
    hashes = {entry.name_id: entry.table_index for entry in archive.entries}
    names = {}
    for family, count, prefix in (("logo", 118, "uniform_logo"), ("endzone", 118, "field_endzone"),
                                 ("textlogo", 206, "uniform_textlogo"), ("jersey", 24, "uniform_jersey"),
                                 ("shoulder", 24, "uniform_shoulder"), ("pants", 24, "uniform_pants"),
                                 ("number", 24, "uniform_number")):
        for index in range(count):
            name = f"{prefix}_{index:02d}.iff"
            outer = hashes.get(zlib.crc32(name.upper().encode("ascii")))
            if outer is not None:
                names[(family, outer)] = (name, index)
    _, teams = apf_uniform_inventory._load_team_selectors(source.index_0a)
    uses = defaultdict(set)
    for team in teams:
        if team["slot_kind"] != "built_in_team":
            continue
        for bank in team["banks"]:
            for selector in bank["selectors"]:
                for family in selector["families"]:
                    uses[(family, int(selector["asset_index_byte_0"]))].add(str(team["display_name"]))
    uniform = {(asset.outer_index, asset.inner_index): asset for asset in catalog.uniform_assets}
    number = {(int(row["entry_index"]), int(row["file_index"])): row for row in number_writer.load_targets()}
    grouped = defaultdict(list)
    for asset in catalog.assets:
        if asset.type_name != "TXTR" or asset.inner_index is None:
            continue
        name = asset.name
        family = ("logo" if name in ("logo_l0", "logo_l1") else
                  "endzone" if name in ("endzone_l0", "endzone_l1") else
                  "number" if number_writer.DIGIT_NAME_RE.fullmatch(name) else
                  name.removesuffix("_color") if name in ("textlogo_color", "jersey_color", "shoulder_color", "pants_color") else None)
        if family is None:
            continue
        location = (asset.outer_index, asset.inner_index)
        contract = field_writer._CONTRACTS.get(location) if family == "endzone" else None
        item = uniform.get(location)
        digit = number.get(location)
        if family == "logo":
            width, height, codec, writable = 512, 512, "RGBA 4:4:4:4", (family, asset.outer_index) in names
        elif contract:
            width, height, codec, writable = contract.width, contract.height, contract.codec.upper(), True
        elif item:
            width, height = item.width, item.height
            codec, writable = ("BC3 / DXT5" if family in ("jersey", "shoulder") else "BC1 / DXT1"), True
        elif digit:
            width, height, codec, writable = int(digit["width"]), int(digit["height"]), str(digit["codec"]).upper(), True
        else:
            # Unknown grammars stay visible but do not acquire a guessed writer.
            width, height, codec, writable = 0, 0, "Unmapped descriptor", False
        grouped[(family, asset.outer_index)].append(ArtLayer(name, asset.asset_id, asset.inner_index,
                                                            width, height, codec, writable,
                                                            item.asset_id if item else None))
    maps = {family: labels(family) for family in ("logo", "textlogo", "endzone")}
    result = []
    for (family, outer), layers in grouped.items():
        name, index = names.get((family, outer), (f"Endzone package {outer}", None))
        retail = tuple(sorted(uses.get((family, index), ())))
        label = maps.get(family, {}).get(outer) or ", ".join(retail) or f"Entry {outer}"
        layers.sort(key=lambda layer: layer.name)
        result.append(ArtPackage(family, outer, name, index, label, retail, tuple(layers)))
    return tuple(sorted(result, key=lambda package: (package.family, package.outer_index)))


def package_modifications(package, modifications):
    ids = {identity for layer in package.layers for identity in (layer.asset_id, layer.writer_asset_id) if identity}
    return tuple(mod for mod in modifications if mod.asset_id in ids or
                 mod.kind == "field_art_texture" and mod.metadata.get("entry_index") == package.outer_index or
                 mod.kind == "helmet_crest_design" and mod.metadata.get("crest_outer_entry_index") == package.outer_index)


def thumbnail(asset_io, package, modifications=()):
    """Worker-only decode. Cache identity includes decoder version and staged art."""
    edits = package_modifications(package, modifications)
    digest = hashlib.sha256("|".join(sorted(mod.replacement_sha256 + str(mod.metadata.get("detail_sha256", ""))
                                           for mod in edits)).encode()).hexdigest()[:20]
    destination = (asset_io.originals_root / asset_io.PREVIEW_CACHE_VERSION / THUMBNAIL_VERSION /
                   f"{package.key.replace(':', '-')}-{digest}.png")
    if destination.is_file():
        try:
            with Image.open(destination) as image:
                image.verify()
            return destination
        except (OSError, ValueError):
            destination.unlink(missing_ok=True)
    selected = package.layers[:2] if package.family in ("logo", "endzone") else package.layers[:1]
    board = Image.new("RGBA", (208, 128), (16, 26, 41, 255))
    width = 208 // len(selected)
    for i, layer in enumerate(selected):
        staged = next((mod.replacement_path for mod in edits if mod.asset_id in (layer.asset_id, layer.writer_asset_id) or
                       mod.kind == "field_art_texture" and mod.metadata.get("file_index") == layer.inner_index), None)
        if package.family == "logo" and edits:
            mod = edits[0]
            staged = mod.replacement_path if layer.name == "logo_l0" else None
            # Detail PNGs are embedded in the crest recipe's content-addressed store.
            detail = mod.metadata.get("detail_sha256")
            if layer.name == "logo_l1" and detail:
                staged = mod.replacement_path.parent / f"{detail}.png"
        path = staged or asset_io.preview_texture(layer.asset_id)
        with Image.open(path) as image:
            image = ImageOps.contain(image.convert("RGBA"), (width - 8, 120), Image.Resampling.LANCZOS)
            board.alpha_composite(image, (i * width + (width - image.width) // 2, (128 - image.height) // 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".thumb-", suffix=".png", dir=destination.parent)
    os.close(descriptor)
    try:
        board.save(temporary, "PNG")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def stage_package(session, package, supplied: Mapping[str, Path]):
    """Resolve the package once, validate every layer, then stage one Undo unit."""
    live = next((value for value in inventory(session.source, session.catalog) if value.key == package.key), None)
    if live != package:
        raise ValueError("The selected Team Art package changed. Select it again.")
    required = {layer.name for layer in package.layers}
    if not supplied or not set(supplied) <= required:
        raise ValueError("Choose PNGs for the named layers in this package.")
    if package.family != "number" and set(supplied) != required:
        raise ValueError("Choose every layer together: " + ", ".join(sorted(required)))
    if not package.writable:
        raise ValueError("This package has no complete replacement writer.")
    for layer in package.layers:
        if layer.name not in supplied:
            continue
        with Image.open(supplied[layer.name]) as image:
            image.load()
            if image.format != "PNG" or image.size != (layer.width, layer.height):
                raise ValueError(f"{layer.name} needs a {layer.width}×{layer.height} PNG.")
    if package.family == "number":
        # Refit the entire shared budget, including digits already in this project.
        combined = {mod.metadata["name"]: mod.replacement_path for mod in session.modifications
                    if mod.kind == "number_texture" and mod.metadata.get("entry_index") == package.outer_index}
        combined.update(supplied)
        number_writer.build_package_patch(session.source.index_0a, package.outer_index, combined)
    result = []
    with session.atomic_edit():
        if package.family == "logo":
            result.append(session.replace_helmet_crest_design(supplied["logo_l0"], profile=RETAIL_CREST_PROFILE,
                          crest_asset_index=package.catalog_index, crest_outer_entry_index=package.outer_index,
                          detail_png=supplied["logo_l1"]))
        else:
            for layer in package.layers:
                if layer.name not in supplied:
                    continue
                if package.family == "endzone":
                    result.append(session.replace_field_art((package.outer_index, layer.inner_index), supplied[layer.name]))
                elif package.family == "number":
                    result.append(session.replace_number(layer.asset_id, supplied[layer.name]))
                else:
                    result.append(session.replace_uniform(layer.writer_asset_id or layer.asset_id, supplied[layer.name]))
    return tuple(result)


def main(argv=None) -> int:
    """Print the Team Art inventory of a user's own APF source (metadata only; nothing is written)."""
    import argparse

    parser = argparse.ArgumentParser(description="List every Team Art package (crests, endzones, wordmarks, jerseys, "
                                                 "shoulders, pants, digits) resolved from an APF 2K8 source, with its "
                                                 "layers, sizes, codecs and writable state.")
    parser.add_argument("--source", type=Path, required=True, help="the APF game folder or ISO (opened read-only)")
    parser.add_argument("--family", choices=("logo", "endzone", "textlogo", "jersey", "shoulder", "pants", "number"),
                        help="only this family (default: every family)")
    parser.add_argument("--json", type=Path, help="write the inventory as JSON here")
    args = parser.parse_args(argv)
    from .facade import ApfStudioFacade

    facade = ApfStudioFacade()
    facade.load_source(args.source)
    session = facade.require_session()
    packages = [package for package in inventory(session.source, session.catalog)
                if args.family is None or package.family == args.family]
    rows = [{"family": p.family, "outer_index": p.outer_index, "package": p.package_name,
             "catalog_index": p.catalog_index, "label": p.label, "retail_teams": list(p.retail_teams),
             "writable": p.writable,
             "layers": [{"name": l.name, "inner_index": l.inner_index, "width": l.width, "height": l.height,
                         "codec": l.codec, "writable": l.writable} for l in p.layers]} for p in packages]
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8", newline="\n")
    for row in rows:
        layers = ", ".join(f"{l['name']} {l['width']}x{l['height']} {l['codec']}" for l in row["layers"])
        print(f"{row['family']:<8} entry {row['outer_index']:>5}  {row['package']:<26} {row['label']:<24} "
              f"{'writable' if row['writable'] else 'browse only':<11} {layers}")
    print(f"{len(rows)} packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
