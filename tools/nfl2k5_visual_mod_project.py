#!/usr/bin/env python3
"""Build or independently verify one fail-closed NFL 2K5 visual/data-mod XISO.

The project file is the only user-authored control file. Existing proved PNG
importers and fixed-size audits own every codec/layout decision; this module
only composes their bounded replacement spans into one layout-identical copy
of the retail XISO.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import platform_compat  # noqa: E402
from mod_editor.core.model import SourceRecord  # noqa: E402
from mod_editor.core.errors import ModEditorError  # noqa: E402
from mod_editor.core.nfl2k5_audio_catalog import (  # noqa: E402
    Nfl2k5AudioCatalog,
)
from mod_editor.core.nfl2k5_audio_origin_authorization import (  # noqa: E402
    AuthorizedPcm16Wav,
    authorize_strict_pcm16_wav,
    require_authorized_pcm16_wav,
)
from mod_editor.core.nfl2k5_audio_source_containment import (  # noqa: E402
    Nfl2k5AudioSourceContainmentScanner,
    Nfl2k5AudioSourceContainmentStore,
    PRIVATE_RELATIVE_PATH as CONTAINMENT_PRIVATE_RELATIVE_PATH,
)
from mod_editor.core.nfl2k5_audio_source_fingerprints import (  # noqa: E402
    Nfl2k5AudioSourceFingerprintStore,
    PRIVATE_RELATIVE_PATH as EXACT_PRIVATE_RELATIVE_PATH,
)
from mod_editor.core.nfl2k5_ausb_build_adapter import (  # noqa: E402
    _compile_authorized_streaming_slot,
)
from mod_editor.core.nfl2k5_ausb_fixed_slots import (  # noqa: E402
    StreamingSlotCatalog,
    build_streaming_slot_catalog,
)
from mod_editor.core.nfl2k5_source_cache import (  # noqa: E402
    INVENTORY_RELATIVE as SOURCE_CACHE_INVENTORY_RELATIVE,
    PACK_FOLDER as SOURCE_CACHE_PACK_FOLDER,
    SOURCE_SHA256 as AUDIO_SOURCE_SHA256,
    SOURCE_SIZE as AUDIO_SOURCE_SIZE,
    SourceCache,
)


def _load_scorebug_adapter() -> Any:
    """Load the pinned bridge file without executing product package imports."""

    path = ROOT / "mod_editor/core/nfl2k5_scorebug_unified_adapter.py"
    spec = importlib.util.spec_from_file_location(
        "_nfl2k5_scorebug_unified_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load the unified scorebug adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_unif_color_adapter() -> Any:
    """Load the facemask/turtleneck colour compiler."""

    path = ROOT / "mod_editor/core/nfl2k5_unif_color_writer.py"
    spec = importlib.util.spec_from_file_location(
        "_nfl2k5_unif_color_unified_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load the unified Unif colour adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_p8_texture_adapter() -> Any:
    """Load the standalone-P8 compiler without product package imports."""

    path = ROOT / "mod_editor/core/nfl2k5_p8_texture_writer.py"
    spec = importlib.util.spec_from_file_location(
        "_nfl2k5_p8_texture_unified_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load the unified P8 texture adapter")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__], which is None for an unregistered module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_stadium_texture_adapter() -> Any:
    """Load the reviewed exact-span compiler without product package imports."""

    path = ROOT / "mod_editor/core/nfl2k5_stadium_texture_writer.py"
    spec = importlib.util.spec_from_file_location(
        "_nfl2k5_stadium_texture_unified_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load the unified Stadium texture adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_safe_text_adapter() -> Any:
    """Load the fixed-text resolver without importing the product GUI stack."""

    path = ROOT / "mod_editor/core/nfl2k5_safe_text_banks.py"
    spec = importlib.util.spec_from_file_location(
        "_nfl2k5_safe_text_unified_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load the unified fixed-text adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_fixed_audo_adapter() -> Any:
    """Load the retail-free fixed-allocation AUDO resolver/encoder."""

    path = ROOT / "mod_editor/core/nfl2k5_audo_fixed_slots.py"
    spec = importlib.util.spec_from_file_location(
        "_nfl2k5_audo_fixed_slots_unified_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError("could not load the unified standalone-audio adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scorebug_adapter = _load_scorebug_adapter()
stadium_texture_adapter = _load_stadium_texture_adapter()
p8_texture_adapter = _load_p8_texture_adapter()
unif_color_adapter = _load_unif_color_adapter()
safe_text_adapter = _load_safe_text_adapter()
fixed_audo_adapter = _load_fixed_audo_adapter()

import nfl2k5_jersey_png_workflow as ownership
import nfl_jersey_tset_png_import as jersey_import
import nfl_jersey_tset_targets as jersey_targets
import nfl_sleeve_tset_png_import as sleeve_import
import nfl_sleeve_tset_targets as sleeve_targets
import nfl_pants_tset_png_import as pants_import
import nfl_pants_tset_targets as pants_targets
import nfl_live_helmet_txtr_png_import as helmet_import
import nfl_live_helmet_txtr_targets as helmet_targets
import nfl_live_numbers_nameplate_png_import as live_art_import
import nfl_live_numbers_nameplate_targets as live_art_targets
import nfl_team_select_card_png_import as card_import
import nfl_team_select_card_targets as card_targets
import nfl_live_face_texture_png_import as face_import
import nfl_live_face_texture_targets as face_targets
import nfl_create_team_field_art_png_import as field_import
import nfl_create_team_field_art_inventory as field_inventory
import nfl_player_portrait_png_import as portrait_import
import nfl_player_portrait_targets as portrait_targets
import nfl_crib_team_photo_png_import as crib_photo_import
import nfl_crib_team_photo_targets as crib_photo_targets
import nfl_crib_bar_monitor_png_xiso as crib_scene_import
from nfl_outer import parse_archive, read_entry_range
import nfl_roster
import nfl_audo_wav_xiso_workflow as audo_import
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_visual_mod_project/v1"
BUILD_SCHEMA = "nfl2k5_visual_mod_build/v1"
VERIFY_SCHEMA = "nfl2k5_visual_mod_verify/v1"

DEFAULT_INDEX = ownership.DEFAULT_INDEX
DEFAULT_INVENTORY = ownership.DEFAULT_INVENTORY
INDEX_SIZE = ownership.INDEX_SIZE
INDEX_SHA256 = ownership.INDEX_SHA256
INVENTORY_SIZE = ownership.INVENTORY_SIZE
INVENTORY_SHA256 = ownership.INVENTORY_SHA256
MAX_PROJECT_BYTES = 64 * 1024 * 1024
MAX_EDITS = 25_000
MAX_TOTAL_INPUT_BYTES = 1024 * 1024 * 1024
HASH_BLOCK = 16 * 1024 * 1024

REPORTS = {
    "torso": jersey_targets.DEFAULT_REPORT,
    "sleeve": sleeve_targets.DEFAULT_REPORT,
    "pants": pants_targets.DEFAULT_REPORT,
    "live_helmet": helmet_targets.DEFAULT_REPORT,
    "live_number_nameplate": live_art_targets.DEFAULT_REPORT,
    "team_select": ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json",
    "live_face": face_targets.DEFAULT_REPORT,
    "create_team_field_art": field_inventory.DEFAULT_JSON,
    "team_identity": ROOT / "reports/assets/nfl2k5_team_identity_audit.json",
    "player_roster": ROOT / "reports/assets/nfl2k5_player_roster_audit.json",
    "player_portrait": ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json",
    "crib_team_photo": ROOT / crib_photo_targets.DEFAULT_REPORT,
    "scorebug_texture": scorebug_adapter.SCOREBUG_REPORT,
    "audo_audio": fixed_audo_adapter.CAPACITY_REPORT,
}

REPORT_SHA256 = {
    "torso": jersey_targets.REPORT_SHA256,
    "sleeve": sleeve_targets.REPORT_SHA256,
    "pants": pants_targets.REPORT_SHA256,
    "live_helmet": helmet_targets.REPORT_SHA256,
    "live_number_nameplate": live_art_targets.REPORT_SHA256,
    "team_select": card_targets.REPORT_SHA256,
    "live_face": face_targets.REPORT_SHA256,
    "create_team_field_art":
        "6014d0ca882c76f0bba68a14338e357d7f33a745e9818856c57da7979ed1a4f5",
    "team_identity":
        "9ddae13f0234b628e28fa10d6935b73e1447362eb41701dc9c45f9dc0a188d7d",
    "player_roster":
        "795336ad0092e6ba6c806e314bb7515ecc0e11103bd889557229f4f1a92451c2",
    "player_portrait": portrait_targets.REPORT_SHA256,
    "crib_team_photo": crib_photo_targets.REPORT_SHA256,
    "scorebug_texture": scorebug_adapter.SCOREBUG_REPORT_SHA256,
    "audo_audio": fixed_audo_adapter.CAPACITY_REPORT_SHA256,
}

TSET_FIELDS = {
    "kind", "asset_code", "side", "variant", "clean_png", "mud_png", "mud_mode",
}
HELMET_FIELDS = {"kind", "asset_code", "side", "variant", "family", "png"}
LIVE_ART_FIELDS = {
    "kind", "asset_code", "side", "variant", "family", "digit", "png",
}
CARD_FIELDS = {
    "kind", "asset_code", "side", "style", "family", "resolution", "png",
}
FACE_FIELDS = {"kind", "face_id", "family", "png"}
FIELD_ART_FIELDS = {"kind", "logo_code", "weather", "texture", "png"}
TEAM_IDENTITY_FIELDS = {
    "kind", "team_index", "city", "nickname", "abbreviation",
    "city_abbreviation",
}
PLAYER_ROSTER_FIELDS = {
    "kind", "primary_player_index", "first_name", "last_name", "jersey_number",
}
PLAYER_PORTRAIT_FIELDS = {"kind", "portrait_id", "png"}
CRIB_TEAM_PHOTO_FIELDS = {"kind", "selector", "png"}
CRIB_SCENE_TEXTURE_FIELDS = {"kind", "selector", "png"}
SCOREBUG_TEXTURE_FIELDS = {"kind", "target", "png"}
STADIUM_TEXTURE_FIELDS = {"kind", "target", "png"}
P8_TEXTURE_FIELDS = {"kind", "asset_id", "png"}
UNIF_COLOR_FIELDS = {"kind", "facemask", "turtleneck"}
UNIVERSAL_FIXED_TEXT_FIELDS = {"kind", "selector", "text"}
ROSTER_TEAM_TEXT_FIELDS = {
    "kind", "resource_outer_index", "team_index", "changes",
}
ROSTER_PLAYER_TEXT_FIELDS = {
    "kind", "resource_outer_index", "primary_player_index", "changes",
}
ROSTER_TEAM_TEXT_CHANGE_FIELDS = frozenset({
    "nickname", "abbreviation", "city", "city_abbreviation",
})
ROSTER_PLAYER_TEXT_CHANGE_FIELDS = frozenset({
    "first_name", "last_name", "jersey_number",
})
MENU_BACK_AUDIO_FIELDS = {"kind", "wav"}
AUDO_AUDIO_FIELDS = {"kind", "asset_id", "wav"}
AUSB_AUDIO_FIELDS = {"kind", "asset_id", "wav"}
ROSTER_TEAM_PROVIDER_KIND = "roster_team_text"
ROSTER_PLAYER_PROVIDER_KIND = "roster_player_text"
MENU_BACK_AUDIO_KIND = "menu_back_audio"
AUDO_AUDIO_KIND = "audo_audio"
AUSB_AUDIO_KIND = "ausb_audio"
CRIB_TEAM_PHOTO_KIND = "crib_team_photo"
CRIB_SCENE_TEXTURE_KIND = "crib_scene_texture"
SCOREBUG_TEXTURE_KIND = scorebug_adapter.SCOREBUG_TEXTURE_KIND
UNIF_COLOR_KIND = "unif_color"
P8_TEXTURE_KIND = "p8_texture"
STADIUM_TEXTURE_KIND = "stadium_texture"
STADIUM_TEXTURE_TARGET = stadium_texture_adapter.TARGET_TEXTURE_ID
STADIUM_TEXTURE_SELECTOR_RE = stadium_texture_adapter.SELECTOR_RE
UNIVERSAL_FIXED_TEXT_KIND = safe_text_adapter.SAFE_TEXT_PROVIDER_KIND
ROSTER_REPORT_FREE_KINDS = frozenset({
    ROSTER_TEAM_PROVIDER_KIND,
    ROSTER_PLAYER_PROVIDER_KIND,
})
REPORT_FREE_KINDS = ROSTER_REPORT_FREE_KINDS | {
    MENU_BACK_AUDIO_KIND,
    AUSB_AUDIO_KIND,
    STADIUM_TEXTURE_KIND,
    P8_TEXTURE_KIND,
    UNIF_COLOR_KIND,
    CRIB_SCENE_TEXTURE_KIND,
    UNIVERSAL_FIXED_TEXT_KIND,
}
AUDIO_KINDS = frozenset({
    MENU_BACK_AUDIO_KIND,
    AUDO_AUDIO_KIND,
    AUSB_AUDIO_KIND,
})
AUSB_LOGICAL_ASSET_RE = re.compile(
    r"nfl2k5\.audio\.ausb\.o\d{4}\.c\d{4}\.r\d{5}\Z"
)
AUSB_CANONICAL_ASSET_RE = re.compile(
    r"nfl2k5\.audio\.ausb\.physical\.o\d{4}\."
    r"s[0-9a-f]{10}\.n[0-9a-f]{10}\Z"
)
TEAM_IDENTITY_POINTERS = {
    "nickname": 0x104,
    "abbreviation": 0x108,
    "city": 0x138,
    "city_abbreviation": 0x13C,
}
ROST_OUTER_PACK_OFFSET = 0x00392800
# The pack holding the compressed-SCNE Crib texture, by name rather than by
# sector: sector numbers differ between a pressed disc and any rebuild.
CRIB_SCENE_PACK_NAME = "c"
ROST_WRAPPER_SIZE = 0x20
ROST_TEAM_STRIDE = 0x1F4
ROST_BODY_SIZE = 593_760
ROST_TEAM_BASE = 0x41C8
ROST_TEAM_COUNT = 52
ROST_TEAM_SLOTS = 65
ROST_TEAM_COUNT_FIELD = 0x11C
ROST_PRIMARY_BASE = 0x0AFA8
ROST_PRIMARY_COUNT = 2479
ROST_SECONDARY_BASE = 0x3DD14
ROST_SECONDARY_COUNT = 68
ROST_PLAYER_STRIDE = 0x54
PLAYER_FIRST_POINTER_FIELD = 0x10
PLAYER_LAST_POINTER_FIELD = 0x14
PLAYER_JERSEY_FIELD = 0x20
PLAYER_JERSEY_MASK = 0x3F8
PLAYER_JERSEY_SHIFT = 3
ROSTER_POINTER_TEXT_FIELDS = (
    "nickname", "abbreviation", "asset_code", "city", "city_abbreviation",
)
UNIVERSAL_TEXT_SELECTOR_RE = re.compile(
    r"(?:strg:\d+:\d+:message:\d+|"
    r"cred:\d+:\d+:string:\d+|"
    r"situ:moment:\d+:(?:title|historical_description|challenge_objective|date)|"
    r"triv:question:\d+:(?:category|subject|question|answer_a|answer_b|answer_c|answer_d))\Z"
)


class ProjectError(ValueError):
    """Raised when any project, source, target, output, or proof fails closed."""


@dataclass(frozen=True)
class RosterResourceView:
    """Strictly decoded ROST bytes and their physical pack-0 ownership."""

    outer_index: int
    outer_id: str
    outer_size: int
    pack_offset: int
    body: bytes
    parsed: Mapping[str, Any]

    @property
    def body_size(self) -> int:
        return len(self.body)

    @property
    def resource_label(self) -> str:
        return str(self.parsed["label"])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProjectError(message)


def fixed_utf16le(value: str, allocation: int, label: str) -> bytes:
    """Encode a shorter/equal UTF-16 string into one existing allocation."""

    require(type(value) is str and bool(value), f"{label} cannot be empty")
    require("\0" not in value, f"{label} cannot contain a NUL character")
    require(allocation >= 2 and allocation % 2 == 0,
            f"{label} has an invalid UTF-16 allocation")
    try:
        encoded = value.encode("utf-16le")
    except UnicodeEncodeError as exc:
        raise ProjectError(f"{label} contains invalid Unicode") from exc
    required = len(encoded) + 2
    limit = allocation // 2 - 1
    if required > allocation:
        used = len(encoded) // 2
        raise ProjectError(
            f"{label} uses {used} UTF-16 units; its existing allocation allows "
            f"{limit}. Some emoji and uncommon symbols use two units."
        )
    payload = encoded + b"\0\0" + bytes(allocation - required)
    require(len(payload) == allocation,
            f"{label} did not preserve its fixed allocation")
    return payload


def load_roster_resources(
    pack0: Path,
    inventory: Path,
    outer_indices: Iterable[int],
) -> dict[int, RosterResourceView]:
    """Load only explicitly selected current/historical ROST resources."""

    wanted = {int(value) for value in outer_indices}
    require(bool(wanted), "sparse roster project selected no ROST resources")
    try:
        archive = parse_archive(pack0)
        records = nfl_roster.parse_inventory(inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ProjectError(f"could not open the NFL 2K5 roster catalog: {exc}") from exc
    selected = [record for record in records if record.outer_index in wanted]
    found = {record.outer_index for record in selected}
    require(found == wanted,
            f"ROST resources are missing from the index: {sorted(wanted - found)}")
    result: dict[int, RosterResourceView] = {}
    for record in selected:
        try:
            _raw, body = nfl_roster.load_body(archive, record)
            parsed = nfl_roster.parse_resource(archive, record)
            entry = archive.entries[record.outer_index]
        except (OSError, ValueError, KeyError, IndexError) as exc:
            raise ProjectError(
                f"could not parse ROST outer {record.outer_index}: {exc}"
            ) from exc
        require(len(entry.segments) == 1,
                f"ROST outer {record.outer_index} crosses archive packs")
        segment = entry.segments[0]
        require(segment.pack_ordinal == 0 and segment.size == entry.size,
                f"ROST outer {record.outer_index} is not wholly owned by pack 0")
        require(digest(body) == parsed.get("body_sha256"),
                f"ROST outer {record.outer_index} changed while parsing")
        result[record.outer_index] = RosterResourceView(
            record.outer_index,
            record.outer_id,
            record.outer_size,
            segment.pack_offset,
            body,
            parsed,
        )
    return result


def roster_text_reference_counts(view: RosterResourceView) -> Counter[int]:
    """Count all decoded ROST pointer domains before allowing an edit."""

    parsed = view.parsed
    result: Counter[int] = Counter({0x20: 1})

    def add(value: object) -> None:
        if value is not None:
            result[int(value)] += 1

    for team in parsed["teams"]:
        for field in ROSTER_POINTER_TEXT_FIELDS:
            add(team.get(f"{field}_offset"))
    for player in parsed["players"]:
        add(player.get("first_name_offset"))
        add(player.get("last_name_offset"))
    for stadium in parsed["stadiums"]:
        for field in (
            "name", "location", "asset_code", "display_name", "secondary_label",
        ):
            add(stadium.get(f"{field}_offset"))
    for coach in parsed["coaches"]:
        for field in (
            "first_name", "last_name", "description_1", "description_2",
            "description_3",
        ):
            add(coach.get(f"{field}_offset"))
    for college in parsed["colleges"]:
        add(college.get("name_offset"))
    for descriptor in parsed["historic_descriptors"]:
        add(descriptor.get("slug_offset"))
    for table_name in ("team_labels", "generated_names"):
        for item in parsed[table_name]:
            record = int(item["offset"])
            for relative in (0, 4):
                add(nfl_roster.relative_pointer(
                    view.body,
                    record + relative,
                    f"outer {view.outer_index} {table_name} {item['index']}",
                ))
    return result


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(HASH_BLOCK), b""):
            result.update(block)
    return result.hexdigest()


def offset_digest(offsets: Iterable[int], width: str) -> str:
    result = hashlib.sha256()
    for value in offsets:
        result.update(struct.pack(width, value))
    return result.hexdigest()


def difference_runs(before: bytes, after: bytes) -> list[list[int]]:
    require(len(before) == len(after), "replacement changed fixed span size")
    runs: list[list[int]] = []
    for index, pair in enumerate(zip(before, after)):
        if pair[0] == pair[1]:
            continue
        if not runs or index != runs[-1][1] + 1:
            runs.append([index, index])
        else:
            runs[-1][1] = index
    return runs


def run_count(runs: list[list[int]]) -> int:
    return sum(end - start + 1 for start, end in runs)


def iter_run_offsets(runs: list[list[int]], base: int = 0) -> Iterable[int]:
    for start, end in runs:
        yield from range(base + start, base + end + 1)


@dataclass(frozen=True)
class ProjectFile:
    path: Path
    payload: bytes
    value: dict[str, Any]
    identity: tuple[int, int]


@dataclass(frozen=True)
class InputPin:
    path: Path
    payload: bytes
    size: int
    sha256: str
    identity: tuple[int, int]


@dataclass
class PreparedEdit:
    order: int
    kind: str
    selector: str
    project_edit: dict[str, Any]
    input_sha256: dict[str, str | None]
    target: dict[str, Any]
    pack_path: str
    pack_sector: int
    pack_size: int
    pack_sha256: str
    pack_offset: int
    absolute: int
    retail_span_sha256: str
    replacement_path: Path
    replacement_size: int
    replacement_sha256: str
    relative_runs: list[list[int]]
    import_report_path: Path
    import_report_sha256: str
    preview_paths: list[tuple[str, Path, int, str]]


@dataclass
class PreparedProject:
    edits: list[PreparedEdit]
    temp_root: ownership.OwnedPath
    temp_files: list[ownership.OwnedPath]
    input_pins: dict[Path, InputPin]
    report_pins: dict[str, InputPin]


@dataclass(frozen=True)
class AudioOriginContext:
    """Private, process-local source-origin gates and complete AUSB topology."""

    exact_inventory: Any
    containment_inventory: Any
    streaming_catalog: StreamingSlotCatalog


def read_regular_bounded(path: Path, maximum: int, label: str) \
        -> tuple[Path, bytes, tuple[int, int]]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ProjectError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        require(stat.S_ISREG(opened.st_mode) and
                identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(resolved) == identity and
                0 < opened.st_size <= maximum,
                f"{label} pathname/type/size changed")
        payload = common.read_exact(descriptor, 0, opened.st_size)
        require(not platform_compat.pread(descriptor, 1, opened.st_size), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                f"{label} changed while reading")
        return resolved, payload, identity
    finally:
        os.close(descriptor)


def _string(record: dict[str, Any], name: str) -> bool:
    return type(record.get(name)) is str and bool(record[name])


def _integer(record: dict[str, Any], name: str) -> bool:
    return type(record.get(name)) is int


def validate_edit_shape(record: object, order: int) -> dict[str, Any]:
    require(isinstance(record, dict) and type(record.get("kind")) is str,
            f"edit {order} must be an object with a string kind")
    kind = record["kind"]
    if kind in {"torso", "sleeve", "pants"}:
        require(set(record) == TSET_FIELDS and
                _string(record, "asset_code") and _string(record, "side") and
                _integer(record, "variant") and _string(record, "clean_png") and
                (record["mud_png"] is None or _string(record, "mud_png")) and
                record["mud_mode"] in {"identity", "darken_60"} and
                not (record["mud_png"] is not None and
                     record["mud_mode"] == "darken_60"),
                f"edit {order} has invalid {kind} fields/types")
    elif kind == "live_helmet":
        require(set(record) == HELMET_FIELDS and
                _string(record, "asset_code") and _string(record, "side") and
                _integer(record, "variant") and _string(record, "family") and
                _string(record, "png"),
                f"edit {order} has invalid live_helmet fields/types")
    elif kind == "live_number_nameplate":
        require(set(record) == LIVE_ART_FIELDS and
                _string(record, "asset_code") and _string(record, "side") and
                _integer(record, "variant") and _string(record, "family") and
                (record["digit"] is None or type(record["digit"]) is int) and
                _string(record, "png"),
                f"edit {order} has invalid live_number_nameplate fields/types")
    elif kind == "team_select":
        require(set(record) == CARD_FIELDS and
                _string(record, "asset_code") and _string(record, "side") and
                _integer(record, "style") and _string(record, "family") and
                _integer(record, "resolution") and _string(record, "png"),
                f"edit {order} has invalid team_select fields/types")
    elif kind == "live_face":
        require(set(record) == FACE_FIELDS and _string(record, "face_id") and
                re.fullmatch(r"\d{4}", record["face_id"]) is not None and
                record.get("family") in {"f", "h", "n"} and
                _string(record, "png"),
                f"edit {order} has invalid live_face fields/types; only f/h/n are writable")
    elif kind == "create_team_field_art":
        require(set(record) == FIELD_ART_FIELDS and
                type(record.get("logo_code")) is int and
                record["logo_code"] in field_inventory.LOGO_CODES and
                record.get("weather") in {"D", "R", "S"} and
                record.get("texture") in {item[0] for item in field_inventory.TEXTURES} and
                _string(record, "png"),
                f"edit {order} has invalid create_team_field_art fields/types")
    elif kind == "team_identity":
        require(set(record) == TEAM_IDENTITY_FIELDS and
                type(record.get("team_index")) is int and
                0 <= record["team_index"] < 52 and
                all(type(record.get(name)) is str and bool(record[name]) and
                    "\0" not in record[name]
                    for name in ("city", "nickname", "abbreviation",
                                 "city_abbreviation")),
                f"edit {order} has invalid team_identity fields/types")
        try:
            for name in ("city", "nickname", "abbreviation", "city_abbreviation"):
                record[name].encode("utf-16le")
        except UnicodeEncodeError as exc:
            raise ProjectError(
                f"edit {order} team_identity contains invalid Unicode") from exc
    elif kind == "player_roster":
        require(set(record) == PLAYER_ROSTER_FIELDS and
                type(record.get("primary_player_index")) is int and
                0 <= record["primary_player_index"] < ROST_PRIMARY_COUNT and
                all(type(record.get(name)) is str and bool(record[name]) and
                    "\0" not in record[name]
                    for name in ("first_name", "last_name")) and
                type(record.get("jersey_number")) is int and
                0 <= record["jersey_number"] <= 99,
                f"edit {order} has invalid player_roster fields/types")
        try:
            record["first_name"].encode("utf-16le")
            record["last_name"].encode("utf-16le")
        except UnicodeEncodeError as exc:
            raise ProjectError(
                f"edit {order} player_roster contains invalid Unicode") from exc
    elif kind == ROSTER_TEAM_PROVIDER_KIND:
        changes = record.get("changes")
        require(set(record) == ROSTER_TEAM_TEXT_FIELDS and
                type(record.get("resource_outer_index")) is int and
                (record["resource_outer_index"] == 5 or
                 113 <= record["resource_outer_index"] <= 187) and
                type(record.get("team_index")) is int and
                record["team_index"] >= 0 and isinstance(changes, dict) and
                1 <= len(changes) <= len(ROSTER_TEAM_TEXT_CHANGE_FIELDS) and
                set(changes) <= ROSTER_TEAM_TEXT_CHANGE_FIELDS and
                all(type(value) is str and bool(value) and "\0" not in value
                    for value in changes.values()),
                f"edit {order} has invalid roster_team_text fields/types")
        try:
            for value in changes.values():
                value.encode("utf-16le")
        except UnicodeEncodeError as exc:
            raise ProjectError(
                f"edit {order} roster_team_text contains invalid Unicode") from exc
    elif kind == ROSTER_PLAYER_PROVIDER_KIND:
        changes = record.get("changes")
        require(set(record) == ROSTER_PLAYER_TEXT_FIELDS and
                type(record.get("resource_outer_index")) is int and
                (record["resource_outer_index"] == 5 or
                 113 <= record["resource_outer_index"] <= 187) and
                type(record.get("primary_player_index")) is int and
                record["primary_player_index"] >= 0 and isinstance(changes, dict) and
                1 <= len(changes) <= len(ROSTER_PLAYER_TEXT_CHANGE_FIELDS) and
                set(changes) <= ROSTER_PLAYER_TEXT_CHANGE_FIELDS and
                all(
                    (name == "jersey_number" and type(value) is int and
                     0 <= value <= 99) or
                    (name in {"first_name", "last_name"} and
                     type(value) is str and bool(value) and "\0" not in value)
                    for name, value in changes.items()
                ),
                f"edit {order} has invalid roster_player_text fields/types")
        try:
            for name in ("first_name", "last_name"):
                if name in changes:
                    changes[name].encode("utf-16le")
        except UnicodeEncodeError as exc:
            raise ProjectError(
                f"edit {order} roster_player_text contains invalid Unicode") from exc
    elif kind == "player_portrait":
        require(set(record) == PLAYER_PORTRAIT_FIELDS and
                type(record.get("portrait_id")) is str and
                re.fullmatch(r"\d{4}", record["portrait_id"], re.ASCII) is not None and
                _string(record, "png"),
                f"edit {order} has invalid player_portrait fields/types")
    elif kind == CRIB_TEAM_PHOTO_KIND:
        require(
            set(record) == CRIB_TEAM_PHOTO_FIELDS
            and type(record.get("selector")) is str
            and crib_photo_targets.SELECTOR_RE.fullmatch(record["selector"])
            is not None
            and int(record["selector"].split(":", 1)[1][:2]) < 32
            and _string(record, "png"),
            f"edit {order} has invalid crib_team_photo fields/types",
        )
    elif kind == CRIB_SCENE_TEXTURE_KIND:
        require(
            set(record) == CRIB_SCENE_TEXTURE_FIELDS
            and record.get("selector") == crib_scene_import.SELECTOR
            and _string(record, "png"),
            f"edit {order} has invalid crib_scene_texture fields/types; only "
            "the proved room:22 bar_monitor target is editable",
        )
    elif kind == SCOREBUG_TEXTURE_KIND:
        require(
            set(record) == SCOREBUG_TEXTURE_FIELDS
            and record.get("target") in scorebug_adapter.SCOREBUG_TARGETS
            and _string(record, "png"),
            f"edit {order} has invalid scorebug_texture fields/types",
        )
    elif kind == STADIUM_TEXTURE_KIND:
        require(
            set(record) == STADIUM_TEXTURE_FIELDS
            and type(record.get("target")) is str
            and STADIUM_TEXTURE_SELECTOR_RE.fullmatch(record["target"]) is not None
            and _string(record, "png"),
            f"edit {order} has invalid stadium_texture fields/types; choose a "
            "canonical Editable P8 target from Stadium Studio",
        )
    elif kind == P8_TEXTURE_KIND:
        require(
            set(record) == P8_TEXTURE_FIELDS
            and type(record.get("asset_id")) is str
            and record["asset_id"].startswith("p8:")
            and _string(record, "png"),
            f"edit {order} has invalid p8_texture fields/types; choose a "
            "target from the All Textures workspace",
        )
    elif kind == UNIF_COLOR_KIND:
        require(
            set(record) == UNIF_COLOR_FIELDS
            and _string(record, "facemask")
            and (record.get("turtleneck") is None or _string(record, "turtleneck")),
            f"edit {order} has invalid unif_color fields/types; give colours as "
            "AARRGGBB or #RRGGBB",
        )
    elif kind == UNIVERSAL_FIXED_TEXT_KIND:
        require(
            set(record) == UNIVERSAL_FIXED_TEXT_FIELDS
            and type(record.get("selector")) is str
            and UNIVERSAL_TEXT_SELECTOR_RE.fullmatch(record["selector"]) is not None
            and type(record.get("text")) is str
            and bool(record["text"])
            and "\0" not in record["text"],
            f"edit {order} has invalid universal_fixed_text fields/types",
        )
        try:
            record["text"].encode("utf-16le")
        except UnicodeEncodeError as exc:
            raise ProjectError(
                f"edit {order} universal_fixed_text contains invalid Unicode"
            ) from exc
    elif kind == MENU_BACK_AUDIO_KIND:
        require(set(record) == MENU_BACK_AUDIO_FIELDS and _string(record, "wav"),
                f"edit {order} has invalid menu_back_audio fields/types")
    elif kind == AUDO_AUDIO_KIND:
        require(
            set(record) == AUDO_AUDIO_FIELDS
            and type(record.get("asset_id")) is str
            and fixed_audo_adapter.ASSET_ID_RE.fullmatch(record["asset_id"])
            is not None
            and _string(record, "wav"),
            f"edit {order} has invalid audo_audio fields/types",
        )
    elif kind == AUSB_AUDIO_KIND:
        require(
            set(record) == AUSB_AUDIO_FIELDS
            and type(record.get("asset_id")) is str
            and (
                AUSB_LOGICAL_ASSET_RE.fullmatch(record["asset_id"]) is not None
                or AUSB_CANONICAL_ASSET_RE.fullmatch(record["asset_id"])
                is not None
            )
            and _string(record, "wav"),
            f"edit {order} has invalid ausb_audio fields/types",
        )
    else:
        raise ProjectError(f"edit {order} has unsupported kind: {kind!r}")
    return dict(record)


def read_project(path: Path) -> ProjectFile:
    resolved, payload, identity = read_regular_bounded(
        path, MAX_PROJECT_BYTES, "visual-mod project")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProjectError("visual-mod project is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value) and
            set(value) == {"schema", "purpose", "edits"} and
            value["schema"] == SCHEMA and type(value["purpose"]) is str and
            bool(value["purpose"]) and isinstance(value["edits"], list) and
            1 <= len(value["edits"]) <= MAX_EDITS,
            "visual-mod project schema/canonical encoding mismatch")
    edits = [validate_edit_shape(record, order)
             for order, record in enumerate(value["edits"])]
    identity_teams = [edit["team_index"] for edit in edits
                      if edit["kind"] == "team_identity"]
    require(len(identity_teams) == len(set(identity_teams)),
            "project repeats one team_identity team_index")
    roster_players = [edit["primary_player_index"] for edit in edits
                      if edit["kind"] == "player_roster"]
    require(len(roster_players) == len(set(roster_players)),
            "project repeats one player_roster primary_player_index")
    sparse_teams = [
        (edit["resource_outer_index"], edit["team_index"])
        for edit in edits if edit["kind"] == ROSTER_TEAM_PROVIDER_KIND
    ]
    require(len(sparse_teams) == len(set(sparse_teams)),
            "project repeats one roster_team_text resource/team")
    sparse_players = [
        (edit["resource_outer_index"], edit["primary_player_index"])
        for edit in edits if edit["kind"] == ROSTER_PLAYER_PROVIDER_KIND
    ]
    require(len(sparse_players) == len(set(sparse_players)),
            "project repeats one roster_player_text resource/player")
    require(not ({(5, value) for value in identity_teams} & set(sparse_teams)),
            "project mixes legacy and sparse edits for one team")
    require(not ({(5, value) for value in roster_players} & set(sparse_players)),
            "project mixes legacy and sparse edits for one player")
    portrait_ids = [edit["portrait_id"] for edit in edits
                    if edit["kind"] == "player_portrait"]
    require(len(portrait_ids) == len(set(portrait_ids)),
            "project repeats one player_portrait portrait_id")
    crib_photo_selectors = [
        edit["selector"] for edit in edits
        if edit["kind"] == CRIB_TEAM_PHOTO_KIND
    ]
    require(
        len(crib_photo_selectors) == len(set(crib_photo_selectors)),
        "project repeats one crib_team_photo selector",
    )
    crib_scene_selectors = [
        edit["selector"] for edit in edits
        if edit["kind"] == CRIB_SCENE_TEXTURE_KIND
    ]
    require(
        len(crib_scene_selectors) == len(set(crib_scene_selectors)),
        "project repeats one crib_scene_texture selector",
    )
    scorebug_targets = [
        edit["target"] for edit in edits
        if edit["kind"] == SCOREBUG_TEXTURE_KIND
    ]
    require(
        len(scorebug_targets) == len(set(scorebug_targets)),
        "project repeats one scorebug_texture target",
    )
    stadium_texture_targets = [
        edit["target"] for edit in edits
        if edit["kind"] == STADIUM_TEXTURE_KIND
    ]
    require(
        len(stadium_texture_targets) == len(set(stadium_texture_targets)),
        "project repeats one stadium_texture target",
    )
    p8_texture_targets = [
        edit["asset_id"] for edit in edits
        if edit["kind"] == P8_TEXTURE_KIND
    ]
    require(
        len(p8_texture_targets) == len(set(p8_texture_targets)),
        "project repeats one p8_texture target",
    )
    require(
        sum(1 for edit in edits if edit["kind"] == UNIF_COLOR_KIND) <= 1,
        "project sets the Unif colours more than once",
    )
    universal_text_selectors = [
        edit["selector"] for edit in edits
        if edit["kind"] == UNIVERSAL_FIXED_TEXT_KIND
    ]
    require(
        len(universal_text_selectors) == len(set(universal_text_selectors)),
        "project repeats one universal_fixed_text selector",
    )
    require(sum(edit["kind"] == MENU_BACK_AUDIO_KIND for edit in edits) <= 1,
            "project repeats the fixed menu_back_audio target")
    audo_assets = [edit["asset_id"] for edit in edits
                   if edit["kind"] == AUDO_AUDIO_KIND]
    require(len(audo_assets) == len(set(audo_assets)),
            "project repeats one standalone AUDO asset")
    ausb_assets = [edit["asset_id"] for edit in edits
                   if edit["kind"] == AUSB_AUDIO_KIND]
    require(len(ausb_assets) == len(set(ausb_assets)),
            "project repeats one streaming AUSB asset")
    normalized = {"schema": SCHEMA, "purpose": value["purpose"], "edits": edits}
    require(payload == canonical_json(normalized), "project normalization changed encoding")
    return ProjectFile(resolved, payload, normalized, identity)


def project_asset_paths(project: ProjectFile) -> list[Path]:
    result: list[Path] = []
    for edit in project.value["edits"]:
        if edit["kind"] in {"torso", "sleeve", "pants"}:
            names = ["clean_png", "mud_png"]
        elif edit["kind"] in {
            "team_identity", "player_roster",
            ROSTER_TEAM_PROVIDER_KIND,
            ROSTER_PLAYER_PROVIDER_KIND,
            UNIVERSAL_FIXED_TEXT_KIND,
            # A colour edit carries colours, not a file to pin.
            UNIF_COLOR_KIND,
        }:
            names = []
        elif edit["kind"] in AUDIO_KINDS:
            names = ["wav"]
        else:
            names = ["png"]
        for name in names:
            text = edit[name]
            if text is None:
                continue
            supplied = Path(text)
            result.append(supplied if supplied.is_absolute()
                          else project.path.parent / supplied)
    return result


def pin_project_inputs(project: ProjectFile) -> dict[Path, InputPin]:
    pins: dict[Path, InputPin] = {}
    total = 0
    for supplied in project_asset_paths(project):
        resolved, payload, identity = read_regular_bounded(
            supplied, 64 * 1024 * 1024 + 44, "project media input")
        if resolved in pins:
            require(pins[resolved].identity == identity and
                    pins[resolved].payload == payload,
                    "one project PNG pathname changed between references")
            continue
        total += len(payload)
        require(total <= MAX_TOTAL_INPUT_BYTES, "project input byte budget exceeded")
        pins[resolved] = InputPin(
            resolved, payload, len(payload), digest(payload), identity)
    return pins


def resolve_asset(project: ProjectFile, text: str,
                  pins: dict[Path, InputPin]) -> InputPin:
    supplied = Path(text)
    resolved = (supplied if supplied.is_absolute()
                else project.path.parent / supplied).resolve(strict=True)
    require(resolved in pins, "project input pin is absent")
    return pins[resolved]


def verify_input_pin(pin: InputPin) -> None:
    descriptor = os.open(
        pin.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        current = os.fstat(descriptor)
        require(stat.S_ISREG(current.st_mode) and
                (current.st_dev, current.st_ino, current.st_size) ==
                (*pin.identity, pin.size) and
                common.path_identity(pin.path) == pin.identity and
                common.sha256_fd(descriptor) == pin.sha256,
                f"pinned input changed during workflow: {pin.path}")
    finally:
        os.close(descriptor)


def pin_reports(required_kinds: set[str]) -> dict[str, InputPin]:
    pins: dict[str, InputPin] = {}
    require(required_kinds <= set(REPORTS) | REPORT_FREE_KINDS,
            "project requires an unknown report kind")
    report_kinds = set(required_kinds - REPORT_FREE_KINDS)
    if required_kinds & AUDIO_KINDS:
        report_kinds.add(AUDO_AUDIO_KIND)
    for kind in sorted(report_kinds):
        path = REPORTS[kind]
        resolved, payload, identity = read_regular_bounded(
            path, 128 * 1024 * 1024, f"{kind} compatibility report")
        require(digest(payload) == REPORT_SHA256[kind],
                f"{kind} compatibility report SHA-256 mismatch")
        pins[kind] = InputPin(
            resolved, payload, len(payload), digest(payload), identity)
    return pins


def load_audio_origin_context(
    index_pin: ownership.PinnedLargeFile,
    inventory_pin: ownership.PinnedLargeFile,
    capacity_report: Path,
    source_cache_root: Path | None,
    exact_inventory_path: Path | None,
    containment_inventory_path: Path | None,
) -> AudioOriginContext:
    """Strictly load both private inventories from one canonical source cache."""

    require(
        all(
            isinstance(value, Path)
            for value in (
                source_cache_root,
                exact_inventory_path,
                containment_inventory_path,
            )
        ),
        "Audio edits need --source-cache-root, --audio-exact-inventory, and "
        "--audio-containment-inventory. Reopen the game in Mod Studio first.",
    )
    assert source_cache_root is not None
    assert exact_inventory_path is not None
    assert containment_inventory_path is not None
    supplied_root = source_cache_root.expanduser()
    root = supplied_root.resolve(strict=True)
    require(
        platform_compat.is_canonical_absolute_path(supplied_root, root),
        "Audio source-cache root must be its canonical absolute path",
    )
    expected_pack0 = root / SOURCE_CACHE_PACK_FOLDER / "0"
    expected_index = root / SOURCE_CACHE_INVENTORY_RELATIVE
    require(
        index_pin.path == expected_pack0
        and inventory_pin.path == expected_index,
        "Audio edits must use the pack index and resource inventory from the "
        "same source cache as the private audio gates",
    )
    source = SourceRecord(
        selected_path="$PINNED_SOURCE_XISO",
        inspected_path="$PINNED_SOURCE_XISO",
        kind="xiso",
        sha256=AUDIO_SOURCE_SHA256,
        size=AUDIO_SOURCE_SIZE,
        recognized=True,
        fingerprint_id="nfl2k5-usa-retail-xiso",
        detected_game="nfl2k5",
        note="Backend-private source-cache binding",
    )
    cache = SourceCache(
        source=source,
        root=root,
        pack0=index_pin.path,
        inventory=inventory_pin.path,
        originals=root / "originals",
        resource_count=0,
        outer_entry_count=0,
        kind_counts={},
    )
    catalog = Nfl2k5AudioCatalog(cache, capacity_report=capacity_report)
    archive = parse_archive(cache.pack0)
    streaming_catalog = build_streaming_slot_catalog(
        catalog.streaming_ranges, archive
    )

    exact_store = Nfl2k5AudioSourceFingerprintStore()
    exact_expected = exact_store.inventory_path(cache)
    require(
        platform_compat.is_canonical_absolute_path(
            exact_inventory_path.expanduser(), exact_expected
        ),
        "Exact audio inventory path is not the canonical file in this source cache",
    )
    exact_inventory = exact_store.load_existing(
        cache, catalog.assets, streaming_catalog.slots
    )
    require(
        exact_inventory is not None,
        "Exact private audio inventory is missing. Reopen the game and let audio "
        "preparation finish before building.",
    )

    owner_ids = tuple(sorted(
        [asset.asset_id for asset in catalog.assets]
        + [
            owner.asset_id
            for slot in streaming_catalog.slots
            for owner in slot.owners
        ]
    ))
    policy = Nfl2k5AudioSourceContainmentScanner._policy(  # noqa: SLF001
        catalog.assets, streaming_catalog.slots
    )
    containment_store = Nfl2k5AudioSourceContainmentStore(
        expected_source_sha256=AUDIO_SOURCE_SHA256
    )
    containment_expected = containment_store.inventory_path(cache)
    require(
        platform_compat.is_canonical_absolute_path(
            containment_inventory_path.expanduser(), containment_expected
        ),
        "Containment audio inventory path is not the canonical file in this "
        "source cache",
    )
    containment_inventory = containment_store.load_existing(
        cache, policy, owner_ids
    )
    require(
        containment_inventory is not None,
        "Private audio containment inventory is missing. Reopen the game and "
        "let audio preparation finish before building.",
    )
    require(
        exact_inventory.source_sha256
        == containment_inventory.source_binding_sha256
        == AUDIO_SOURCE_SHA256,
        "The two private audio inventories do not belong to this source XISO",
    )
    return AudioOriginContext(
        exact_inventory,
        containment_inventory,
        streaming_catalog,
    )


def authorize_audio_input(
    pin: InputPin,
    *,
    channels: int,
    sample_rate: int,
    frame_count: int,
    context: AudioOriginContext,
) -> AuthorizedPcm16Wav:
    """Authorize the exact already-pinned bytes and return the sealed hand-off."""

    issued = authorize_strict_pcm16_wav(
        pin.payload,
        target_channels=channels,
        target_sample_rate=sample_rate,
        target_frame_count=frame_count,
        source_fingerprints=context.exact_inventory,
        containment_fingerprints=context.containment_inventory,
    )
    issued = require_authorized_pcm16_wav(issued)
    require(
        issued.wav_bytes is pin.payload
        and issued.wav_sha256 == pin.sha256,
        "Audio origin gate did not preserve the exact pinned WAV snapshot",
    )
    return issued


def resolve_ausb_project_edits(
    project: ProjectFile,
    input_pins: dict[Path, InputPin],
    context: AudioOriginContext,
) -> tuple[dict[int, Any], set[int]]:
    """Resolve aliases once; deduplicate identical PCM inputs, reject divergence."""

    slots_by_edit: dict[int, Any] = {}
    deduplicated_edits: set[int] = set()
    physical_inputs: dict[str, tuple[bytes, str, int]] = {}
    for edit_index, edit in enumerate(project.value["edits"]):
        if edit["kind"] != AUSB_AUDIO_KIND:
            continue
        slot = context.streaming_catalog.resolve(edit["asset_id"])
        pin = resolve_asset(project, edit["wav"], input_pins)
        previous = physical_inputs.get(slot.canonical_id)
        if previous is not None:
            previous_payload, previous_sha256, _previous_index = previous
            require(
                pin.sha256 == previous_sha256
                and pin.payload == previous_payload,
                "Streaming-audio aliases for one physical slot use different "
                "WAVs. Keep one edit or give every alias the same replacement.",
            )
            deduplicated_edits.add(edit_index)
            continue
        physical_inputs[slot.canonical_id] = (
            pin.payload, pin.sha256, edit_index
        )
        slots_by_edit[edit_index] = slot
    return slots_by_edit, deduplicated_edits


def safe_name(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return (result or "target")[:120]


def exclusive_payload(path: Path, payload: bytes,
                      parent: ownership.OwnedPath) -> ownership.OwnedPath:
    return ownership.exclusive_copy(path, payload, parent)


def normalized_import_report(report: dict[str, Any], project_edit: dict[str, Any],
                             kind: str) -> dict[str, Any]:
    value = copy.deepcopy(report)
    if "source_index" in value:
        value["source_index"] = "$CANONICAL_INDEX"
    if "canonical_inventory" in value:
        value["canonical_inventory"] = "$CANONICAL_INVENTORY"
    if isinstance(value.get("canonical_index"), dict):
        value["canonical_index"]["path"] = "$CANONICAL_INDEX"
    if isinstance(value.get("compatibility_report"), dict):
        value["compatibility_report"]["path"] = f"$PINNED_REPORT/{kind}"
    if isinstance(value.get("catalog"), dict):
        value["catalog"]["path"] = f"$PINNED_REPORT/{kind}"
    if isinstance(value.get("inventory"), dict):
        value["inventory"]["path"] = f"$PINNED_REPORT/{kind}"
    if isinstance(value.get("audit"), dict):
        value["audit"]["path"] = f"$PINNED_REPORT/{kind}"
    if isinstance(value.get("input_png"), dict):
        value["input_png"]["path"] = project_edit["png"]
        value["input_png"]["file_name"] = Path(project_edit["png"]).name
    if isinstance(value.get("input_pngs"), list):
        project_rows = project_edit.get("edits")
        by_target = {
            str(row.get("target")): str(row.get("png"))
            for row in project_rows
            if isinstance(row, dict)
            and isinstance(row.get("target"), str)
            and isinstance(row.get("png"), str)
        } if isinstance(project_rows, list) else {}
        for row in value["input_pngs"]:
            if not isinstance(row, dict):
                continue
            original = by_target.get(str(row.get("target")))
            if original is not None:
                row["path"] = original
                row["file_name"] = Path(original).name
    return value


def stable_report_pin_record(kind: str, pin: InputPin) -> dict[str, Any]:
    """Serialize report evidence without leaking a private bundle root."""

    path = (
        f"$PINNED_REPORT/{kind}"
        if kind == CRIB_TEAM_PHOTO_KIND
        else str(pin.path)
    )
    return {"path": path, "size": pin.size, "sha256": pin.sha256}


def target_proof(kind: str, target: dict[str, Any]) \
        -> tuple[str, int, int, str, int, int, str]:
    if kind == "team_select":
        return (str(target["pack_path"]), int(target["pack_sector"]),
                int(target["pack_size"]), str(target["pack_sha256"]),
                int(target["span_pack_offset"]),
                int(target["xiso_absolute_span_offset"]), str(target["span_sha256"]))
    return (str(target["xiso_pack_path"]), int(target["xiso_pack_sector"]),
            int(target["xiso_pack_size"]), str(target["xiso_pack_sha256"]),
            int(target["pack_offset"]),
            int(target["xiso_absolute_span_offset"]), str(target["span_sha256"]))


def selector_for(kind: str, target: dict[str, Any]) -> str:
    if "selector" in target:
        return str(target["selector"])
    if kind == "live_helmet":
        return f"{target['asset_code']}{target['side']}{target['variant']}:{target['family']}"
    return f"{target['asset_code']}{target['side']}{target['variant']}"


def _copy_edit_input(order: int, role: str, pin: InputPin,
                     temp_root: ownership.OwnedPath,
                     files: list[ownership.OwnedPath]) -> Path:
    path = temp_root.path / f"{order:05d}_{role}.png"
    files.append(exclusive_payload(path, pin.payload, temp_root))
    return path


def build_team_identity_imports(edit: dict[str, Any], audit_path: Path) \
        -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any],
                      str, dict[str, Any]]]:
    resolved, payload, _ = read_regular_bounded(
        audit_path, 32 * 1024 * 1024, "team-identity audit")
    require(digest(payload) == REPORT_SHA256["team_identity"],
            "team-identity audit SHA-256 mismatch")
    try:
        audit = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProjectError("team-identity audit is invalid JSON") from exc
    require(payload == canonical_json(audit) and
            audit.get("schema") == "nfl2k5_team_identity_audit/v1" and
            audit.get("summary", {}).get("main_team_count") == 52 and
            audit.get("claims", {}).get("team_identity_disc_schema_proved") is True and
            audit.get("claims", {}).get("general_roster_writer_emitted") is False and
            audit.get("claims", {}).get("new_team_added") is False and
            audit.get("sources", {}).get("pack0", {}).get("sha256") == INDEX_SHA256 and
            isinstance(audit.get("teams"), list) and len(audit["teams"]) == 52,
            "team-identity audit schema/source/claims changed")
    team_index = int(edit["team_index"])
    team = audit["teams"][team_index]
    expected_record_offset = 0x41C8 + team_index * ROST_TEAM_STRIDE
    require(team.get("team_index") == team_index and
            int(team.get("team_record_body_offset")) == expected_record_offset and
            isinstance(team.get("fields"), dict),
            "team-identity audit team row changed")

    results = []
    for field in ("nickname", "abbreviation", "city", "city_abbreviation"):
        record = team["fields"].get(field)
        require(isinstance(record, dict) and
                int(record.get("record_pointer_field_offset")) ==
                TEAM_IDENTITY_POINTERS[field] and
                int(record.get("known_decoded_pointer_reference_count")) == 1 and
                record.get("value") == team.get(field),
                f"team-identity audit field changed/shared: {field}")
        allocation = int(record["utf16le_size_including_terminator"])
        before = (str(record["value"]) + "\0").encode("utf-16le")
        after = fixed_utf16le(
            str(edit[field]), allocation, f"team_identity {field}")
        require(len(before) == allocation,
                f"team_identity {field} retail UTF-16 allocation changed")
        body_offset = int(record["body_string_offset"])
        pack_offset = ROST_OUTER_PACK_OFFSET + ROST_WRAPPER_SIZE + body_offset
        absolute = 1_631_188_992 + pack_offset
        selector = f"team:{team_index}:{field}"
        target = {
            "selector": selector,
            "team_index": team_index,
            "field": field,
            "team_record_body_offset": expected_record_offset,
            "record_pointer_field_offset": TEAM_IDENTITY_POINTERS[field],
            "body_string_offset": body_offset,
            "allocation_bytes": allocation,
            "before": record["value"],
            "after": edit[field],
            "asset_code": team["asset_code"],
            "roster_size": int(team["roster_size"]),
            "stadium_index": int(team["stadium_index"]),
            "xiso_pack_path": "vc_53450030/0",
            "xiso_pack_sector": 796_479,
            "xiso_pack_byte_offset": 1_631_188_992,
            "xiso_pack_size": INDEX_SIZE,
            "xiso_pack_sha256": INDEX_SHA256,
            "pack_offset": pack_offset,
            "xiso_absolute_span_offset": absolute,
            "span_sha256": digest(before),
        }
        report: dict[str, Any] = {
            "schema": "nfl2k5_visual_mod_team_identity_span/v1",
            "audit": {
                "path": str(resolved), "sha256": digest(payload),
            },
            "target": target,
            "replacement": {
                "utf16le_hex": after.hex(), "span_size": allocation,
                "span_sha256": digest(after),
                "same_allocation_size": True,
            },
            "unchanged": {
                "asset_code": team["asset_code"],
                "roster_size": int(team["roster_size"]),
                "stadium_index": int(team["stadium_index"]),
                "team_record_and_all_serialized_pointers": True,
            },
            "claims": {
                "fixed_size_team_identity_string_only": True,
                "art_code_modified": False,
                "roster_pointer_or_membership_modified": False,
                "stadium_modified": False,
                "xbe_color_modified": False,
                "relocation_or_allocation_modified": False,
                "runtime_visibility_proved": False,
            },
        }
        results.append((after, [], report, selector, target))
    return results


def build_player_roster_imports(edit: dict[str, Any], audit_path: Path) \
        -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any],
                      str, dict[str, Any]]]:
    """Expand one public primary-player edit into three fixed physical spans."""
    resolved, payload, _ = read_regular_bounded(
        audit_path, 32 * 1024 * 1024, "player-roster audit")
    require(digest(payload) == REPORT_SHA256["player_roster"],
            "player-roster audit SHA-256 mismatch")
    try:
        audit = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProjectError("player-roster audit is invalid JSON") from exc
    summary = audit.get("summary", {})
    layout = audit.get("layout", {})
    require(payload == canonical_json(audit) and
            audit.get("schema") == "nfl2k5_player_roster_audit/v1" and
            summary.get("primary_player_count") == ROST_PRIMARY_COUNT and
            summary.get("secondary_player_count") == ROST_SECONDARY_COUNT and
            summary.get("team_count") == ROST_TEAM_COUNT and
            layout.get("primary_players") == {
                "count": ROST_PRIMARY_COUNT, "offset": ROST_PRIMARY_BASE,
                "stride": ROST_PLAYER_STRIDE,
            } and
            layout.get("secondary_players") == {
                "count": ROST_SECONDARY_COUNT, "offset": ROST_SECONDARY_BASE,
                "stride": ROST_PLAYER_STRIDE,
            } and
            layout.get("teams") == {
                "count": ROST_TEAM_COUNT, "offset": ROST_TEAM_BASE,
                "stride": ROST_TEAM_STRIDE,
            } and
            audit.get("membership", {}).get("pointer_formula") ==
                "target = pointer_field + signed_i32 - 1" and
            audit.get("membership", {}).get("active_membership_pointer_count") == 2634 and
            audit.get("membership", {}).get("all_unused_slots_null") is True and
            audit.get("claims", {}).get("disc_player_table_proved") is True and
            audit.get("claims", {}).get("player_name_pointer_schema_proved") is True and
            audit.get("claims", {}).get("jersey_number_bits_proved") is True and
            audit.get("claims", {}).get("team_membership_pointer_schema_proved") is True and
            audit.get("claims", {}).get("all_28_rating_semantics_proved") is False and
            audit.get("claims", {}).get("runtime_visibility_proved") is False and
            audit.get("sources", {}).get("pack0", {}).get("sha256") == INDEX_SHA256 and
            audit.get("sources", {}).get("main_roster_body", {}).get("size") ==
                ROST_BODY_SIZE and
            isinstance(audit.get("players"), list) and
            len(audit["players"]) == ROST_PRIMARY_COUNT + ROST_SECONDARY_COUNT,
            "player-roster audit schema/source/claim boundary changed")

    player_index = int(edit["primary_player_index"])
    player = audit["players"][player_index]
    record_offset = ROST_PRIMARY_BASE + player_index * ROST_PLAYER_STRIDE
    require(player.get("pool") == "primary_players" and
            player.get("index") == player_index and
            int(player.get("record_body_offset")) == record_offset and
            int(player.get("first_name_known_pointer_reference_count")) == 1 and
            int(player.get("last_name_known_pointer_reference_count")) == 1 and
            type(player.get("first_name")) is str and
            type(player.get("last_name")) is str and
            type(player.get("jersey_number")) is int and
            type(player.get("face_id")) is int and
            type(player.get("position_code")) is int and
            isinstance(player.get("team_indices"), list) and
            player["team_indices"] == sorted(set(player["team_indices"])) and
            all(type(value) is int and 0 <= value < ROST_TEAM_COUNT
                for value in player["team_indices"]),
            "player-roster audit primary-player row changed")

    before_word = int(str(player["jersey_word_20"]), 16)
    old_number = int(player["jersey_number"])
    new_number = int(edit["jersey_number"])
    require((before_word >> PLAYER_JERSEY_SHIFT) & 0x7F == old_number and
            0 <= old_number <= 99,
            "player-roster audit jersey word changed")
    after_word = ((before_word & ~PLAYER_JERSEY_MASK) |
                  ((new_number & 0x7F) << PLAYER_JERSEY_SHIFT))
    require((after_word & ~PLAYER_JERSEY_MASK) ==
            (before_word & ~PLAYER_JERSEY_MASK),
            "player_roster jersey edit would alter unrelated word bits")

    common_target = {
        "primary_player_index": player_index,
        "player_record_body_offset": record_offset,
        "first_name_body_offset": int(player["first_name_body_offset"]),
        "last_name_body_offset": int(player["last_name_body_offset"]),
        "face_id": int(player["face_id"]),
        "position_code": int(player["position_code"]),
        "position": str(player["position"]),
        "team_indices": list(player["team_indices"]),
        "retail_jersey_number": old_number,
        "retail_jersey_word": f"0x{before_word:08x}",
        "replacement_jersey_number": new_number,
        "replacement_jersey_word": f"0x{after_word:08x}",
        "xiso_pack_path": "vc_53450030/0",
        "xiso_pack_sector": 796_479,
        "xiso_pack_byte_offset": 1_631_188_992,
        "xiso_pack_size": INDEX_SIZE,
        "xiso_pack_sha256": INDEX_SHA256,
    }
    results = []
    fields = (
        ("first_name", PLAYER_FIRST_POINTER_FIELD,
         int(player["first_name_body_offset"]), str(player["first_name"]),
         str(edit["first_name"])),
        ("last_name", PLAYER_LAST_POINTER_FIELD,
         int(player["last_name_body_offset"]), str(player["last_name"]),
         str(edit["last_name"])),
    )
    for field, pointer_field, body_offset, before_text, after_text in fields:
        before = (before_text + "\0").encode("utf-16le")
        after = fixed_utf16le(
            after_text, len(before), f"player_roster {field}")
        pack_offset = ROST_OUTER_PACK_OFFSET + ROST_WRAPPER_SIZE + body_offset
        selector = f"primary-player:{player_index}:{field}"
        target = {
            **common_target, "selector": selector, "field": field,
            "record_pointer_field_offset": pointer_field,
            "body_string_offset": body_offset,
            "allocation_bytes": len(before), "before": before_text,
            "after": after_text, "pack_offset": pack_offset,
            "xiso_absolute_span_offset": 1_631_188_992 + pack_offset,
            "span_sha256": digest(before),
        }
        report = {
            "schema": "nfl2k5_visual_mod_player_roster_span/v1",
            "audit": {"path": str(resolved), "sha256": digest(payload)},
            "target": target,
            "replacement": {
                "utf16le_hex": after.hex(), "span_size": len(after),
                "span_sha256": digest(after), "same_allocation_size": True,
            },
            "unchanged": {
                "team_membership_and_roster_counts": True,
                "all_serialized_pointers": True,
                "position": player["position"], "face_id": player["face_id"],
                "all_rating_and_unselected_player_bits": True,
            },
            "claims": {
                "primary_player_only": True,
                "fixed_size_identity_and_jersey_only": True,
                "team_membership_modified": False,
                "roster_count_modified": False,
                "serialized_pointer_modified": False,
                "position_modified": False, "face_id_modified": False,
                "ratings_modified": False, "runtime_visibility_proved": False,
            },
        }
        results.append((after, [], report, selector, target))

    before = struct.pack("<I", before_word)
    after = struct.pack("<I", after_word)
    body_offset = record_offset + PLAYER_JERSEY_FIELD
    pack_offset = ROST_OUTER_PACK_OFFSET + ROST_WRAPPER_SIZE + body_offset
    selector = f"primary-player:{player_index}:jersey_number"
    target = {
        **common_target, "selector": selector, "field": "jersey_number",
        "record_field_offset": PLAYER_JERSEY_FIELD,
        "body_field_offset": body_offset, "allocation_bytes": 4,
        "pack_offset": pack_offset,
        "xiso_absolute_span_offset": 1_631_188_992 + pack_offset,
        "span_sha256": digest(before),
    }
    report = {
        "schema": "nfl2k5_visual_mod_player_roster_span/v1",
        "audit": {"path": str(resolved), "sha256": digest(payload)},
        "target": target,
        "replacement": {
            "word_hex": after.hex(), "span_size": 4,
            "span_sha256": digest(after), "same_allocation_size": True,
            "masked_preservation_formula":
                "new_word = (old_word & ~0x3f8) | ((jersey & 0x7f) << 3)",
        },
        "unchanged": {
            "jersey_word_bits_outside_0x3f8": True,
            "team_membership_and_roster_counts": True,
            "all_serialized_pointers": True,
            "position": player["position"], "face_id": player["face_id"],
            "all_rating_and_unselected_player_bits": True,
        },
        "claims": {
            "primary_player_only": True,
            "fixed_size_identity_and_jersey_only": True,
            "team_membership_modified": False,
            "roster_count_modified": False,
            "serialized_pointer_modified": False,
            "position_modified": False, "face_id_modified": False,
            "ratings_modified": False, "runtime_visibility_proved": False,
        },
    }
    results.append((after, [], report, selector, target))
    return results


def _roster_span_target(
    view: RosterResourceView,
    *,
    selector: str,
    body_offset: int,
    before: bytes,
) -> dict[str, Any]:
    pack_offset = view.pack_offset + ROST_WRAPPER_SIZE + body_offset
    return {
        "selector": selector,
        "resource_outer_index": view.outer_index,
        "resource_outer_id": view.outer_id,
        "resource_label": view.resource_label,
        "resource_pack_offset": view.pack_offset,
        "resource_outer_size": view.outer_size,
        "resource_body_size": view.body_size,
        "resource_body_sha256": digest(view.body),
        "body_offset": body_offset,
        "allocation_bytes": len(before),
        "xiso_pack_path": "vc_53450030/0",
        "xiso_pack_sector": 796_479,
        "xiso_pack_byte_offset": 1_631_188_992,
        "xiso_pack_size": INDEX_SIZE,
        "xiso_pack_sha256": INDEX_SHA256,
        "pack_offset": pack_offset,
        "xiso_absolute_span_offset": 1_631_188_992 + pack_offset,
        "span_sha256": digest(before),
    }


def build_roster_team_text_imports(
    edit: dict[str, Any], view: RosterResourceView,
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any],
                str, dict[str, Any]]]:
    """Expand one sparse team edit into unique fixed UTF-16 spans."""

    team_index = int(edit["team_index"])
    teams = list(view.parsed["teams"])
    require(0 <= team_index < len(teams),
            "roster_team_text team_index is outside this resource")
    team = teams[team_index]
    require(int(team["index"]) == team_index and
            view.resource_label in {"roster", "historic"},
            "roster_team_text resource/team ordering changed")
    references = roster_text_reference_counts(view)
    results = []
    field_offsets = dict(TEAM_IDENTITY_POINTERS)
    for field in ("nickname", "abbreviation", "city", "city_abbreviation"):
        if field not in edit["changes"]:
            continue
        before_text = str(team[field])
        body_offset = int(team[f"{field}_offset"])
        before = (before_text + "\0").encode("utf-16le")
        require(view.body[body_offset:body_offset + len(before)] == before and
                references[body_offset] == 1,
                f"roster_team_text {field} allocation is changed or shared")
        after = fixed_utf16le(
            str(edit["changes"][field]), len(before),
            f"roster_team_text {field}")
        selector = f"roster:{view.outer_index}:team:{team_index}:{field}"
        target = {
            **_roster_span_target(
                view, selector=selector, body_offset=body_offset, before=before),
            "field": field,
            "team_index": team_index,
            "team_record_body_offset": int(team["offset"]),
            "record_pointer_field_offset": field_offsets[field],
            "body_string_offset": body_offset,
            "asset_code": str(team["asset_code"]),
            "roster_size": int(team["roster_size"]),
            "before": before_text,
            "after": str(edit["changes"][field]),
            "known_decoded_pointer_reference_count": references[body_offset],
        }
        report = {
            "schema": "nfl2k5_visual_mod_roster_team_text_span/v1",
            "target": target,
            "replacement": {
                "utf16le_hex": after.hex(),
                "span_size": len(after),
                "span_sha256": digest(after),
                "required_nul_terminator": True,
                "unused_allocation_zero_filled": True,
                "same_allocation_size": True,
            },
            "unchanged": {
                "asset_code": str(team["asset_code"]),
                "roster_size": int(team["roster_size"]),
                "team_record_and_all_serialized_pointers": True,
            },
            "claims": {
                "fixed_allocation_team_identity_string_only": True,
                "historical_resource": view.resource_label == "historic",
                "art_code_modified": False,
                "roster_pointer_or_membership_modified": False,
                "relocation_or_allocation_modified": False,
                "runtime_visibility_proved": False,
            },
        }
        results.append((after, [], report, selector, target))
    require(bool(results), "roster_team_text contains no supported changes")
    return results


def build_roster_player_text_imports(
    edit: dict[str, Any], view: RosterResourceView,
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any],
                str, dict[str, Any]]]:
    """Expand one sparse primary-player edit into fixed name/number spans."""

    player_index = int(edit["primary_player_index"])
    matches = [
        player for player in view.parsed["players"]
        if player["pool"] == "primary_players" and
        int(player["index"]) == player_index
    ]
    require(len(matches) == 1,
            "roster_player_text primary_player_index is outside this resource")
    player = matches[0]
    record_offset = int(player["offset"])
    raw = bytes.fromhex(str(player["raw_hex"]))
    require(len(raw) == ROST_PLAYER_STRIDE and
            view.body[record_offset:record_offset + ROST_PLAYER_STRIDE] == raw,
            "roster_player_text player record changed")
    before_word = struct.unpack_from("<I", raw, PLAYER_JERSEY_FIELD)[0]
    old_number = (before_word >> PLAYER_JERSEY_SHIFT) & 0x7F
    require(0 <= old_number <= 99,
            "roster_player_text retail jersey number is outside 0..99")
    references = roster_text_reference_counts(view)
    common_target = {
        "primary_player_index": player_index,
        "player_record_body_offset": record_offset,
        "face_id": struct.unpack_from("<H", raw, 0x06)[0],
        "position_code": raw[0x35],
        "team_indices": sorted(int(value) for value in player["team_refs"]),
        "retail_jersey_number": old_number,
        "retail_jersey_word": f"0x{before_word:08x}",
    }
    results = []
    for field, pointer_field in (
        ("first_name", PLAYER_FIRST_POINTER_FIELD),
        ("last_name", PLAYER_LAST_POINTER_FIELD),
    ):
        if field not in edit["changes"]:
            continue
        before_text = str(player[field])
        body_offset = int(player[f"{field}_offset"])
        before = (before_text + "\0").encode("utf-16le")
        require(view.body[body_offset:body_offset + len(before)] == before and
                references[body_offset] == 1,
                f"roster_player_text {field} allocation is changed or shared")
        after = fixed_utf16le(
            str(edit["changes"][field]), len(before),
            f"roster_player_text {field}")
        selector = f"roster:{view.outer_index}:primary-player:{player_index}:{field}"
        target = {
            **_roster_span_target(
                view, selector=selector, body_offset=body_offset, before=before),
            **common_target,
            "field": field,
            "record_pointer_field_offset": pointer_field,
            "body_string_offset": body_offset,
            "before": before_text,
            "after": str(edit["changes"][field]),
            "known_decoded_pointer_reference_count": references[body_offset],
        }
        report = {
            "schema": "nfl2k5_visual_mod_roster_player_text_span/v1",
            "target": target,
            "replacement": {
                "utf16le_hex": after.hex(), "span_size": len(after),
                "span_sha256": digest(after), "required_nul_terminator": True,
                "unused_allocation_zero_filled": True,
                "same_allocation_size": True,
            },
            "unchanged": {
                "team_membership_and_roster_counts": True,
                "all_serialized_pointers": True,
                "face_id": common_target["face_id"],
                "position_code": common_target["position_code"],
                "all_rating_and_unselected_player_bits": True,
            },
            "claims": {
                "primary_player_only": True,
                "fixed_allocation_identity_and_jersey_only": True,
                "historical_resource": view.resource_label == "historic",
                "team_membership_modified": False,
                "serialized_pointer_modified": False,
                "position_or_face_modified": False,
                "ratings_modified": False,
                "runtime_visibility_proved": False,
            },
        }
        results.append((after, [], report, selector, target))

    if "jersey_number" in edit["changes"]:
        new_number = int(edit["changes"]["jersey_number"])
        after_word = ((before_word & ~PLAYER_JERSEY_MASK) |
                      ((new_number & 0x7F) << PLAYER_JERSEY_SHIFT))
        require((before_word & ~PLAYER_JERSEY_MASK) ==
                (after_word & ~PLAYER_JERSEY_MASK),
                "roster_player_text jersey edit changes unrelated bits")
        before = struct.pack("<I", before_word)
        after = struct.pack("<I", after_word)
        body_offset = record_offset + PLAYER_JERSEY_FIELD
        selector = (f"roster:{view.outer_index}:primary-player:{player_index}:"
                    "jersey_number")
        target = {
            **_roster_span_target(
                view, selector=selector, body_offset=body_offset, before=before),
            **common_target,
            "field": "jersey_number",
            "record_field_offset": PLAYER_JERSEY_FIELD,
            "body_field_offset": body_offset,
            "replacement_jersey_number": new_number,
            "replacement_jersey_word": f"0x{after_word:08x}",
        }
        report = {
            "schema": "nfl2k5_visual_mod_roster_player_text_span/v1",
            "target": target,
            "replacement": {
                "word_hex": after.hex(), "span_size": 4,
                "span_sha256": digest(after),
                "masked_preservation_formula":
                    "new_word = (old_word & ~0x3f8) | ((jersey & 0x7f) << 3)",
            },
            "unchanged": {
                "jersey_word_bits_outside_0x3f8": True,
                "team_membership_and_roster_counts": True,
                "all_serialized_pointers": True,
                "face_id": common_target["face_id"],
                "position_code": common_target["position_code"],
                "all_rating_and_unselected_player_bits": True,
            },
            "claims": {
                "primary_player_only": True,
                "fixed_allocation_identity_and_jersey_only": True,
                "historical_resource": view.resource_label == "historic",
                "team_membership_modified": False,
                "serialized_pointer_modified": False,
                "position_or_face_modified": False,
                "ratings_modified": False,
                "runtime_visibility_proved": False,
            },
        }
        results.append((after, [], report, selector, target))
    require(bool(results), "roster_player_text contains no supported changes")
    return results


def build_player_portrait_imports(
    order: int, edit: dict[str, Any], project: ProjectFile,
    input_pins: dict[Path, InputPin], report_path: Path, index: Path,
    temp_root: ownership.OwnedPath, temp_files: list[ownership.OwnedPath],
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any],
                str, dict[str, Any]]]:
    """Split one logical portrait import across its proved physical segments."""
    png_pin = resolve_asset(project, edit["png"], input_pins)
    png = _copy_edit_input(order, "portrait", png_pin, temp_root, temp_files)
    names = {
        "span_file": f"{order:05d}_portrait_replacement.bin",
        "manifest_file": f"{order:05d}_portrait_import.json",
        "preview_file": f"{order:05d}_portrait_preview.png",
    }
    replacement, preview, report = portrait_import.build_import(
        index, report_path, edit["portrait_id"], png, names)
    full_target = dict(report["target"])
    logical_selector = str(full_target["selector"])
    segments = list(full_target["span_segments"])
    require(1 <= len(segments) <= 2 and
            sum(int(item["size"]) for item in segments) == len(replacement) and
            int(full_target["span_size"]) == len(replacement),
            "player_portrait logical segment contract changed")
    archive = parse_archive(index)
    entry = archive.entries[int(full_target["outer_index"])]
    retail = read_entry_range(
        archive, entry, int(full_target["chunk_offset"]), len(replacement))
    require(digest(retail) == str(full_target["span_sha256"]),
            "player_portrait canonical retail span changed")

    results = []
    cursor = 0
    for segment_index, segment in enumerate(segments):
        relative = int(segment["span_relative_offset"])
        size = int(segment["size"])
        require(relative == cursor and size > 0 and relative + size <= len(retail),
                "player_portrait segments are not contiguous in logical order")
        cursor += size
        before_piece = retail[relative:relative + size]
        after_piece = replacement[relative:relative + size]
        selector = (f"{logical_selector}:segment:{segment_index + 1}-of-"
                    f"{len(segments)}")
        target = {
            "selector": selector,
            "logical_selector": logical_selector,
            "portrait_id": str(full_target["name"]),
            "segment_index": segment_index,
            "segment_count": len(segments),
            "span_relative_offset": relative,
            "logical_span_size": len(retail),
            "logical_retail_span_sha256": digest(retail),
            "logical_replacement_span_sha256": digest(replacement),
            "xiso_pack_path": str(segment["pack_path"]),
            "xiso_pack_sector": int(segment["pack_sector"]),
            "xiso_pack_size": int(segment["pack_size"]),
            "xiso_pack_sha256": str(segment["pack_sha256"]),
            "pack_offset": int(segment["pack_offset"]),
            "xiso_absolute_span_offset": int(segment["xiso_absolute_offset"]),
            "span_sha256": digest(before_piece),
        }
        segment_report = copy.deepcopy(report)
        segment_report["unified_physical_segment"] = {
            "selector": selector, "segment_index": segment_index,
            "segment_count": len(segments), "span_relative_offset": relative,
            "span_size": size, "retail_span_sha256": digest(before_piece),
            "replacement_span_sha256": digest(after_piece),
            "cross_pack_safe": len(segments) > 1,
        }
        previews = [(names["preview_file"], preview)] if segment_index == 0 else []
        results.append((after_piece, previews, segment_report, selector, target))
    require(cursor == len(retail), "player_portrait segment coverage changed")
    return results


def build_crib_scene_texture_import(
    source_fd: int, png: Path, names: dict[str, str]
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Compile the one proved compressed-SCNE Crib texture from the live source."""

    # SPAN_ABSOLUTE is where this span sits in the project's own rebuild, and a
    # pressed disc or a repack puts the same pack somewhere else entirely. The
    # pack is therefore located by NAME -- which is layout-independent -- and the
    # span offset derived from wherever that pack actually starts. Verified: in
    # the reference image pack "c" is at 5,231,806,464 and
    # 5,231,806,464 + SPAN_PACK_OFFSET == SPAN_ABSOLUTE exactly.
    _entries, _ = common.parse_xdvdfs(source_fd, os.fstat(source_fd).st_size)
    _pack = _entries.get(f"vc_53450030/{CRIB_SCENE_PACK_NAME}".casefold())
    require(_pack is not None, "crib scene source pack is missing")
    assert _pack is not None
    _span_absolute = _pack.byte_offset + crib_scene_import.SPAN_PACK_OFFSET
    source_span = common.read_exact(
        source_fd, _span_absolute, crib_scene_import.SPAN_SIZE
    )
    try:
        resolved, png_payload, rgba = crib_scene_import.read_png(png)
        replacement, preview, compile_report = crib_scene_import.compile_replacement(
            source_span, rgba
        )
    except crib_scene_import.BarMonitorError as exc:
        detail = str(exc)
        if "too visually complex" in detail:
            message = (
                "This Crib screen image has too much fine noise or dithering for "
                "the fixed game slot. Simplify those areas and try again."
            )
        elif "compresses outside" in detail:
            message = (
                "This Crib screen image is too flat for the safe game slot. Add "
                "a small amount of repeated visual detail and try again."
            )
        else:
            message = f"Could not prepare the Crib screen replacement: {detail}"
        raise ProjectError(message) from exc
    target = {
        "selector": crib_scene_import.SELECTOR,
        "asset_id": crib_scene_import.ASSET_ID,
        "scene": crib_scene_import.SCENE_NAME,
        "texture_index": crib_scene_import.TEXTURE_INDEX,
        "material": crib_scene_import.MATERIAL_NAME,
        "owning_shape": crib_scene_import.SHAPE_NAME,
        "owning_submesh_index": crib_scene_import.SUBMESH_INDEX,
        "width": 128,
        "height": 128,
        "format": "P8",
        "mip_levels": 5,
        "xiso_pack_path": crib_scene_import.PACK_PATH,
        "xiso_pack_sector": crib_scene_import.PACK_SECTOR,
        "xiso_pack_size": crib_scene_import.PACK_SIZE,
        "xiso_pack_sha256": crib_scene_import.PACK_SHA256,
        "pack_offset": crib_scene_import.SPAN_PACK_OFFSET,
        "xiso_absolute_span_offset": crib_scene_import.SPAN_ABSOLUTE,
        "span_size": crib_scene_import.SPAN_SIZE,
        "span_sha256": crib_scene_import.SOURCE_SPAN_SHA256,
    }
    report = {
        "schema": "nfl2k5_crib_scene_texture_import/v1",
        "target": target,
        "input_png": {
            "path": str(resolved),
            "file_name": resolved.name,
            "size": len(png_payload),
            "sha256": digest(png_payload),
            "rgba_sha256": digest(rgba),
            "strict_rgba8_noninterlaced": True,
        },
        "compile": compile_report,
        "replacement": {
            "span_size": len(replacement),
            "span_sha256": digest(replacement),
            "preview_file": names["preview_file"],
            "preview_sha256": digest(preview),
        },
        "claims": {
            "fixed_room_scne_span_only": True,
            "decoded_changes_bounded_to_bar_monitor_allocation": True,
            "all_five_p8_mips_regenerated": True,
            "room_geometry_and_other_decoded_allocations_preserved": True,
            "opaque_tail_preserved_from_user_source": True,
            "runtime_visibility_proved": False,
        },
    }
    return (
        replacement,
        [(names["preview_file"], preview)],
        report,
        crib_scene_import.SELECTOR,
        target,
    )


def build_one_import(order: int, edit: dict[str, Any], project: ProjectFile,
                     input_pins: dict[Path, InputPin], report_paths: dict[str, Path],
                     index: Path, inventory: Path, temp_root: ownership.OwnedPath,
                     temp_files: list[ownership.OwnedPath], source_fd: int) \
        -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    kind = edit["kind"]
    if kind in {"torso", "sleeve", "pants"}:
        clean_pin = resolve_asset(project, edit["clean_png"], input_pins)
        clean = _copy_edit_input(order, "clean", clean_pin, temp_root, temp_files)
        mud = None
        if edit["mud_png"] is not None:
            mud_pin = resolve_asset(project, edit["mud_png"], input_pins)
            mud = _copy_edit_input(order, "mud", mud_pin, temp_root, temp_files)
        module_targets, module_import = {
            "torso": (jersey_targets, jersey_import),
            "sleeve": (sleeve_targets, sleeve_import),
            "pants": (pants_targets, pants_import),
        }[kind]
        _, _, _, target = module_targets.select_target(
            edit["asset_code"], edit["side"], edit["variant"], report_paths[kind])
        replacement, previews, report = module_import.import_png(
            index, inventory, report_paths[kind], target, clean, mud, edit["mud_mode"])
        return replacement, previews, report, target.selector, asdict(target)

    png_pin = resolve_asset(project, edit["png"], input_pins)
    png = _copy_edit_input(order, "input", png_pin, temp_root, temp_files)
    names = {
        "span_file": f"{order:05d}_replacement.bin",
        "manifest_file": f"{order:05d}_import.json",
        "preview_file": f"{order:05d}_preview.png",
    }
    if kind == "live_helmet":
        replacement, previews, report = helmet_import.build_import(
            index, report_paths[kind], edit["asset_code"], edit["side"],
            edit["variant"], edit["family"], png)
        return (replacement, previews, report,
                selector_for(kind, report["target"]), dict(report["target"]))
    if kind == "live_number_nameplate":
        replacement, preview, report = live_art_import.build_import(
            index, report_paths[kind], edit["family"], edit["asset_code"],
            edit["side"], edit["variant"], edit["digit"], png, names)
        return (replacement, [(names["preview_file"], preview)], report,
                str(report["target"]["selector"]), dict(report["target"]))
    if kind == "team_select":
        replacement, preview, report = card_import.build_import(
            index, report_paths[kind], edit["family"], edit["asset_code"],
            edit["side"], edit["style"], edit["resolution"], png, names)
        return (replacement, [(names["preview_file"], preview)], report,
                str(report["target"]["selector"]), dict(report["target"]))
    if kind == "live_face":
        replacement, previews, report = face_import.build_import(
            index, report_paths[kind], edit["face_id"], edit["family"], png)
        return (replacement, previews, report,
                str(report["target"]["face_id"]) + ":" +
                str(report["target"]["family"]), dict(report["target"]))
    if kind == "create_team_field_art":
        replacement, previews, report = field_import.build_import(
            index, report_paths[kind], edit["logo_code"], edit["weather"],
            edit["texture"], png)
        raw_target = dict(report["target"])
        proof_target = dict(raw_target)
        proof_target.update({
            "xiso_pack_path": "vc_53450030/0",
            "xiso_pack_sector": 796_479,
            "xiso_pack_byte_offset": 1_631_188_992,
            "xiso_pack_size": INDEX_SIZE,
            "xiso_pack_sha256": INDEX_SHA256,
            "pack_offset": (int(raw_target["pack_offset"]) +
                            int(raw_target["chunk_offset"])),
            "xiso_absolute_span_offset": (
                1_631_188_992 + int(raw_target["pack_offset"]) +
                int(raw_target["chunk_offset"])),
        })
        return (replacement, previews, report,
                str(raw_target["selector"]), proof_target)
    if kind == CRIB_TEAM_PHOTO_KIND:
        replacement, preview, report = crib_photo_import.build_import(
            index, report_paths[kind], edit["selector"], png, names)
        return (
            replacement,
            [(names["preview_file"], preview)],
            report,
            str(report["target"]["selector"]),
            dict(report["target"]),
        )
    if kind == CRIB_SCENE_TEXTURE_KIND:
        return build_crib_scene_texture_import(source_fd, png, names)
    if kind == SCOREBUG_TEXTURE_KIND:
        return scorebug_adapter.build_scorebug_texture_import(
            index,
            report_paths[kind],
            {**edit, "png": png},
        )
    if kind == STADIUM_TEXTURE_KIND:
        try:
            return stadium_texture_adapter.build_unified_stadium_texture_import(
                index, inventory, edit["target"], png
            )
        except stadium_texture_adapter.StadiumTextureWriterError as exc:
            raise ProjectError(str(exc)) from exc
    if kind == P8_TEXTURE_KIND:
        try:
            return p8_texture_adapter.build_unified_p8_texture_import(
                index, str(edit["asset_id"]), Path(png)
            )
        except p8_texture_adapter.P8TextureWriterError as exc:
            raise ProjectError(str(exc)) from exc
    raise ProjectError(f"unsupported edit kind after validation: {kind}")


def build_stadium_scene_import(
    order: int,
    edits: list[dict[str, Any]],
    project: ProjectFile,
    input_pins: dict[Path, InputPin],
    index: Path,
    inventory: Path,
    temp_root: ownership.OwnedPath,
    temp_files: list[ownership.OwnedPath],
) -> tuple[
    bytes,
    list[tuple[str, bytes]],
    dict[str, Any],
    str,
    dict[str, Any],
]:
    """Stage and compose every selected P8 allocation in one Stadium SCNE."""

    require(bool(edits), "Stadium scene edit group is empty")
    staged: list[tuple[str, Path]] = []
    for index_in_scene, edit in enumerate(edits):
        pin = resolve_asset(project, edit["png"], input_pins)
        path = _copy_edit_input(
            order,
            f"stadium_{index_in_scene:04d}",
            pin,
            temp_root,
            temp_files,
        )
        staged.append((str(edit["target"]), path))
    try:
        built = stadium_texture_adapter.build_unified_stadium_texture_imports(
            index, inventory, staged
        )
    except stadium_texture_adapter.StadiumTextureWriterError as exc:
        raise ProjectError(str(exc)) from exc
    require(len(built) == 1, "One Stadium scene produced multiple resource spans")
    return built[0]


def _safe_text_pack_sha256(pack: Any) -> str:
    """Hash one private extracted pack through a no-follow identity check."""

    path = Path(pack.path)
    supplied = path.lstat()
    require(
        stat.S_ISREG(supplied.st_mode)
        and not stat.S_ISLNK(supplied.st_mode)
        and supplied.st_size == int(pack.size),
        f"private text pack {pack.name} has the wrong type or size",
    )
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        require(
            stat.S_ISREG(opened.st_mode)
            and (supplied.st_dev, supplied.st_ino, supplied.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size)
            and common.path_identity(path.resolve(strict=True)) == identity,
            f"private text pack {pack.name} changed while opening",
        )
        result = common.sha256_fd(descriptor)
        current = path.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size),
            f"private text pack {pack.name} changed while hashing",
        )
        return result
    finally:
        os.close(descriptor)


def build_universal_fixed_text_import(
    edit: dict[str, Any],
    catalog: Any,
    replacement: Any,
    entries: Mapping[str, common.XdvdfsEntry],
    pack_hashes: dict[str, str],
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Translate one logical safe-text selector into its private fixed span."""

    selector = str(edit["selector"])
    asset = catalog.get_selector(selector)
    require(
        asset.editable
        and asset.provider_kind == UNIVERSAL_FIXED_TEXT_KIND
        and replacement.selector == selector
        and replacement.asset_id == asset.asset_id
        and replacement.size == asset.allocation_bytes,
        f"universal text capability changed for {selector}",
    )
    pack = next(
        (item for item in catalog.archive.packs if item.name == replacement.pack_name),
        None,
    )
    require(pack is not None, f"universal text pack is missing for {selector}")
    assert pack is not None
    xiso_path = f"vc_53450030/{pack.name}"
    xiso_pack = entries.get(xiso_path.casefold())
    require(
        xiso_pack is not None and xiso_pack.size == pack.size,
        f"universal text XISO pack extent changed for {selector}",
    )
    assert xiso_pack is not None
    if pack.name not in pack_hashes:
        pack_hashes[pack.name] = _safe_text_pack_sha256(pack)
    absolute = xiso_pack.byte_offset + replacement.pack_offset
    target = {
        "selector": selector,
        "asset_id": asset.asset_id,
        "bank_kind": asset.bank_kind,
        "field": asset.field_name,
        "allocation_bytes": asset.allocation_bytes,
        "reference_count": asset.reference_count,
        "xiso_pack_path": xiso_path,
        "xiso_pack_sector": xiso_pack.sector,
        "xiso_pack_size": xiso_pack.size,
        "xiso_pack_sha256": pack_hashes[pack.name],
        "pack_offset": replacement.pack_offset,
        "xiso_absolute_span_offset": absolute,
        "span_sha256": replacement.preimage_sha256,
    }
    report = {
        "schema": "nfl2k5_visual_mod_universal_fixed_text_span/v1",
        "target": target,
        "replacement": {
            "span_size": replacement.size,
            "span_sha256": replacement.replacement_sha256,
            "utf16_code_units": len(str(edit["text"]).encode("utf-16le")) // 2,
            "required_nul_terminator": True,
            "unused_allocation_zero_filled": True,
            "same_allocation_size": True,
        },
        "claims": {
            "logical_selector_resolved_from_user_source": True,
            "pointer_and_resource_sizes_preserved": True,
            "public_project_contains_raw_offsets": False,
            "public_project_contains_original_text_or_bytes": False,
            "runtime_visibility_proved": False,
        },
    }
    return replacement.replacement, [], report, selector, target


def build_menu_back_audio_import(
    edit: dict[str, Any],
    project: ProjectFile,
    input_pins: dict[Path, InputPin],
    audio_origin: AudioOriginContext,
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Encode the one proved fixed AUDO slot for the composed writer."""

    pin = resolve_asset(project, edit["wav"], input_pins)
    authorized = authorize_audio_input(
        pin,
        channels=audo_import.CHANNELS,
        sample_rate=audo_import.SAMPLE_RATE,
        frame_count=audo_import.FRAME_COUNT,
        context=audio_origin,
    )
    source = audo_import.InputFile(
        pin.path,
        -1,
        pin.identity,
        len(authorized.wav_bytes),
        authorized.wav_sha256,
        authorized.wav_bytes,
    )
    try:
        wav = audo_import.parse_strict_wav(source)
        encoded = audo_import.encode_xbox_ima(wav.samples)
        decoded = audo_import.decode_xbox_ima(encoded)
        metrics = audo_import.quality(wav.samples, decoded)
    except audo_import.AudioImportError as exc:
        raise ProjectError(f"menu-back WAV is invalid: {exc}") from exc
    pack_offset = (
        audo_import.OUTER_PACK_OFFSET + audo_import.CHUNK_OFFSET +
        audo_import.HEADER_SIZE + audo_import.SYSTEM_SIZE
    )
    target = {
        "selector": "menu-back_01",
        "outer_index": audo_import.OUTER_INDEX,
        "chunk_index": audo_import.CHUNK_INDEX,
        "xiso_pack_path": audo_import.PACK_PATH,
        "xiso_pack_sector": audo_import.PACK_SECTOR,
        "xiso_pack_size": audo_import.PACK_SIZE,
        "xiso_pack_sha256": audo_import.PACK_SHA256,
        "pack_offset": pack_offset,
        "xiso_absolute_span_offset": audo_import.ABSOLUTE_PAYLOAD_OFFSET,
        "span_sha256": audo_import.SOURCE_PAYLOAD_SHA256,
        "wrapper_pack_offset": (
            audo_import.OUTER_PACK_OFFSET + audo_import.CHUNK_OFFSET
        ),
        "wrapper_size": audo_import.WRAPPER_SIZE,
        "wrapper_sha256": audo_import.WRAPPER_SHA256,
    }
    report = {
        "schema": "nfl2k5_visual_mod_menu_back_audio_span/v1",
        "input_wav": {
            "path": edit["wav"],
            "size": pin.size,
            "sha256": pin.sha256,
            "pcm_sha256": authorized.pcm_sha256,
            "channels": audo_import.CHANNELS,
            "sample_rate": audo_import.SAMPLE_RATE,
            "frame_count": audo_import.FRAME_COUNT,
        },
        "target": target,
        "replacement": {
            "span_size": len(encoded),
            "span_sha256": digest(encoded),
            "codec": "Xbox IMA ADPCM",
            "quality": metrics,
        },
        "claims": {
            "exact_source_origin_gate_passed": True,
            "source_containment_gate_passed": True,
            "fixed_size_standalone_audo_wav_import_proved": True,
            "generic_nfl_audo_import_proved": False,
            "runtime_visibility_proved": False,
            "wrapper_header_preserved": True,
            "system_metadata_preserved": True,
            "unknown_tail_preserved": True,
        },
    }
    return encoded, [], report, "menu-back_01", target


def build_audo_audio_import(
    edit: dict[str, Any],
    project: ProjectFile,
    input_pins: dict[Path, InputPin],
    slot: Any,
    audio_origin: AudioOriginContext,
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Encode one catalog-authorized exact standalone AUDO physical slot."""

    require(edit["asset_id"] == slot.asset_id,
            "standalone-audio logical selector changed during resolution")
    pin = resolve_asset(project, edit["wav"], input_pins)
    authorized = authorize_audio_input(
        pin,
        channels=slot.channels,
        sample_rate=slot.sample_rate,
        frame_count=slot.frame_count,
        context=audio_origin,
    )
    try:
        wav = fixed_audo_adapter.parse_strict_wav(authorized.wav_bytes, slot)
        encoded = fixed_audo_adapter.encode_xbox_ima(wav, slot)
        decoded = fixed_audo_adapter.decode_xbox_ima(encoded, slot)
        metrics = fixed_audo_adapter.quality(wav.samples, decoded, slot)
    except fixed_audo_adapter.FixedAudoError as exc:
        raise ProjectError(
            f"standalone-audio WAV is invalid for {slot.name}: {exc}"
        ) from exc
    target = {
        "selector": slot.asset_id,
        "asset_id": slot.asset_id,
        "name": slot.name,
        "outer_index": slot.outer_index,
        "chunk_index": slot.chunk_index,
        "channels": slot.channels,
        "sample_rate": slot.sample_rate,
        "frame_count": slot.frame_count,
        "xiso_pack_path": slot.pack_path,
        "xiso_pack_sector": slot.pack_sector,
        "xiso_pack_size": slot.pack_size,
        "xiso_pack_sha256": slot.pack_sha256,
        "pack_offset": slot.payload_pack_offset,
        "xiso_absolute_span_offset": slot.payload_absolute_offset,
        "span_sha256": slot.payload_sha256,
        "wrapper_pack_offset": slot.wrapper_pack_offset,
        "wrapper_size": slot.wrapper_size,
        "wrapper_sha256": slot.wrapper_sha256,
        "wrapper_header_sha256": slot.wrapper_header_sha256,
        "system_size": slot.system_size,
        "system_sha256": slot.system_sha256,
        "tail_size": slot.tail_size,
        "tail_sha256": slot.tail_sha256,
    }
    report = {
        "schema": "nfl2k5_visual_mod_audo_audio_span/v1",
        "catalog": {
            "path": str(fixed_audo_adapter.CAPACITY_REPORT),
            "sha256": fixed_audo_adapter.CAPACITY_REPORT_SHA256,
            "legacy_capacity_classification": slot.classification,
            "product_edit_status": "Editable",
        },
        "input_wav": {
            "path": edit["wav"],
            "size": pin.size,
            "sha256": pin.sha256,
            "pcm_sha256": authorized.pcm_sha256,
            "channels": slot.channels,
            "sample_rate": slot.sample_rate,
            "frame_count": slot.frame_count,
        },
        "target": target,
        "replacement": {
            "span_size": len(encoded),
            "span_sha256": digest(encoded),
            "codec": "Xbox IMA ADPCM",
            "quality": metrics,
        },
        "claims": {
            "exact_source_origin_gate_passed": True,
            "source_containment_gate_passed": True,
            "fixed_size_standalone_audo_wav_import_proved": True,
            "distinct_exact_physical_slot_boundary": True,
            "semantic_aliases_expand_write_span": False,
            "semantic_cue_identity_proved": False,
            "exact_physical_outer_chunk_selector": True,
            "runtime_selector_ownership_proved": False,
            "runtime_visibility_proved": False,
            "wrapper_header_preserved": True,
            "system_metadata_preserved": True,
            "unknown_tail_preserved": True,
            "public_project_contains_raw_offsets": False,
            "public_project_contains_retail_audio": False,
        },
    }
    return encoded, [], report, slot.asset_id, target


def build_ausb_audio_imports(
    edit: dict[str, Any],
    project: ProjectFile,
    input_pins: dict[Path, InputPin],
    slot: Any,
    audio_origin: AudioOriginContext,
    entries: Mapping[str, common.XdvdfsEntry],
    source_fd: int,
    pack_hashes: dict[str, str],
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any],
                str, dict[str, Any]]]:
    """Authorize and compile one logical AUSB slot into one or two XISO spans."""

    requested_asset_id = str(edit["asset_id"])
    require(
        audio_origin.streaming_catalog.resolve(requested_asset_id) is slot,
        "streaming-audio selector changed during resolution",
    )
    pin = resolve_asset(project, edit["wav"], input_pins)
    authorized = authorize_audio_input(
        pin,
        channels=slot.channels,
        sample_rate=slot.sample_rate,
        frame_count=slot.frame_count,
        context=audio_origin,
    )
    compiled = _compile_authorized_streaming_slot(slot, authorized)
    compiled.resolve_asset_id(requested_asset_id)
    require(
        compiled.input_wav_sha256 == pin.sha256
        and compiled.input_pcm_sha256 == authorized.pcm_sha256
        and 1 <= len(compiled.pack_slices) <= 2,
        "streaming-audio compiler lost its authorized input or fixed span plan",
    )

    results = []
    for span_index, payload_slice in enumerate(compiled.pack_slices):
        pack_path = f"vc_53450030/{payload_slice.pack_name}"
        pack = entries.get(pack_path.casefold())
        require(
            pack is not None
            and payload_slice.pack_offset + payload_slice.length <= pack.size,
            f"streaming-audio pack extent is unavailable: {pack_path}",
        )
        assert pack is not None
        if pack_path not in pack_hashes:
            pack_hashes[pack_path] = common.sha256_fd(
                source_fd, pack.byte_offset, pack.size
            )
        absolute = pack.byte_offset + payload_slice.pack_offset
        retail_sha256 = digest(common.read_exact(
            source_fd, absolute, payload_slice.length
        ))
        selector = (
            f"{compiled.canonical_id}.span{span_index}."
            f"p{payload_slice.payload_offset:010x}"
        )
        target = {
            "selector": selector,
            "requested_asset_id": requested_asset_id,
            "canonical_id": compiled.canonical_id,
            "affected_asset_ids": list(compiled.affected_asset_ids),
            "shared_owner_effect": compiled.shared_owner_effect,
            "composition_sha256": compiled.composition_sha256,
            "span_index": span_index,
            "span_count": len(compiled.pack_slices),
            "payload_offset": payload_slice.payload_offset,
            "xiso_pack_path": pack_path,
            "xiso_pack_sector": pack.sector,
            "xiso_pack_size": pack.size,
            "xiso_pack_sha256": pack_hashes[pack_path],
            "pack_offset": payload_slice.pack_offset,
            "xiso_absolute_span_offset": absolute,
            "span_sha256": retail_sha256,
        }
        report = {
            "schema": "nfl2k5_visual_mod_ausb_audio_span/v1",
            "input_wav": {
                "path": edit["wav"],
                "size": pin.size,
                "sha256": pin.sha256,
                "pcm_sha256": authorized.pcm_sha256,
                "channels": slot.channels,
                "sample_rate": slot.sample_rate,
                "frame_count": slot.frame_count,
            },
            "logical_effect": {
                "requested_asset_id": requested_asset_id,
                "canonical_id": compiled.canonical_id,
                "affected_asset_ids": list(compiled.affected_asset_ids),
                "shared_owner_effect": compiled.shared_owner_effect,
            },
            "target": target,
            "replacement": {
                "span_size": payload_slice.length,
                "span_sha256": payload_slice.payload_sha256,
                "whole_encoded_sha256": compiled.encoded_sha256,
                "decoded_pcm_sha256": compiled.decoded_pcm_sha256,
                "composition_sha256": compiled.composition_sha256,
                "codec": "Xbox IMA ADPCM",
            },
            "claims": {
                "exact_source_origin_gate_passed": True,
                "source_containment_gate_passed": True,
                "same_authorized_snapshot_encoded": True,
                "fixed_allocation_preserved": True,
                "one_or_two_pack_spans_only": True,
                "all_physical_aliases_change_together": True,
                "public_project_contains_raw_offsets": False,
                "public_project_contains_retail_audio": False,
                "private_source_fingerprints_serialized": False,
                "runtime_visibility_proved": False,
            },
        }
        results.append((payload_slice.payload, [], report, selector, target))
    return results


def prepare_project(project: ProjectFile, index_pin: ownership.PinnedLargeFile,
                    inventory_pin: ownership.PinnedLargeFile,
                    report_pins: dict[str, InputPin],
                    output_parent: Path, source_fd: int,
                    entries: Mapping[str, common.XdvdfsEntry],
                    source_cache_root: Path | None = None,
                    exact_inventory_path: Path | None = None,
                    containment_inventory_path: Path | None = None) \
        -> PreparedProject:
    input_pins = pin_project_inputs(project)
    temporary = Path(tempfile.mkdtemp(
        prefix=".nfl2k5-visual-mod-", dir=output_parent)).resolve(strict=True)
    temp_root = ownership.track_existing(temporary, True)
    temp_files: list[ownership.OwnedPath] = []
    report_paths: dict[str, Path] = {}
    try:
        for number, (kind, pin) in enumerate(sorted(report_pins.items())):
            path = temporary / f"report_{number:02d}_{kind}.json"
            temp_files.append(exclusive_payload(path, pin.payload, temp_root))
            report_paths[kind] = path

        roster_outer_indices = {
            int(edit["resource_outer_index"])
            for edit in project.value["edits"]
            if edit["kind"] in ROSTER_REPORT_FREE_KINDS
        }
        roster_views = (
            load_roster_resources(
                index_pin.path, inventory_pin.path, roster_outer_indices)
            if roster_outer_indices else {}
        )
        universal_edits = [
            edit for edit in project.value["edits"]
            if edit["kind"] == UNIVERSAL_FIXED_TEXT_KIND
        ]
        safe_catalog = (
            safe_text_adapter.SafeTextCatalog.from_paths(
                index_pin.path, inventory_pin.path
            )
            if universal_edits else None
        )
        safe_replacements = {
            replacement.selector: replacement
            for replacement in (
                safe_catalog.resolve_edits(universal_edits)
                if safe_catalog is not None else ()
            )
        }
        require(
            len(safe_replacements) == len(universal_edits),
            "universal text resolver changed the logical edit count",
        )
        safe_pack_hashes: dict[str, str] = {}
        audio_edits = [
            edit for edit in project.value["edits"]
            if edit["kind"] in AUDIO_KINDS
        ]
        audio_origin = (
            load_audio_origin_context(
                index_pin,
                inventory_pin,
                report_paths[AUDO_AUDIO_KIND],
                source_cache_root,
                exact_inventory_path,
                containment_inventory_path,
            )
            if audio_edits else None
        )
        audo_edits = [
            edit for edit in project.value["edits"]
            if edit["kind"] == AUDO_AUDIO_KIND
        ]
        audo_slots = (
            {
                slot.asset_id: slot
                for slot in fixed_audo_adapter.load_editable_slots(
                    report_paths[AUDO_AUDIO_KIND]
                )
            }
            if audo_edits else {}
        )
        require(
            all(edit["asset_id"] in audo_slots for edit in audo_edits),
            "standalone-audio project selects an unknown physical asset slot",
        )
        ausb_slots_by_edit: dict[int, Any] = {}
        deduplicated_ausb_edits: set[int] = set()
        if any(edit["kind"] == AUSB_AUDIO_KIND for edit in audio_edits):
            assert audio_origin is not None
            ausb_slots_by_edit, deduplicated_ausb_edits = \
                resolve_ausb_project_edits(project, input_pins, audio_origin)
        prepared: list[PreparedEdit] = []
        selectors: set[tuple[str, str]] = set()
        stadium_groups: dict[str, list[dict[str, Any]]] = {}
        for row in project.value["edits"]:
            if row["kind"] != STADIUM_TEXTURE_KIND:
                continue
            scene_key = str(row["target"]).rsplit(".texture", 1)[0]
            stadium_groups.setdefault(scene_key, []).append(row)
        handled_stadium_scenes: set[str] = set()
        ausb_pack_hashes: dict[str, str] = {}
        for edit_index, edit in enumerate(project.value["edits"]):
            kind = edit["kind"]
            if edit_index in deduplicated_ausb_edits:
                continue
            effective_edit = edit
            effective_input_hashes: dict[str, str | None] | None = None
            if kind == UNIF_COLOR_KIND:
                try:
                    built = unif_color_adapter.build_unif_color_imports(edit)
                except unif_color_adapter.UnifColorWriterError as exc:
                    raise ProjectError(str(exc)) from exc
            elif kind == "team_identity":
                built = build_team_identity_imports(edit, report_paths[kind])
            elif kind == "player_roster":
                built = build_player_roster_imports(edit, report_paths[kind])
            elif kind == ROSTER_TEAM_PROVIDER_KIND:
                built = build_roster_team_text_imports(
                    edit, roster_views[int(edit["resource_outer_index"])])
            elif kind == ROSTER_PLAYER_PROVIDER_KIND:
                built = build_roster_player_text_imports(
                    edit, roster_views[int(edit["resource_outer_index"])])
            elif kind == UNIVERSAL_FIXED_TEXT_KIND:
                assert safe_catalog is not None
                built = [build_universal_fixed_text_import(
                    edit,
                    safe_catalog,
                    safe_replacements[str(edit["selector"])],
                    entries,
                    safe_pack_hashes,
                )]
            elif kind == "player_portrait":
                built = build_player_portrait_imports(
                    len(prepared), edit, project, input_pins, report_paths[kind],
                    index_pin.path, temp_root, temp_files)
            elif kind == MENU_BACK_AUDIO_KIND:
                assert audio_origin is not None
                built = [build_menu_back_audio_import(
                    edit, project, input_pins, audio_origin
                )]
            elif kind == AUDO_AUDIO_KIND:
                assert audio_origin is not None
                built = [build_audo_audio_import(
                    edit,
                    project,
                    input_pins,
                    audo_slots[edit["asset_id"]],
                    audio_origin,
                )]
            elif kind == AUSB_AUDIO_KIND:
                assert audio_origin is not None
                built = build_ausb_audio_imports(
                    edit,
                    project,
                    input_pins,
                    ausb_slots_by_edit[edit_index],
                    audio_origin,
                    entries,
                    source_fd,
                    ausb_pack_hashes,
                )
            elif kind == STADIUM_TEXTURE_KIND:
                scene_key = str(edit["target"]).rsplit(".texture", 1)[0]
                if scene_key in handled_stadium_scenes:
                    continue
                handled_stadium_scenes.add(scene_key)
                scene_edits = stadium_groups[scene_key]
                built = [build_stadium_scene_import(
                    len(prepared),
                    scene_edits,
                    project,
                    input_pins,
                    index_pin.path,
                    inventory_pin.path,
                    temp_root,
                    temp_files,
                )]
                effective_edit = {
                    "kind": STADIUM_TEXTURE_KIND,
                    "scene": scene_key,
                    "edits": [
                        {"target": row["target"], "png": row["png"]}
                        for row in scene_edits
                    ],
                }
                effective_input_hashes = {
                    str(row["target"]): resolve_asset(
                        project, str(row["png"]), input_pins
                    ).sha256
                    for row in scene_edits
                }
            else:
                built = [build_one_import(
                    len(prepared), edit, project, input_pins, report_paths,
                    index_pin.path, inventory_pin.path, temp_root, temp_files,
                    source_fd)]
            for replacement, previews, report, selector, target in built:
                order = len(prepared)
                key = (kind, selector)
                require(key not in selectors,
                        f"project repeats target {kind}:{selector}")
                selectors.add(key)
                (pack_path, pack_sector, pack_size, pack_sha, pack_offset,
                 absolute, retail_sha) = target_proof(kind, target)
                # Bound to retail bytes before any XISO copy.
                runs: list[list[int]] = []
                span_path = temporary / f"{order:05d}_replacement.bin"
                temp_files.append(exclusive_payload(
                    span_path, replacement, temp_root))
                normalized = normalized_import_report(report, effective_edit, kind)
                import_payload = canonical_json(normalized)
                import_path = temporary / f"{order:05d}_import.json"
                temp_files.append(exclusive_payload(
                    import_path, import_payload, temp_root))
                preview_records: list[tuple[str, Path, int, str]] = []
                for preview_order, (name, payload) in enumerate(previews):
                    final_name = (f"{order:05d}_{safe_name(selector)}_"
                                  f"{preview_order:02d}_{safe_name(name)}")
                    preview_path = temporary / final_name
                    temp_files.append(exclusive_payload(
                        preview_path, payload, temp_root))
                    preview_records.append(
                        (final_name, preview_path, len(payload), digest(payload)))
                input_hashes: dict[str, str | None] = (
                    dict(effective_input_hashes)
                    if effective_input_hashes is not None else {}
                )
                if effective_input_hashes is None:
                    if kind in {"torso", "sleeve", "pants"}:
                        input_fields = ("clean_png", "mud_png")
                    elif kind in {"team_identity", "player_roster"} \
                            | ROSTER_REPORT_FREE_KINDS \
                            | {UNIVERSAL_FIXED_TEXT_KIND, UNIF_COLOR_KIND}:
                        # A colour edit carries no file input to hash.
                        input_fields = ()
                    elif kind in AUDIO_KINDS:
                        input_fields = ("wav",)
                    else:
                        input_fields = ("png",)
                    for field in input_fields:
                        value = edit[field]
                        input_hashes[field] = (None if value is None else
                            resolve_asset(project, value, input_pins).sha256)
                prepared.append(PreparedEdit(
                    order, kind, selector, effective_edit, input_hashes, target,
                    pack_path, pack_sector, pack_size, pack_sha, pack_offset,
                    absolute, retail_sha, span_path,
                    len(replacement), digest(replacement), runs, import_path,
                    digest(import_payload), preview_records))
        return PreparedProject(prepared, temp_root, temp_files, input_pins, report_pins)
    except Exception:
        ownership.cleanup_owned(temp_files, [temp_root])
        raise


def validate_source(source_path: Path) \
        -> tuple[Path, int, tuple[int, int], str, dict[str, common.XdvdfsEntry],
                 dict[str, int], common.XdvdfsEntry]:
    supplied = source_path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "source XISO must be a non-symlink regular file")
    source = source_path.resolve(strict=True)
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        info = os.fstat(descriptor)
        identity = common.fd_identity(descriptor)
        # The container is NOT pinned. How a disc was read -- raw with the video
        # partition in front, extracted, padded, trimmed -- changes the file's
        # size and hash without changing one byte of the game, and requiring it
        # to equal the project's own rip refused legal dumps at Build time. What
        # is still exact is below and stronger: the game partition is located,
        # its file count checked, and default.xbe hashed. `sha` remains the real
        # digest of this file, recorded for provenance rather than compared.
        require(stat.S_ISREG(info.st_mode) and
                identity == (supplied.st_dev, supplied.st_ino) and
                common.path_identity(source) == identity,
                "source XISO identity/type changed")
        sha = common.sha256_fd(descriptor)
        entries, directory = common.parse_xdvdfs(descriptor, info.st_size)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        xbe = entries.get("default.xbe")
        require(len(files) == 19 and xbe is not None and
                xbe.size == common.EXPECTED_XBE_SIZE and
                common.sha256_fd(descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "retail XDVDFS/default.xbe identity changed")
        assert xbe is not None
        return source, descriptor, identity, sha, entries, directory, xbe
    except Exception:
        os.close(descriptor)
        raise


def validate_team_identity_source(edit: PreparedEdit, source_fd: int,
                                  pack: common.XdvdfsEntry) -> None:
    target = edit.target
    body_pack_offset = ROST_OUTER_PACK_OFFSET + ROST_WRAPPER_SIZE
    wrapper = common.read_exact(
        source_fd, pack.byte_offset + ROST_OUTER_PACK_OFFSET, ROST_WRAPPER_SIZE)
    require(struct.unpack_from("<4s7I", wrapper) ==
            (b"ROST", 593_760, 593_760, 0, 0, 0, 0, 0),
            "team_identity main ROST wrapper changed")
    team_record = int(target["team_record_body_offset"])
    pointer_field = int(target["record_pointer_field_offset"])
    record_absolute = pack.byte_offset + body_pack_offset + team_record
    pointer = struct.unpack(
        "<i", common.read_exact(source_fd, record_absolute + pointer_field, 4))[0]
    require(team_record + pointer_field + pointer - 1 ==
            int(target["body_string_offset"]),
            f"team_identity serialized pointer changed: {edit.selector}")
    asset_pointer = struct.unpack(
        "<i", common.read_exact(source_fd, record_absolute + 0x10C, 4))[0]
    asset_body_offset = team_record + 0x10C + asset_pointer - 1
    asset = (str(target["asset_code"]) + "\0").encode("utf-16le")
    require(len(asset) == 6 and common.read_exact(
        source_fd, pack.byte_offset + body_pack_offset + asset_body_offset, 6) == asset,
        "team_identity asset-code selector changed")
    require(common.read_exact(source_fd, record_absolute + 0x11C, 1) ==
            bytes([int(target["roster_size"])]),
            "team_identity roster count changed")


def validate_player_roster_source(edit: PreparedEdit, source_fd: int,
                                  pack: common.XdvdfsEntry) -> None:
    """Bind an audit-derived player selector to retail pointers and memberships."""
    target = edit.target
    body_pack_offset = ROST_OUTER_PACK_OFFSET + ROST_WRAPPER_SIZE
    wrapper = common.read_exact(
        source_fd, pack.byte_offset + ROST_OUTER_PACK_OFFSET, ROST_WRAPPER_SIZE)
    require(struct.unpack_from("<4s7I", wrapper) ==
            (b"ROST", ROST_BODY_SIZE, ROST_BODY_SIZE, 0, 0, 0, 0, 0),
            "player_roster main ROST wrapper changed")
    body = common.read_exact(
        source_fd, pack.byte_offset + body_pack_offset, ROST_BODY_SIZE)
    player_index = int(target["primary_player_index"])
    record_offset = ROST_PRIMARY_BASE + player_index * ROST_PLAYER_STRIDE
    require(record_offset == int(target["player_record_body_offset"]),
            f"player_roster record selector changed: {edit.selector}")
    record = body[record_offset:record_offset + ROST_PLAYER_STRIDE]
    require(len(record) == ROST_PLAYER_STRIDE and
            struct.unpack_from("<H", record, 0x06)[0] == int(target["face_id"]) and
            record[0x35] == int(target["position_code"]),
            f"player_roster face/position selector changed: {edit.selector}")
    before_word = int(str(target["retail_jersey_word"]), 16)
    after_word = int(str(target["replacement_jersey_word"]), 16)
    actual_word = struct.unpack_from("<I", record, PLAYER_JERSEY_FIELD)[0]
    require(actual_word == before_word and
            ((before_word >> PLAYER_JERSEY_SHIFT) & 0x7F) ==
                int(target["retail_jersey_number"]) and
            ((after_word >> PLAYER_JERSEY_SHIFT) & 0x7F) ==
                int(target["replacement_jersey_number"]) and
            (before_word & ~PLAYER_JERSEY_MASK) ==
                (after_word & ~PLAYER_JERSEY_MASK),
            f"player_roster masked jersey contract changed: {edit.selector}")

    for field, pointer_field in (("first_name", PLAYER_FIRST_POINTER_FIELD),
                                 ("last_name", PLAYER_LAST_POINTER_FIELD)):
        pointer = struct.unpack_from("<i", record, pointer_field)[0]
        actual_target = record_offset + pointer_field + pointer - 1
        require(actual_target == int(target[f"{field}_body_offset"]),
                f"player_roster {field} pointer changed: {edit.selector}")
    if target["field"] in {"first_name", "last_name"}:
        require(int(target["record_pointer_field_offset"]) ==
                ({"first_name": PLAYER_FIRST_POINTER_FIELD,
                  "last_name": PLAYER_LAST_POINTER_FIELD}[target["field"]]) and
                int(target["body_string_offset"]) ==
                int(target[f"{target['field']}_body_offset"]),
                f"player_roster string target arithmetic changed: {edit.selector}")
    else:
        require(target["field"] == "jersey_number" and
                int(target["record_field_offset"]) == PLAYER_JERSEY_FIELD and
                int(target["body_field_offset"]) ==
                    record_offset + PLAYER_JERSEY_FIELD,
                f"player_roster jersey target arithmetic changed: {edit.selector}")

    # One full pass is attached to the first subspan.  It proves the audit's
    # relative-pointer formula and binds this player to exactly its listed teams.
    if target["field"] == "first_name":
        memberships: list[int] = []
        active_total = 0
        primary_end = ROST_PRIMARY_BASE + ROST_PRIMARY_COUNT * ROST_PLAYER_STRIDE
        secondary_end = ROST_SECONDARY_BASE + ROST_SECONDARY_COUNT * ROST_PLAYER_STRIDE
        for team_index in range(ROST_TEAM_COUNT):
            team_offset = ROST_TEAM_BASE + team_index * ROST_TEAM_STRIDE
            count = body[team_offset + ROST_TEAM_COUNT_FIELD]
            require(count <= ROST_TEAM_SLOTS,
                    "player_roster team roster count exceeds slot allocation")
            found = 0
            for slot in range(ROST_TEAM_SLOTS):
                field_offset = team_offset + slot * 4
                pointer = struct.unpack_from("<i", body, field_offset)[0]
                if slot >= count:
                    require(pointer == 0,
                            "player_roster unused membership pointer is non-null")
                    continue
                active_total += 1
                selected = field_offset + pointer - 1
                valid = ((ROST_PRIMARY_BASE <= selected < primary_end and
                          (selected - ROST_PRIMARY_BASE) % ROST_PLAYER_STRIDE == 0) or
                         (ROST_SECONDARY_BASE <= selected < secondary_end and
                          (selected - ROST_SECONDARY_BASE) % ROST_PLAYER_STRIDE == 0))
                require(pointer != 0 and valid,
                        "player_roster active membership pointer is invalid")
                if selected == record_offset:
                    found += 1
            require(found <= 1,
                    "player_roster player appears twice in one team")
            if found:
                memberships.append(team_index)
        require(active_total == 2634 and memberships == target["team_indices"],
                f"player_roster membership selector changed: {edit.selector}")


def validate_sparse_roster_source(edit: PreparedEdit, source_fd: int,
                                  pack: common.XdvdfsEntry) -> None:
    """Bind one report-free sparse ROST span to the retail copy."""

    target = edit.target
    resource_pack_offset = int(target["resource_pack_offset"])
    body_size = int(target["resource_body_size"])
    wrapper = common.read_exact(
        source_fd, pack.byte_offset + resource_pack_offset, ROST_WRAPPER_SIZE)
    require(struct.unpack_from("<4s7I", wrapper) ==
            (b"ROST", body_size, body_size, 0, 0, 0, 0, 0),
            f"sparse ROST wrapper changed: {edit.selector}")
    body = common.read_exact(
        source_fd, pack.byte_offset + resource_pack_offset + ROST_WRAPPER_SIZE,
        body_size)
    require(digest(body) == target["resource_body_sha256"] and
            body[0x0C:0x10] == b"ROST" and
            fixed_utf16le(
                str(target["resource_label"]),
                len((str(target["resource_label"]) + "\0").encode("utf-16le")),
                "ROST resource label",
            ) == body[0x20:0x20 +
                      len((str(target["resource_label"]) + "\0").encode("utf-16le"))],
            f"sparse ROST body/label changed: {edit.selector}")

    field = str(target["field"])
    if edit.kind == ROSTER_TEAM_PROVIDER_KIND:
        record = int(target["team_record_body_offset"])
        pointer_field = int(target["record_pointer_field_offset"])
        pointer = struct.unpack_from("<i", body, record + pointer_field)[0]
        require(record + pointer_field + pointer - 1 ==
                int(target["body_string_offset"]) == int(target["body_offset"]),
                f"sparse team pointer changed: {edit.selector}")
        asset_pointer = struct.unpack_from("<i", body, record + 0x10C)[0]
        asset_offset = record + 0x10C + asset_pointer - 1
        asset = (str(target["asset_code"]) + "\0").encode("utf-16le")
        require(body[asset_offset:asset_offset + len(asset)] == asset and
                body[record + ROST_TEAM_COUNT_FIELD] == int(target["roster_size"]),
                f"sparse team art/roster selector changed: {edit.selector}")
    else:
        require(edit.kind == ROSTER_PLAYER_PROVIDER_KIND,
                "unexpected sparse roster edit kind")
        record = int(target["player_record_body_offset"])
        raw = body[record:record + ROST_PLAYER_STRIDE]
        require(len(raw) == ROST_PLAYER_STRIDE and
                struct.unpack_from("<H", raw, 0x06)[0] == int(target["face_id"]) and
                raw[0x35] == int(target["position_code"]),
                f"sparse player face/position selector changed: {edit.selector}")
        actual_word = struct.unpack_from("<I", raw, PLAYER_JERSEY_FIELD)[0]
        require(actual_word == int(str(target["retail_jersey_word"]), 16),
                f"sparse player jersey source changed: {edit.selector}")
        if field in {"first_name", "last_name"}:
            pointer_field = int(target["record_pointer_field_offset"])
            pointer = struct.unpack_from("<i", raw, pointer_field)[0]
            require(record + pointer_field + pointer - 1 ==
                    int(target["body_string_offset"]) == int(target["body_offset"]),
                    f"sparse player name pointer changed: {edit.selector}")
        else:
            require(field == "jersey_number" and
                    int(target["record_field_offset"]) == PLAYER_JERSEY_FIELD and
                    int(target["body_field_offset"]) ==
                        record + PLAYER_JERSEY_FIELD == int(target["body_offset"]) and
                    (int(str(target["replacement_jersey_word"]), 16) &
                     ~PLAYER_JERSEY_MASK) == (actual_word & ~PLAYER_JERSEY_MASK),
                    f"sparse player jersey target changed: {edit.selector}")


def validate_universal_fixed_text_source(
    edit: PreparedEdit, source_fd: int, pack: common.XdvdfsEntry
) -> None:
    """Recheck the logical-only fixed-text contract against the retail XISO."""

    target = edit.target
    require(
        edit.project_edit == {
            "kind": UNIVERSAL_FIXED_TEXT_KIND,
            "selector": edit.selector,
            "text": edit.project_edit.get("text"),
        }
        and UNIVERSAL_TEXT_SELECTOR_RE.fullmatch(edit.selector) is not None
        and target["selector"] == edit.selector
        and int(target["allocation_bytes"]) == edit.replacement_size
        and edit.replacement_size >= 4
        and edit.replacement_size % 2 == 0,
        f"universal text target arithmetic changed: {edit.selector}",
    )
    before = common.read_exact(source_fd, edit.absolute, edit.replacement_size)
    after = edit.replacement_path.read_bytes()
    require(
        digest(before) == edit.retail_span_sha256
        and before[-2:] == b"\0\0"
        and len(after) == edit.replacement_size,
        f"universal text source allocation changed: {edit.selector}",
    )
    terminator = next(
        (offset for offset in range(0, len(after), 2)
         if after[offset:offset + 2] == b"\0\0"),
        None,
    )
    require(
        terminator is not None
        and after[terminator:] == bytes(len(after) - terminator),
        f"universal text replacement lost its terminator/zero fill: {edit.selector}",
    )


def validate_menu_back_audio_source(
    edit: PreparedEdit, source_fd: int, pack: common.XdvdfsEntry
) -> None:
    target = edit.target
    wrapper_offset = int(target["wrapper_pack_offset"])
    wrapper = common.read_exact(
        source_fd, pack.byte_offset + wrapper_offset,
        int(target["wrapper_size"]),
    )
    try:
        audo_import.validate_retail_wrapper(wrapper)
    except audo_import.AudioImportError as exc:
        raise ProjectError(f"menu-back retail AUDO changed: {exc}") from exc
    require(
        digest(wrapper) == target["wrapper_sha256"] and
        edit.pack_offset == wrapper_offset + audo_import.HEADER_SIZE +
        audo_import.SYSTEM_SIZE and
        edit.replacement_size == audo_import.PAYLOAD_SIZE,
        "menu-back AUDO target arithmetic changed",
    )


def validate_audo_audio_source(
    edit: PreparedEdit, source_fd: int, pack: common.XdvdfsEntry
) -> None:
    """Rebind a logical standalone-audio ID to its complete retail wrapper."""

    target = edit.target
    wrapper_offset = int(target["wrapper_pack_offset"])
    wrapper_size = int(target["wrapper_size"])
    wrapper = common.read_exact(
        source_fd, pack.byte_offset + wrapper_offset, wrapper_size
    )
    slots = {
        slot.asset_id: slot
        for slot in fixed_audo_adapter.load_editable_slots()
    }
    slot = slots.get(edit.selector)
    require(slot is not None, f"standalone-audio selector is no longer editable: {edit.selector}")
    try:
        fixed_audo_adapter.validate_source_wrapper(wrapper, slot)
    except fixed_audo_adapter.FixedAudoError as exc:
        raise ProjectError(
            f"standalone-audio retail AUDO changed ({edit.selector}): {exc}"
        ) from exc
    require(
        edit.project_edit == {
            "asset_id": edit.selector,
            "kind": AUDO_AUDIO_KIND,
            "wav": edit.project_edit.get("wav"),
        }
        and target["asset_id"] == edit.selector
        and wrapper_offset == slot.wrapper_pack_offset
        and wrapper_size == slot.wrapper_size
        and edit.pack_offset == slot.payload_pack_offset
        and edit.replacement_size == slot.payload_size
        and edit.retail_span_sha256 == slot.payload_sha256,
        f"standalone-audio target arithmetic changed: {edit.selector}",
    )


def validate_ausb_audio_source(
    edit: PreparedEdit, source_fd: int, pack: common.XdvdfsEntry
) -> None:
    """Recheck one compiled AUSB slice without serializing private fingerprints."""

    del source_fd
    target = edit.target
    canonical_id = target.get("canonical_id")
    affected = target.get("affected_asset_ids")
    require(
        edit.project_edit == {
            "asset_id": edit.project_edit.get("asset_id"),
            "kind": AUSB_AUDIO_KIND,
            "wav": edit.project_edit.get("wav"),
        }
        and type(canonical_id) is str
        and AUSB_CANONICAL_ASSET_RE.fullmatch(canonical_id) is not None
        and target.get("requested_asset_id")
        == edit.project_edit.get("asset_id")
        and isinstance(affected, list)
        and 1 <= len(affected) <= 2
        and len(set(affected)) == len(affected)
        and all(
            type(value) is str
            and AUSB_LOGICAL_ASSET_RE.fullmatch(value) is not None
            for value in affected
        )
        and (
            edit.project_edit.get("asset_id") == canonical_id
            or edit.project_edit.get("asset_id") in affected
        )
        and target.get("shared_owner_effect") is (len(affected) == 2)
        and type(target.get("span_index")) is int
        and type(target.get("span_count")) is int
        and 0 <= target["span_index"] < target["span_count"] <= 2
        and type(target.get("payload_offset")) is int
        and target["payload_offset"] >= 0
        and target.get("selector") == edit.selector
        and edit.selector == (
            f"{canonical_id}.span{target['span_index']}."
            f"p{target['payload_offset']:010x}"
        )
        and target.get("xiso_pack_path") == edit.pack_path
        and target.get("xiso_pack_sector") == pack.sector
        and target.get("xiso_pack_size") == pack.size
        and target.get("pack_offset") == edit.pack_offset
        and target.get("span_sha256") == edit.retail_span_sha256,
        f"streaming-audio target arithmetic changed: {edit.selector}",
    )


def validate_crib_team_photo_source(
    edit: PreparedEdit, source_fd: int, pack: common.XdvdfsEntry
) -> None:
    """Bind the logical photo selector to its live fixed slot and padding."""

    target = edit.target
    padding_size = int(target["post_span_zero_padding"])
    require(
        edit.selector == target["selector"]
        and edit.replacement_size == int(target["span_size"])
        and edit.pack_offset == int(target["pack_offset"])
        and padding_size == crib_photo_targets.POST_SPAN_ZERO_PADDING,
        f"Crib Team Photo target arithmetic changed: {edit.selector}",
    )
    span = common.read_exact(source_fd, edit.absolute, edit.replacement_size)
    padding = common.read_exact(
        source_fd, edit.absolute + edit.replacement_size, padding_size)
    try:
        crib_photo_import.validate_source_binding(span, padding, target)
    except ValueError as exc:
        raise ProjectError(
            f"Crib Team Photo live source proof failed: {edit.selector}: {exc}"
        ) from exc


def require_non_overlapping_ranges(
    ranges: Iterable[tuple[int, int, str]],
) -> None:
    """Validate prepared spans in O(n log n), independent of project order."""

    ordered = sorted(ranges)
    for previous, current in zip(ordered, ordered[1:]):
        require(
            previous[1] <= current[0],
            f"project target spans overlap at {current[2]}",
        )


def bind_prepared_to_source(prepared: PreparedProject, source_fd: int,
                            entries: dict[str, common.XdvdfsEntry]) -> None:
    pack_hashes: dict[str, str] = {}
    ranges: list[tuple[int, int, str]] = []
    for edit in prepared.edits:
        pack_key = edit.pack_path.casefold()
        pack = entries.get(pack_key)
        # Sector is NOT compared. A sector number is where a particular build
        # of the image happened to place the file: a pressed disc, an
        # extract-xiso rebuild and a repack put all 19 files at completely
        # different sectors while every file is byte-identical. Pinning it meant
        # no image but the project's own could ever build. Size is compared here
        # and the pack's CONTENT hash immediately below, which is what actually
        # matters and is layout-independent.
        require(pack is not None and pack.size == edit.pack_size,
                f"source pack extent changed for {edit.kind}:{edit.selector}")
        assert pack is not None
        # DERIVE the absolute offset from the pack we just located, rather than
        # trusting the one recorded in the target. That recorded value was the
        # byte position in the project's own rebuild; a pressed disc and a
        # repack put the same pack somewhere else entirely, so every downstream
        # read would have landed in the wrong place. Everything that matters --
        # the pack's content hash, the span hash, the wrapper and padding -- is
        # still verified below, now against the right bytes.
        edit.absolute = pack.byte_offset + edit.pack_offset
        if pack_key not in pack_hashes:
            pack_hashes[pack_key] = common.sha256_fd(
                source_fd, pack.byte_offset, pack.size)
        require(pack_hashes[pack_key] == edit.pack_sha256,
                f"source pack hash changed for {edit.kind}:{edit.selector}")
        if edit.kind == "team_identity":
            validate_team_identity_source(edit, source_fd, pack)
        elif edit.kind == "player_roster":
            validate_player_roster_source(edit, source_fd, pack)
        elif edit.kind in ROSTER_REPORT_FREE_KINDS:
            validate_sparse_roster_source(edit, source_fd, pack)
        elif edit.kind == UNIVERSAL_FIXED_TEXT_KIND:
            validate_universal_fixed_text_source(edit, source_fd, pack)
        elif edit.kind == MENU_BACK_AUDIO_KIND:
            validate_menu_back_audio_source(edit, source_fd, pack)
        elif edit.kind == AUDO_AUDIO_KIND:
            validate_audo_audio_source(edit, source_fd, pack)
        elif edit.kind == AUSB_AUDIO_KIND:
            validate_ausb_audio_source(edit, source_fd, pack)
        elif edit.kind == CRIB_TEAM_PHOTO_KIND:
            validate_crib_team_photo_source(edit, source_fd, pack)
        require(edit.absolute == pack.byte_offset + edit.pack_offset and
                pack.byte_offset <= edit.absolute and
                edit.absolute + edit.replacement_size <= pack.byte_offset + pack.size,
                f"target arithmetic/extent changed for {edit.kind}:{edit.selector}")
        retail = common.read_exact(source_fd, edit.absolute, edit.replacement_size)
        require(digest(retail) == edit.retail_span_sha256,
                f"retail target span changed for {edit.kind}:{edit.selector}")
        replacement = edit.replacement_path.read_bytes()
        require(len(replacement) == edit.replacement_size and
                digest(replacement) == edit.replacement_sha256,
                f"temporary replacement changed for {edit.kind}:{edit.selector}")
        edit.relative_runs = difference_runs(retail, replacement)
        require(edit.kind in {"team_identity", "player_roster"} or edit.relative_runs,
                f"replacement equals retail for {edit.kind}:{edit.selector}")
        end = edit.absolute + edit.replacement_size
        ranges.append((edit.absolute, end, f"{edit.kind}:{edit.selector}"))
    require_non_overlapping_ranges(ranges)
    require(any(edit.relative_runs for edit in prepared.edits),
            "project produces no changed retail bytes")


def stream_pair(source_fd: int, output_fd: int, start: int, length: int,
                source_hash: Any, output_hash: Any,
                require_equal: bool) -> None:
    position = start
    remaining = length
    while remaining:
        amount = min(HASH_BLOCK, remaining)
        before = platform_compat.pread(source_fd, amount, position)
        after = platform_compat.pread(output_fd, amount, position)
        require(len(before) == amount and len(after) == amount,
                "short read during union-span verification")
        if require_equal:
            require(before == after,
                    f"output differs outside selected spans at 0x{position:x}")
        source_hash.update(before)
        output_hash.update(after)
        position += amount
        remaining -= amount


def verify_union(source_fd: int, output_fd: int, size: int,
                 edits: list[PreparedEdit]) -> dict[str, Any]:
    ordered = sorted(edits, key=lambda item: item.absolute)
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()
    offset_hash = hashlib.sha256()
    cursor = 0
    changed_count = 0
    total_span_bytes = 0
    for edit in ordered:
        require(edit.absolute >= cursor, "selected spans overlap during final verification")
        stream_pair(source_fd, output_fd, cursor, edit.absolute - cursor,
                    source_hash, output_hash, True)
        before = common.read_exact(source_fd, edit.absolute, edit.replacement_size)
        after = common.read_exact(output_fd, edit.absolute, edit.replacement_size)
        replacement = edit.replacement_path.read_bytes()
        require(digest(before) == edit.retail_span_sha256 and
                after == replacement and digest(after) == edit.replacement_sha256,
                f"selected span readback failed for {edit.kind}:{edit.selector}")
        source_hash.update(before)
        output_hash.update(after)
        actual_runs = difference_runs(before, after)
        require(actual_runs == edit.relative_runs,
                f"changed-byte ledger changed for {edit.kind}:{edit.selector}")
        for offset in iter_run_offsets(actual_runs, edit.absolute):
            offset_hash.update(struct.pack("<Q", offset))
            changed_count += 1
        total_span_bytes += edit.replacement_size
        cursor = edit.absolute + edit.replacement_size
    stream_pair(source_fd, output_fd, cursor, size - cursor,
                source_hash, output_hash, True)
    return {
        "source_sha256": source_hash.hexdigest(),
        "output_sha256": output_hash.hexdigest(),
        "span_count": len(ordered),
        "selected_span_bytes": total_span_bytes,
        "changed_byte_count": changed_count,
        "changed_offsets_u64le_sha256": offset_hash.hexdigest(),
        "all_bytes_outside_selected_spans_identical": True,
        "all_selected_spans_equal_validated_replacements": True,
        "selected_spans_non_overlapping": True,
    }


def write_all(descriptor: int, offset: int, payload: bytes) -> None:
    position = 0
    while position < len(payload):
        amount = platform_compat.pwrite(descriptor, payload[position:], offset + position)
        require(amount > 0, "short XISO patch write")
        position += amount


def stable_edit_record(edit: PreparedEdit) -> dict[str, Any]:
    return {
        "order": edit.order,
        "kind": edit.kind,
        "selector": edit.selector,
        "project_edit": edit.project_edit,
        "input_sha256": dict(sorted(edit.input_sha256.items())),
        "target": {
            "pack_path": edit.pack_path,
            "pack_sector": edit.pack_sector,
            "pack_size": edit.pack_size,
            "pack_sha256": edit.pack_sha256,
            "pack_offset": edit.pack_offset,
            "absolute_span_offset": edit.absolute,
            "retail_span_sha256": edit.retail_span_sha256,
        },
        "replacement": {
            "span_size": edit.replacement_size,
            "span_sha256": edit.replacement_sha256,
            "relative_changed_byte_count": run_count(edit.relative_runs),
            "relative_changed_offsets_u32le_sha256": offset_digest(
                iter_run_offsets(edit.relative_runs), "<I"),
            "relative_changed_runs": edit.relative_runs,
        },
        "import_report": {
            "file_name": edit.import_report_path.name,
            "sha256": edit.import_report_sha256,
        },
        "previews": [
            {"file_name": name, "size": size, "sha256": sha}
            for name, _, size, sha in edit.preview_paths
        ],
    }


def claims_for(edits: list[PreparedEdit]) -> dict[str, Any]:
    kinds = {edit.kind for edit in edits}
    claims: dict[str, Any] = {
        "single_retail_xiso_copy": True,
        "no_intermediate_xiso_copies": True,
        "fixed_span_importers_reused_without_codec_changes": True,
        "all_bytes_outside_union_identical": True,
        "originals_modified": False,
        "runtime_visibility_proved": False,
        "xemu_started": False, "title_executed": False,
        "portme": (
            "PORTME(runtime): capture each edited asset in title before claiming "
            "runtime visibility or a complete playable mod."
        ),
    }
    if "live_face" in kinds:
        claims["live_face_shape_geometry_modified"] = False
    if "create_team_field_art" in kinds:
        claims["create_team_field_art_is_static_live_field_resource"] = True
        claims["create_team_menu_or_team_select_imagery_modified"] = False
    if "team_identity" in kinds or ROSTER_TEAM_PROVIDER_KIND in kinds:
        claims.update({
            "team_identity_fixed_size_strings_only": True,
            "team_identity_art_code_modified": False,
            "team_identity_roster_pointer_or_membership_modified": False,
            "team_identity_stadium_modified": False,
            "team_identity_xbe_color_modified": False,
            "team_identity_relocation_or_allocation_modified": False,
        })
    if "player_roster" in kinds or ROSTER_PLAYER_PROVIDER_KIND in kinds:
        claims.update({
            "player_roster_primary_table_only": True,
            "player_roster_fixed_size_identity_and_jersey_only": True,
            "player_roster_team_membership_modified": False,
            "player_roster_team_count_modified": False,
            "player_roster_serialized_pointer_modified": False,
            "player_roster_position_modified": False,
            "player_roster_face_id_modified": False,
            "player_roster_ratings_modified": False,
            "player_roster_all_other_bits_modified": False,
            "player_roster_save_container_modified": False,
            "public_project_schema_exposes_raw_offsets": False,
            "speculative_executable_or_gameplay_patch_applied": False,
        })
    if kinds & ROSTER_REPORT_FREE_KINDS:
        claims.update({
            "roster_text_user_source_derived_catalog": True,
            "roster_text_sparse_project_contains_only_user_changes": True,
            "roster_text_shorter_strings_zero_fill_existing_allocation": True,
            "historical_roster_resources_supported": True,
        })
    if UNIVERSAL_FIXED_TEXT_KIND in kinds:
        claims.update({
            "universal_text_fixed_utf16le_allocations_only": True,
            "universal_text_strg_aliases_edit_together": True,
            "universal_text_situ_display_fields_only": True,
            "universal_text_situ_team_selectors_modified": False,
            "universal_text_situ_scenario_or_unlock_logic_modified": False,
            "universal_text_credit_event_types_modified": False,
            "universal_text_trivia_answer_keys_modified": False,
            "universal_text_pointers_or_resource_sizes_modified": False,
            "public_project_schema_exposes_raw_offsets": False,
            "public_project_contains_original_text_or_bytes": False,
        })
    if MENU_BACK_AUDIO_KIND in kinds:
        claims.update({
            "menu_back_audio_fixed_audo_slot_only": True,
            "menu_back_audio_user_supplied_pcm_input": True,
            "menu_back_audio_wrapper_and_metadata_preserved": True,
            "generic_audio_replacement_proved": False,
            "audio_runtime_visibility_proved": False,
        })
    if AUDO_AUDIO_KIND in kinds:
        claims.update({
            "standalone_audo_exact_distinct_physical_slots_only": True,
            "standalone_audo_user_supplied_pcm_input": True,
            "standalone_audo_wrapper_and_metadata_preserved": True,
            "standalone_audo_semantic_aliases_expand_writes": False,
            "standalone_audo_semantic_cue_identity_proved": False,
            "standalone_audo_runtime_selector_ownership_proved": False,
            "standalone_audo_runtime_visibility_proved": False,
            "standalone_audo_public_project_contains_retail_audio": False,
        })
    if AUSB_AUDIO_KIND in kinds:
        claims.update({
            "streaming_ausb_fixed_allocations_only": True,
            "streaming_ausb_user_supplied_pcm_input": True,
            "streaming_ausb_one_or_two_pack_spans_only": True,
            "streaming_ausb_physical_aliases_change_together": True,
            "streaming_ausb_identical_alias_edits_deduplicated": True,
            "streaming_ausb_divergent_alias_edits_rejected": True,
            "streaming_ausb_private_source_fingerprints_serialized": False,
            "streaming_ausb_public_project_contains_retail_audio": False,
            "streaming_ausb_runtime_visibility_proved": False,
        })
    if "player_portrait" in kinds:
        claims.update({
            "player_portrait_numeric_roster_portrait_only": True,
            "player_portrait_cross_pack_segments_proved": True,
            "player_portrait_action_photo_family_modified": False,
            "player_portrait_live_3d_face_family_modified": False,
            "player_portrait_wrapper_descriptor_system_bytes_preserved": True,
            "public_project_schema_exposes_raw_offsets": False,
            "speculative_executable_or_gameplay_patch_applied": False,
        })
    if CRIB_TEAM_PHOTO_KIND in kinds:
        claims.update({
            "crib_team_photo_fixed_slot_only": True,
            "crib_team_photo_all_five_p8_mips_regenerated": True,
            "crib_team_photo_wrapper_descriptor_and_system_preserved": True,
            "crib_team_photo_post_span_padding_preserved": True,
            "crib_team_photo_compact_catalog_contains_retail_bytes": False,
            "crib_team_photo_roster_portrait_modified": False,
            "crib_team_photo_live_face_modified": False,
            "public_project_schema_exposes_raw_offsets": False,
            "speculative_executable_or_gameplay_patch_applied": False,
        })
    if CRIB_SCENE_TEXTURE_KIND in kinds:
        claims.update({
            "crib_scene_texture_room_22_bar_monitor_only": True,
            "crib_scene_texture_fixed_scne_span_only": True,
            "crib_scene_texture_all_five_p8_mips_regenerated": True,
            "crib_scene_texture_decoded_geometry_and_other_textures_preserved": True,
            "crib_scene_texture_opaque_tail_preserved_from_user_source": True,
            "crib_scene_texture_other_electronics_targets_editable": False,
            "public_project_schema_exposes_raw_offsets": False,
            "speculative_executable_or_gameplay_patch_applied": False,
        })
    if SCOREBUG_TEXTURE_KIND in kinds:
        claims.update({
            "scorebug_texture_fixed_p8_span_only": True,
            "scorebug_scene_geometry_or_behavior_modified": False,
            "scorebug_digital_font_may_have_shared_ui_consumers": True,
            "scorebug_typed_importer_reused": True,
            "public_project_schema_exposes_raw_offsets": False,
            "speculative_executable_or_gameplay_patch_applied": False,
        })
    if STADIUM_TEXTURE_KIND in kinds:
        claims.update({
            "stadium_texture_source_resolved_p8_fixed_scne_spans_only": True,
            "stadium_texture_complete_mip_chains_regenerated": True,
            "stadium_texture_same_scene_edits_composed_before_compression": True,
            "stadium_texture_all_linked_material_surfaces_change_together": True,
            "stadium_texture_geometry_or_collision_modified": False,
            "stadium_texture_non_p8_or_cross_pack_writer_proved": False,
            "public_project_schema_exposes_raw_offsets": False,
            "speculative_executable_or_gameplay_patch_applied": False,
        })
    return claims


def verify_prepared_pins(project: ProjectFile, prepared: PreparedProject,
                         index_pin: ownership.PinnedLargeFile,
                         inventory_pin: ownership.PinnedLargeFile) -> None:
    current = project.path.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino, current.st_size) ==
            (*project.identity, len(project.payload)) and
            project.path.read_bytes() == project.payload,
            "project changed during workflow")
    for pin in prepared.input_pins.values():
        verify_input_pin(pin)
    for kind, pin in prepared.report_pins.items():
        verify_input_pin(pin)
    ownership.verify_large_pin(index_pin, "canonical extracted pack 0")
    ownership.verify_large_pin(inventory_pin, "canonical chunk inventory")


def copy_artifacts(prepared: PreparedProject, artifact_dir: Path) \
        -> tuple[ownership.OwnedPath, list[ownership.OwnedPath]]:
    os.mkdir(artifact_dir, 0o755)
    root = ownership.track_existing(artifact_dir, True)
    files: list[ownership.OwnedPath] = []
    try:
        for edit in prepared.edits:
            for source in [edit.import_report_path,
                           *[item[1] for item in edit.preview_paths]]:
                payload = source.read_bytes()
                files.append(ownership.exclusive_copy(
                    artifact_dir / source.name, payload, root))
        ownership.assert_owned_tree(root, files, [])
        return root, files
    except Exception:
        ownership.cleanup_owned(files, [root])
        raise


def build(project_path: Path, source_path: Path, output_path: Path,
          manifest_path: Path, artifact_dir_path: Path,
          index_path: Path = DEFAULT_INDEX,
          inventory_path: Path = DEFAULT_INVENTORY,
          source_cache_root: Path | None = None,
          exact_inventory_path: Path | None = None,
          containment_inventory_path: Path | None = None) -> dict[str, Any]:
    project = read_project(project_path)
    output = common.canonical_new_path(output_path)
    manifest = common.canonical_new_path(manifest_path)
    artifact_dir = artifact_dir_path.parent.resolve(strict=True) / artifact_dir_path.name
    require(all(path.name not in {"", ".", ".."}
                for path in (output, manifest, artifact_dir)) and
            not output.exists() and not manifest.exists() and not artifact_dir.exists() and
            len({output, manifest, artifact_dir}) == 3,
            "output XISO, manifest, or artifact directory exists/collides")

    index_pin = ownership.pin_large_file(
        index_path, "canonical extracted pack 0", INDEX_SIZE, INDEX_SHA256)
    inventory_pin: ownership.PinnedLargeFile | None = None
    reports: dict[str, InputPin] = {}
    source_fd: int | None = None
    output_owned: common.OwnedFile | None = None
    manifest_owned: common.OwnedFile | None = None
    artifacts_root: ownership.OwnedPath | None = None
    artifact_files: list[ownership.OwnedPath] = []
    prepared: PreparedProject | None = None
    success = False
    try:
        inventory_pin = ownership.pin_large_file(
            inventory_path, "canonical chunk inventory",
            INVENTORY_SIZE, INVENTORY_SHA256)
        reports = pin_reports({edit["kind"] for edit in project.value["edits"]})
        source, source_fd, source_identity, source_sha, entries, directory, xbe = \
            validate_source(source_path)
        audio_controls = {
            value.expanduser().absolute()
            for value in (
                source_cache_root,
                exact_inventory_path,
                containment_inventory_path,
            )
            if value is not None
        }
        fixed = {project.path, source, output, manifest, artifact_dir,
                 index_pin.path, inventory_pin.path,
                 *[pin.path for pin in reports.values()], *audio_controls}
        require(len(fixed) == 7 + len({pin.path for pin in reports.values()})
                + len(audio_controls),
                "workflow control/output paths alias")
        prepared = prepare_project(
            project, index_pin, inventory_pin, reports, output.parent, source_fd,
            entries, source_cache_root, exact_inventory_path,
            containment_inventory_path)
        require(not (fixed & set(prepared.input_pins)),
                "a project PNG aliases a control/output path")
        ownership.assert_owned_tree(prepared.temp_root, prepared.temp_files, [])
        bind_prepared_to_source(prepared, source_fd, entries)

        # The build copies the user's container and patches it in place, so
        # every length here is the size of THEIR file. Using the project's own
        # EXPECTED_XISO_SIZE truncated or over-read any legal dump packaged
        # differently, which is why Build refused images that had loaded fine.
        source_size = os.fstat(source_fd).st_size
        output_owned = common.reserve_file(output)
        require(output_owned.identity != source_identity, "output XISO aliases source")
        copy_method = common.copy_fd_exact(
            source_fd, output_owned.descriptor, source_size)
        for edit in prepared.edits:
            replacement = edit.replacement_path.read_bytes()
            write_all(output_owned.descriptor, edit.absolute, replacement)
            require(common.read_exact(output_owned.descriptor, edit.absolute,
                                      edit.replacement_size) == replacement,
                    f"replacement readback failed for {edit.kind}:{edit.selector}")
        os.fsync(output_owned.descriptor)
        union = verify_union(
            source_fd, output_owned.descriptor, source_size,
            prepared.edits)
        require(union["source_sha256"] == source_sha and
                common.path_identity(source) == source_identity and
                common.owned_path_matches(output_owned),
                "source/output identity or union verification changed")
        output_entries, output_directory = common.parse_xdvdfs(
            output_owned.descriptor, source_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_owned.descriptor, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "output XDVDFS tree/default.xbe changed")
        verify_prepared_pins(project, prepared, index_pin, inventory_pin)

        artifacts_root, artifact_files = copy_artifacts(prepared, artifact_dir)
        artifact_hashes = {
            item.path.name: file_digest(item.path) for item in artifact_files
        }
        expected_artifacts = {
            edit.import_report_path.name: edit.import_report_sha256
            for edit in prepared.edits
        }
        for edit in prepared.edits:
            expected_artifacts.update({name: sha for name, _, _, sha in edit.preview_paths})
        require(artifact_hashes == expected_artifacts,
                "final artifact copies differ from prepared artifacts")
        ownership.assert_owned_tree(artifacts_root, artifact_files, [])
        verify_prepared_pins(project, prepared, index_pin, inventory_pin)
        require(common.path_identity(source) == source_identity and
                common.sha256_fd(source_fd) == source_sha and
                common.owned_path_matches(output_owned) and
                common.sha256_fd(output_owned.descriptor) == union["output_sha256"],
                "source or output changed before final manifest commit")

        result: dict[str, Any] = {
            "schema": BUILD_SCHEMA,
            "project": {
                "path": str(project.path), "size": len(project.payload),
                "sha256": digest(project.payload),
                "purpose": project.value["purpose"],
                "edit_count": len(project.value["edits"]),
            },
            "source": {
                "path": str(source), "size": source_size,
                "sha256_before": source_sha,
                "sha256_after": union["source_sha256"],
                "device": source_identity[0], "inode": source_identity[1],
                "opened_read_only": True, "modified": False,
            },
            "canonical_inputs": {
                "index": {"path": str(index_pin.path), "size": INDEX_SIZE,
                          "sha256": INDEX_SHA256},
                "inventory": {"path": str(inventory_pin.path),
                              "size": INVENTORY_SIZE,
                              "sha256": INVENTORY_SHA256},
                "compatibility_reports": {
                    kind: stable_report_pin_record(kind, pin)
                    for kind, pin in sorted(reports.items())
                },
            },
            "edits": [stable_edit_record(edit) for edit in prepared.edits],
            "output": {
                "xiso_path": str(output), "xiso_size": source_size,
                "xiso_sha256": union["output_sha256"],
                "device": output_owned.identity[0], "inode": output_owned.identity[1],
                "copy_method": copy_method, "exclusively_created": True,
                "manifest_path": str(manifest),
                "artifact_directory": str(artifact_dir),
                "artifact_file_count": len(artifact_files),
                "artifact_sha256": dict(sorted(artifact_hashes.items())),
            },
            "xdvdfs": {**directory, "file_count": 19,
                       "tree_identical_after_patch": True,
                       "all_sector_extents_preserved": True,
                       "default_xbe_sha256": common.EXPECTED_XBE_SHA256},
            "patch": union,
            "claims": claims_for(prepared.edits),
        }
        manifest_owned = common.reserve_file(manifest)
        common.write_owned_json(manifest_owned, result)
        require(common.owned_path_matches(output_owned) and
                common.owned_path_matches(manifest_owned) and
                ownership.owned_matches(artifacts_root),
                "final output ownership changed")
        success = True
        return result
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if output_owned is not None:
            os.close(output_owned.descriptor)
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)
        if inventory_pin is not None:
            os.close(inventory_pin.descriptor)
        os.close(index_pin.descriptor)
        if prepared is not None:
            leftovers = ownership.cleanup_owned(prepared.temp_files, [prepared.temp_root])
            if leftovers and success:
                # Never recurse into a pathname whose identity changed.
                success = False
                common.unlink_if_owned(manifest_owned)
                common.unlink_if_owned(output_owned)
                if artifacts_root is not None:
                    ownership.cleanup_owned(artifact_files, [artifacts_root])
                raise ProjectError(f"owned temporary cleanup incomplete: {leftovers}")
        if not success:
            common.unlink_if_owned(manifest_owned)
            common.unlink_if_owned(output_owned)
            if artifacts_root is not None:
                ownership.cleanup_owned(artifact_files, [artifacts_root])


def read_build_manifest(path: Path) \
        -> tuple[Path, bytes, dict[str, Any], tuple[int, int]]:
    resolved, payload, identity = read_regular_bounded(
        path, 512 * 1024 * 1024, "build manifest")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProjectError("build manifest is invalid JSON") from exc
    require(isinstance(value, dict) and payload == canonical_json(value) and
            set(value) == {"schema", "project", "source", "canonical_inputs",
                           "edits", "output", "xdvdfs", "patch", "claims"} and
            value.get("schema") == BUILD_SCHEMA,
            "build manifest schema/canonical encoding mismatch")
    return resolved, payload, value, identity


def verify_artifacts(path: Path, expected: dict[str, str]) \
        -> tuple[Path, tuple[int, int]]:
    supplied = path.lstat()
    require(stat.S_ISDIR(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "artifact directory must be a non-symlink directory")
    resolved = path.resolve(strict=True)
    identity = (supplied.st_dev, supplied.st_ino)
    current = resolved.stat(follow_symlinks=False)
    require(stat.S_ISDIR(current.st_mode) and
            (current.st_dev, current.st_ino) == identity,
            "artifact directory pathname changed")
    require({child.name for child in resolved.iterdir()} == set(expected),
            "artifact directory file set differs from build manifest")
    for name, sha in expected.items():
        child = resolved / name
        _, payload, _ = read_regular_bounded(
            child, 512 * 1024 * 1024, f"artifact {name}")
        require(digest(payload) == sha, f"artifact changed: {name}")
    current = resolved.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino) == identity and
            {child.name for child in resolved.iterdir()} == set(expected),
            "artifact directory changed during verification")
    return resolved, identity


def verify(project_path: Path, source_path: Path, output_path: Path,
           manifest_path: Path, artifact_dir_path: Path,
           index_path: Path = DEFAULT_INDEX,
           inventory_path: Path = DEFAULT_INVENTORY,
           source_cache_root: Path | None = None,
           exact_inventory_path: Path | None = None,
           containment_inventory_path: Path | None = None) -> dict[str, Any]:
    project = read_project(project_path)
    manifest_resolved, manifest_payload, manifest, manifest_identity = \
        read_build_manifest(manifest_path)
    reports = pin_reports({edit["kind"] for edit in project.value["edits"]})
    index_pin = ownership.pin_large_file(
        index_path, "canonical extracted pack 0", INDEX_SIZE, INDEX_SHA256)
    inventory_pin: ownership.PinnedLargeFile | None = None
    source_fd: int | None = None
    output_fd: int | None = None
    prepared: PreparedProject | None = None
    try:
        inventory_pin = ownership.pin_large_file(
            inventory_path, "canonical chunk inventory",
            INVENTORY_SIZE, INVENTORY_SHA256)
        source, source_fd, source_identity, source_sha, entries, directory, xbe = \
            validate_source(source_path)
        # The user's container size, never the project's own -- see build().
        source_size = os.fstat(source_fd).st_size
        output_supplied = output_path.lstat()
        require(stat.S_ISREG(output_supplied.st_mode) and
                not stat.S_ISLNK(output_supplied.st_mode),
                "output XISO must be a non-symlink regular file")
        output = output_path.resolve(strict=True)
        output_fd = os.open(output, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                            getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
        output_info = os.fstat(output_fd)
        output_identity = common.fd_identity(output_fd)
        require(stat.S_ISREG(output_info.st_mode) and
                output_info.st_size == source_size and
                output_identity == (output_supplied.st_dev, output_supplied.st_ino) and
                common.path_identity(output) == output_identity and
                output_identity != source_identity,
                "output XISO identity/type/size mismatch")

        prepared = prepare_project(
            project, index_pin, inventory_pin, reports, manifest_resolved.parent,
            source_fd, entries, source_cache_root, exact_inventory_path,
            containment_inventory_path)
        ownership.assert_owned_tree(prepared.temp_root, prepared.temp_files, [])
        bind_prepared_to_source(prepared, source_fd, entries)
        union = verify_union(source_fd, output_fd, source_size,
                             prepared.edits)
        output_entries, output_directory = common.parse_xdvdfs(
            output_fd, source_size)
        require(output_entries == entries and output_directory == directory and
                common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "verified output XDVDFS/default.xbe changed")

        expected_edits = [stable_edit_record(edit) for edit in prepared.edits]
        expected_inputs = {
            "index": {"path": str(index_pin.path), "size": INDEX_SIZE,
                      "sha256": INDEX_SHA256},
            "inventory": {"path": str(inventory_pin.path),
                          "size": INVENTORY_SIZE, "sha256": INVENTORY_SHA256},
            "compatibility_reports": {
                kind: stable_report_pin_record(kind, pin)
                for kind, pin in sorted(reports.items())
            },
        }
        expected_xdvdfs = {
            **directory, "file_count": 19,
            "tree_identical_after_patch": True,
            "all_sector_extents_preserved": True,
            "default_xbe_sha256": common.EXPECTED_XBE_SHA256,
        }
        expected_claims = claims_for(prepared.edits)
        require(manifest.get("project", {}).get("sha256") == digest(project.payload) and
                manifest.get("project", {}).get("path") == str(project.path) and
                manifest.get("project", {}).get("size") == len(project.payload) and
                manifest.get("project", {}).get("purpose") == project.value["purpose"] and
                manifest.get("project", {}).get("edit_count") ==
                len(project.value["edits"]) and
                manifest.get("source", {}).get("path") == str(source) and
                manifest.get("source", {}).get("size") == source_size and
                manifest.get("source", {}).get("sha256_before") == source_sha and
                manifest.get("source", {}).get("sha256_after") == source_sha and
                manifest.get("source", {}).get("device") == source_identity[0] and
                manifest.get("source", {}).get("inode") == source_identity[1] and
                manifest.get("source", {}).get("opened_read_only") is True and
                manifest.get("source", {}).get("modified") is False and
                manifest.get("canonical_inputs") == expected_inputs and
                manifest.get("edits") == expected_edits and
                manifest.get("output", {}).get("xiso_sha256") == union["output_sha256"] and
                manifest.get("patch") == union and
                manifest.get("xdvdfs") == expected_xdvdfs and
                manifest.get("claims") == expected_claims,
                "build manifest differs from independently reconstructed project proof")
        expected_artifacts = manifest.get("output", {}).get("artifact_sha256")
        require(isinstance(expected_artifacts, dict) and
                all(type(name) is str and type(sha) is str
                    for name, sha in expected_artifacts.items()),
                "build manifest artifact ledger is invalid")
        reconstructed_artifacts = {
            edit.import_report_path.name: edit.import_report_sha256
            for edit in prepared.edits
        }
        for edit in prepared.edits:
            reconstructed_artifacts.update(
                {name: sha for name, _, _, sha in edit.preview_paths})
        require(expected_artifacts == dict(sorted(reconstructed_artifacts.items())),
                "build manifest artifact ledger is forged or stale")
        artifact_resolved, artifact_identity = verify_artifacts(
            artifact_dir_path, expected_artifacts)
        require(manifest.get("output", {}).get("xiso_path") == str(output) and
                manifest.get("output", {}).get("xiso_size") ==
                source_size and
                manifest.get("output", {}).get("device") == output_identity[0] and
                manifest.get("output", {}).get("inode") == output_identity[1] and
                manifest.get("output", {}).get("exclusively_created") is True and
                manifest.get("output", {}).get("manifest_path") ==
                str(manifest_resolved) and
                manifest.get("output", {}).get("artifact_directory") ==
                str(artifact_resolved) and
                manifest.get("output", {}).get("artifact_file_count") ==
                len(expected_artifacts),
                "build manifest output identity/path ledger changed")
        verify_prepared_pins(project, prepared, index_pin, inventory_pin)
        manifest_pin = InputPin(
            manifest_resolved, manifest_payload, len(manifest_payload),
            digest(manifest_payload), manifest_identity)
        verify_input_pin(manifest_pin)
        require(common.path_identity(source) == source_identity and
                common.path_identity(output) == output_identity and
                common.path_identity(manifest_resolved) == manifest_identity and
                common.path_identity(artifact_resolved) == artifact_identity,
                "source/output/manifest pathname changed during verification")
        return {
            "schema": VERIFY_SCHEMA,
            "project_sha256": digest(project.payload),
            "manifest_sha256": digest(manifest_payload),
            "source_sha256": source_sha,
            "output_sha256": union["output_sha256"],
            "edit_count": len(project.value["edits"]),
            "span_count": len(prepared.edits),
            "changed_byte_count": union["changed_byte_count"],
            "changed_offsets_u64le_sha256":
                union["changed_offsets_u64le_sha256"],
            "union_spans_reconstructed_from_pinned_importers": True,
            "all_bytes_outside_union_identical": True,
            "xdvdfs_identical": True,
            "default_xbe_unchanged": True,
            "artifacts_match_reconstructed_imports": True,
            "runtime_visibility_proved": False,
        }
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if output_fd is not None:
            os.close(output_fd)
        if inventory_pin is not None:
            os.close(inventory_pin.descriptor)
        os.close(index_pin.descriptor)
        if prepared is not None:
            ownership.cleanup_owned(prepared.temp_files, [prepared.temp_root])


def validate_only(project_path: Path) -> dict[str, Any]:
    project = read_project(project_path)
    pins = pin_project_inputs(project)
    try:
        kinds: dict[str, int] = {}
        for edit in project.value["edits"]:
            kinds[edit["kind"]] = kinds.get(edit["kind"], 0) + 1
        return {
            "schema": SCHEMA,
            "project_path": str(project.path),
            "project_sha256": digest(project.payload),
            "edit_count": len(project.value["edits"]),
            "kind_counts": dict(sorted(kinds.items())),
            "unique_png_count": len(pins),
            "png_bytes": sum(pin.size for pin in pins.values()),
            "schema_and_png_pins_valid": True,
            "target_compatibility_validated": False,
            "portme": (
                "PORTME(validate): use build or verify to run pinned target selectors and "
                "fixed-span importers; validate alone does not claim target compatibility."
            ),
        }
    finally:
        for pin in pins.values():
            verify_input_pin(pin)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate schema and pin PNGs")
    validate_parser.add_argument("--project", required=True, type=Path)
    for command in ("build", "verify"):
        item = subparsers.add_parser(command)
        item.add_argument("--project", required=True, type=Path)
        item.add_argument("--source-xiso", required=True, type=Path)
        item.add_argument("--output-xiso", required=True, type=Path)
        item.add_argument("--manifest", required=True, type=Path)
        item.add_argument("--artifact-dir", required=True, type=Path)
        item.add_argument("--index", type=Path, default=DEFAULT_INDEX)
        item.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
        item.add_argument("--source-cache-root", type=Path)
        item.add_argument("--audio-exact-inventory", type=Path)
        item.add_argument("--audio-containment-inventory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            result = validate_only(args.project)
        elif args.command == "build":
            result = build(args.project, args.source_xiso, args.output_xiso,
                           args.manifest, args.artifact_dir,
                           args.index, args.inventory,
                           args.source_cache_root,
                           args.audio_exact_inventory,
                           args.audio_containment_inventory)
        else:
            result = verify(args.project, args.source_xiso, args.output_xiso,
                            args.manifest, args.artifact_dir,
                            args.index, args.inventory,
                            args.source_cache_root,
                            args.audio_exact_inventory,
                            args.audio_containment_inventory)
    except (OSError, ValueError, KeyError, TypeError, ModEditorError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.command == "validate":
        print(json.dumps(result, sort_keys=True))
    elif args.command == "build":
        print(f"NFL2K5_VISUAL_MOD_BUILD_PASS edits={result['project']['edit_count']} "
              f"changed={result['patch']['changed_byte_count']} "
              f"sha256={result['output']['xiso_sha256']} runtime=false")
    else:
        print(f"NFL2K5_VISUAL_MOD_VERIFY_PASS edits={result['edit_count']} "
              f"changed={result['changed_byte_count']} "
              f"sha256={result['output_sha256']} runtime=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
