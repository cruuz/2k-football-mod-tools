#!/usr/bin/env python3
"""Refuse undeclared, retail-derived, binary, or local-workspace release files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Iterable
import xml.etree.ElementTree as ET


MAX_RELEASE_FILE_BYTES = 8 * 1024 * 1024

PRIVATE_BOUNDARY = "packaging/b76_private_paths.json"
PRIVATE_BOUNDARY_SHA256 = "32d92f4a0fa03facfbfbab146b1feef36bf911b7680ee4936f6a96ce231e02c1"


def _private_boundary():
    data = (Path(__file__).resolve().parents[1] / PRIVATE_BOUNDARY).read_bytes()
    if hashlib.sha256(data).hexdigest() != PRIVATE_BOUNDARY_SHA256:
        raise ReleaseCheckError("private marks boundary hash changed")
    doc = json.loads(data)
    return set(doc["paths"]), set(doc["blobs"].values())

# Product target catalogs are decoded metadata: selectors, dimensions, hashes,
# offsets, ownership labels, and constraints. They contain no compressed game
# spans, decoded pixels, audio, or other retail payload. ``reports/`` remains a
# forbidden root except for these exact size/hash/schema-pinned files.  The
# compact Crib catalog and sanitized product-inspection snapshots live with
# product data instead of ``reports/``, but are held to the same immutable
# contract so a release cannot silently acquire retail payloads.
REVIEWED_METADATA: dict[str, tuple[int, str, str | int]] = {
    # Source-labelled historic player facts and derived ratings, no game payload.
    "data/nfl2k5_historic_rosters/manifest.json": (
        29_855_432,
        "7d68eb7c7798c28c839114d180701d6942d875b0d8f271dc3ea668f699b662db",
        "nfl2k5_historic_rosters/v1",
    ),
    # Bounded music routing evidence: names, addresses and hashes only. The
    # all_modes_proved field explicitly excludes audible/gameplay certification.
    "reports/music_playlist_contexts.v1.json": (
        24_799,
        "327d8e73f276005d2f65bbe84b4df7c914fd9cbbf7f5a94552e09660a6e8222f",
        1,
    ),
    "reports/guardian_cap_receipt.v1.json": (
        20_105,
        "195ec69360c95520b44cfaa4af591bc25c297658d906c77da36392a0be46ea99",
        "nfl2k5_guardian_cap/v1",
    ),
    "reports/assets/menu_state_trace.json": (
        39_938,
        "ecd93117a3a808a16697c23ae10e3225953bcb4dabda30afabdc5c02911974f1",
        "vc_menu_state_trace/v1",
    ),
    "reports/assets/nfl_main_menu_live_state.json": (
        18_483,
        "a5d4b64962fefb2e5dbee4768d120172c0642405df2a0137759e2bce3737b89a",
        "nfl2k5_main_menu_live_state/v1",
    ),
    "reports/assets/nfl2k5_p8_texture_inventory.json": (
        8_338_553,
        "01b030e9f7b58786a76ba23a66d59a485024e7001656b03d595991aec0c8cf3f",
        "nfl2k5_p8_texture_inventory/v1",
    ),
    "reports/assets/nfl2k5_jersey_tset_compatibility.json": (
        2_155_779,
        "046d03546242c11478d39b48d7f6f80b5f2009c85641b5c81abdaa6f8171cacd",
        "nfl2k5_jersey_tset_compatibility/v1",
    ),
    "reports/assets/nfl2k5_sleeve_tset_compatibility.json": (
        2_244_430,
        "72a25d908135322a6c15c1f19f2f575224ab224c8b8c4c6969f5b4ba2359ae2b",
        "nfl2k5_sleeve_tset_compatibility/v1",
    ),
    "reports/assets/nfl2k5_pants_tset_compatibility.json": (
        2_329_500,
        "cab15d4f03c69f5143edd40f567ec038d2425bba80bf9dd1a85b642e144ac1ac",
        "nfl2k5_pants_tset_compatibility/v1",
    ),
    "reports/assets/nfl2k5_live_helmet_txtr_compatibility.json": (
        2_572_552,
        "1b7bdbb67a28b9d70531c3af80ff67574a7d60ef421bcf42ba9422f0f278e6ff",
        "nfl2k5_live_helmet_txtr_compatibility/v1",
    ),
    "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json": (
        63_407_409,
        "d122c1e7de4fbad42c725969dce3473fc16a100e75d68ae5fb5d64077f536cd4",
        "nfl2k5_live_numbers_nameplate_compatibility/v1",
    ),
    "reports/assets/nfl2k5_team_select_card_inventory.json": (
        4_855_883,
        "3a1d3543afbf851331389228bc910ba453d749c04f7cf12f6471ba0cde64bf13",
        "nfl2k5_team_select_card_inventory/v1",
    ),
    "reports/assets/nfl2k5_player_portrait_compatibility.json": (
        9_446_076,
        "c0f792df4aa03a9a0c4e670c7b214da53a97f19526c84fd52765137120713481",
        "nfl2k5_player_portrait_compatibility/v1",
    ),
    "reports/assets/nfl2k5_live_face_texture_compatibility.json": (
        5_188_081,
        "812db90df6b50b4491d8701a0ceb13b54a26ea7afadc2fbd86c4715b15aa9e09",
        "nfl2k5_live_face_texture_compatibility/v1",
    ),
    "reports/assets/nfl2k5_create_team_field_art_inventory.json": (
        1_870_444,
        "6014d0ca882c76f0bba68a14338e357d7f33a745e9818856c57da7979ed1a4f5",
        "nfl2k5_create_team_field_art_inventory/v1",
    ),
    "reports/assets/scorebug_presentation_audit.json": (
        46_512,
        "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1",
        "vc_scorebug_presentation_audit/v1",
    ),
    "reports/assets/nfl2k5_audo_import_capacity.json": (
        3_759_183,
        "1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556",
        "nfl2k5_audo_import_capacity/v1",
    ),
    "reports/assets/nfl2k5_audo_family_labels.json": (
        72_257,
        "ea66da8ea539114563de5694599a6046bde78661556846a34f8addeb31d544dd",
        "nfl2k5_audo_family_labels/v2",
    ),
    "reports/assets/uniform_texture_sharing.v2.json": (
        415_528,
        "992ea79c46c98fe218712540d0fb3159685eee2de67edb01b1659f1897d51c88",
        "uniform_texture_sharing_audit/v2",
    ),
    "mod_editor/data/nfl2k5_crib_catalog.v1.json": (
        735_928,
        "c78801144df2f070e003ba458c5affa15a52cc00221cc1a3d9983f1fbf172cd8",
        "2k5_mod_studio_crib_catalog/v1",
    ),
    "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json": (
        5_851_450,
        "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173",
        "nfl2k5_uniform_equipment_export_catalog/v1",
    ),
    "reports/specs/nfl2k5_crib_static_position_targets.v1.json": (
        14_024,
        "90f955166c8582f7041bd0d936bacbef1f44b3869487f71535acec1caeb44b4f",
        "nfl2k5_crib_static_position_targets/v1",
    ),
    "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json": (
        858_600,
        "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
        "nfl2k5_stadium_static_target_catalog/v1",
    ),
    "mod_editor/data/nfl2k5_gameplay_inspection.v1.json": (
        22_874,
        "19ad4f892c3ddd4d534b6778dab5c6b2e4545ae5ba4832b15dd046e2f7c8116e",
        "nfl2k5_mod_studio_gameplay_inspection/v1",
    ),
    "mod_editor/data/nfl2k5_main_menu_inspection.v1.json": (
        3_563,
        "fae27305eada0ac1200896f0b907307e20942d2cf4506b2ff172c22ceb767629",
        "mod_editor_named_main_menu_inspector/v1",
    ),
}

# This 55 MiB inventory is reproducibly generated in the user's private cache
# from their selected XISO. It is deliberately not a release metadata input.
PRIVATE_INVENTORY_PATH = "reports/assets/nfl2k5_resource_chunks_v2.json"
PRIVATE_INVENTORY_SHA256 = (
    "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
)
PRIVATE_AUDIO_ORIGIN_SCHEMAS = frozenset({
    "2k5_mod_studio_audio_source_pcm_fingerprints/v1",
    "2k5_mod_studio_audio_pcm_containment/v1",
    "2k5_mod_studio_audio_pcm_containment/v2",
})
PRIVATE_AUDIO_ORIGIN_NAME_MARKERS = (
    "audio-origin",
    "audio-pcm-containment",
    "audio-source-pcm-fingerprints",
)

# These roots contain local research, extracted retail data, runtime captures,
# or generated outputs. A release-stage tree must never contain them, even if a
# future allowlist accidentally names a file below one.
FORBIDDEN_COMPONENTS = frozenset(
    {
        ".cache",
        ".codex-tmp",
        ".geometry-proof",
        ".git",
        "__pycache__",
        "assets",
        "build",
        "cache",
        "derived",
        "dist",
        "evidence",
        "exports",
        "extracted",
        "fixtures",
        "ghidra_projects",
        "originals",
        "projects",
        "reports",
        "runtime",
    }
)
FORBIDDEN_PREFIXES = ("build-", "vc_53450030")
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".0a",
        ".7z",
        ".arc",
        ".bin",
        ".chd",
        ".cso",
        ".dat",
        ".deb",
        ".dll",
        ".dol",
        ".elf",
        ".exe",
        ".gz",
        ".glb",
        ".gltf",
        ".iff",
        ".img",
        ".iso",
        ".jpg",
        ".jpeg",
        ".ogg",
        ".pak",
        ".png",
        ".qcow2",
        ".rar",
        ".raw",
        ".rom",
        ".rvz",
        ".sav",
        ".so",
        ".tar",
        ".vhd",
        ".vhdx",
        ".wad",
        ".wav",
        ".xbe",
        ".xex",
        ".xex2",
        ".xiso",
        ".xma",
        ".zip",
    }
)
ALLOWED_SUFFIXES = frozenset(
    {
        ".2k5book",   # data/playbooks/*.2k5book: a community playbook recipe -- UTF-8 JSON, zero retail bytes
        ".bat",
        ".cfg",
        ".command",
        ".css",
        ".csv",        # data/nfl2k5_retail_team_history.csv, data/nfl2k5_modern_names.csv (nflverse, CC-BY-4.0; text, reviewed)
        ".desktop",
        ".html",
        ".ini",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".svg",
        ".toml",
        ".txt",
    }
)
# Double-click launchers that must carry the owner-executable bit or they will
# silently fail to start (a macOS .command, a Unix .sh). A Windows .bat is not
# executed through a Unix mode bit, so it is deliberately excluded here.
EXECUTABLE_LAUNCHER_SUFFIXES = frozenset({".command", ".sh"})
ALLOWED_SUFFIXLESS_NAMES = frozenset({"copying", "license", "notice"})

# Renaming a known retail file to a text-looking extension must not bypass the
# path and suffix checks. Hashes are metadata only; none of the payloads ship.
KNOWN_RETAIL_SHA256 = frozenset(
    {
        # NFL 2K5 USA retail XISO.
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
        # NFL 2K5 USA default.xbe.
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        # NFL 2K5 extracted vc_53450030/0 retail archive.
        "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
    }
)
RETAIL_MAGIC = (
    b"MICROSOFT*XBOX*MEDIA",
    b"XBEH",
    b"XEX2",
)

# The one binary asset in this release: the application icon Windows puts on the
# Start Menu shortcut. Icons are the classic hiding place for a payload someone
# renamed, so this file is not merely allowlisted -- it is pinned to an exact
# size and SHA-256 and required to still be a Windows icon image, the same
# treatment the APF release gives its reviewed extractor binaries.
#
# The bytes are original work generated from geometry by tools/make_app_icons.py
# (also in this release), which is deterministic: anyone can re-run it and get
# this exact file back. Update the pin only from that script's --print-pins
# output, never by hand.
ICO_MAGIC = b"\x00\x00\x01\x00"
REVIEWED_ICON = "packaging/icons/2k5-mod-studio.ico"
REVIEWED_ICON_SIZE = 24_127
REVIEWED_ICON_SHA256 = (
    "76fdffd1de77aa7ed53ba87076e995b7443f3cc379981c1241f7c9c108f5a18f"
)

# V10's new pixel art is distributable; retail PNGs remain forbidden. Each
# exception is an exact reviewed path, byte count, hash and PNG dimension.
SCOREBUG_TEMPLATE_PNG_CATALOG = "packaging/nfl2k5_scorebug_template_pngs.json"
SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "b46b11b64be74d2a9e1c71b6f52d22a6b13d0f1ff2cf2dd09d9a15ab48c10ccb"  # b778-sb5 merge: the merged catalog

# Anniversary paint is authored or cropped from publicly sourced references.
# Retail wordmarks/shields/scenes are read from the user's disc at compile time
# and are not included here. This separate, immutable catalog grants no general
# PNG exception, even inside the Anniversary art directory.
ANNIVERSARY_FIELD_PNG_CATALOG = "packaging/nfl2k5_espn25_field_pngs.json"
ANNIVERSARY_FIELD_PNG_CATALOG_SHA256 = "c621d94c4f48f26ab6c44e912dd5d5ff7a36d07042485d12253016a150a6b1ab"

# b772: the 2026 coaches (co1/co2), the 2026 fans (fr1) and the 2025-26 officials (rf1) ship authored PNG art.
# Like the two catalogs above this is an exact, immutable list (path, byte count, SHA-256, PNG dimensions) of files
# reviewed as authored art: no photograph or photo crop and no retail-extracted pixels, except the scanned coach heads
# (b778 cf1-cf4: photo-derived likeness textures, Noah 2026-10-12; see the catalog's classification). It grants no general PNG
# exception inside those folders; tools/b77/modern_art_png_catalog.py regenerates it and prints the digest below.
MODERN_ART_PNG_CATALOG = "packaging/nfl2k5_modern_art_pngs.json"
MODERN_ART_PNG_CATALOG_SHA256 = "df2fdee961dda47bd66c6564b0c90a95d585cc0931b426665333cfc1cb39242b"  # b81-seamen: the documents this branch changed (classic.json, kits.json, the moment kit pins, the classic relief, the s48 walls), re-pinned by texel_rows.py and the catalog tool; b81 integration (merge of #11 onto the later merges): the documents those merges changed (the reservation inventory) re-pinned by texel_rows.py and the catalog tool; b81-retail-free-art round 3 + round 2 (R2-G): the texel data of every data document is listed (glyph paint, kit-fix runs and texels); b81-retail-free-art round 3: no layout mask ships (146 relief files), the reviewed paint of the glyph document is listed; b81-retail-free-art: + the 2026 relief as differences (147 files: no retail-derived map) and the 387 b81u glyph pictures drawn new or edited from project art (the 231 retail-derived ones ship as build-time operations or as the texels that differ from the build's glyph); b780 pillowfont: + the scorebug digit glyph layer (939 files); b780-rst2: + 121 more real portraits (faces_03 filled, a fifth atlas pair faces_04: the 119 players the 11/03 refresh creates, Thorson and Masses); b780-b9: + 49 more real portraits in faces_03 (the no-photo players the pt1 target list missed); b779-int1: rf3 + pt1 regenerated together (936 files); b779-pt1: + the 8 real free-agent portrait atlases; b779-rf3: + new rookie face atlases (faces_14..16); b778 cf5: seven scanned coach heads (ARI BUF DEN HOU LV NO SEA); b778 3d1: classification names the scanned heads as photo-derived; b778-pg2: + the TROPHY ROOM emblem; b778-ee1: + the 4 gray alien PNGs; b778-ss1: + the 15 Seamen card/field/face PNGs; b778-rh1/rh2: + the 18 rookie face bank atlases; b778 cf1: four scanned coach heads; b778 cf2: seven scanned coach heads and the PIT rescan; b778 cf3: seven scanned coach heads; b778 cf4: seven scanned coach heads, KC head.png in place of head_mask + head_overlay; b778 cm2: six coach heads and apparel; b776-int2: + fn2 four Titans 7 digits; b775-int1: sb1 marks + hs1 nine hair textures

# sb3: Noah (2026-10-28) cleared real logos for this free fan mod, so his real Super Bowl event logos, network marks
# and team-season logos ship as the bundled default. This is a separate exact catalog, not an authored-art exception:
# the files are real brand and club marks copied from his Desktop user_art folder, and SOURCES.txt lists every source.
SUPER_BOWL_LOGO_PNG_CATALOG = "packaging/nfl2k5_super_bowl_logo_pngs.json"
SUPER_BOWL_LOGO_PNG_CATALOG_SHA256 = "e8838ef6a2f48cd830664534fb4943231e7e05f159a899abe72d21c6b50f6eb6"


def _scorebug_template_pngs(root: Path) -> dict:
    catalog = root / SCOREBUG_TEMPLATE_PNG_CATALOG
    if not catalog.exists():
        return {}
    with catalog.open("rb") as stream:
        data = stream.read(256 * 1024 + 1)
    if (len(data) > 256 * 1024
            or hashlib.sha256(data).hexdigest() != SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256):
        raise ReleaseCheckError("reviewed scorebar PNG catalog hash changed")
    document = json.loads(data)
    if document.get("schema") != "nfl2k5_scorebug_template_pngs/v1":
        raise ReleaseCheckError("reviewed scorebar PNG catalog schema changed")
    return document["files"]


def _validate_scorebug_template_png(path: Path, relative: str, info, contract: dict) -> None:
    _validate_reviewed_png(path, relative, info, contract, "scorebar")


def _anniversary_field_pngs(root: Path) -> dict:
    catalog = root / ANNIVERSARY_FIELD_PNG_CATALOG
    if not catalog.exists():
        return {}
    with catalog.open("rb") as stream:
        data = stream.read(128 * 1024 + 1)
    if (len(data) > 128 * 1024
            or hashlib.sha256(data).hexdigest() != ANNIVERSARY_FIELD_PNG_CATALOG_SHA256):
        raise ReleaseCheckError("reviewed Anniversary PNG catalog hash changed")
    document = json.loads(data)
    if document.get("schema") != "nfl2k5_espn25_field_pngs/v1":
        raise ReleaseCheckError("reviewed Anniversary PNG catalog schema changed")
    return document["files"]


def _modern_art_pngs(root: Path) -> dict:
    catalog = root / MODERN_ART_PNG_CATALOG
    if not catalog.exists():
        return {}
    with catalog.open("rb") as stream:
        data = stream.read(512 * 1024 + 1)
    if (len(data) > 512 * 1024
            or hashlib.sha256(data).hexdigest() != MODERN_ART_PNG_CATALOG_SHA256):
        raise ReleaseCheckError("reviewed modern-art PNG catalog hash changed")
    document = json.loads(data)
    if document.get("schema") != "nfl2k5_modern_art_pngs/v1":
        raise ReleaseCheckError("reviewed modern-art PNG catalog schema changed")
    return document["files"]


def _reviewed_paint(root: Path) -> dict:
    """b81-retail-free-art (review F5): the reviewed texel data of the data documents, from the pinned modern-art
    catalog (read and hash-checked the same way as its PNG list)."""
    catalog = root / MODERN_ART_PNG_CATALOG
    if not catalog.exists():
        return {}
    with catalog.open("rb") as stream:
        data = stream.read(512 * 1024 + 1)
    if len(data) > 512 * 1024 or hashlib.sha256(data).hexdigest() != MODERN_ART_PNG_CATALOG_SHA256:
        raise ReleaseCheckError("reviewed modern-art PNG catalog hash changed")
    return json.loads(data).get("paint", {})


_TEXEL_OPS = {"paint": "runs", "runs": "rows", "texels": "points"}
# b81-retail-free-art (fix 1, the reviewer's injections): position-bearing primitives below a minimum are texel data too
SMALL = 16                                   # texels: a box or a polygon under this is a position list
SMALL_BOX_EDGE_LIMIT = 0.25
_DATA_KEY = re.compile(r"^(?:[0-9]+|[0-9A-Z]{2,5}:[0-9A-Za-z_:.\-]+|(?:retail|logo):[0-9A-Za-z_:.\-]+|[A-Z]{2,4}(?:_[0-9A-Za-z_]+)?"
                       r"|[0-9a-f]{64})$")


def _is_box(value) -> bool:
    """Four numbers, end-exclusive and non-empty. Non-integer coordinates count too (fix 1, the re-check's A14): the
    build refuses them, but the bytes would ship."""
    return (isinstance(value, list) and len(value) == 4
            and all(type(v) in (int, float) and v == v and abs(v) != float("inf") for v in value)
            and value[2] > value[0] and value[3] > value[1])


def _box_area(box) -> int:
    return (box[2] - box[0]) * (box[3] - box[1])


def _poly_area(points) -> float:
    pts = [(float(p[0]), float(p[1])) for p in points if isinstance(p, (list, tuple)) and len(p) == 2]
    if len(pts) < 3:
        return 0.0
    return abs(sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1]
                   for k in range(len(pts)))) / 2.0


def _boxes_in(value, key=None):
    """(key, box) for every box anywhere inside an operation (a list of four ints, end-exclusive and non-empty)."""
    if _is_box(value):
        yield key, value
    elif isinstance(value, list):
        for item in value:
            yield from _boxes_in(item, key)
    elif isinstance(value, dict):
        for k, item in value.items():
            yield from _boxes_in(item, k)


def _op_texels(op: dict) -> int:
    """Texel data an operation holds (0: none): texel runs and lists, glyph keep runs, warp masks, boxes and polygons
    under SMALL texels, every box of a clear whose threshold is below 0."""
    kind = op.get("op")
    key = _TEXEL_OPS.get(kind)
    if key is not None and key in op:
        if kind == "texels":
            return len(op[key])
        width = 8 if kind == "paint" else 6
        return sum(len(r[2]) // width if isinstance(r, list) and len(r) == 3 and isinstance(r[2], str) else 1
                   for r in op[key])
    total = 0
    if kind == "keep" and isinstance(op.get("runs"), list):          # glyph keep runs: [y, x0, count]
        total += sum(int(r[2]) if isinstance(r, list) and len(r) == 3 and type(r[2]) is int else 1 for r in op["runs"])
    if kind == "warp" and isinstance(op.get("mask"), list):          # warp masks: [y, x0, x1] at the warp's scale
        total += sum(max(int(r[2]) - int(r[1]), 1) if isinstance(r, list) and len(r) == 3 else 1 for r in op["mask"])
    if kind == "clear" and isinstance(op.get("above", 0), (int, float)) and op.get("above", 0) < 0:
        total += sum(max(1, int(_box_area(b) + 0.999)) for _k, b in _boxes_in(op.get("boxes", [])))
    else:
        total += sum(max(1, int(_box_area(b) + 0.999)) for _k, b in _boxes_in(op) if _box_area(b) < SMALL)
    if kind == "poly" and isinstance(op.get("points"), list) and _poly_area(op["points"]) < SMALL:
        total += max(1, int(_poly_area(op["points"]) + 0.999))
    if kind == "multipoly" and isinstance(op.get("polys"), list):
        total += sum(max(1, int(_poly_area(p) + 0.999)) for p in op["polys"]
                     if isinstance(p, list) and _poly_area(p) < SMALL)
    return total


def _texel_rows(document: object) -> dict:
    """Every operation that stores texel data (see _op_texels) anywhere inside a JSON value, grouped by the row that
    holds it ("<selector>:<chunk>:<kind>", "-" outside a row)."""
    out: dict = {}
    pending = [(document, "-")]
    while pending:
        value, owner = pending.pop()
        if isinstance(value, dict):
            if isinstance(value.get("op"), str) and _op_texels(value):
                out.setdefault(owner, []).append(value)
                continue
            if "selector" in value and "chunk" in value:
                owner = f"{value['selector']}:{value['chunk']}:{value.get('kind', '')}"
            pending.extend((item, owner) for item in reversed(list(value.values())))
        elif isinstance(value, list):
            pending.extend((item, owner) for item in reversed(value))
    return out


def _one_texel_painting_boxes(ops) -> int:
    """Painting boxes of one texel (keep-outs paint nothing and are measured instead)."""
    return sum(1 for op in ops for key, box in _boxes_in(op) if key != "keep" and _box_area(box) <= 1)


def _holds_operations(document) -> bool:
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if isinstance(value.get("op"), str):
                return True
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


# keys of texture pins, shapes and texel data: a document holding any of them edits textures (with or without `op`)
_TEXTURE_KEYS = frozenset({"after_sha256", "before_sha256", "boxes", "derive", "ints", "map", "mask", "nodes", "pixels",
                           "points", "polys", "relayout", "runs", "texels"})


def _edits_textures(document) -> bool:
    """b81-retail-free-art (fix 1 of the re-check): a document that holds operations, texture pins, shapes or texel data.
    The release check pins every such data document by its whole SHA-256."""
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if isinstance(value.get("op"), str) or not _TEXTURE_KEYS.isdisjoint(value):
                return True
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return False


def _shape(document) -> set:
    """The key paths of a document (see tools/b81_uniforms/gate_shapes.py)."""
    out = set()
    pending = [(document, "")]
    while pending:
        value, path = pending.pop()
        if isinstance(value, dict):
            if isinstance(value.get("op"), str):
                tag = value["op"] + (":" + str(value.get("module")) if value["op"] == "rule" else "")
                path = path + "{" + tag + "}"
            variable = bool(value) and all(isinstance(k, str) and _DATA_KEY.match(k) for k in value) and "op" not in value
            for k, item in value.items():
                child = path + "." + ("*" if variable else str(k))
                out.add(child)
                pending.append((item, child))
        elif isinstance(value, list):
            for item in value:
                pending.append((item, path + "[]"))
    return out


def _check_shape(relative: str, document) -> None:
    """b81-retail-free-art (fix 1): a data document that holds operations may use only the operations and keys its
    schema's reviewed shape holds (DOCUMENT_SHAPES); anything else could carry pixel data past the paint check."""
    if not _holds_operations(document):
        return
    schema = document.get("schema") if isinstance(document, dict) else None
    allowed = DOCUMENT_SHAPES.get(schema)
    if allowed is None:
        raise ReleaseCheckError(f"a data document with operations has no reviewed shape: {relative}")
    unknown = sorted(_shape(document) - allowed)
    if unknown:
        shown = ", ".join(unknown[:4]) + (f" and {len(unknown) - 4} more" if len(unknown) > 4 else "")
        raise ReleaseCheckError(f"unknown operation or key in a data document: {relative}: {shown}")


DOCUMENT_SHAPES = {   # generated by tools/b81_uniforms/gate_shapes.py: do not edit by hand
    'nfl2k5_glyph_fixes_2026/v1': frozenset((
        '.art',
        '.names_purpose',
        '.names_references',
        '.names_references.*',
        '.purpose',
        '.references',
        '.references.*',
        '.schema',
        '.textures',
        '.textures[].after_sha256',
        '.textures[].before_sha256',
        '.textures[].chunk',
        '.textures[].defects',
        '.textures[].derive',
        '.textures[].derive[]{clear_rgb}.colour',
        '.textures[].derive[]{clear_rgb}.op',
        '.textures[].derive[]{edge}.edge',
        '.textures[].derive[]{edge}.fill',
        '.textures[].derive[]{edge}.keep',
        '.textures[].derive[]{edge}.op',
        '.textures[].derive[]{embolden}.extra',
        '.textures[].derive[]{embolden}.fill',
        '.textures[].derive[]{embolden}.k',
        '.textures[].derive[]{embolden}.op',
        '.textures[].derive[]{embolden}.outline',
        '.textures[].derive[]{embolden}.ring',
        '.textures[].derive[]{inline_dark}.colour',
        '.textures[].derive[]{inline_dark}.op',
        '.textures[].derive[]{inline_fill}.colour',
        '.textures[].derive[]{inline_fill}.fill',
        '.textures[].derive[]{inline_fill}.op',
        '.textures[].derive[]{keep}.op',
        '.textures[].derive[]{keep}.runs',
        '.textures[].derive[]{paint}.op',
        '.textures[].derive[]{paint}.runs',
        '.textures[].derive[]{recolour}.hidden',
        '.textures[].derive[]{recolour}.op',
        '.textures[].derive[]{recolour}.pairs',
        '.textures[].derive[]{remap}.cols',
        '.textures[].derive[]{remap}.op',
        '.textures[].derive[]{remap}.rows',
        '.textures[].derive[]{thin_letters}.bar',
        '.textures[].derive[]{thin_letters}.cap',
        '.textures[].derive[]{thin_letters}.fill',
        '.textures[].derive[]{thin_letters}.offsets',
        '.textures[].derive[]{thin_letters}.op',
        '.textures[].derive[]{thin_letters}.stem',
        '.textures[].derive[]{thin_letters}.top',
        '.textures[].derive[]{thin_letters}.weights',
        '.textures[].derive[]{thin_letters}.weights.K',
        '.textures[].derive[]{thin_letters}.weights.M',
        '.textures[].derive[]{thin_letters}.weights.N',
        '.textures[].derive[]{thin_letters}.weights.W',
        '.textures[].derive[]{thin_letters}.weights.X',
        '.textures[].derive[]{thin_letters}.weights.Y',
        '.textures[].derive[]{thin_letters}.weights.Z',
        '.textures[].kind',
        '.textures[].length',
        '.textures[].note',
        '.textures[].offset',
        '.textures[].png',
        '.textures[].png_sha256',
        '.textures[].reference',
        '.textures[].resource_size',
        '.textures[].rgba_sha256',
        '.textures[].selector',
        '.textures[].texture',
        '.textures[].widths',
    )),
    'nfl2k5_kit_fixes_2026/v1': frozenset((
        '.base_disc_sha256',
        '.method',
        '.output_disc_sha256',
        '.schema',
        '.source',
        '.textures',
        '.textures[].after_equivalent_sha256',
        '.textures[].after_sha256',
        '.textures[].also',
        '.textures[].also[].after_sha256',
        '.textures[].also[].before_sha256',
        '.textures[].before_sha256',
        '.textures[].chunk',
        '.textures[].defects',
        '.textures[].donor_chunk',
        '.textures[].donor_selector',
        '.textures[].donor_sha256',
        '.textures[].donor_texture',
        '.textures[].donors',
        '.textures[].donors.*',
        '.textures[].equivalent_note',
        '.textures[].fields',
        '.textures[].fields.facemask',
        '.textures[].folded_twin_entries',
        '.textures[].ints',
        '.textures[].ints.helmet_number_route',
        '.textures[].ints.number_route',
        '.textures[].kind',
        '.textures[].length',
        '.textures[].map',
        '.textures[].map[].alpha_min',
        '.textures[].map[].from',
        '.textures[].map[].to',
        '.textures[].map[].tolerance',
        '.textures[].max_blend_slots',
        '.textures[].mip',
        '.textures[].note',
        '.textures[].offset',
        '.textures[].ops',
        '.textures[].ops[]{clear}.above',
        '.textures[].ops[]{clear}.alpha',
        '.textures[].ops[]{clear}.boxes',
        '.textures[].ops[]{clear}.grow',
        '.textures[].ops[]{clear}.keep',
        '.textures[].ops[]{clear}.op',
        '.textures[].ops[]{clear}.to',
        '.textures[].ops[]{close}.box',
        '.textures[].ops[]{close}.color',
        '.textures[].ops[]{close}.colors',
        '.textures[].ops[]{close}.into',
        '.textures[].ops[]{close}.into_tolerance',
        '.textures[].ops[]{close}.op',
        '.textures[].ops[]{close}.radius',
        '.textures[].ops[]{close}.tolerance',
        '.textures[].ops[]{copy}.dst',
        '.textures[].ops[]{copy}.op',
        '.textures[].ops[]{copy}.skip',
        '.textures[].ops[]{copy}.skip_col',
        '.textures[].ops[]{copy}.src',
        '.textures[].ops[]{copy}.tolerance',
        '.textures[].ops[]{enclosed}.box',
        '.textures[].ops[]{enclosed}.color',
        '.textures[].ops[]{enclosed}.edge',
        '.textures[].ops[]{enclosed}.invert',
        '.textures[].ops[]{enclosed}.op',
        '.textures[].ops[]{enclosed}.tolerance',
        '.textures[].ops[]{flood}.box',
        '.textures[].ops[]{flood}.color',
        '.textures[].ops[]{flood}.op',
        '.textures[].ops[]{flood}.seed',
        '.textures[].ops[]{flood}.tolerance',
        '.textures[].ops[]{grow}.box',
        '.textures[].ops[]{grow}.color',
        '.textures[].ops[]{grow}.except',
        '.textures[].ops[]{grow}.from',
        '.textures[].ops[]{grow}.into',
        '.textures[].ops[]{grow}.op',
        '.textures[].ops[]{grow}.radius',
        '.textures[].ops[]{grow}.tolerance',
        '.textures[].ops[]{halo}.box',
        '.textures[].ops[]{halo}.color',
        '.textures[].ops[]{halo}.edge',
        '.textures[].ops[]{halo}.into',
        '.textures[].ops[]{halo}.into_tolerance',
        '.textures[].ops[]{halo}.op',
        '.textures[].ops[]{halo}.radius',
        '.textures[].ops[]{halo}.tolerance',
        '.textures[].ops[]{lift}.box',
        '.textures[].ops[]{lift}.from',
        '.textures[].ops[]{lift}.keep',
        '.textures[].ops[]{lift}.op',
        '.textures[].ops[]{lift}.tolerance',
        '.textures[].ops[]{multipoly}.alpha',
        '.textures[].ops[]{multipoly}.color',
        '.textures[].ops[]{multipoly}.op',
        '.textures[].ops[]{multipoly}.polys',
        '.textures[].ops[]{poly}.alpha',
        '.textures[].ops[]{poly}.color',
        '.textures[].ops[]{poly}.only',
        '.textures[].ops[]{poly}.only_tolerance',
        '.textures[].ops[]{poly}.op',
        '.textures[].ops[]{poly}.points',
        '.textures[].ops[]{poly}.protect',
        '.textures[].ops[]{poly}.protect.box',
        '.textures[].ops[]{poly}.protect.colors',
        '.textures[].ops[]{poly}.protect.tolerance',
        '.textures[].ops[]{recolor}.box',
        '.textures[].ops[]{recolor}.color',
        '.textures[].ops[]{recolor}.from',
        '.textures[].ops[]{recolor}.invert',
        '.textures[].ops[]{recolor}.match',
        '.textures[].ops[]{recolor}.op',
        '.textures[].ops[]{recolor}.tolerance',
        '.textures[].ops[]{retint}.base',
        '.textures[].ops[]{retint}.box',
        '.textures[].ops[]{retint}.color',
        '.textures[].ops[]{retint}.field',
        '.textures[].ops[]{retint}.op',
        '.textures[].ops[]{retint}.source',
        '.textures[].ops[]{retint}.tolerance',
        '.textures[].ops[]{ring}.box',
        '.textures[].ops[]{ring}.color',
        '.textures[].ops[]{ring}.from',
        '.textures[].ops[]{ring}.inside',
        '.textures[].ops[]{ring}.invert',
        '.textures[].ops[]{ring}.op',
        '.textures[].ops[]{ring}.to',
        '.textures[].ops[]{ring}.tolerance',
        '.textures[].ops[]{rule:emblem}.emblem',
        '.textures[].ops[]{rule:emblem}.halves',
        '.textures[].ops[]{rule:emblem}.halves[].flip',
        '.textures[].ops[]{rule:emblem}.halves[].nh',
        '.textures[].ops[]{rule:emblem}.halves[].nw',
        '.textures[].ops[]{rule:emblem}.halves[].rows',
        '.textures[].ops[]{rule:emblem}.module',
        '.textures[].ops[]{rule:emblem}.op',
        '.textures[].ops[]{rule:emblem}.template',
        '.textures[].ops[]{rule:fill}.after',
        '.textures[].ops[]{rule:fill}.after[].box',
        '.textures[].ops[]{rule:fill}.after[].boxes',
        '.textures[].ops[]{rule:fill}.after[].do',
        '.textures[].ops[]{rule:fill}.after[].donor',
        '.textures[].ops[]{rule:fill}.after[].grow',
        '.textures[].ops[]{rule:fill}.after[].height',
        '.textures[].ops[]{rule:fill}.after[].ink',
        '.textures[].ops[]{rule:fill}.after[].logo_file',
        '.textures[].ops[]{rule:fill}.after[].logo_sha256',
        '.textures[].ops[]{rule:fill}.after[].mark_file',
        '.textures[].ops[]{rule:fill}.after[].mark_sha256',
        '.textures[].ops[]{rule:fill}.after[].recipe',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].do',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].logo_file',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].logo_sha256',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs[].h',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs[].ori',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs[].panel',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs[].w',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs[].x0',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.after[].regs[].y0',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.flag',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.flag.from',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.flag.how',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.flag.paint',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.logo',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs[].h',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs[].ori',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs[].panel',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs[].w',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs[].x0',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.foot.regs[].y0',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.hardware',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.kind',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.module',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.old_ink',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.old_ink.panels',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.old_ink.refs',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.old_ink.reviewed',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.op',
        '.textures[].ops[]{rule:fill}.after[].recipe{rule:fill}.vents',
        '.textures[].ops[]{rule:fill}.after[].regs',
        '.textures[].ops[]{rule:fill}.after[].regs[].h',
        '.textures[].ops[]{rule:fill}.after[].regs[].ori',
        '.textures[].ops[]{rule:fill}.after[].regs[].panel',
        '.textures[].ops[]{rule:fill}.after[].regs[].w',
        '.textures[].ops[]{rule:fill}.after[].regs[].x0',
        '.textures[].ops[]{rule:fill}.after[].regs[].y0',
        '.textures[].ops[]{rule:fill}.after[].shift',
        '.textures[].ops[]{rule:fill}.after[].shift.lower',
        '.textures[].ops[]{rule:fill}.after[].shift.upper',
        '.textures[].ops[]{rule:fill}.after[].to_upper',
        '.textures[].ops[]{rule:fill}.alpha',
        '.textures[].ops[]{rule:fill}.boxes',
        '.textures[].ops[]{rule:fill}.boxes.all',
        '.textures[].ops[]{rule:fill}.boxes.all[].above',
        '.textures[].ops[]{rule:fill}.boxes.all[].box',
        '.textures[].ops[]{rule:fill}.boxes.all[].far2',
        '.textures[].ops[]{rule:fill}.boxes.any',
        '.textures[].ops[]{rule:fill}.boxes.any[].all',
        '.textures[].ops[]{rule:fill}.boxes.any[].all[].above',
        '.textures[].ops[]{rule:fill}.boxes.any[].all[].box',
        '.textures[].ops[]{rule:fill}.boxes.any[].all[].far2',
        '.textures[].ops[]{rule:fill}.decal',
        '.textures[].ops[]{rule:fill}.decal.box',
        '.textures[].ops[]{rule:fill}.decal.to',
        '.textures[].ops[]{rule:fill}.flag',
        '.textures[].ops[]{rule:fill}.flag.from',
        '.textures[].ops[]{rule:fill}.flag.how',
        '.textures[].ops[]{rule:fill}.flag.paint',
        '.textures[].ops[]{rule:fill}.foot',
        '.textures[].ops[]{rule:fill}.foot.above',
        '.textures[].ops[]{rule:fill}.foot.crop',
        '.textures[].ops[]{rule:fill}.foot.logo',
        '.textures[].ops[]{rule:fill}.foot.regs',
        '.textures[].ops[]{rule:fill}.foot.regs[].h',
        '.textures[].ops[]{rule:fill}.foot.regs[].ori',
        '.textures[].ops[]{rule:fill}.foot.regs[].panel',
        '.textures[].ops[]{rule:fill}.foot.regs[].w',
        '.textures[].ops[]{rule:fill}.foot.regs[].x0',
        '.textures[].ops[]{rule:fill}.foot.regs[].y0',
        '.textures[].ops[]{rule:fill}.hardware',
        '.textures[].ops[]{rule:fill}.island',
        '.textures[].ops[]{rule:fill}.keep',
        '.textures[].ops[]{rule:fill}.keep.all',
        '.textures[].ops[]{rule:fill}.keep.all[].box',
        '.textures[].ops[]{rule:fill}.keep.all[].cross',
        '.textures[].ops[]{rule:fill}.keep.all[].grow',
        '.textures[].ops[]{rule:fill}.keep.all[].of',
        '.textures[].ops[]{rule:fill}.keep.all[].of.above',
        '.textures[].ops[]{rule:fill}.keep.all[].of.far2',
        '.textures[].ops[]{rule:fill}.kind',
        '.textures[].ops[]{rule:fill}.mask',
        '.textures[].ops[]{rule:fill}.mask.all',
        '.textures[].ops[]{rule:fill}.mask.all[].above',
        '.textures[].ops[]{rule:fill}.mask.all[].box',
        '.textures[].ops[]{rule:fill}.mask.all[].far',
        '.textures[].ops[]{rule:fill}.module',
        '.textures[].ops[]{rule:fill}.near',
        '.textures[].ops[]{rule:fill}.old',
        '.textures[].ops[]{rule:fill}.old.any',
        '.textures[].ops[]{rule:fill}.old.any[].all',
        '.textures[].ops[]{rule:fill}.old.any[].all[].above',
        '.textures[].ops[]{rule:fill}.old.any[].all[].box',
        '.textures[].ops[]{rule:fill}.old.any[].all[].far2',
        '.textures[].ops[]{rule:fill}.old_ink',
        '.textures[].ops[]{rule:fill}.old_ink.add',
        '.textures[].ops[]{rule:fill}.old_ink.add_dev',
        '.textures[].ops[]{rule:fill}.old_ink.despeckle',
        '.textures[].ops[]{rule:fill}.old_ink.erase',
        '.textures[].ops[]{rule:fill}.old_ink.erase_edge_neutral',
        '.textures[].ops[]{rule:fill}.old_ink.gold',
        '.textures[].ops[]{rule:fill}.old_ink.grow',
        '.textures[].ops[]{rule:fill}.old_ink.grow_dev',
        '.textures[].ops[]{rule:fill}.old_ink.panels',
        '.textures[].ops[]{rule:fill}.old_ink.refs',
        '.textures[].ops[]{rule:fill}.old_ink.reviewed',
        '.textures[].ops[]{rule:fill}.old_ink.shell_boxes',
        '.textures[].ops[]{rule:fill}.op',
        '.textures[].ops[]{rule:fill}.snap',
        '.textures[].ops[]{rule:fill}.to',
        '.textures[].ops[]{rule:fill}.vents',
        '.textures[].ops[]{rule:fill}.within',
        '.textures[].ops[]{rule:fill}.zone',
        '.textures[].ops[]{rule:recolour}.at',
        '.textures[].ops[]{rule:recolour}.boxes',
        '.textures[].ops[]{rule:recolour}.by',
        '.textures[].ops[]{rule:recolour}.cuts',
        '.textures[].ops[]{rule:recolour}.dilate',
        '.textures[].ops[]{rule:recolour}.do',
        '.textures[].ops[]{rule:recolour}.dst',
        '.textures[].ops[]{rule:recolour}.dy',
        '.textures[].ops[]{rule:recolour}.ends',
        '.textures[].ops[]{rule:recolour}.far',
        '.textures[].ops[]{rule:recolour}.far_tolerance',
        '.textures[].ops[]{rule:recolour}.field',
        '.textures[].ops[]{rule:recolour}.footprint',
        '.textures[].ops[]{rule:recolour}.footprint.above_milli',
        '.textures[].ops[]{rule:recolour}.footprint.box',
        '.textures[].ops[]{rule:recolour}.footprint.donor',
        '.textures[].ops[]{rule:recolour}.footprint.field',
        '.textures[].ops[]{rule:recolour}.footprint.mark',
        '.textures[].ops[]{rule:recolour}.footprint.offset',
        '.textures[].ops[]{rule:recolour}.from',
        '.textures[].ops[]{rule:recolour}.levels',
        '.textures[].ops[]{rule:recolour}.min',
        '.textures[].ops[]{rule:recolour}.module',
        '.textures[].ops[]{rule:recolour}.near',
        '.textures[].ops[]{rule:recolour}.off',
        '.textures[].ops[]{rule:recolour}.off_above',
        '.textures[].ops[]{rule:recolour}.op',
        '.textures[].ops[]{rule:recolour}.pairs',
        '.textures[].ops[]{rule:recolour}.rows',
        '.textures[].ops[]{rule:recolour}.seeds',
        '.textures[].ops[]{rule:recolour}.src',
        '.textures[].ops[]{rule:recolour}.to',
        '.textures[].ops[]{rule:recolour}.tolerance',
        '.textures[].ops[]{rule:recolour}.vacate',
        '.textures[].ops[]{rule:recolour}.vacate.copy_by',
        '.textures[].ops[]{rule:recolour}.vacate.to',
        '.textures[].ops[]{runs}.op',
        '.textures[].ops[]{runs}.rows',
        '.textures[].ops[]{stamp}.alpha_line',
        '.textures[].ops[]{stamp}.alpha_line.field',
        '.textures[].ops[]{stamp}.alpha_line.mark',
        '.textures[].ops[]{stamp}.color',
        '.textures[].ops[]{stamp}.donor',
        '.textures[].ops[]{stamp}.dst',
        '.textures[].ops[]{stamp}.op',
        '.textures[].ops[]{stamp}.remap',
        '.textures[].ops[]{stamp}.remap[].from',
        '.textures[].ops[]{stamp}.remap[].to',
        '.textures[].ops[]{stamp}.remap[].tolerance',
        '.textures[].ops[]{stamp}.skip',
        '.textures[].ops[]{stamp}.src',
        '.textures[].ops[]{stamp}.tolerance',
        '.textures[].ops[]{texels}.color',
        '.textures[].ops[]{texels}.op',
        '.textures[].ops[]{texels}.points',
        '.textures[].ops[]{want}.color',
        '.textures[].ops[]{want}.op',
        '.textures[].ops[]{warp}.alpha_line',
        '.textures[].ops[]{warp}.alpha_line.field',
        '.textures[].ops[]{warp}.alpha_line.mark',
        '.textures[].ops[]{warp}.arm',
        '.textures[].ops[]{warp}.color',
        '.textures[].ops[]{warp}.donor',
        '.textures[].ops[]{warp}.gain',
        '.textures[].ops[]{warp}.grid',
        '.textures[].ops[]{warp}.grid.s',
        '.textures[].ops[]{warp}.grid.t',
        '.textures[].ops[]{warp}.grid.x',
        '.textures[].ops[]{warp}.grid.y',
        '.textures[].ops[]{warp}.mask',
        '.textures[].ops[]{warp}.nodes',
        '.textures[].ops[]{warp}.nodes.a',
        '.textures[].ops[]{warp}.nodes.b',
        '.textures[].ops[]{warp}.nodes.dst',
        '.textures[].ops[]{warp}.nodes.use',
        '.textures[].ops[]{warp}.op',
        '.textures[].palette_remap',
        '.textures[].palette_remap.pairs',
        '.textures[].palette_remap.tolerance',
        '.textures[].reference',
        '.textures[].resource_size',
        '.textures[].selector',
        '.textures[].size',
        '.textures[].texels',
        '.textures[].texels_moved_one_level',
        '.textures[].texture',
    )),
    'nfl2k5_moment_kits/v1': frozenset((
        '.about',
        '.classic_defaults',
        '.classic_defaults[].before',
        '.classic_defaults[].file',
        '.classic_defaults[].style',
        '.classic_defaults[].why',
        '.classic_defaults_note',
        '.free_index_rule',
        '.kits',
        '.kits[].card_art',
        '.kits[].card_art.flipchip',
        '.kits[].card_art.helm_a',
        '.kits[].card_art.helm_h',
        '.kits[].card_art.logo',
        '.kits[].card_art.logo_s',
        '.kits[].card_art.mini_a',
        '.kits[].card_art.mini_h',
        '.kits[].card_art.unif_a',
        '.kits[].card_art.unif_h',
        '.kits[].cards',
        '.kits[].cards.A',
        '.kits[].cards.H',
        '.kits[].cards.helm_a',
        '.kits[].cards.logo',
        '.kits[].cards.mini_a',
        '.kits[].cards.unif_a',
        '.kits[].cards.unif_h',
        '.kits[].classic',
        '.kits[].code',
        '.kits[].evidence',
        '.kits[].id',
        '.kits[].label',
        '.kits[].look',
        '.kits[].moments',
        '.kits[].sides',
        '.kits[].sides.A',
        '.kits[].sides.A.art',
        '.kits[].sides.A.art[].chunk',
        '.kits[].sides.A.art[].kind',
        '.kits[].sides.A.art[].map',
        '.kits[].sides.A.art[].map[].from',
        '.kits[].sides.A.art[].map[].to',
        '.kits[].sides.A.art[].max_blend_slots',
        '.kits[].sides.A.art[].note',
        '.kits[].sides.A.art[].ops',
        '.kits[].sides.A.art[].ops[]{flood}.box',
        '.kits[].sides.A.art[].ops[]{flood}.color',
        '.kits[].sides.A.art[].ops[]{flood}.op',
        '.kits[].sides.A.art[].ops[]{flood}.seed',
        '.kits[].sides.A.art[].ops[]{flood}.tolerance',
        '.kits[].sides.A.art[].ops[]{multipoly}.alpha',
        '.kits[].sides.A.art[].ops[]{multipoly}.color',
        '.kits[].sides.A.art[].ops[]{multipoly}.op',
        '.kits[].sides.A.art[].ops[]{multipoly}.polys',
        '.kits[].sides.A.art[].ops[]{poly}.alpha',
        '.kits[].sides.A.art[].ops[]{poly}.color',
        '.kits[].sides.A.art[].ops[]{poly}.note',
        '.kits[].sides.A.art[].ops[]{poly}.op',
        '.kits[].sides.A.art[].ops[]{poly}.points',
        '.kits[].sides.A.art[].ops[]{recolor}.box',
        '.kits[].sides.A.art[].ops[]{recolor}.color',
        '.kits[].sides.A.art[].ops[]{recolor}.from',
        '.kits[].sides.A.art[].ops[]{recolor}.op',
        '.kits[].sides.A.art[].ops[]{recolor}.tolerance',
        '.kits[].sides.A.art[].ops[]{ring}.box',
        '.kits[].sides.A.art[].ops[]{ring}.color',
        '.kits[].sides.A.art[].ops[]{ring}.from',
        '.kits[].sides.A.art[].ops[]{ring}.inside',
        '.kits[].sides.A.art[].ops[]{ring}.op',
        '.kits[].sides.A.art[].ops[]{ring}.to',
        '.kits[].sides.A.art[].ops[]{ring}.tolerance',
        '.kits[].sides.A.art[].ops[]{texels}.color',
        '.kits[].sides.A.art[].ops[]{texels}.note',
        '.kits[].sides.A.art[].ops[]{texels}.op',
        '.kits[].sides.A.art[].ops[]{texels}.points',
        '.kits[].sides.A.art[].reencode',
        '.kits[].sides.A.art[].size',
        '.kits[].sides.A.art[].texture',
        '.kits[].sides.A.art[].texture_kind',
        '.kits[].sides.A.art[].tolerance',
        '.kits[].sides.A.atlas',
        '.kits[].sides.A.atlas.format',
        '.kits[].sides.A.atlas.ops',
        '.kits[].sides.A.atlas.ops[]{copy}.dst',
        '.kits[].sides.A.atlas.ops[]{copy}.note',
        '.kits[].sides.A.atlas.ops[]{copy}.op',
        '.kits[].sides.A.atlas.ops[]{copy}.src',
        '.kits[].sides.A.atlas.ops[]{multipoly}.color',
        '.kits[].sides.A.atlas.ops[]{multipoly}.op',
        '.kits[].sides.A.atlas.ops[]{multipoly}.polys',
        '.kits[].sides.A.atlas.ops[]{poly}.color',
        '.kits[].sides.A.atlas.ops[]{poly}.note',
        '.kits[].sides.A.atlas.ops[]{poly}.op',
        '.kits[].sides.A.atlas.ops[]{poly}.points',
        '.kits[].sides.A.atlas.ops[]{remap}.box',
        '.kits[].sides.A.atlas.ops[]{remap}.op',
        '.kits[].sides.A.atlas.ops[]{remap}.pairs',
        '.kits[].sides.A.atlas.ops[]{remap}.tolerance',
        '.kits[].sides.A.atlas.overlays',
        '.kits[].sides.A.atlas.overlays[].boxes',
        '.kits[].sides.A.atlas.overlays[].donor',
        '.kits[].sides.A.base',
        '.kits[].sides.A.chunks',
        '.kits[].sides.A.chunks.*',
        '.kits[].sides.A.chunks.1',
        '.kits[].sides.A.chunks.13-22',
        '.kits[].sides.A.chunks.23-32',
        '.kits[].sides.A.chunks.3',
        '.kits[].sides.A.chunks.33-44',
        '.kits[].sides.A.chunks.4',
        '.kits[].sides.A.chunks.4-12',
        '.kits[].sides.A.chunks.45',
        '.kits[].sides.A.chunks.46',
        '.kits[].sides.A.chunks.48',
        '.kits[].sides.A.own_look',
        '.kits[].sides.A.unif',
        '.kits[].sides.A.unif_colours',
        '.kits[].sides.H',
        '.kits[].sides.H.art',
        '.kits[].sides.H.art[].chunk',
        '.kits[].sides.H.art[].kind',
        '.kits[].sides.H.art[].map',
        '.kits[].sides.H.art[].map[].from',
        '.kits[].sides.H.art[].map[].to',
        '.kits[].sides.H.art[].max_blend_slots',
        '.kits[].sides.H.art[].ops',
        '.kits[].sides.H.art[].ops[]{flood}.box',
        '.kits[].sides.H.art[].ops[]{flood}.color',
        '.kits[].sides.H.art[].ops[]{flood}.op',
        '.kits[].sides.H.art[].ops[]{flood}.seed',
        '.kits[].sides.H.art[].ops[]{flood}.tolerance',
        '.kits[].sides.H.art[].ops[]{grow}.box',
        '.kits[].sides.H.art[].ops[]{grow}.color',
        '.kits[].sides.H.art[].ops[]{grow}.from',
        '.kits[].sides.H.art[].ops[]{grow}.into',
        '.kits[].sides.H.art[].ops[]{grow}.op',
        '.kits[].sides.H.art[].ops[]{grow}.radius',
        '.kits[].sides.H.art[].ops[]{grow}.tolerance',
        '.kits[].sides.H.art[].ops[]{multipoly}.alpha',
        '.kits[].sides.H.art[].ops[]{multipoly}.color',
        '.kits[].sides.H.art[].ops[]{multipoly}.op',
        '.kits[].sides.H.art[].ops[]{multipoly}.polys',
        '.kits[].sides.H.art[].ops[]{poly}.alpha',
        '.kits[].sides.H.art[].ops[]{poly}.color',
        '.kits[].sides.H.art[].ops[]{poly}.note',
        '.kits[].sides.H.art[].ops[]{poly}.op',
        '.kits[].sides.H.art[].ops[]{poly}.points',
        '.kits[].sides.H.art[].ops[]{recolor}.box',
        '.kits[].sides.H.art[].ops[]{recolor}.color',
        '.kits[].sides.H.art[].ops[]{recolor}.from',
        '.kits[].sides.H.art[].ops[]{recolor}.invert',
        '.kits[].sides.H.art[].ops[]{recolor}.match',
        '.kits[].sides.H.art[].ops[]{recolor}.op',
        '.kits[].sides.H.art[].ops[]{recolor}.tolerance',
        '.kits[].sides.H.art[].ops[]{ring}.box',
        '.kits[].sides.H.art[].ops[]{ring}.color',
        '.kits[].sides.H.art[].ops[]{ring}.from',
        '.kits[].sides.H.art[].ops[]{ring}.inside',
        '.kits[].sides.H.art[].ops[]{ring}.op',
        '.kits[].sides.H.art[].ops[]{ring}.to',
        '.kits[].sides.H.art[].ops[]{ring}.tolerance',
        '.kits[].sides.H.art[].ops[]{texels}.color',
        '.kits[].sides.H.art[].ops[]{texels}.note',
        '.kits[].sides.H.art[].ops[]{texels}.op',
        '.kits[].sides.H.art[].ops[]{texels}.points',
        '.kits[].sides.H.art[].reencode',
        '.kits[].sides.H.art[].size',
        '.kits[].sides.H.art[].texture',
        '.kits[].sides.H.art[].texture_kind',
        '.kits[].sides.H.art[].tolerance',
        '.kits[].sides.H.atlas',
        '.kits[].sides.H.atlas.format',
        '.kits[].sides.H.atlas.ops',
        '.kits[].sides.H.atlas.ops[]{copy}.dst',
        '.kits[].sides.H.atlas.ops[]{copy}.note',
        '.kits[].sides.H.atlas.ops[]{copy}.op',
        '.kits[].sides.H.atlas.ops[]{copy}.src',
        '.kits[].sides.H.atlas.ops[]{multipoly}.color',
        '.kits[].sides.H.atlas.ops[]{multipoly}.op',
        '.kits[].sides.H.atlas.ops[]{multipoly}.polys',
        '.kits[].sides.H.atlas.ops[]{poly}.color',
        '.kits[].sides.H.atlas.ops[]{poly}.note',
        '.kits[].sides.H.atlas.ops[]{poly}.op',
        '.kits[].sides.H.atlas.ops[]{poly}.points',
        '.kits[].sides.H.atlas.ops[]{recolor}.box',
        '.kits[].sides.H.atlas.ops[]{recolor}.color',
        '.kits[].sides.H.atlas.ops[]{recolor}.from',
        '.kits[].sides.H.atlas.ops[]{recolor}.note',
        '.kits[].sides.H.atlas.ops[]{recolor}.op',
        '.kits[].sides.H.atlas.ops[]{recolor}.tolerance',
        '.kits[].sides.H.atlas.ops[]{remap}.box',
        '.kits[].sides.H.atlas.ops[]{remap}.op',
        '.kits[].sides.H.atlas.ops[]{remap}.pairs',
        '.kits[].sides.H.atlas.ops[]{remap}.tolerance',
        '.kits[].sides.H.atlas.overlays',
        '.kits[].sides.H.atlas.overlays[].boxes',
        '.kits[].sides.H.atlas.overlays[].donor',
        '.kits[].sides.H.base',
        '.kits[].sides.H.chunks',
        '.kits[].sides.H.chunks.*',
        '.kits[].sides.H.own_look',
        '.kits[].sides.H.unif',
        '.kits[].sides.H.unif_colours',
        '.kits[].style',
        '.kits[].team',
        '.schema',
        '.selections',
        '.selections[].before',
        '.selections[].file',
        '.selections[].kit',
        '.selections[].reuse',
        '.selections[].row',
        '.selections[].side',
        '.selections[].style',
        '.selections[].why',
    )),
    'nfl2k5_team_select_old_logo_cleanup/v1': frozenset((
        '.cards',
        '.cards.helm_a00_0_128',
        '.cards.helm_a00_0_128.changed_pixels',
        '.cards.helm_a00_0_128.clean_rgba_sha256',
        '.cards.helm_a00_0_128.source_rgba_sha256',
        '.cards.helm_a00_0_256',
        '.cards.helm_a00_0_256.changed_pixels',
        '.cards.helm_a00_0_256.clean_rgba_sha256',
        '.cards.helm_a00_0_256.source_rgba_sha256',
        '.cards.helm_a00_6_128',
        '.cards.helm_a00_6_128.changed_pixels',
        '.cards.helm_a00_6_128.clean_rgba_sha256',
        '.cards.helm_a00_6_128.source_rgba_sha256',
        '.cards.helm_a00_6_256',
        '.cards.helm_a00_6_256.changed_pixels',
        '.cards.helm_a00_6_256.clean_rgba_sha256',
        '.cards.helm_a00_6_256.source_rgba_sha256',
        '.cards.helm_a00_7_128',
        '.cards.helm_a00_7_128.changed_pixels',
        '.cards.helm_a00_7_128.clean_rgba_sha256',
        '.cards.helm_a00_7_128.source_rgba_sha256',
        '.cards.helm_a00_7_256',
        '.cards.helm_a00_7_256.changed_pixels',
        '.cards.helm_a00_7_256.clean_rgba_sha256',
        '.cards.helm_a00_7_256.source_rgba_sha256',
        '.cards.helm_a02_0_128',
        '.cards.helm_a02_0_128.changed_pixels',
        '.cards.helm_a02_0_128.clean_rgba_sha256',
        '.cards.helm_a02_0_128.source_rgba_sha256',
        '.cards.helm_a02_0_256',
        '.cards.helm_a02_0_256.changed_pixels',
        '.cards.helm_a02_0_256.clean_rgba_sha256',
        '.cards.helm_a02_0_256.source_rgba_sha256',
        '.cards.helm_a02_2_128',
        '.cards.helm_a02_2_128.changed_pixels',
        '.cards.helm_a02_2_128.clean_rgba_sha256',
        '.cards.helm_a02_2_128.source_rgba_sha256',
        '.cards.helm_a02_2_256',
        '.cards.helm_a02_2_256.changed_pixels',
        '.cards.helm_a02_2_256.clean_rgba_sha256',
        '.cards.helm_a02_2_256.source_rgba_sha256',
        '.cards.helm_a02_3_128',
        '.cards.helm_a02_3_128.changed_pixels',
        '.cards.helm_a02_3_128.clean_rgba_sha256',
        '.cards.helm_a02_3_128.source_rgba_sha256',
        '.cards.helm_a02_3_256',
        '.cards.helm_a02_3_256.changed_pixels',
        '.cards.helm_a02_3_256.clean_rgba_sha256',
        '.cards.helm_a02_3_256.source_rgba_sha256',
        '.cards.helm_a09_0_128',
        '.cards.helm_a09_0_128.changed_pixels',
        '.cards.helm_a09_0_128.clean_rgba_sha256',
        '.cards.helm_a09_0_128.source_rgba_sha256',
        '.cards.helm_a09_0_256',
        '.cards.helm_a09_0_256.changed_pixels',
        '.cards.helm_a09_0_256.clean_rgba_sha256',
        '.cards.helm_a09_0_256.source_rgba_sha256',
        '.cards.helm_a09_2_128',
        '.cards.helm_a09_2_128.changed_pixels',
        '.cards.helm_a09_2_128.clean_rgba_sha256',
        '.cards.helm_a09_2_128.source_rgba_sha256',
        '.cards.helm_a09_2_256',
        '.cards.helm_a09_2_256.changed_pixels',
        '.cards.helm_a09_2_256.clean_rgba_sha256',
        '.cards.helm_a09_2_256.source_rgba_sha256',
        '.cards.helm_a09_9_128',
        '.cards.helm_a09_9_128.changed_pixels',
        '.cards.helm_a09_9_128.clean_rgba_sha256',
        '.cards.helm_a09_9_128.source_rgba_sha256',
        '.cards.helm_a09_9_256',
        '.cards.helm_a09_9_256.changed_pixels',
        '.cards.helm_a09_9_256.clean_rgba_sha256',
        '.cards.helm_a09_9_256.source_rgba_sha256',
        '.cards.helm_a19_7_128',
        '.cards.helm_a19_7_128.changed_pixels',
        '.cards.helm_a19_7_128.clean_rgba_sha256',
        '.cards.helm_a19_7_128.source_rgba_sha256',
        '.cards.helm_a19_7_256',
        '.cards.helm_a19_7_256.changed_pixels',
        '.cards.helm_a19_7_256.clean_rgba_sha256',
        '.cards.helm_a19_7_256.source_rgba_sha256',
        '.cards.helm_a29_0_128',
        '.cards.helm_a29_0_128.changed_pixels',
        '.cards.helm_a29_0_128.clean_rgba_sha256',
        '.cards.helm_a29_0_128.source_rgba_sha256',
        '.cards.helm_a29_0_256',
        '.cards.helm_a29_0_256.changed_pixels',
        '.cards.helm_a29_0_256.clean_rgba_sha256',
        '.cards.helm_a29_0_256.source_rgba_sha256',
        '.cards.helm_a29_9_128',
        '.cards.helm_a29_9_128.changed_pixels',
        '.cards.helm_a29_9_128.clean_rgba_sha256',
        '.cards.helm_a29_9_128.source_rgba_sha256',
        '.cards.helm_a29_9_256',
        '.cards.helm_a29_9_256.changed_pixels',
        '.cards.helm_a29_9_256.clean_rgba_sha256',
        '.cards.helm_a29_9_256.source_rgba_sha256',
        '.cards.helm_h00_0_128',
        '.cards.helm_h00_0_128.changed_pixels',
        '.cards.helm_h00_0_128.clean_rgba_sha256',
        '.cards.helm_h00_0_128.source_rgba_sha256',
        '.cards.helm_h00_0_256',
        '.cards.helm_h00_0_256.changed_pixels',
        '.cards.helm_h00_0_256.clean_rgba_sha256',
        '.cards.helm_h00_0_256.source_rgba_sha256',
        '.cards.helm_h00_6_128',
        '.cards.helm_h00_6_128.changed_pixels',
        '.cards.helm_h00_6_128.clean_rgba_sha256',
        '.cards.helm_h00_6_128.source_rgba_sha256',
        '.cards.helm_h00_6_256',
        '.cards.helm_h00_6_256.changed_pixels',
        '.cards.helm_h00_6_256.clean_rgba_sha256',
        '.cards.helm_h00_6_256.source_rgba_sha256',
        '.cards.helm_h00_7_128',
        '.cards.helm_h00_7_128.changed_pixels',
        '.cards.helm_h00_7_128.clean_rgba_sha256',
        '.cards.helm_h00_7_128.source_rgba_sha256',
        '.cards.helm_h00_7_256',
        '.cards.helm_h00_7_256.changed_pixels',
        '.cards.helm_h00_7_256.clean_rgba_sha256',
        '.cards.helm_h00_7_256.source_rgba_sha256',
        '.cards.helm_h02_0_128',
        '.cards.helm_h02_0_128.changed_pixels',
        '.cards.helm_h02_0_128.clean_rgba_sha256',
        '.cards.helm_h02_0_128.source_rgba_sha256',
        '.cards.helm_h02_0_256',
        '.cards.helm_h02_0_256.changed_pixels',
        '.cards.helm_h02_0_256.clean_rgba_sha256',
        '.cards.helm_h02_0_256.source_rgba_sha256',
        '.cards.helm_h02_2_128',
        '.cards.helm_h02_2_128.changed_pixels',
        '.cards.helm_h02_2_128.clean_rgba_sha256',
        '.cards.helm_h02_2_128.source_rgba_sha256',
        '.cards.helm_h02_2_256',
        '.cards.helm_h02_2_256.changed_pixels',
        '.cards.helm_h02_2_256.clean_rgba_sha256',
        '.cards.helm_h02_2_256.source_rgba_sha256',
        '.cards.helm_h02_3_128',
        '.cards.helm_h02_3_128.changed_pixels',
        '.cards.helm_h02_3_128.clean_rgba_sha256',
        '.cards.helm_h02_3_128.source_rgba_sha256',
        '.cards.helm_h02_3_256',
        '.cards.helm_h02_3_256.changed_pixels',
        '.cards.helm_h02_3_256.clean_rgba_sha256',
        '.cards.helm_h02_3_256.source_rgba_sha256',
        '.cards.helm_h09_0_128',
        '.cards.helm_h09_0_128.changed_pixels',
        '.cards.helm_h09_0_128.clean_rgba_sha256',
        '.cards.helm_h09_0_128.source_rgba_sha256',
        '.cards.helm_h09_0_256',
        '.cards.helm_h09_0_256.changed_pixels',
        '.cards.helm_h09_0_256.clean_rgba_sha256',
        '.cards.helm_h09_0_256.source_rgba_sha256',
        '.cards.helm_h09_2_128',
        '.cards.helm_h09_2_128.changed_pixels',
        '.cards.helm_h09_2_128.clean_rgba_sha256',
        '.cards.helm_h09_2_128.source_rgba_sha256',
        '.cards.helm_h09_2_256',
        '.cards.helm_h09_2_256.changed_pixels',
        '.cards.helm_h09_2_256.clean_rgba_sha256',
        '.cards.helm_h09_2_256.source_rgba_sha256',
        '.cards.helm_h09_9_128',
        '.cards.helm_h09_9_128.changed_pixels',
        '.cards.helm_h09_9_128.clean_rgba_sha256',
        '.cards.helm_h09_9_128.source_rgba_sha256',
        '.cards.helm_h09_9_256',
        '.cards.helm_h09_9_256.changed_pixels',
        '.cards.helm_h09_9_256.clean_rgba_sha256',
        '.cards.helm_h09_9_256.source_rgba_sha256',
        '.cards.helm_h19_7_128',
        '.cards.helm_h19_7_128.changed_pixels',
        '.cards.helm_h19_7_128.clean_rgba_sha256',
        '.cards.helm_h19_7_128.source_rgba_sha256',
        '.cards.helm_h19_7_256',
        '.cards.helm_h19_7_256.changed_pixels',
        '.cards.helm_h19_7_256.clean_rgba_sha256',
        '.cards.helm_h19_7_256.source_rgba_sha256',
        '.cards.helm_h29_0_128',
        '.cards.helm_h29_0_128.changed_pixels',
        '.cards.helm_h29_0_128.clean_rgba_sha256',
        '.cards.helm_h29_0_128.source_rgba_sha256',
        '.cards.helm_h29_0_256',
        '.cards.helm_h29_0_256.changed_pixels',
        '.cards.helm_h29_0_256.clean_rgba_sha256',
        '.cards.helm_h29_0_256.source_rgba_sha256',
        '.cards.helm_h29_9_128',
        '.cards.helm_h29_9_128.changed_pixels',
        '.cards.helm_h29_9_128.clean_rgba_sha256',
        '.cards.helm_h29_9_128.source_rgba_sha256',
        '.cards.helm_h29_9_256',
        '.cards.helm_h29_9_256.changed_pixels',
        '.cards.helm_h29_9_256.clean_rgba_sha256',
        '.cards.helm_h29_9_256.source_rgba_sha256',
        '.cards.unif_a00_0_256',
        '.cards.unif_a00_0_256.changed_pixels',
        '.cards.unif_a00_0_256.clean_rgba_sha256',
        '.cards.unif_a00_0_256.source_rgba_sha256',
        '.cards.unif_a00_6_256',
        '.cards.unif_a00_6_256.changed_pixels',
        '.cards.unif_a00_6_256.clean_rgba_sha256',
        '.cards.unif_a00_6_256.source_rgba_sha256',
        '.cards.unif_a00_7_256',
        '.cards.unif_a00_7_256.changed_pixels',
        '.cards.unif_a00_7_256.clean_rgba_sha256',
        '.cards.unif_a00_7_256.source_rgba_sha256',
        '.cards.unif_a02_0_256',
        '.cards.unif_a02_0_256.changed_pixels',
        '.cards.unif_a02_0_256.clean_rgba_sha256',
        '.cards.unif_a02_0_256.source_rgba_sha256',
        '.cards.unif_a02_2_256',
        '.cards.unif_a02_2_256.changed_pixels',
        '.cards.unif_a02_2_256.clean_rgba_sha256',
        '.cards.unif_a02_2_256.source_rgba_sha256',
        '.cards.unif_a02_3_256',
        '.cards.unif_a02_3_256.changed_pixels',
        '.cards.unif_a02_3_256.clean_rgba_sha256',
        '.cards.unif_a02_3_256.source_rgba_sha256',
        '.cards.unif_a09_0_256',
        '.cards.unif_a09_0_256.changed_pixels',
        '.cards.unif_a09_0_256.clean_rgba_sha256',
        '.cards.unif_a09_0_256.source_rgba_sha256',
        '.cards.unif_a09_2_256',
        '.cards.unif_a09_2_256.changed_pixels',
        '.cards.unif_a09_2_256.clean_rgba_sha256',
        '.cards.unif_a09_2_256.source_rgba_sha256',
        '.cards.unif_a09_9_256',
        '.cards.unif_a09_9_256.changed_pixels',
        '.cards.unif_a09_9_256.clean_rgba_sha256',
        '.cards.unif_a09_9_256.source_rgba_sha256',
        '.cards.unif_a19_7_256',
        '.cards.unif_a19_7_256.changed_pixels',
        '.cards.unif_a19_7_256.clean_rgba_sha256',
        '.cards.unif_a19_7_256.source_rgba_sha256',
        '.cards.unif_a29_0_256',
        '.cards.unif_a29_0_256.changed_pixels',
        '.cards.unif_a29_0_256.clean_rgba_sha256',
        '.cards.unif_a29_0_256.source_rgba_sha256',
        '.cards.unif_a29_9_256',
        '.cards.unif_a29_9_256.changed_pixels',
        '.cards.unif_a29_9_256.clean_rgba_sha256',
        '.cards.unif_a29_9_256.source_rgba_sha256',
        '.cards.unif_h00_0_256',
        '.cards.unif_h00_0_256.changed_pixels',
        '.cards.unif_h00_0_256.clean_rgba_sha256',
        '.cards.unif_h00_0_256.source_rgba_sha256',
        '.cards.unif_h00_6_256',
        '.cards.unif_h00_6_256.changed_pixels',
        '.cards.unif_h00_6_256.clean_rgba_sha256',
        '.cards.unif_h00_6_256.source_rgba_sha256',
        '.cards.unif_h00_7_256',
        '.cards.unif_h00_7_256.changed_pixels',
        '.cards.unif_h00_7_256.clean_rgba_sha256',
        '.cards.unif_h00_7_256.source_rgba_sha256',
        '.cards.unif_h02_0_256',
        '.cards.unif_h02_0_256.changed_pixels',
        '.cards.unif_h02_0_256.clean_rgba_sha256',
        '.cards.unif_h02_0_256.source_rgba_sha256',
        '.cards.unif_h02_2_256',
        '.cards.unif_h02_2_256.changed_pixels',
        '.cards.unif_h02_2_256.clean_rgba_sha256',
        '.cards.unif_h02_2_256.source_rgba_sha256',
        '.cards.unif_h02_3_256',
        '.cards.unif_h02_3_256.changed_pixels',
        '.cards.unif_h02_3_256.clean_rgba_sha256',
        '.cards.unif_h02_3_256.source_rgba_sha256',
        '.cards.unif_h09_0_256',
        '.cards.unif_h09_0_256.changed_pixels',
        '.cards.unif_h09_0_256.clean_rgba_sha256',
        '.cards.unif_h09_0_256.source_rgba_sha256',
        '.cards.unif_h09_2_256',
        '.cards.unif_h09_2_256.changed_pixels',
        '.cards.unif_h09_2_256.clean_rgba_sha256',
        '.cards.unif_h09_2_256.source_rgba_sha256',
        '.cards.unif_h09_9_256',
        '.cards.unif_h09_9_256.changed_pixels',
        '.cards.unif_h09_9_256.clean_rgba_sha256',
        '.cards.unif_h09_9_256.source_rgba_sha256',
        '.cards.unif_h19_7_256',
        '.cards.unif_h19_7_256.changed_pixels',
        '.cards.unif_h19_7_256.clean_rgba_sha256',
        '.cards.unif_h19_7_256.source_rgba_sha256',
        '.cards.unif_h29_0_256',
        '.cards.unif_h29_0_256.changed_pixels',
        '.cards.unif_h29_0_256.clean_rgba_sha256',
        '.cards.unif_h29_0_256.source_rgba_sha256',
        '.cards.unif_h29_9_256',
        '.cards.unif_h29_9_256.changed_pixels',
        '.cards.unif_h29_9_256.clean_rgba_sha256',
        '.cards.unif_h29_9_256.source_rgba_sha256',
        '.coordinates',
        '.derived_128',
        '.groups',
        '.groups[].card',
        '.groups[].code',
        '.groups[].regions',
        '.groups[].regions[].estimate',
        '.groups[].regions[].grow',
        '.groups[].regions[].inset',
        '.groups[].regions[].keep_band',
        '.groups[].regions[].mode',
        '.groups[].regions[].note',
        '.groups[].regions[].poly',
        '.groups[].regions[].shell_box',
        '.groups[].regions[].sign',
        '.groups[].regions[].threshold',
        '.groups[].styles',
        '.groups[].team',
        '.purpose',
        '.schema',
        '.source',
        '.texture_pins',
        '.texture_pins.bal_pants_02A0',
        '.texture_pins.bal_pants_02A0.changed_pixels',
        '.texture_pins.bal_pants_02A0.clean_rgba_sha256',
        '.texture_pins.bal_pants_02A0.edits',
        '.texture_pins.bal_pants_02A0.source_rgba_sha256',
        '.texture_pins.bal_pants_02A2',
        '.texture_pins.bal_pants_02A2.changed_pixels',
        '.texture_pins.bal_pants_02A2.clean_rgba_sha256',
        '.texture_pins.bal_pants_02A2.edits',
        '.texture_pins.bal_pants_02A2.source_rgba_sha256',
        '.texture_pins.bal_pants_02H0',
        '.texture_pins.bal_pants_02H0.changed_pixels',
        '.texture_pins.bal_pants_02H0.clean_rgba_sha256',
        '.texture_pins.bal_pants_02H0.edits',
        '.texture_pins.bal_pants_02H0.source_rgba_sha256',
        '.texture_pins.bal_pants_02H2',
        '.texture_pins.bal_pants_02H2.changed_pixels',
        '.texture_pins.bal_pants_02H2.clean_rgba_sha256',
        '.texture_pins.bal_pants_02H2.edits',
        '.texture_pins.bal_pants_02H2.source_rgba_sha256',
        '.texture_pins.bal_pants_02x3',
        '.texture_pins.bal_pants_02x3.changed_pixels',
        '.texture_pins.bal_pants_02x3.clean_rgba_sha256',
        '.texture_pins.bal_pants_02x3.edits',
        '.texture_pins.bal_pants_02x3.source_rgba_sha256',
        '.texture_pins.buf_splayer_a',
        '.texture_pins.buf_splayer_a.changed_pixels',
        '.texture_pins.buf_splayer_a.clean_rgba_sha256',
        '.texture_pins.buf_splayer_a.edits',
        '.texture_pins.buf_splayer_a.source_rgba_sha256',
        '.texture_pins.buf_splayer_h',
        '.texture_pins.buf_splayer_h.changed_pixels',
        '.texture_pins.buf_splayer_h.clean_rgba_sha256',
        '.texture_pins.buf_splayer_h.edits',
        '.texture_pins.buf_splayer_h.source_rgba_sha256',
        '.texture_pins.car_pants_04A0',
        '.texture_pins.car_pants_04A0.changed_pixels',
        '.texture_pins.car_pants_04A0.clean_rgba_sha256',
        '.texture_pins.car_pants_04A0.edits',
        '.texture_pins.car_pants_04A0.source_rgba_sha256',
        '.texture_pins.car_pants_04H0',
        '.texture_pins.car_pants_04H0.changed_pixels',
        '.texture_pins.car_pants_04H0.clean_rgba_sha256',
        '.texture_pins.car_pants_04H0.edits',
        '.texture_pins.car_pants_04H0.source_rgba_sha256',
        '.texture_pins.car_splayer_a',
        '.texture_pins.car_splayer_a.changed_pixels',
        '.texture_pins.car_splayer_a.clean_rgba_sha256',
        '.texture_pins.car_splayer_a.edits',
        '.texture_pins.car_splayer_a.source_rgba_sha256',
        '.texture_pins.cle_helmet02_30_0',
        '.texture_pins.cle_helmet02_30_0.changed_pixels',
        '.texture_pins.cle_helmet02_30_0.clean_rgba_sha256',
        '.texture_pins.cle_helmet02_30_0.edits',
        '.texture_pins.cle_helmet02_30_0.source_rgba_sha256',
        '.texture_pins.cle_helmet02_30_3',
        '.texture_pins.cle_helmet02_30_3.changed_pixels',
        '.texture_pins.cle_helmet02_30_3.clean_rgba_sha256',
        '.texture_pins.cle_helmet02_30_3.edits',
        '.texture_pins.cle_helmet02_30_3.source_rgba_sha256',
        '.texture_pins.cle_helmet02_30_4',
        '.texture_pins.cle_helmet02_30_4.changed_pixels',
        '.texture_pins.cle_helmet02_30_4.clean_rgba_sha256',
        '.texture_pins.cle_helmet02_30_4.edits',
        '.texture_pins.cle_helmet02_30_4.source_rgba_sha256',
        '.texture_pins.den_helmet00_alt',
        '.texture_pins.den_helmet00_alt.changed_pixels',
        '.texture_pins.den_helmet00_alt.clean_rgba_sha256',
        '.texture_pins.den_helmet00_alt.edits',
        '.texture_pins.den_helmet00_alt.source_rgba_sha256',
        '.texture_pins.den_helmet02_navy',
        '.texture_pins.den_helmet02_navy.changed_pixels',
        '.texture_pins.den_helmet02_navy.clean_rgba_sha256',
        '.texture_pins.den_helmet02_navy.edits',
        '.texture_pins.den_helmet02_navy.source_rgba_sha256',
        '.texture_pins.den_helmet02_navy6',
        '.texture_pins.den_helmet02_navy6.changed_pixels',
        '.texture_pins.den_helmet02_navy6.clean_rgba_sha256',
        '.texture_pins.den_helmet02_navy6.edits',
        '.texture_pins.den_helmet02_navy6.source_rgba_sha256',
        '.texture_pins.den_helmet02_white',
        '.texture_pins.den_helmet02_white.changed_pixels',
        '.texture_pins.den_helmet02_white.clean_rgba_sha256',
        '.texture_pins.den_helmet02_white.edits',
        '.texture_pins.den_helmet02_white.source_rgba_sha256',
        '.texture_pins.det_helmet00_alt',
        '.texture_pins.det_helmet00_alt.changed_pixels',
        '.texture_pins.det_helmet00_alt.clean_rgba_sha256',
        '.texture_pins.det_helmet00_alt.edits',
        '.texture_pins.det_helmet00_alt.source_rgba_sha256',
        '.texture_pins.det_helmet02_alt',
        '.texture_pins.det_helmet02_alt.changed_pixels',
        '.texture_pins.det_helmet02_alt.clean_rgba_sha256',
        '.texture_pins.det_helmet02_alt.edits',
        '.texture_pins.det_helmet02_alt.source_rgba_sha256',
        '.texture_pins.det_splayer_a',
        '.texture_pins.det_splayer_a.changed_pixels',
        '.texture_pins.det_splayer_a.clean_rgba_sha256',
        '.texture_pins.det_splayer_a.edits',
        '.texture_pins.det_splayer_a.source_rgba_sha256',
        '.texture_pins.det_splayer_h',
        '.texture_pins.det_splayer_h.changed_pixels',
        '.texture_pins.det_splayer_h.clean_rgba_sha256',
        '.texture_pins.det_splayer_h.edits',
        '.texture_pins.det_splayer_h.source_rgba_sha256',
        '.texture_pins.hou_helmet00_horns',
        '.texture_pins.hou_helmet00_horns.changed_pixels',
        '.texture_pins.hou_helmet00_horns.clean_rgba_sha256',
        '.texture_pins.hou_helmet00_horns.edits',
        '.texture_pins.hou_helmet00_horns.source_rgba_sha256',
        '.texture_pins.hou_helmet02_bull',
        '.texture_pins.hou_helmet02_bull.changed_pixels',
        '.texture_pins.hou_helmet02_bull.clean_rgba_sha256',
        '.texture_pins.hou_helmet02_bull.edits',
        '.texture_pins.hou_helmet02_bull.source_rgba_sha256',
        '.texture_pins.lac_helmet00_24',
        '.texture_pins.lac_helmet00_24.changed_pixels',
        '.texture_pins.lac_helmet00_24.clean_rgba_sha256',
        '.texture_pins.lac_helmet00_24.edits',
        '.texture_pins.lac_helmet00_24.source_rgba_sha256',
        '.texture_pins.ten_splayer_a',
        '.texture_pins.ten_splayer_a.changed_pixels',
        '.texture_pins.ten_splayer_a.clean_rgba_sha256',
        '.texture_pins.ten_splayer_a.edits',
        '.texture_pins.ten_splayer_a.source_rgba_sha256',
        '.texture_pins.ten_splayer_h',
        '.texture_pins.ten_splayer_h.changed_pixels',
        '.texture_pins.ten_splayer_h.clean_rgba_sha256',
        '.texture_pins.ten_splayer_h.edits',
        '.texture_pins.ten_splayer_h.source_rgba_sha256',
        '.texture_pins.was_helmet00_29_9',
        '.texture_pins.was_helmet00_29_9.changed_pixels',
        '.texture_pins.was_helmet00_29_9.clean_rgba_sha256',
        '.texture_pins.was_helmet00_29_9.edits',
        '.texture_pins.was_helmet00_29_9.source_rgba_sha256',
        '.texture_pins.was_helmet02_29_9',
        '.texture_pins.was_helmet02_29_9.changed_pixels',
        '.texture_pins.was_helmet02_29_9.clean_rgba_sha256',
        '.texture_pins.was_helmet02_29_9.edits',
        '.texture_pins.was_helmet02_29_9.source_rgba_sha256',
        '.textures',
        '.textures[].alpha',
        '.textures[].edits',
        '.textures[].kind',
        '.textures[].marks',
        '.textures[].marks[].box',
        '.textures[].marks[].flip',
        '.textures[].marks[].png',
        '.textures[].match',
        '.textures[].match.asset_code',
        '.textures[].match.asset_id',
        '.textures[].match.family',
        '.textures[].match.side',
        '.textures[].match.variant',
        '.textures[].name',
        '.textures[].note',
        '.textures[].regions',
        '.textures[].regions[].from',
        '.textures[].regions[].grow',
        '.textures[].regions[].mode',
        '.textures[].regions[].note',
        '.textures[].regions[].ops',
        '.textures[].regions[].ops[]{poly}.color',
        '.textures[].regions[].ops[]{poly}.only',
        '.textures[].regions[].ops[]{poly}.only_tolerance',
        '.textures[].regions[].ops[]{poly}.op',
        '.textures[].regions[].ops[]{poly}.points',
        '.textures[].regions[].poly',
        '.textures[].regions[].runs',
        '.textures[].regions[].shell_box',
        '.textures[].regions[].sign',
        '.textures[].regions[].threshold',
        '.textures_note',
    )),
    'nfl2k5_uniform_alternates_2026/v1': frozenset((
        '.alternates',
        '.alternates.*',
        '.alternates.*.blank',
        '.alternates.*.blank_why',
        '.alternates.*.build_type',
        '.alternates.*.card_facemask',
        '.alternates.*.code',
        '.alternates.*.estimates',
        '.alternates.*.keep_slot',
        '.alternates.*.keep_slot_why',
        '.alternates.*.kits',
        '.alternates.*.kits.A',
        '.alternates.*.kits.A.donor',
        '.alternates.*.kits.A.ops',
        '.alternates.*.kits.A.ops[]{remix}.boxes',
        '.alternates.*.kits.A.ops[]{remix}.components',
        '.alternates.*.kits.A.ops[]{remix}.exclude',
        '.alternates.*.kits.A.ops[]{remix}.from',
        '.alternates.*.kits.A.ops[]{remix}.moved',
        '.alternates.*.kits.A.ops[]{remix}.op',
        '.alternates.*.kits.A.ops[]{remix}.region',
        '.alternates.*.kits.A.ops[]{remix}.to',
        '.alternates.*.kits.A.ops[]{remix}.tolerance',
        '.alternates.*.kits.A.ops[]{remix}.why',
        '.alternates.*.kits.A.part_donors',
        '.alternates.*.kits.A.part_donors.sleeve',
        '.alternates.*.kits.A.socks',
        '.alternates.*.kits.A.splayer_socks',
        '.alternates.*.kits.H',
        '.alternates.*.kits.H.donor',
        '.alternates.*.kits.H.ops',
        '.alternates.*.kits.H.ops[]{remix}.boxes',
        '.alternates.*.kits.H.ops[]{remix}.components',
        '.alternates.*.kits.H.ops[]{remix}.exclude',
        '.alternates.*.kits.H.ops[]{remix}.from',
        '.alternates.*.kits.H.ops[]{remix}.moved',
        '.alternates.*.kits.H.ops[]{remix}.op',
        '.alternates.*.kits.H.ops[]{remix}.region',
        '.alternates.*.kits.H.ops[]{remix}.to',
        '.alternates.*.kits.H.ops[]{remix}.tolerance',
        '.alternates.*.kits.H.ops[]{remix}.why',
        '.alternates.*.kits.H.part_donors',
        '.alternates.*.kits.H.part_donors.sleeve',
        '.alternates.*.kits.H.socks',
        '.alternates.*.kits.H.socks.colour',
        '.alternates.*.kits.H.splayer_socks',
        '.alternates.*.label',
        '.alternates.*.note',
        '.alternates.*.ops',
        '.alternates.*.ops[]{halo}.colour',
        '.alternates.*.ops[]{halo}.components',
        '.alternates.*.ops[]{halo}.op',
        '.alternates.*.ops[]{halo}.target',
        '.alternates.*.ops[]{halo}.tolerance',
        '.alternates.*.ops[]{halo}.why',
        '.alternates.*.ops[]{halo}.width',
        '.alternates.*.ops[]{outline}.components',
        '.alternates.*.ops[]{outline}.fill',
        '.alternates.*.ops[]{outline}.line',
        '.alternates.*.ops[]{outline}.op',
        '.alternates.*.ops[]{outline}.why',
        '.alternates.*.ops[]{outline}.width',
        '.alternates.*.ops[]{paint}.components',
        '.alternates.*.ops[]{paint}.op',
        '.alternates.*.ops[]{paint}.rects',
        '.alternates.*.ops[]{paint}.rects[].box',
        '.alternates.*.ops[]{paint}.rects[].colour',
        '.alternates.*.ops[]{paint}.why',
        '.alternates.*.ops[]{remix}.boxes',
        '.alternates.*.ops[]{remix}.components',
        '.alternates.*.ops[]{remix}.exclude',
        '.alternates.*.ops[]{remix}.from',
        '.alternates.*.ops[]{remix}.moved',
        '.alternates.*.ops[]{remix}.op',
        '.alternates.*.ops[]{remix}.region',
        '.alternates.*.ops[]{remix}.to',
        '.alternates.*.ops[]{remix}.tolerance',
        '.alternates.*.ops[]{remix}.why',
        '.alternates.*.ops[]{star}.components',
        '.alternates.*.ops[]{star}.op',
        '.alternates.*.ops[]{star}.stars',
        '.alternates.*.ops[]{star}.stars[].R',
        '.alternates.*.ops[]{star}.stars[].c',
        '.alternates.*.ops[]{star}.stars[].fill',
        '.alternates.*.ops[]{star}.stars[].line',
        '.alternates.*.ops[]{star}.stars[].outline',
        '.alternates.*.ops[]{star}.stars[].r',
        '.alternates.*.ops[]{star}.stars[].rot',
        '.alternates.*.ops[]{star}.why',
        '.alternates.*.ops[]{tint}.colour',
        '.alternates.*.ops[]{tint}.components',
        '.alternates.*.ops[]{tint}.op',
        '.alternates.*.ops[]{tint}.why',
        '.alternates.*.retail_pair',
        '.alternates.*.set',
        '.alternates.*.socks',
        '.alternates.*.socks.colour',
        '.alternates.*.socks.why',
        '.alternates.*.sources',
        '.alternates.*.sources[].supports',
        '.alternates.*.sources[].url',
        '.alternates.*.splayer_socks',
        '.alternates.*.style',
        '.alternates.*.team',
        '.alternates.*.unif',
        '.alternates.*.unif.facemask',
        '.alternates.*.unif.turtleneck',
        '.note',
        '.schema',
    )),
}   # end of DOCUMENT_SHAPES


# b81-retail-free-art (coordinator, 2026-11-20): third-party pictures that ship under a licence requiring attribution are
# recorded in these SOURCES files; each such file ships only with its NOTICE.md entry, and every PNG beside a SOURCES file
# needs its record.
THIRD_PARTY_SOURCES = ("data/nfl2k5_kit_rule_fill/SOURCES.json",)


def _check_third_party_notices(root: Path, shipped: set) -> None:
    """Refuse a shipped picture without its source record, or a third-party one (``licence`` in its record) whose
    NOTICE.md attribution is missing: every string of the record's ``notice`` list must appear in NOTICE.md."""
    notice = (root / "NOTICE.md").read_text(encoding="utf-8") if "NOTICE.md" in shipped else ""
    for record in THIRD_PARTY_SOURCES:
        folder = record.rsplit("/", 1)[0] + "/"
        pictures = sorted(r for r in shipped if r.startswith(folder) and r.lower().endswith(".png"))
        if not pictures:
            continue
        if record not in shipped:
            raise ReleaseCheckError(f"pictures ship without their source record: {record}")
        files = json.loads((root / record).read_text(encoding="utf-8")).get("files", {})
        for relative in pictures:
            row = files.get(relative[len(folder):])
            if not isinstance(row, dict):
                raise ReleaseCheckError(f"picture ships without its source record: {relative}")
            if row.get("licence"):
                needed = row.get("notice")
                if not needed or relative not in needed or any(text not in notice for text in needed):
                    raise ReleaseCheckError(f"third-party picture ships without its NOTICE.md attribution: {relative}")


def _reviewed_documents(root: Path) -> dict:
    """b81-retail-free-art (fix 1 of the re-check): every shipped data/*.json the catalog knows, with the SHA-256 of the
    whole document for each one that edits textures (and for every data JSON added after the list began); written
    only by tools/b77/modern_art_png_catalog.py from tools/b81_uniforms/texel_rows.py's measured hashes."""
    catalog = root / MODERN_ART_PNG_CATALOG
    if not catalog.exists():
        return {}
    with catalog.open("rb") as stream:
        data = stream.read(512 * 1024 + 1)
    if len(data) > 512 * 1024 or hashlib.sha256(data).hexdigest() != MODERN_ART_PNG_CATALOG_SHA256:
        raise ReleaseCheckError("reviewed modern-art PNG catalog hash changed")
    return json.loads(data).get("documents", {})


def _check_document_pin(relative: str, path: Path, documents: dict) -> None:
    """A data JSON ships only if the reviewed catalog lists it; one listed with a hash only with exactly that whole-document
    SHA-256 (the PNG catalog's rule, for data documents); one listed by name only, only while it edits no texture."""
    if relative not in documents:
        raise ReleaseCheckError(f"a data document the reviewed catalog does not list: {relative}")
    data = path.read_bytes()
    pinned = documents[relative]
    if pinned is None:
        try:
            document = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            document = None
        if _edits_textures(document):
            raise ReleaseCheckError(f"a data document that edits textures has no reviewed hash: {relative}")
        return
    if hashlib.sha256(data).hexdigest() != pinned:
        raise ReleaseCheckError(f"a data document differs from its reviewed hash: {relative}")


def _check_paint(relative: str, path: Path, reviewed: dict) -> None:
    """Texel data inside a data file must be exactly the reviewed texel data of the catalog: no pixel data may ride in a
    JSON document past the PNG gate, in the glyph document or any other."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return
    _check_shape(relative, document)
    rows = _texel_rows(document)
    found = {owner: hashlib.sha256(json.dumps(ops, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
             for owner, ops in rows.items()}
    expected = reviewed.get(relative, {}).get("rows", {})
    if not found and not expected:
        return
    if set(found) != set(expected) or any(found[k] != expected[k]["sha256"] for k in found):
        raise ReleaseCheckError(f"texel data in a data file is not the reviewed texel data: {relative}")
    # fix 1: no one-texel painting box at all; the small boxes of a row (painting and keep-outs together) cover at most
    # EDGE_LIMIT of the edge texels, measured against the base the step holds and against retail (catalog values)
    ones = sorted(owner for owner, ops in rows.items() if _one_texel_painting_boxes(ops))
    if ones:
        raise ReleaseCheckError(f"one-texel painting boxes in a data file: {relative}: {', '.join(ones[:8])}")
    wide = sorted(owner for owner, row in expected.items() if row.get("small_box_texels")
                  and not all(isinstance(row.get(k), (int, float)) and row[k] <= SMALL_BOX_EDGE_LIMIT
                              for k in ("small_box_edge_base", "small_box_edge_retail")))
    if wide:
        raise ReleaseCheckError(f"small boxes cover too much of the edges or are unmeasured: {relative}: {', '.join(wide[:8])}")
    # Ruling 2 (b81-retail-free-art): judge, not only list. A row whose base is class ii (built from the user's retail
    # disc) must not carry base content: it is refused unless its recorded measures pass (edge overlap within the
    # limit, no base-equal texel, colours that do not follow the base's shading); class i and iii rows pass with their
    # recorded reason.
    refused = sorted(owner for owner, row in expected.items()
                     if row.get("cls") not in ("i", "iii") and not (row.get("cls") == "ii" and row.get("passes") is True))
    if refused:
        shown = ", ".join(refused[:8]) + (f" and {len(refused) - 8} more" if len(refused) > 8 else "")
        raise ReleaseCheckError(f"texel rows carry content of a base built from the retail disc: {relative}: {shown}")


def _super_bowl_logo_pngs(root: Path) -> dict:
    catalog = root / SUPER_BOWL_LOGO_PNG_CATALOG
    if not catalog.exists():
        return {}
    with catalog.open("rb") as stream:
        data = stream.read(256 * 1024 + 1)
    if (len(data) > 256 * 1024
            or hashlib.sha256(data).hexdigest() != SUPER_BOWL_LOGO_PNG_CATALOG_SHA256):
        raise ReleaseCheckError("bundled Super Bowl logo PNG catalog hash changed")
    document = json.loads(data)
    if document.get("schema") != "nfl2k5_super_bowl_logo_pngs/v1":
        raise ReleaseCheckError("bundled Super Bowl logo PNG catalog schema changed")
    return document["files"]


def _validate_reviewed_png(path: Path, relative: str, info, contract: dict, label: str) -> None:
    import struct
    # b778-rh1/rh2: the rookie face banks are 2048x2048 atlases, much larger than a single authored texture.
    limit = (MAX_RELEASE_FILE_BYTES if relative.startswith(("data/nfl2k5_rookie_faces/", "data/nfl2k5_real_portraits/"))
             else 512 * 1024)  # b779-pt1: the real portrait atlases are 2048x2048 like the rookie bank
    if info.st_size != contract["size"] or info.st_size > limit:
        raise ReleaseCheckError(f"reviewed {label} PNG size changed: {relative}")
    with path.open("rb") as stream:
        data = stream.read(info.st_size + 1)
    if (hashlib.sha256(data).hexdigest() != contract["sha256"]
            or data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR"
            or len(data) < 24
            or struct.unpack_from(">II", data, 16) != (contract["width"], contract["height"])):
        raise ReleaseCheckError(f"reviewed {label} PNG identity changed: {relative}")

# Reject only the two known workstation prefixes.  Build the strings from
# fragments so this allowlisted checker does not contain the private paths it
# is designed to detect in staged text.
FORBIDDEN_PRIVATE_TEXT_FRAGMENTS = (
    "/" + "home" + "/" + "noah",
    "/" + "media" + "/" + "noah",
)


class ReleaseCheckError(ValueError):
    """One or more release-stage invariants failed."""


def _safe_relative(value: str, label: str) -> PurePosixPath:
    if "\\" in value:
        raise ReleaseCheckError(f"{label} uses a backslash: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseCheckError(f"{label} is not a safe relative path: {value!r}")
    return path


def read_allowlist(path: Path) -> tuple[frozenset[str], tuple[str, ...]]:
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseCheckError(f"cannot read release allowlist: {exc}") from exc
    exact: set[str] = set()
    prefixes: list[str] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(payload.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        is_prefix = line.endswith("/")
        normalized = line[:-1] if is_prefix else line
        relative = _safe_relative(normalized, f"allowlist line {line_number}").as_posix()
        key = relative + ("/" if is_prefix else "")
        if key in seen:
            raise ReleaseCheckError(f"duplicate release allowlist entry: {key}")
        seen.add(key)
        if is_prefix:
            prefixes.append(relative + "/")
        else:
            exact.add(relative)
    if not exact and not prefixes:
        raise ReleaseCheckError("release allowlist is empty")
    return frozenset(exact), tuple(sorted(prefixes))


def _is_allowed(relative: str, exact: frozenset[str], prefixes: tuple[str, ...]) -> bool:
    return relative in exact or any(relative.startswith(prefix) for prefix in prefixes)


def _is_declared_directory(relative: str, exact: frozenset[str], prefixes: tuple[str, ...]) -> bool:
    prefix = relative.rstrip("/") + "/"
    return any(item.startswith(prefix) for item in exact) or any(
        item == prefix or item.startswith(prefix) or prefix.startswith(item)
        for item in prefixes
    )


def _is_reviewed_metadata_or_parent(relative: PurePosixPath) -> bool:
    value = relative.as_posix().rstrip("/")
    prefix = value + "/"
    return value in REVIEWED_METADATA or any(
        item.startswith(prefix) for item in REVIEWED_METADATA
    )


def _forbidden_path(relative: PurePosixPath) -> str | None:
    if _is_reviewed_metadata_or_parent(relative):
        return None
    for component in relative.parts:
        folded = component.casefold()
        if folded in FORBIDDEN_COMPONENTS:
            return component
        if any(folded.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            return component
    return None


def _iter_tree(root: Path) -> Iterable[tuple[Path, os.stat_result]]:
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ReleaseCheckError(f"cannot scan release directory {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ReleaseCheckError(f"cannot inspect release entry {path}: {exc}") from exc
            yield path, info
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)


def _validate_reviewed_icon(path: Path, relative: str, info: os.stat_result) -> str:
    """Confirm the staged icon is byte-for-byte the reviewed one."""
    if info.st_size != REVIEWED_ICON_SIZE:
        raise ReleaseCheckError(f"reviewed application icon size changed: {relative}")
    payload = path.read_bytes()
    if len(payload) != REVIEWED_ICON_SIZE:
        raise ReleaseCheckError(f"release file changed while being read: {relative}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != REVIEWED_ICON_SHA256:
        raise ReleaseCheckError(f"reviewed application icon hash changed: {relative}")
    if not payload.startswith(ICO_MAGIC):
        raise ReleaseCheckError(
            f"reviewed application icon is no longer a Windows icon: {relative}"
        )
    return digest


def _hash_and_validate_text(
    path: Path, relative: str, size: int, maximum_size: int,
) -> tuple[str, str]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    completed = 0
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            completed += len(block)
            if completed > maximum_size:
                raise ReleaseCheckError(
                    f"release file exceeds its reviewed size ceiling: {relative}"
                )
            digest.update(block)
            chunks.append(block)
    if completed != size:
        raise ReleaseCheckError(f"release file changed while being read: {relative}")
    payload = b"".join(chunks)
    if b"\0" in payload:
        raise ReleaseCheckError(f"binary NUL byte in release text file: {relative}")
    # Format-aware source code legitimately names these signatures. Refuse a
    # disguised container whose payload starts with one; ordinary UTF-8 code
    # that documents or checks the signature remains distributable tooling.
    if any(payload.startswith(magic) for magic in RETAIL_MAGIC):
        raise ReleaseCheckError(f"retail/container magic in release file: {relative}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseCheckError(f"release file is not UTF-8 text: {relative}") from exc
    folded_text = text.casefold()
    if any(fragment.casefold() in folded_text
           for fragment in FORBIDDEN_PRIVATE_TEXT_FRAGMENTS):
        raise ReleaseCheckError(f"private host path in release text file: {relative}")
    # Long whitespace-free strings are typical of embedded base64/binary blobs,
    # never a required product-code resource in this allowlist.
    token_length = 0
    for character in text:
        if character.isspace():
            token_length = 0
        else:
            token_length += 1
            if token_length > 4096:
                raise ReleaseCheckError(
                    f"possible embedded binary blob in release file: {relative}"
                )
    return digest.hexdigest(), text


def _metadata_contains_payload(value: object) -> bool:
    """Reject byte arrays/data URIs even inside an otherwise valid JSON file."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                folded = str(key).casefold()
                if folded in {
                    "base64", "data_uri", "payload", "payload_base64",
                    "raw_bytes", "retail_bytes", "rgba_bytes",
                } and isinstance(item, (str, list)):
                    return True
                pending.append(item)
        elif isinstance(current, list):
            if len(current) > 256 and all(
                type(item) is int and 0 <= item <= 255 for item in current
            ):
                return True
            pending.extend(current)
        elif isinstance(current, str):
            folded = current.casefold()
            if folded.startswith("data:") or folded.startswith("base64:"):
                return True
    return False


def _validate_reviewed_metadata(
    relative: str, size: int, digest: str, text: str,
) -> None:
    expected_size, expected_digest, expected_schema = REVIEWED_METADATA[relative]
    if size != expected_size or digest != expected_digest:
        raise ReleaseCheckError(
            f"reviewed metadata size/hash changed: {relative}"
        )
    try:
        document = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ReleaseCheckError(f"reviewed metadata is invalid JSON: {relative}") from exc
    if not isinstance(document, dict) or document.get("schema") != expected_schema:
        raise ReleaseCheckError(f"reviewed metadata schema changed: {relative}")
    if _metadata_contains_payload(document):
        raise ReleaseCheckError(f"retail payload data found in metadata: {relative}")


def audit_release(root: Path, allowlist: Path) -> dict[str, object]:
    private_paths, private_hashes = _private_boundary()
    try:
        root_info = root.lstat()
    except FileNotFoundError as exc:
        raise ReleaseCheckError(f"release root does not exist: {root}") from exc
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise ReleaseCheckError("release root must be a non-symlink directory")
    release_root = root.resolve(strict=True)
    exact, prefixes = read_allowlist(allowlist)

    seen_files: set[str] = set()
    seen_directories: set[str] = set()
    folded_paths: set[str] = set()
    total_bytes = 0
    reviewed_metadata_count = 0
    reviewed_icon_count = 0
    reviewed_scorebug_png_count = 0
    reviewed_anniversary_png_count = 0
    reviewed_modern_art_png_count = 0
    reviewed_super_bowl_logo_png_count = 0
    scorebug_pngs = _scorebug_template_pngs(release_root)
    anniversary_pngs = _anniversary_field_pngs(release_root)
    modern_art_pngs = _modern_art_pngs(release_root)
    super_bowl_logo_pngs = _super_bowl_logo_pngs(release_root)
    reviewed_paint = _reviewed_paint(release_root)
    if (set(modern_art_pngs) & (set(scorebug_pngs) | set(anniversary_pngs))
            or set(super_bowl_logo_pngs) & (set(scorebug_pngs) | set(anniversary_pngs) | set(modern_art_pngs))):
        raise ReleaseCheckError("a PNG is listed in more than one reviewed catalog")
    for path, info in _iter_tree(release_root):
        relative_path = PurePosixPath(path.relative_to(release_root).as_posix())
        relative = relative_path.as_posix()
        if relative in private_paths:
            raise ReleaseCheckError(f"private marks/evidence path is forbidden: {relative}")
        folded = relative.casefold()
        if folded in folded_paths:
            raise ReleaseCheckError(f"case-colliding release path: {relative}")
        folded_paths.add(folded)
        forbidden = _forbidden_path(relative_path)
        if forbidden is not None:
            raise ReleaseCheckError(
                f"forbidden extracted/build/local-data path component {forbidden!r}: {relative}"
            )
        if stat.S_ISLNK(info.st_mode):
            raise ReleaseCheckError(f"release symlinks are forbidden: {relative}")
        if stat.S_ISDIR(info.st_mode):
            if not _is_declared_directory(relative, exact, prefixes):
                raise ReleaseCheckError(f"undeclared release directory: {relative}")
            seen_directories.add(relative + "/")
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ReleaseCheckError(f"special release filesystem entry is forbidden: {relative}")
        with path.open("rb") as handle:
            private_digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if private_digest in private_hashes:
            raise ReleaseCheckError(f"private marks/evidence bytes are forbidden: {relative}")
        # more than one link is a hard link; Windows directory-listing stats report 0 (unknown), never 1
        if info.st_nlink > 1:
            raise ReleaseCheckError(f"hardlinked release file is forbidden: {relative}")
        # Windows reports 0o666 on every regular file; the mode bits carry no meaning there.
        if info.st_mode & stat.S_IWOTH and os.name != "nt":
            raise ReleaseCheckError(f"world-writable release file is forbidden: {relative}")
        if not _is_allowed(relative, exact, prefixes):
            raise ReleaseCheckError(f"file is absent from the release allowlist: {relative}")
        if relative == REVIEWED_ICON:
            # The only non-text file here, and the exemption is anchored to this
            # one path: ".ico" stays an unapproved suffix everywhere else, so
            # nothing can ship simply by taking the extension.  Whether the icon
            # is *present* is not decided here -- the allowlist declares it, and
            # the completeness check below refuses a release that omits it.
            _validate_reviewed_icon(path, relative, info)
            reviewed_icon_count += 1
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        equipment_contracts = {
            "tools/nfl2k5_equipment_optimal": (16504, "949aad6a251de3f039f83bff15d4aa033183c250dbeadd1029e7c79dee4817c4"),
            "tools/nfl2k5_equipment_optimal.c": (4648, "6c9c7470d40ce3b99ac000fe75bd51c7d2fbeb44f783e313eb7b7dee0f0b8390"),
        }
        if relative in equipment_contracts:
            expected_size, expected_sha256 = equipment_contracts[relative]
            if info.st_size != expected_size:
                raise ReleaseCheckError(f"reviewed equipment helper size changed: {relative}")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != expected_sha256:
                raise ReleaseCheckError(f"reviewed equipment helper hash changed: {relative}")
            if relative == "tools/nfl2k5_equipment_optimal":
                if payload[:4] != b"\x7fELF":
                    raise ReleaseCheckError("reviewed equipment helper is not ELF")
                if os.name != "nt" and (info.st_mode & 0o777) != 0o755:
                    raise ReleaseCheckError("reviewed equipment helper must be mode 0755")
            else:
                payload.decode("utf-8")
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        suffix = path.suffix.casefold()
        if relative in scorebug_pngs:
            _validate_scorebug_template_png(path, relative, info, scorebug_pngs[relative])
            reviewed_scorebug_png_count += 1
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        if relative in anniversary_pngs:
            _validate_reviewed_png(path, relative, info, anniversary_pngs[relative], "Anniversary")
            reviewed_anniversary_png_count += 1
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        if relative in modern_art_pngs:
            _validate_reviewed_png(path, relative, info, modern_art_pngs[relative], "modern-art")
            reviewed_modern_art_png_count += 1
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        if relative in super_bowl_logo_pngs:
            _validate_reviewed_png(path, relative, info, super_bowl_logo_pngs[relative], "bundled Super Bowl logo")
            reviewed_super_bowl_logo_png_count += 1
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        if suffix == ".span":
            # b778-ss1: authored span patches are binary inputs; the explicit allowlist entry is the review.
            if info.st_size > MAX_RELEASE_FILE_BYTES:
                raise ReleaseCheckError(f"release file exceeds its reviewed size ceiling: {relative}")
            payload = path.read_bytes()
            if len(payload) != info.st_size:
                raise ReleaseCheckError(f"release file changed while being read: {relative}")
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        if suffix in FORBIDDEN_SUFFIXES:
            raise ReleaseCheckError(f"retail/container/media suffix is forbidden: {relative}")
        if suffix not in ALLOWED_SUFFIXES and path.name.casefold() not in ALLOWED_SUFFIXLESS_NAMES:
            raise ReleaseCheckError(f"unapproved release file type: {relative}")
        if suffix in EXECUTABLE_LAUNCHER_SUFFIXES and not info.st_mode & stat.S_IXUSR:
            raise ReleaseCheckError(f"launcher script is not executable: {relative}")
        metadata_contract = REVIEWED_METADATA.get(relative)
        maximum_size = (
            metadata_contract[0] if metadata_contract is not None
            else MAX_RELEASE_FILE_BYTES
        )
        if info.st_size > maximum_size:
            raise ReleaseCheckError(
                f"release file exceeds its reviewed size ceiling: {relative}"
            )
        digest, text = _hash_and_validate_text(
            path, relative, info.st_size, maximum_size
        )
        if any(
            marker in relative.casefold()
            for marker in PRIVATE_AUDIO_ORIGIN_NAME_MARKERS
        ):
            raise ReleaseCheckError(
                f"private audio-origin inventory path is forbidden: {relative}"
            )
        if suffix == ".json":
            try:
                json_document = json.loads(text)
            except (ValueError, TypeError):
                json_document = None
            if isinstance(json_document, dict) and json_document.get("schema") \
                    in PRIVATE_AUDIO_ORIGIN_SCHEMAS:
                raise ReleaseCheckError(
                    f"private audio-origin inventory schema is forbidden: {relative}"
                )
        if digest in KNOWN_RETAIL_SHA256:
            raise ReleaseCheckError(f"known retail payload hash in release: {relative}")
        if digest == PRIVATE_INVENTORY_SHA256 or relative == PRIVATE_INVENTORY_PATH:
            raise ReleaseCheckError(
                f"private user-XISO inventory is forbidden in release: {relative}"
            )
        if metadata_contract is not None:
            _validate_reviewed_metadata(relative, info.st_size, digest, text)
            reviewed_metadata_count += 1
        if suffix == ".svg":
            try:
                ET.parse(path)
            except (ET.ParseError, OSError) as exc:
                raise ReleaseCheckError(f"invalid SVG XML in release: {relative}") from exc
        seen_files.add(relative)
        total_bytes += info.st_size

    reviewed_documents = _reviewed_documents(release_root)
    for relative in sorted(seen_files):
        if relative.endswith(".json") and relative.startswith("data/"):
            _check_document_pin(relative, release_root / relative, reviewed_documents)
            _check_paint(relative, release_root / relative, reviewed_paint)
    _check_third_party_notices(release_root, seen_files)
    missing_files = sorted(exact - seen_files)
    missing_prefixes = sorted(prefix for prefix in prefixes if prefix not in seen_directories)
    if missing_files or missing_prefixes:
        raise ReleaseCheckError(
            f"release is incomplete; missing files={missing_files}, missing directories={missing_prefixes}"
        )
    return {
        "schema": "2k5_mod_studio_release_audit/v1",
        "file_count": len(seen_files),
        "directory_count": len(seen_directories),
        "total_bytes": total_bytes,
        "reviewed_metadata_file_count": reviewed_metadata_count,
        "reviewed_icon_count": reviewed_icon_count,
        "reviewed_scorebug_template_png_count": reviewed_scorebug_png_count,
        "reviewed_anniversary_field_png_count": reviewed_anniversary_png_count,
        "reviewed_modern_art_png_count": reviewed_modern_art_png_count,
        "reviewed_super_bowl_logo_png_count": reviewed_super_bowl_logo_png_count,
        "private_generated_inventories_included": False,
        "retail_payloads_included": False,
        "symlinks_included": False,
        "undeclared_files_included": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_root", type=Path, help="already-staged release directory")
    parser.add_argument(
        "--allowlist",
        type=Path,
        help="allowlist file (default: <release-root>/packaging/release-allowlist.txt)",
    )
    args = parser.parse_args(argv)
    allowlist = args.allowlist or args.release_root / "packaging/release-allowlist.txt"
    try:
        report = audit_release(args.release_root, allowlist)
    except ReleaseCheckError as exc:
        print(f"2K5_MOD_STUDIO_RELEASE_REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        "2K5_MOD_STUDIO_RELEASE_PASS "
        f"files={report['file_count']} directories={report['directory_count']} "
        f"bytes={report['total_bytes']} "
        f"metadata={report['reviewed_metadata_file_count']} "
        "private_inventory=false retail=false symlinks=false undeclared=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
