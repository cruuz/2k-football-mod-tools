#!/usr/bin/env python3
"""Export and verify the private NFL 2K5 Giants GIMP hand-off bundle.

The unified visual provider is a fail-closed import/build provider and does not
currently expose an export command.  This narrow adapter selects the same
hash-pinned target reports used by that provider, decodes the six embedded
TSET images from the authenticated retail extraction, and re-authenticates the
standalone PNG extractions before placing them in one private editing bundle.

The exported PNGs are retail-derived.  They are for the dump owner's private
editing workflow and are not public-release assets.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import Any, Callable

import nfl2k5_jersey_png_workflow as ownership
import nfl_jersey_tset_png_import as jersey_import
import nfl_jersey_tset_targets as jersey_targets
import nfl_live_helmet_txtr_targets as helmet_targets
import nfl_live_numbers_nameplate_targets as live_art_targets
import nfl_pants_tset_png_import as pants_import
import nfl_pants_tset_targets as pants_targets
import nfl_sleeve_tset_png_import as sleeve_import
import nfl_sleeve_tset_targets as sleeve_targets
import nfl_team_select_card_targets as card_targets
import nfl_tset_png_import as png_codec
import nfl2k5_visual_mod_project as visual_provider
from nfl_outer import parse_archive
from nfl_txtr import encode_rgba_png
from nfl_uniform_inventory import read_and_validate_span


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_giants_gimp_bundle/v1"
EDIT_MAP_SCHEMA = "nfl2k5_giants_provider_edit_map/v1"
VERIFY_SCHEMA = "nfl2k5_giants_gimp_bundle_verify/v1"
ASSET_CODE = "18"
VARIANT = 0
SOURCE_SIZE = 6_300_499_968
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
ALL_TXTR = ROOT / "reports/assets/nfl2k5_all_txtr_inventory_v2.json"
ALL_TXTR_SIZE = 62_137_803
ALL_TXTR_SHA256 = "5295168a4596b7be273e534b36efd2b53f44c7ed5f16893110a63413397f4929"
PROVIDER_ID = "nfl2k5-unified-visual-v1"
PROVIDER_CAPABILITY = "nfl2k5.uniforms.all_visual"
PROVIDER_BACKEND = "tools/nfl2k5_visual_mod_project.py"
PROVIDER_BACKEND_SHA256 = \
    "253c9ff3ac4cb32f2741d69ed535a0cdbc9a3a7cab4b099864f810d713f03e62"
HASH_BLOCK = 16 * 1024 * 1024

REPORT_PINS = {
    "resource_chunks": {
        "path": ownership.DEFAULT_INVENTORY,
        "size": ownership.INVENTORY_SIZE,
        "sha256": ownership.INVENTORY_SHA256,
    },
    "all_txtr": {
        "path": ALL_TXTR,
        "size": ALL_TXTR_SIZE,
        "sha256": ALL_TXTR_SHA256,
    },
    "torso": {
        "path": jersey_targets.DEFAULT_REPORT,
        "sha256": jersey_targets.REPORT_SHA256,
    },
    "sleeve": {
        "path": sleeve_targets.DEFAULT_REPORT,
        "sha256": sleeve_targets.REPORT_SHA256,
    },
    "pants": {
        "path": pants_targets.DEFAULT_REPORT,
        "sha256": pants_targets.REPORT_SHA256,
    },
    "live_helmet": {
        "path": helmet_targets.DEFAULT_REPORT,
        "sha256": helmet_targets.REPORT_SHA256,
    },
    "live_number_nameplate": {
        "path": live_art_targets.DEFAULT_REPORT,
        "sha256": live_art_targets.REPORT_SHA256,
    },
    "team_select": {
        "path": ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json",
        "size": card_targets.REPORT_SIZE,
        "sha256": card_targets.REPORT_SHA256,
    },
}


class BundleError(ValueError):
    """Raised when an input, target, PNG, or output fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(HASH_BLOCK), b""):
            result.update(block)
    return result.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def regular_file(path: Path, label: str) -> os.stat_result:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise BundleError(f"{label} is missing: {path}") from exc
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file: {path}")
    return supplied


def pinned_payload(path: Path, label: str, expected_sha256: str,
                   expected_size: int | None = None) -> bytes:
    info = regular_file(path, label)
    if expected_size is not None:
        require(info.st_size == expected_size,
                f"{label} size mismatch: {info.st_size} != {expected_size}")
    payload = path.read_bytes()
    require(len(payload) == info.st_size, f"{label} changed while reading")
    require(digest(payload) == expected_sha256, f"{label} SHA-256 mismatch")
    return payload


def verify_source(path: Path) -> dict[str, object]:
    info = regular_file(path, "retail source XISO")
    require(info.st_size == SOURCE_SIZE,
            f"retail source XISO size mismatch: {info.st_size} != {SOURCE_SIZE}")
    actual = file_digest(path)
    require(actual == SOURCE_SHA256, "retail source XISO SHA-256 mismatch")
    return {"path": str(path.resolve()), "size": info.st_size, "sha256": actual}


def report_manifest() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for name, pin in REPORT_PINS.items():
        path = Path(pin["path"])
        payload = pinned_payload(
            path, f"{name} report", str(pin["sha256"]),
            int(pin["size"]) if "size" in pin else None,
        )
        result[name] = {
            "path": str(path.relative_to(ROOT)),
            "size": len(payload),
            "sha256": digest(payload),
        }
    backend = pinned_payload(
        ROOT / PROVIDER_BACKEND, "unified provider backend",
        PROVIDER_BACKEND_SHA256,
    )
    result["provider_backend"] = {
        "path": PROVIDER_BACKEND,
        "size": len(backend),
        "sha256": digest(backend),
    }
    return result


def strict_png(payload: bytes, dimensions: tuple[int, int]) \
        -> tuple[int, int, bytes]:
    return png_codec.decode_rgba_png(payload, dimensions)


def canonical_png(width: int, height: int, rgba: bytes) -> bytes:
    require(len(rgba) == width * height * 4, "RGBA byte count mismatch")
    payload = encode_rgba_png(width, height, rgba)
    parsed_width, parsed_height, parsed_rgba = strict_png(payload, (width, height))
    require((parsed_width, parsed_height, parsed_rgba) == (width, height, rgba),
            "generated PNG failed strict RGBA round-trip")
    return payload


def alpha_stats(rgba: bytes) -> dict[str, int]:
    values = rgba[3::4]
    return {
        "minimum": min(values),
        "maximum": max(values),
        "transparent_pixels": sum(value == 0 for value in values),
        "partial_alpha_pixels": sum(0 < value < 255 for value in values),
        "opaque_pixels": sum(value == 255 for value in values),
    }


def load_json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise BundleError(f"{label} is invalid JSON") from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    return value


def standalone_inventory() -> tuple[dict[tuple[int, int, str], dict[str, Any]],
                                    dict[str, Any]]:
    value = load_json(
        pinned_payload(ALL_TXTR, "all-TXTR inventory", ALL_TXTR_SHA256,
                       ALL_TXTR_SIZE),
        "all-TXTR inventory",
    )
    require(value.get("schema") == "nfl2k5_all_txtr_inventory/v1",
            "all-TXTR inventory schema mismatch")
    lookup: dict[tuple[int, int, str], dict[str, Any]] = {}
    for row in value.get("textures", []):
        key = (int(row["outer_index"]), int(row["chunk_index"]), str(row["name"]))
        require(key not in lookup, f"duplicate all-TXTR inventory key: {key}")
        lookup[key] = row
    require(len(lookup) == 57_208, "all-TXTR texture count mismatch")
    return lookup, value


def authenticated_png_from_inventory(
    row: dict[str, Any], expected_dimensions: tuple[int, int],
    expected_rgba_sha256: str | None,
) -> tuple[bytes, bytes]:
    path = ROOT / str(row["png_path"])
    regular_file(path, "authenticated retail PNG")
    payload = path.read_bytes()
    width, height, rgba = strict_png(payload, expected_dimensions)
    require((width, height) == expected_dimensions,
            "authenticated retail PNG dimensions changed")
    row_rgba = str(row["rgba_sha256"])
    require(digest(rgba) == row_rgba,
            f"authenticated retail PNG RGBA hash mismatch: {path}")
    if expected_rgba_sha256 is not None:
        require(row_rgba == expected_rgba_sha256,
                "target report and all-TXTR RGBA hashes disagree")
    return canonical_png(width, height, rgba), rgba


def authenticated_card_png(
    report: dict[str, Any], target: card_targets.CardTarget,
) -> tuple[bytes, bytes, dict[str, Any]]:
    rows = [row for row in report["targets"] if row["selector"] == target.selector]
    require(len(rows) == 1, f"card target row is absent/ambiguous: {target.selector}")
    row = rows[0]
    path = ROOT / str(row["retail_png_path"])
    regular_file(path, "authenticated Team Select PNG")
    payload = path.read_bytes()
    width, height, rgba = strict_png(payload, (target.resolution, target.resolution))
    require((width, height) == (target.resolution, target.resolution) and
            digest(rgba) == target.rgba_sha256 == str(row["rgba_sha256"]),
            f"Team Select PNG authentication failed: {target.selector}")
    return canonical_png(width, height, rgba), rgba, row


def markdown_start_here() -> str:
    return """# START HERE — Edit These Files and Hand Them Back

This is your **private New York Giants working bundle** made from your own NFL
2K5 dump. Do not upload or redistribute it: the PNGs reproduce retail artwork.

## What to do

1. Make a backup copy of this entire folder.
2. In GIMP, open PNGs only under `EDIT_THESE/HOME/` and
   `EDIT_THESE/AWAY/`. Paint directly over the supplied art so the existing
   seams, transparent margins, placement, and orientation stay intact.
3. For a complete uniform, edit torso, pants, sleeve, **both** helmet files,
   any digits/nameplate whose look changes, and all three Team Select cards for
   each side. The cards are separate baked menu pictures and do not update from
   the live uniform automatically.
4. Export each result back over the same PNG filename. Keep the exact pixel
   size. Export as 8-bit RGBA PNG with interlacing off. Do not flatten away
   transparency, resize, crop, rotate, or rename files. An `.xcf` does not
   replace the required `.png`.
5. Do not edit `REFERENCE_ONLY/`. Its six mud-state images show the original
   dirty look. I will safely generate the modified mud palettes from your clean
   art during the build.
6. Hand back this whole folder, including the untouched
   `bundle-manifest.json` and `provider-edit-map.json`. Optional XCF files may
   go in a new `WORKFILES/` folder.

## The only design warning that matters while painting

There is not yet a proved pixel-by-pixel UV diagram saying “this rectangle is
the front” or “this is the left sleeve.” Use the visible retail art as the
template, preserve its borders/seams, and avoid moving whole panels. The two
helmet files (`helmet00` and `helmet02`) are different player-model UV modes;
edit each one on its own template.

## What to tell me when you return it

Say which HOME and AWAY pieces you intended to change and whether each Team
Select card is final. I will decode the returned pixels and compare their RGBA
hashes with the baseline, include only truly changed art, build and independently
verify a new XISO, then test HOME and AWAY at coin toss, during actual gameplay,
and in Team Select. Unchanged files are allowed; do not make fake one-pixel
changes. A GIMP re-export with identical pixels will correctly count as unchanged.
"""


def markdown_asset_map() -> str:
    return """# New York Giants Current Uniform — Technical Asset Map

## Scope and provenance

This bundle targets New York Giants roster team index `15`, asset code `18`,
current uniform variant/style `0`: HOME package `18H0.IFF` (outer `3762`, ID
`0xa92f4231`) and AWAY package `18A0.IFF` (outer `4079`, ID `0x348678a0`). It
was exported from the pinned retail XISO recorded in `bundle-manifest.json`.

The import/build route is typed capability `nfl2k5.uniforms.all_visual`,
provider `nfl2k5-unified-visual-v1`, schema
`nfl2k5_visual_mod_project/v1`. The provider itself has `validate`, `build`,
and `verify`, but no export command. This bundle's narrow exporter therefore
uses the provider's same hash-pinned target selectors and codecs. The six
embedded TSET resources are decoded from authenticated pack 0; all standalone
images are strict-reparsed and matched to their pinned target and all-TXTR
inventory records.

There are **78 editable PNG targets** plus **6 mud reference PNGs**, for 84 PNGs
total. “Complete” here means every provider-supported part requested for this
workflow. Socks, shoes, gloves, long sleeves, elbow/wrist bands, bump maps,
models/UVs, and `logo`/`chiclet`/`splayer`/`flipchip` resources remain unchanged
because unified provider v1 has no proved writer for them.

## File map

| Folder / files per side | Count | Size | Game role |
|---|---:|---:|---|
| `01_LIVE_UNIFORM/torso_jersey.png` | 1 | 512×256 | Torso/jersey clean TSET |
| `01_LIVE_UNIFORM/pants.png` | 1 | 512×256 | Pants clean TSET |
| `01_LIVE_UNIFORM/sleeve.png` | 1 | 128×128 | Sleeve clean TSET |
| `02_LIVE_HELMETS/helmet00.png` | 1 | 256×256 | Player mode 0 / material family A |
| `02_LIVE_HELMETS/helmet02.png` | 1 | 256×256 | Player mode 1 / material family C |
| `03_LIVE_DIGITS/jersey/digit_0..9.png` | 10 | 64×64 | Front/back jersey digits |
| `03_LIVE_DIGITS/helmet/digit_0..9.png` | 10 | 32×32 | Helmet digits |
| `03_LIVE_DIGITS/arm/digit_0..9.png` | 10 | 64×64 | Arm/shoulder digits |
| `04_NAMEPLATE/nameplate_atlas.png` | 1 | 1024×32 | Uniform name glyph atlas |
| `05_TEAM_SELECT/uniform_card_256.png` | 1 | 256×256 | Baked uniform/menu card |
| `05_TEAM_SELECT/helmet_card_256.png` | 1 | 256×256 | Large helmet/menu card |
| `05_TEAM_SELECT/helmet_card_128.png` | 1 | 128×128 | Separate small helmet card |
| `REFERENCE_ONLY/.../*_mud.png` | 3 | as live TSET | Original mud palettes, not hand-back inputs |

The same 39 editable paths exist under HOME and AWAY. Each image has its exact
selector, source chunk/span, PNG hash, RGBA hash, dimensions, alpha statistics,
and future provider edit object in the JSON ledgers.

## TSET clean/mud behavior

Torso (`jersey00`), pants (`pants00`), and sleeve (`sleeve00`) are P8 indexed
texture sets. Torso/pants have six mip levels; sleeve has five. Clean and mud
inside each TSET share one exact index chain but use separate palettes. Two
independently painted PNGs may not reduce to the same indices at every mip, so
the safe build form is the edited clean PNG plus `mud_png: null` and
`mud_mode: darken_60`. The original `_mud` images are exported only as visual
references. The provider regenerates all lower mips deterministically.

The Giants torso/pants/sleeve retail base images are fully opaque, but their
files must remain RGBA. P8 means at most 256 palette entries after quantization.
Very noisy art, fine gradients, and one-pixel detail can quantize poorly and can
also make a compressed fixed-span resource fail its allocation limit. A failed
fit is a safe refusal, not permission to grow or relocate the resource.

## UV/layout evidence and painting rule

These are UV atlases, not flat front-and-back photographs. No proved semantic
UV overlay currently maps exact pixels to front/back/left/right body regions;
the recovered body mesh lacks usable exported UV/material semantics and that
work remains a `PORTME`. Do not invent coordinates from appearance. Paint over
the retail template, keep the existing islands, borders, blank margins,
orientation, and stripe breaks, and use an eventual runtime capture to judge
placement.

`helmet00` binds live player mode 0 to `HI_HELMET_A` /
`HELMET_A_accessories`; `helmet02` binds mode 1 to `HI_HELMET_C` /
`HELMET_C_accessories`. They are distinct UV maps. Editing or copying only one
does not prove coverage of the other model mode.

## Digits and nameplate

Per side, chunks/resources `48`–`57` are jersey digits 0–9, `hn48`–`hn57`
are helmet digits, and `an48`–`an57` are arm/shoulder digits. The numeric
resource suffix is ASCII-derived: `48` is digit 0 and `57` is digit 9. Jersey
and arm glyph pixels currently match within a side, but their spans are
independent and both must be targeted if the digit design changes.

`names` is a 1024×32 horizontal alphabet atlas, not one player's name strip. Its
29 metric entries are read-only: apostrophe at stored offset 32; hyphen at 64
(space reuses its advance without drawing); A/a through Z/z at offsets 96–896
in 32-pixel steps; entry 28 at 928 remains unmapped. Keep glyph registration
and existing widths. HOME and AWAY use different atlas pixels and advances.

Digits, nameplates, helmets, and cards contain transparent/partially transparent
pixels. Preserve their transparent margins and antialiased alpha; do not flatten
them onto a background.

## Team Select is separate

Each side has a 256×256 `unif` card and 256×256 plus 128×128 `helm` cards.
`unif` is a baked torso-plus-lower-helmet illustration, so its helmet portion
must be painted even after editing the separate helmet card. These cards do not
regenerate from live assets. The 256 class has prior runtime ownership evidence;
the exact consumer/timing of the separate 128 helmet resource is unresolved, so
both sizes are included for honest completeness.

## Retail sharing versus writable ownership

All selected targets occupy independent, non-overlapping disc spans even when
their current RGBA is identical. HOME/AWAY pants, both live helmet families,
and helmet digits have matching retail content but separate writable ownership.
HOME/AWAY torso, sleeve, jersey digits, arm digits, nameplate atlas, and all
cards differ. Within a side, jersey and arm digits match visually but are also
separate spans. Reusing an authored design across paths is allowed deliberately;
one write never updates another target automatically.

Across the full retail selector inventory, each current HOME and AWAY torso is
content-unique. The shared current pants art also occurs in Giants historical
variants 1 and 7. The HOME sleeve repeats in several Giants historical variants;
the AWAY sleeve's pixels occur under 66 selectors spanning 33 asset codes. The
two live helmet images repeat in Giants variants 0, 1, and 7. Team Select card
visual aliases are confined to other Giants styles. These are content aliases,
not shared storage: an `18H0`/`18A0` write still changes only the selected Giants
current-uniform spans.

## Changed-only build rule

Do not put all 78 exports into a provider project. Several importers reject a
pixel-identical retail replacement, and the unified builder rejects zero-diff
non-identity edits. On hand-back, strict-decode each PNG and compare the decoded
RGBA SHA-256 with `baseline_rgba_sha256` in `provider-edit-map.json`, then
construct canonical project JSON from pixel-changed entries only. Do **not** use
the encoded PNG file hash for that decision: GIMP may change PNG compression or
metadata without changing any pixels. `validate` checks schema and input pins
but explicitly does not prove target compatibility; full PNG/codec/allocation
proof occurs in `build`, and independent reconstruction occurs in `verify`.

## Private/public boundary

This folder contains retail-derived PNGs and must not be redistributed. A later
public tool may ship source, schemas, metadata, documentation, and user-authored
art only. It must extract/read required bytes from each user's own legal dump;
it must not ship this bundle, an XISO, extracted packs, IFF/TSET/TXTR spans,
retail previews, or build artifacts. Xemu is the intended runtime target;
original Xbox hardware remains untested.
"""


class BundleBuilder:
    def __init__(self, root: Path, source: dict[str, object],
                 reports: dict[str, dict[str, object]]) -> None:
        self.root = root
        self.source = source
        self.reports = reports
        self.images: list[dict[str, Any]] = []
        self.edit_entries: list[dict[str, Any]] = []

    def write(self, relative: str, payload: bytes) -> Path:
        require(not relative.startswith("/") and ".." not in Path(relative).parts,
                f"unsafe bundle-relative path: {relative}")
        path = self.root / relative
        require(not path.exists(), f"duplicate bundle output path: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def add_png(self, relative: str, payload: bytes, rgba: bytes,
                width: int, height: int, role: str, side: str, part: str,
                selector: str, storage: dict[str, Any],
                provider_edit: dict[str, Any] | None) -> None:
        require(role in {"editable", "reference_only"}, "invalid PNG role")
        parsed_width, parsed_height, parsed_rgba = strict_png(
            payload, (width, height))
        require((parsed_width, parsed_height, parsed_rgba) ==
                (width, height, rgba), f"PNG round-trip mismatch: {relative}")
        self.write(relative, payload)
        row: dict[str, Any] = {
            "alpha": alpha_stats(rgba),
            "baseline_png_sha256": digest(payload),
            "baseline_rgba_sha256": digest(rgba),
            "dimensions": {"width": width, "height": height},
            "part": part,
            "path": relative,
            "role": role,
            "selector": selector,
            "side": side,
            "storage": storage,
        }
        self.images.append(row)
        if provider_edit is not None:
            require(role == "editable", "reference PNG cannot have provider edit")
            entry = {
                "baseline_png_sha256": digest(payload),
                "baseline_rgba_sha256": digest(rgba),
                "dimensions": {"width": width, "height": height},
                "edit": provider_edit,
                "path": relative,
                "selector": selector,
            }
            self.edit_entries.append(entry)

    def finish(self) -> None:
        require(len(self.images) == 84, f"expected 84 PNGs, got {len(self.images)}")
        require(len(self.edit_entries) == 78,
                f"expected 78 editable targets, got {len(self.edit_entries)}")
        require(len({row["path"] for row in self.images}) == 84,
                "bundle PNG paths are not unique")
        require(len({row["selector"] for row in self.edit_entries}) == 78,
                "editable target selectors are not unique")

        groups: dict[str, list[str]] = {}
        for row in self.images:
            if row["role"] == "editable":
                groups.setdefault(row["baseline_rgba_sha256"], []).append(row["path"])
        aliases = [
            {"baseline_rgba_sha256": rgba_hash, "paths": sorted(paths)}
            for rgba_hash, paths in sorted(groups.items()) if len(paths) > 1
        ]

        self.write("START_HERE_EDIT_AND_RETURN.md",
                   markdown_start_here().encode("utf-8"))
        self.write("ASSET_MAP_TECHNICAL.md", markdown_asset_map().encode("utf-8"))
        edit_map = {
            "changed_only_rule": (
                "Strict-decode each current PNG and generate an edit only when its "
                "decoded RGBA SHA-256 differs from baseline_rgba_sha256. Encoded PNG "
                "bytes may change on a GIMP re-export without changing pixels; never "
                "use baseline_png_sha256 to select edits."
            ),
            "entries": sorted(self.edit_entries, key=lambda row: row["selector"]),
            "future_project_schema": "nfl2k5_visual_mod_project/v1",
            "mud_policy": {
                "editable_input": "clean PNG only",
                "mud_mode": "darken_60",
                "mud_png": None,
                "reason": "clean and mud must share one exact P8 index chain",
            },
            "provider": {
                "backend": PROVIDER_BACKEND,
                "backend_sha256": PROVIDER_BACKEND_SHA256,
                "capability": PROVIDER_CAPABILITY,
                "id": PROVIDER_ID,
            },
            "purpose": "New York Giants HOME/AWAY current-uniform changed-file map",
            "schema": EDIT_MAP_SCHEMA,
        }
        self.write("provider-edit-map.json", canonical_json(edit_map))

        manifest = {
            "counts": {
                "editable_pngs": 78,
                "home_editable_pngs": 39,
                "away_editable_pngs": 39,
                "reference_only_mud_pngs": 6,
                "total_pngs": 84,
            },
            "images": sorted(self.images, key=lambda row: row["path"]),
            "known_exact_rgba_aliases": aliases,
            "legal": {
                "contains_retail_derived_pngs": True,
                "public_redistribution_allowed": False,
                "use": "private editing by the owner of the authenticated dump",
            },
            "provider": {
                "backend": PROVIDER_BACKEND,
                "backend_sha256": PROVIDER_BACKEND_SHA256,
                "capability": PROVIDER_CAPABILITY,
                "export_api_available": False,
                "id": PROVIDER_ID,
                "project_schema": "nfl2k5_visual_mod_project/v1",
            },
            "reports": self.reports,
            "schema": SCHEMA,
            "source_xiso": self.source,
            "team": {
                "asset_code": ASSET_CODE,
                "away": {"logical_name": "18A0.IFF", "outer_id": "0x348678a0",
                         "outer_index": 4079, "selector": "18A0"},
                "home": {"logical_name": "18H0.IFF", "outer_id": "0xa92f4231",
                         "outer_index": 3762, "selector": "18H0"},
                "name": "New York Giants",
                "roster_team_index": 15,
                "style": 0,
                "variant": VARIANT,
            },
            "warnings": [
                "PRIVATE: PNGs contain retail-derived artwork; do not redistribute.",
                "No proved semantic UV overlay exists; preserve retail seams/layout.",
                "Only decoded-RGBA-changed PNGs may enter the eventual provider project.",
                "Mud PNGs are references; modified mud is derived with darken_60.",
            ],
        }
        self.write("bundle-manifest.json", canonical_json(manifest))

        checksum_paths = sorted(
            path for path in self.root.rglob("*") if path.is_file() and
            path.name != "BASELINE_SHA256SUMS.txt"
        )
        lines = [
            f"{file_digest(path)}  {path.relative_to(self.root).as_posix()}"
            for path in checksum_paths
        ]
        self.write("BASELINE_SHA256SUMS.txt", ("\n".join(lines) + "\n").encode())


def tset_exports(builder: BundleBuilder) -> None:
    inventory_payload = pinned_payload(
        ownership.DEFAULT_INVENTORY, "resource chunk inventory",
        ownership.INVENTORY_SHA256, ownership.INVENTORY_SIZE,
    )
    inventory = load_json(inventory_payload, "resource chunk inventory")
    index_payload = pinned_payload(
        ownership.DEFAULT_INDEX, "authenticated extracted pack 0",
        ownership.INDEX_SHA256, ownership.INDEX_SIZE,
    )
    # parse_archive accepts a path and independently reads the same pinned file.
    del index_payload
    archive = parse_archive(ownership.DEFAULT_INDEX)

    kinds: list[tuple[
        str, Any, Any,
        Callable[[bytes], tuple[list[Any], list[Any]]], str, int, int, int,
    ]] = [
        ("torso", jersey_targets, jersey_import,
         jersey_import.legacy.decode_tset_levels, "jersey00", 512, 256, 6),
        ("pants", pants_targets, pants_import,
         pants_import.decode_tset_levels, "pants00", 512, 256, 6),
        ("sleeve", sleeve_targets, sleeve_import,
         sleeve_import.decode_tset_levels, "sleeve00", 128, 128, 5),
    ]
    for side_code, side_name in (("H", "HOME"), ("A", "AWAY")):
        for kind, target_module, import_module, decoder, resource_name, width, height, mips \
                in kinds:
            _, _, _, target = target_module.select_target(
                ASSET_CODE, side_code, VARIANT)
            item, _ = import_module.target_record(inventory, target)
            _, span, decoded, _ = read_and_validate_span(archive, item)
            require(digest(span) == target.span_sha256 and
                    digest(decoded) == target.decoded_sha256,
                    f"TSET target hash mismatch: {target.selector}")
            clean_levels, mud_levels = decoder(decoded)
            require(len(clean_levels) == len(mud_levels) == mips and
                    (clean_levels[0].width, clean_levels[0].height) == (width, height),
                    f"TSET mip layout mismatch: {target.selector}:{kind}")
            storage = {
                "chunk_index": target.chunk_index,
                "format": "P8",
                "logical_name": target.logical_name,
                "mip_levels": mips,
                "outer_id": f"0x{target.outer_id:08x}",
                "outer_index": target.outer_index,
                "resource_name": resource_name,
                "span_sha256": target.span_sha256,
                "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
            }
            clean = clean_levels[0]
            clean_path = (
                f"EDIT_THESE/{side_name}/01_LIVE_UNIFORM/"
                f"{'torso_jersey' if kind == 'torso' else kind}.png"
            )
            edit = {
                "asset_code": ASSET_CODE,
                "clean_png": clean_path,
                "kind": kind,
                "mud_mode": "darken_60",
                "mud_png": None,
                "side": side_code,
                "variant": VARIANT,
            }
            builder.add_png(
                clean_path, canonical_png(width, height, clean.rgba), clean.rgba,
                width, height, "editable", side_name, kind,
                f"{target.selector}:{kind}:clean", storage, edit,
            )
            mud = mud_levels[0]
            mud_path = (
                f"REFERENCE_ONLY/{side_name}/MUD/"
                f"{'torso_jersey' if kind == 'torso' else kind}_mud.png"
            )
            builder.add_png(
                mud_path, canonical_png(width, height, mud.rgba), mud.rgba,
                width, height, "reference_only", side_name, f"{kind}_mud",
                f"{target.selector}:{kind}:mud", storage, None,
            )


def standalone_exports(builder: BundleBuilder) -> None:
    lookup, _ = standalone_inventory()
    card_report_payload = pinned_payload(
        ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json",
        "Team Select card report", card_targets.REPORT_SHA256,
        card_targets.REPORT_SIZE,
    )
    card_report = load_json(card_report_payload, "Team Select card report")

    for side_code, side_name, card_side in (
        ("H", "HOME", "home"), ("A", "AWAY", "away"),
    ):
        # Both live player helmet material/UV modes.
        for family in ("helmet00", "helmet02"):
            _, _, _, target = helmet_targets.select_target(
                ASSET_CODE, side_code, VARIANT, family)
            key = (target.outer_index, target.chunk_index, family)
            require(key in lookup, f"helmet is absent from all-TXTR inventory: {key}")
            row = lookup[key]
            payload, rgba = authenticated_png_from_inventory(
                row, (256, 256), target.rgba_sha256)
            relative = f"EDIT_THESE/{side_name}/02_LIVE_HELMETS/{family}.png"
            edit = {
                "asset_code": ASSET_CODE,
                "family": family,
                "kind": "live_helmet",
                "png": relative,
                "side": side_code,
                "variant": VARIANT,
            }
            storage = {
                "chunk_index": target.chunk_index,
                "format": "P8",
                "live_player_mode": target.live_player_mode,
                "logical_name": target.logical_name,
                "material_family": "A" if family == "helmet00" else "C",
                "mip_levels": 6,
                "outer_id": f"0x{target.outer_id:08x}",
                "outer_index": target.outer_index,
                "resource_name": family,
                "span_sha256": target.span_sha256,
                "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
            }
            builder.add_png(relative, payload, rgba, 256, 256, "editable",
                            side_name, family, f"{target.logical_name[:-4]}:{family}",
                            storage, edit)

        # Jersey, helmet, and arm/shoulder digit 0..9 resources.
        digit_specs = (
            ("jersey", "jersey", 64, 64),
            ("helmet", "helmet", 32, 32),
            ("arm", "arm", 64, 64),
        )
        for public_family, folder, width, height in digit_specs:
            for digit_value in range(10):
                _, _, target = live_art_targets.select_target(
                    public_family, ASSET_CODE, side_code, VARIANT, digit_value)
                key = (target.outer_index, target.chunk_index, target.resource_name)
                require(key in lookup,
                        f"live digit is absent from all-TXTR inventory: {key}")
                row = lookup[key]
                payload, rgba = authenticated_png_from_inventory(
                    row, (width, height), None)
                relative = (
                    f"EDIT_THESE/{side_name}/03_LIVE_DIGITS/{folder}/"
                    f"digit_{digit_value}.png"
                )
                edit = {
                    "asset_code": ASSET_CODE,
                    "digit": digit_value,
                    "family": public_family,
                    "kind": "live_number_nameplate",
                    "png": relative,
                    "side": side_code,
                    "variant": VARIANT,
                }
                storage = {
                    "chunk_index": target.chunk_index,
                    "format": target.format_name,
                    "logical_name": target.logical_name,
                    "mip_levels": target.mip_levels,
                    "outer_id": f"0x{target.outer_id:08x}",
                    "outer_index": target.outer_index,
                    "resource_name": target.resource_name,
                    "span_sha256": target.span_sha256,
                    "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
                }
                builder.add_png(
                    relative, payload, rgba, width, height, "editable", side_name,
                    f"{public_family}_digit_{digit_value}", target.selector,
                    storage, edit,
                )

        # One vertical alphabet/nameplate atlas per side.
        _, _, target = live_art_targets.select_target(
            "nameplate", ASSET_CODE, side_code, VARIANT, None)
        key = (target.outer_index, target.chunk_index, target.resource_name)
        require(key in lookup, f"nameplate is absent from all-TXTR inventory: {key}")
        row = lookup[key]
        payload, rgba = authenticated_png_from_inventory(row, (1024, 32), None)
        relative = f"EDIT_THESE/{side_name}/04_NAMEPLATE/nameplate_atlas.png"
        edit = {
            "asset_code": ASSET_CODE,
            "digit": None,
            "family": "nameplate",
            "kind": "live_number_nameplate",
            "png": relative,
            "side": side_code,
            "variant": VARIANT,
        }
        storage = {
            "chunk_index": target.chunk_index,
            "format": target.format_name,
            "logical_name": target.logical_name,
            "mip_levels": target.mip_levels,
            "outer_id": f"0x{target.outer_id:08x}",
            "outer_index": target.outer_index,
            "resource_name": target.resource_name,
            "span_sha256": target.span_sha256,
            "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
        }
        builder.add_png(relative, payload, rgba, 1024, 32, "editable", side_name,
                        "nameplate_atlas", target.selector, storage, edit)

        # Menu-only uniform card and both independent helmet-card resolutions.
        for family, resolution, file_name in (
            ("unif", 256, "uniform_card_256.png"),
            ("helm", 256, "helmet_card_256.png"),
            ("helm", 128, "helmet_card_128.png"),
        ):
            _, _, target = card_targets.select_target(
                family, ASSET_CODE, card_side, 0, resolution,
                ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json")
            payload, rgba, row = authenticated_card_png(card_report, target)
            relative = f"EDIT_THESE/{side_name}/05_TEAM_SELECT/{file_name}"
            edit = {
                "asset_code": ASSET_CODE,
                "family": family,
                "kind": "team_select",
                "png": relative,
                "resolution": resolution,
                "side": card_side,
                "style": 0,
            }
            storage = {
                "chunk_index": target.chunk_index,
                "format": "P8",
                "mip_levels": 1,
                "outer_id": f"0x{target.outer_id:08x}",
                "outer_index": target.outer_index,
                "resource_name": target.name,
                "span_sha256": target.span_sha256,
                "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
                "runtime_note": (
                    "256 class has prior ownership proof" if resolution == 256 else
                    "exact visible consumer/timing remains unresolved"
                ),
                "retail_png_path": row["retail_png_path"],
            }
            builder.add_png(relative, payload, rgba, resolution, resolution,
                            "editable", side_name, f"team_select_{family}_{resolution}",
                            target.selector, storage, edit)


def export_bundle(source_xiso: Path, output: Path) -> dict[str, Any]:
    require(not output.exists() and not output.is_symlink(),
            f"output bundle already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    source = verify_source(source_xiso)
    reports = report_manifest()
    temporary = Path(tempfile.mkdtemp(
        prefix=f".{output.name}.tmp-", dir=str(output.parent)))
    try:
        builder = BundleBuilder(temporary, source, reports)
        tset_exports(builder)
        standalone_exports(builder)
        builder.finish()
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "bundle": str(output.resolve()),
        "editable_pngs": 78,
        "reference_pngs": 6,
        "schema": SCHEMA,
        "source_sha256": SOURCE_SHA256,
        "total_pngs": 84,
    }


def verify_bundle(source_xiso: Path, bundle: Path,
                  expect_baseline: bool) -> dict[str, Any]:
    source = verify_source(source_xiso)
    reports = report_manifest()
    manifest_path = bundle / "bundle-manifest.json"
    regular_file(manifest_path, "bundle manifest")
    manifest_payload = manifest_path.read_bytes()
    manifest = load_json(manifest_payload, "bundle manifest")
    require(manifest_payload == canonical_json(manifest),
            "bundle manifest is not canonical JSON")
    require(set(manifest) == {
        "counts", "images", "known_exact_rgba_aliases", "legal", "provider",
        "reports", "schema", "source_xiso", "team", "warnings",
    } and manifest.get("schema") == SCHEMA, "bundle manifest schema mismatch")
    require(manifest.get("source_xiso") == source,
            "bundle/source XISO pin mismatch")
    require(manifest.get("reports") == reports, "bundle report pins changed")
    rows = manifest.get("images")
    require(isinstance(rows, list) and len(rows) == 84,
            "bundle manifest must describe exactly 84 PNGs")
    require(len({row["path"] for row in rows}) == 84,
            "bundle manifest contains duplicate PNG paths")
    pixel_changed: list[str] = []
    pixel_unchanged: list[str] = []
    byte_exact: list[str] = []
    reencoded_pixel_identical: list[str] = []
    for row in rows:
        relative = str(row["path"])
        require(not relative.startswith("/") and ".." not in Path(relative).parts,
                f"unsafe manifest PNG path: {relative}")
        path = bundle / relative
        regular_file(path, f"bundle PNG {relative}")
        payload = path.read_bytes()
        dimensions = row["dimensions"]
        width = int(dimensions["width"])
        height = int(dimensions["height"])
        _, _, rgba = strict_png(payload, (width, height))
        png_sha256 = digest(payload)
        rgba_sha256 = digest(rgba)
        if rgba_sha256 == row["baseline_rgba_sha256"]:
            pixel_unchanged.append(relative)
            if png_sha256 == row["baseline_png_sha256"]:
                byte_exact.append(relative)
            else:
                reencoded_pixel_identical.append(relative)
        else:
            pixel_changed.append(relative)
    if expect_baseline:
        require(not pixel_changed,
                f"expected pristine baseline; pixel-changed PNGs: {pixel_changed}")
        require(not reencoded_pixel_identical,
                "expected byte-exact baseline; pixel-identical PNGs were re-encoded: "
                f"{reencoded_pixel_identical}")

    edit_map_path = bundle / "provider-edit-map.json"
    regular_file(edit_map_path, "provider edit map")
    edit_map_payload = edit_map_path.read_bytes()
    edit_map = load_json(edit_map_payload, "provider edit map")
    entries = edit_map.get("entries")
    require(edit_map_payload == canonical_json(edit_map),
            "provider edit map is not canonical JSON")
    require(set(edit_map) == {
        "changed_only_rule", "entries", "future_project_schema", "mud_policy",
        "provider", "purpose", "schema",
    } and edit_map.get("schema") == EDIT_MAP_SCHEMA and
            isinstance(entries, list) and len(entries) == 78,
            "provider edit map schema/count mismatch")
    require(len({entry["selector"] for entry in entries}) == 78,
            "provider edit map contains duplicate selectors")
    manifest_editable = {row["path"] for row in rows if row["role"] == "editable"}
    require({entry["path"] for entry in entries} == manifest_editable and
            len(manifest_editable) == 78,
            "provider edit map and editable PNG ledger disagree")

    image_by_path = {row["path"]: row for row in rows}
    for order, entry in enumerate(entries):
        row = image_by_path[entry["path"]]
        require(entry["baseline_png_sha256"] == row["baseline_png_sha256"] and
                entry["baseline_rgba_sha256"] == row["baseline_rgba_sha256"] and
                entry["dimensions"] == row["dimensions"] and
                entry["selector"] == row["selector"],
                f"provider edit map/manifest ledger mismatch: {entry['path']}")
        edit = visual_provider.validate_edit_shape(entry["edit"], order)
        input_field = "clean_png" if edit["kind"] in {"torso", "sleeve", "pants"} \
            else "png"
        require(edit[input_field] == entry["path"],
                f"provider edit input path mismatch: {entry['path']}")

        kind = edit["kind"]
        if kind == "torso":
            _, _, _, target = jersey_targets.select_target(
                edit["asset_code"], edit["side"], edit["variant"])
            expected_selector = f"{target.selector}:torso:clean"
        elif kind == "sleeve":
            _, _, _, target = sleeve_targets.select_target(
                edit["asset_code"], edit["side"], edit["variant"])
            expected_selector = f"{target.selector}:sleeve:clean"
        elif kind == "pants":
            _, _, _, target = pants_targets.select_target(
                edit["asset_code"], edit["side"], edit["variant"])
            expected_selector = f"{target.selector}:pants:clean"
        elif kind == "live_helmet":
            _, _, _, target = helmet_targets.select_target(
                edit["asset_code"], edit["side"], edit["variant"], edit["family"])
            expected_selector = f"{target.logical_name[:-4]}:{target.family}"
        elif kind == "live_number_nameplate":
            _, _, target = live_art_targets.select_target(
                edit["family"], edit["asset_code"], edit["side"],
                edit["variant"], edit["digit"])
            expected_selector = target.selector
        elif kind == "team_select":
            _, _, target = card_targets.select_target(
                edit["family"], edit["asset_code"], edit["side"],
                edit["style"], edit["resolution"],
                ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json")
            expected_selector = target.selector
        else:
            raise BundleError(f"unexpected Giants edit kind: {kind}")
        storage = row["storage"]
        require(entry["selector"] == expected_selector and
                storage["outer_index"] == target.outer_index and
                storage["chunk_index"] == target.chunk_index and
                storage["span_sha256"] == target.span_sha256 and
                storage["xiso_absolute_span_offset"] ==
                target.xiso_absolute_span_offset,
                f"provider target re-selection mismatch: {entry['selector']}")

    baseline_checksum_files = 0
    if expect_baseline:
        sums_path = bundle / "BASELINE_SHA256SUMS.txt"
        regular_file(sums_path, "baseline checksum ledger")
        sums_payload = sums_path.read_text(encoding="utf-8")
        checksum_rows: dict[str, str] = {}
        for line in sums_payload.splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            require(match is not None, "invalid baseline checksum ledger line")
            checksum, relative = match.groups()
            require(relative not in checksum_rows and not relative.startswith("/") and
                    ".." not in Path(relative).parts,
                    f"unsafe/duplicate baseline checksum path: {relative}")
            checksum_rows[relative] = checksum
        actual_paths = {
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file() and path != sums_path
        }
        require(set(checksum_rows) == actual_paths,
                "baseline checksum ledger file set mismatch")
        for relative, expected in checksum_rows.items():
            require(file_digest(bundle / relative) == expected,
                    f"baseline checksum mismatch: {relative}")
        baseline_checksum_files = len(checksum_rows)

    return {
        "byte_exact_baseline_pngs": len(byte_exact),
        "bundle": str(bundle.resolve()),
        "baseline_checksum_files": baseline_checksum_files,
        "editable_pngs": len(manifest_editable),
        "expect_baseline": expect_baseline,
        "pixel_changed_pngs": len(pixel_changed),
        "pixel_unchanged_pngs": len(pixel_unchanged),
        "reference_pngs": len(rows) - len(manifest_editable),
        "reencoded_but_pixel_identical_pngs": len(reencoded_pixel_identical),
        "reports_reauthenticated": len(reports),
        "provider_targets_reselected": len(entries),
        "schema": VERIFY_SCHEMA,
        "source_sha256": source["sha256"],
        "strict_pngs_passed": len(rows),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="create the private bundle")
    export_parser.add_argument("--source-xiso", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify", help="strictly verify a bundle")
    verify_parser.add_argument("--source-xiso", type=Path, required=True)
    verify_parser.add_argument("--bundle", type=Path, required=True)
    verify_parser.add_argument(
        "--expect-baseline", action="store_true",
        help="also require all PNG byte hashes to match the original export",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "export":
            result = export_bundle(args.source_xiso, args.output)
        else:
            result = verify_bundle(
                args.source_xiso, args.bundle, bool(args.expect_baseline))
    except (BundleError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(canonical_json(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
