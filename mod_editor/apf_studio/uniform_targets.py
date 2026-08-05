"""Retail-free target pins and writer bridge for APF uniform textures.

The shipped catalog contains only identifiers, allocation sizes, and SHA-256
digests.  It deliberately excludes decoded pixels, compressed texture bytes,
IFF payloads, rollback preimages, and research fixtures.  Replacement data is
always supplied by the user and writers read the user's validated 0A volume.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Iterator

from .backend import PRODUCT_ROOT, ensure_tools_importable
from .source import EXPECTED_0A_SHA256


ensure_tools_importable()
import apf_helmet_color_transport  # type: ignore  # noqa: E402
import apf_pants_color_transport  # type: ignore  # noqa: E402
import apf_shoulder_color_transport  # type: ignore  # noqa: E402
import apf_uniform_mip_patch  # type: ignore  # noqa: E402
import apf_textlogo_patch  # type: ignore  # noqa: E402


CATALOG = PRODUCT_ROOT / "mod_editor" / "data" / "apf2k8_uniform_targets.v1.json"
EXPECTED_CATALOG_SHA256 = (
    "2c5457150195a9c634e0dda93f05d28814c275fef6d4d2f1485428e98b800ed9"
)
SCHEMA = "apf2k8_mod_studio_uniform_writer/v1"
FAMILIES = ("jersey", "pants", "helmet", "shoulder")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_NAME_ID_RE = re.compile(r"0x[0-9a-f]{8}")
_JERSEY_BIND_LOCK = threading.RLock()


class UniformTargetError(ValueError):
    """The shipped pins or a requested APF uniform target are invalid."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validated_row(family: str, ordinal: int, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise UniformTargetError(f"{family} target {ordinal} is not an object")
    expected_keys = {
        "asset_index",
        "outer_name",
        "outer_name_id",
        "outer_table_index",
        "outer_allocation",
        "inner_file",
    }
    if set(value) != expected_keys:
        raise UniformTargetError(f"{family} target {ordinal} has unexpected fields")
    if value["asset_index"] != ordinal:
        raise UniformTargetError(f"{family} target order changed")
    outer_name = value["outer_name"]
    if outer_name != f"uniform_{family}_{ordinal:02d}.iff":
        raise UniformTargetError(f"{family} target {ordinal} has the wrong name")
    name_id = value["outer_name_id"]
    if not isinstance(name_id, str) or _NAME_ID_RE.fullmatch(name_id) is None:
        raise UniformTargetError(f"{family} target {ordinal} has an invalid name ID")
    table_index = value["outer_table_index"]
    if not isinstance(table_index, int) or not 0 <= table_index < 1543:
        raise UniformTargetError(f"{family} target {ordinal} has an invalid outer index")
    allocation = value["outer_allocation"]
    if not isinstance(allocation, dict) or set(allocation) != {"size", "sha256"}:
        raise UniformTargetError(f"{family} target {ordinal} has invalid allocation pins")
    if not isinstance(allocation["size"], int) or allocation["size"] <= 0:
        raise UniformTargetError(f"{family} target {ordinal} has an invalid allocation size")
    if not isinstance(allocation["sha256"], str) or _SHA256_RE.fullmatch(
        allocation["sha256"]
    ) is None:
        raise UniformTargetError(f"{family} target {ordinal} has an invalid entry digest")
    inner = value["inner_file"]
    if not isinstance(inner, dict) or set(inner) != {"index", "texture_sha256"}:
        raise UniformTargetError(f"{family} target {ordinal} has invalid inner pins")
    if not isinstance(inner["index"], int) or not 0 <= inner["index"] < 32:
        raise UniformTargetError(f"{family} target {ordinal} has an invalid inner index")
    if not isinstance(inner["texture_sha256"], str) or _SHA256_RE.fullmatch(
        inner["texture_sha256"]
    ) is None:
        raise UniformTargetError(f"{family} target {ordinal} has an invalid texture digest")
    return value


def load_targets() -> dict[str, tuple[dict[str, object], ...]]:
    """Load and strictly validate the small, retail-free shipped target catalog."""

    data = CATALOG.read_bytes()
    if _digest(data) != EXPECTED_CATALOG_SHA256:
        raise UniformTargetError("The APF uniform target catalog was changed")
    document = json.loads(data)
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "game",
        "source_0a_sha256",
        "purpose",
        "families",
    }:
        raise UniformTargetError("The APF uniform target catalog has unexpected fields")
    if (
        document["schema"] != "apf2k8_uniform_targets/v1"
        or document["game"] != "apf2k8_xbox360_usa"
        or document["source_0a_sha256"] != EXPECTED_0A_SHA256
    ):
        raise UniformTargetError("The APF uniform target catalog is for another source")
    families = document["families"]
    if not isinstance(families, dict) or tuple(families) != FAMILIES:
        raise UniformTargetError("The APF uniform family roster changed")
    result: dict[str, tuple[dict[str, object], ...]] = {}
    seen_outer: set[int] = set()
    for family in FAMILIES:
        rows = families[family]
        if not isinstance(rows, list) or len(rows) != 24:
            raise UniformTargetError(f"{family} no longer has exactly 24 targets")
        validated = tuple(
            _validated_row(family, ordinal, row) for ordinal, row in enumerate(rows)
        )
        for row in validated:
            outer = int(row["outer_table_index"])
            if outer in seen_outer:
                raise UniformTargetError(f"Outer target {outer} is assigned more than once")
            seen_outer.add(outer)
        result[family] = validated
    if len(seen_outer) != 96:
        raise UniformTargetError("The APF uniform target coverage is incomplete")
    return result


def target_record(family: str, asset_index: int) -> dict[str, object]:
    if family not in FAMILIES:
        raise UniformTargetError(f"Unsupported APF uniform family: {family}")
    if not isinstance(asset_index, int) or not 0 <= asset_index < 24:
        raise UniformTargetError("APF uniform asset index must be in 0..23")
    return load_targets()[family][asset_index]


@contextmanager
def _selected_jersey(row: dict[str, object]) -> Iterator[None]:
    """Bind the proven single-target transport to one pinned jersey safely."""

    with _JERSEY_BIND_LOCK:
        old = (
            apf_uniform_mip_patch.ENTRY_INDEX,
            apf_uniform_mip_patch.FILE_INDEX,
            apf_uniform_mip_patch.ENTRY_NAME,
            apf_uniform_mip_patch.INNER_NAME,
            apf_uniform_mip_patch.EXPECTED_ENTRY_SHA256,
            apf_uniform_mip_patch.EXPECTED_TEXTURE_SHA256,
        )
        try:
            inner = row["inner_file"]
            allocation = row["outer_allocation"]
            assert isinstance(inner, dict) and isinstance(allocation, dict)
            apf_uniform_mip_patch.ENTRY_INDEX = int(row["outer_table_index"])
            apf_uniform_mip_patch.FILE_INDEX = int(inner["index"])
            apf_uniform_mip_patch.ENTRY_NAME = str(row["outer_name"])
            apf_uniform_mip_patch.INNER_NAME = "jersey_color"
            apf_uniform_mip_patch.EXPECTED_ENTRY_SHA256 = str(allocation["sha256"])
            apf_uniform_mip_patch.EXPECTED_TEXTURE_SHA256 = str(
                inner["texture_sha256"]
            )
            yield
        finally:
            (
                apf_uniform_mip_patch.ENTRY_INDEX,
                apf_uniform_mip_patch.FILE_INDEX,
                apf_uniform_mip_patch.ENTRY_NAME,
                apf_uniform_mip_patch.INNER_NAME,
                apf_uniform_mip_patch.EXPECTED_ENTRY_SHA256,
                apf_uniform_mip_patch.EXPECTED_TEXTURE_SHA256,
            ) = old


def compile_uniform_patch(
    index_0a: Path, png_path: Path, family: str, asset_index: int
):
    """Compile one replacement with the proved transport and sanitized pins."""

    if family == "textlogo":
        result = apf_textlogo_patch.build_patch(index_0a, png_path, asset_index)
        target = result.manifest.get("family_target", {})
        if (
            not isinstance(target, dict)
            or target.get("asset_index") != asset_index
            or target.get("selector_slot") != apf_textlogo_patch.SELECTOR_SLOT
        ):
            raise UniformTargetError("The wordmark writer resolved another target")
        return result

    row = target_record(family, asset_index)
    if family == "jersey":
        with _selected_jersey(row):
            result = apf_uniform_mip_patch.build_patch(index_0a, png_path)
    elif family == "pants":
        result = apf_pants_color_transport.build_patch(index_0a, png_path, row)
    elif family == "helmet":
        result = apf_helmet_color_transport.build_patch(index_0a, png_path, row)
    else:
        result = apf_shoulder_color_transport.build_patch(index_0a, png_path, row)

    allocation = row["outer_allocation"]
    inner = row["inner_file"]
    assert isinstance(allocation, dict) and isinstance(inner, dict)
    source = result.manifest.get("source", {})
    if not isinstance(source, dict) or (
        source.get("outer_entry_index") != row["outer_table_index"]
        or source.get("entry_sha256") != allocation["sha256"]
        or source.get("texture_sha256") != inner["texture_sha256"]
        or len(result.entry_bytes) != allocation["size"]
    ):
        raise UniformTargetError("The uniform writer resolved a different retail target")
    transport_schema = str(result.manifest.get("schema"))
    result.manifest["transport_schema"] = transport_schema
    result.manifest["schema"] = SCHEMA
    result.manifest["family_target"] = {
        "asset_index": asset_index,
        "outer_name": row["outer_name"],
        "outer_table_index": row["outer_table_index"],
        "fixed_allocation": allocation["size"],
        "retail_entry_sha256": allocation["sha256"],
        "retail_texture_sha256": inner["texture_sha256"],
        "target_catalog_sha256": EXPECTED_CATALOG_SHA256,
        "catalog_contains_retail_payloads": False,
    }
    return result
