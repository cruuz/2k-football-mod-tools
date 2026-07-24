"""Hash-pinned uniform-sharing lookups for the public editor.

This inspection surface is intentionally read-only.  It exposes affected
selectors/teams without accepting archive offsets, and accurately distinguishes
the proved offline APF selector CLI from the still-hidden production GUI path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from .errors import ValidationError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "reports/assets/uniform_texture_sharing.v2.json"
REPORT_SIZE = 415_528
REPORT_SHA256 = "9094ad0b6a199adc240dc254fdcd031573a16070c0aa80805f36fc951143b36a"
REPORT_SCHEMA = "uniform_texture_sharing_audit/v2"
DEFAULT_PANTS_REPORT = ROOT / "reports/assets/apf_pants_family_layout.json"
PANTS_REPORT_SIZE = 274_896
PANTS_REPORT_SHA256 = "82241aefe6728a7426552663ee69ecffbdabca01f4359e8322edf75775adf293"
PANTS_REPORT_SCHEMA = "apf_pants_family_layout/v1"
DEFAULT_HELMET_REPORT = ROOT / "reports/assets/apf_helmet_family_layout.json"
HELMET_REPORT_SIZE = 280_394
HELMET_REPORT_SHA256 = "72bf3efd4495e03fb856e0fb776313c842ebfafeb8d20d19f91318d7161aba03"
HELMET_REPORT_SCHEMA = "apf_helmet_family_layout/v1"
DEFAULT_SHOULDER_REPORT = ROOT / "reports/assets/apf_shoulder_family_layout.json"
SHOULDER_REPORT_SIZE = 345_097
SHOULDER_REPORT_SHA256 = "a2ea45adb931677ef4d9d9a37530f2acc53013050793a47f41f69c65e8319875"
SHOULDER_REPORT_SCHEMA = "apf_shoulder_family_layout/v1"
NFL_SELECTOR = re.compile(r"^[0-9]{2}[HA](?:0|[1-9][0-9]?)$")


def _read_report(path: Path) -> dict[str, Any]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"Uniform-sharing report is missing: {path}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("Uniform-sharing report must be a non-symlink regular file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError("Uniform-sharing report identity changed while opening")
        if opened.st_size != REPORT_SIZE:
            raise ValidationError("Uniform-sharing report size does not match the pinned audit")
        chunks: list[bytes] = []
        remaining = REPORT_SIZE
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError("Uniform-sharing report ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError("Uniform-sharing report grew while reading")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev, opened.st_ino, opened.st_size
        ):
            raise ValidationError("Uniform-sharing report changed while reading")
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    if hashlib.sha256(payload).hexdigest() != REPORT_SHA256:
        raise ValidationError("Uniform-sharing report hash does not match the pinned audit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Uniform-sharing report is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != REPORT_SCHEMA:
        raise ValidationError("Uniform-sharing report schema does not match")
    return value


def _read_pants_report(path: Path) -> dict[str, Any]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"APF pants report is missing: {path}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("APF pants report must be a non-symlink regular file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError("APF pants report identity changed while opening")
        if opened.st_size != PANTS_REPORT_SIZE:
            raise ValidationError("APF pants report size does not match the pinned audit")
        chunks: list[bytes] = []
        remaining = PANTS_REPORT_SIZE
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError("APF pants report ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError("APF pants report grew while reading")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev, opened.st_ino, opened.st_size
        ):
            raise ValidationError("APF pants report changed while reading")
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    if hashlib.sha256(payload).hexdigest() != PANTS_REPORT_SHA256:
        raise ValidationError("APF pants report hash does not match the pinned audit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("APF pants report is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != PANTS_REPORT_SCHEMA:
        raise ValidationError("APF pants report schema does not match")
    return value


def _read_helmet_report(path: Path) -> dict[str, Any]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"APF helmet report is missing: {path}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("APF helmet report must be a non-symlink regular file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError("APF helmet report identity changed while opening")
        if opened.st_size != HELMET_REPORT_SIZE:
            raise ValidationError("APF helmet report size does not match the pinned audit")
        chunks: list[bytes] = []
        remaining = HELMET_REPORT_SIZE
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError("APF helmet report ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError("APF helmet report grew while reading")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev, opened.st_ino, opened.st_size
        ):
            raise ValidationError("APF helmet report changed while reading")
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    if hashlib.sha256(payload).hexdigest() != HELMET_REPORT_SHA256:
        raise ValidationError("APF helmet report hash does not match the pinned audit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("APF helmet report is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != HELMET_REPORT_SCHEMA:
        raise ValidationError("APF helmet report schema does not match")
    return value


def _read_shoulder_report(path: Path) -> dict[str, Any]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"APF shoulder report is missing: {path}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("APF shoulder report must be a non-symlink regular file")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError("APF shoulder report identity changed while opening")
        if opened.st_size != SHOULDER_REPORT_SIZE:
            raise ValidationError("APF shoulder report size does not match the pinned audit")
        chunks: list[bytes] = []
        remaining = SHOULDER_REPORT_SIZE
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError("APF shoulder report ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError("APF shoulder report grew while reading")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev, opened.st_ino, opened.st_size
        ):
            raise ValidationError("APF shoulder report changed while reading")
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    if hashlib.sha256(payload).hexdigest() != SHOULDER_REPORT_SHA256:
        raise ValidationError("APF shoulder report hash does not match the pinned audit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("APF shoulder report is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != SHOULDER_REPORT_SCHEMA:
        raise ValidationError("APF shoulder report schema does not match")
    return value


def inspect_nfl_uniform_sharing(
    selector: str, report_path: Path = DEFAULT_REPORT
) -> dict[str, Any]:
    normalized = selector.strip().upper()
    if not NFL_SELECTOR.fullmatch(normalized):
        raise ValidationError(
            "NFL uniform selector must be two digits, H/A, and a decimal variant "
            "(for example 09A0)"
        )
    report = _read_report(report_path)
    nfl = report["nfl2k5"]
    rows = [row for row in nfl["selectors"] if row["selector"] == normalized]
    if len(rows) != 1:
        raise ValidationError(f"NFL uniform selector is absent: {normalized}")
    aliases = []
    for group in nfl["cross_asset_code_content_alias_groups"]:
        if any(owner["selector"] == normalized for owner in group["owners"]):
            aliases.append({
                "group_id": group["group_id"],
                "family": group["family"],
                "texture_name": group["texture_name"],
                "identity_basis": group["identity_basis"],
                "affected_owner_count": group["owner_count"],
                "affected_asset_code_count": group["asset_code_count"],
                "affected_owners": group["owners"],
            })
    return {
        "schema": "mod_editor_nfl_uniform_sharing_lookup/v1",
        "game": nfl["game"],
        "selector": rows[0],
        "cross_asset_code_content_alias_count": len(aliases),
        "cross_asset_code_content_aliases": aliases,
        "on_disc_span_is_independent": True,
        "physical_storage_result": nfl["physical_storage"]["result"],
        "safe_fix": nfl["practical_fix"],
        "warning": (
            "A hash-keyed emulator replacement affects every owner listed below; "
            "a direct selector-specific XISO import changes only this selector's "
            "independent fixed span."
            if aliases else
            "No cross-asset-code exact-content alias is present for this selector "
            "in the audited torso, pants, sleeve, or live-helmet families."
        ),
    }


def inspect_apf_jersey_sharing(
    asset_index: int, report_path: Path = DEFAULT_REPORT
) -> dict[str, Any]:
    if isinstance(asset_index, bool) or not isinstance(asset_index, int) \
            or not 0 <= asset_index <= 23:
        raise ValidationError("APF jersey asset index must be an integer in 0..23")
    report = _read_report(report_path)
    apf = report["apf2k8"]
    rows = [row for row in apf["assets"] if row["asset_index"] == asset_index]
    if len(rows) != 1:
        raise ValidationError(f"APF jersey asset is absent: {asset_index}")
    asset = rows[0]
    proposed = [
        row for row in apf["built_in_unique_allocation_plan"]["plan"]
        if row["retail_asset_index"] == asset_index or
        row["proposed_unique_asset_index"] == asset_index
    ]
    return {
        "schema": "mod_editor_apf_jersey_sharing_lookup/v1",
        "game": apf["game"],
        "asset": asset,
        "built_in_allocation_plan_rows": proposed,
        "safe_dealias_writer_available": bool(
            apf["practical_fix"].get(
                "safe_offline_cli_dealias_writer_available", False
            )
        ),
        "safe_offline_cli_dealias_writer_available": bool(
            apf["practical_fix"].get(
                "safe_offline_cli_dealias_writer_available", False
            )
        ),
        "public_gui_dealias_writer_available": bool(
            apf["practical_fix"].get(
                "public_gui_dealias_writer_available", False
            )
        ),
        "dealias_boundary": apf["practical_fix"],
        "warning": (
            f"Editing asset {asset_index} changes every listed team/bank selector "
            "because they resolve the same physical jersey package."
            if asset["selector_owner_count"] else
            f"Asset {asset_index} has no retail team/bank selector owner."
        ),
    }


def inspect_apf_pants_sharing(
    asset_index: int, report_path: Path = DEFAULT_PANTS_REPORT
) -> dict[str, Any]:
    if isinstance(asset_index, bool) or not isinstance(asset_index, int) \
            or not 0 <= asset_index <= 23:
        raise ValidationError("APF pants asset index must be an integer in 0..23")
    report = _read_pants_report(report_path)
    rows = [row for row in report["pants"] if row["asset_index"] == asset_index]
    if len(rows) != 1:
        raise ValidationError(f"APF pants asset is absent: {asset_index}")
    asset = rows[0]
    owners = [
        {
            "team_index": row["team_index"],
            "team_name": row["team_name"],
            "abbreviation": row["abbreviation"],
            "slot_kind": row["slot_kind"],
            "bank": row["bank"],
        }
        for row in asset["team_bank_uses"]
    ]
    return {
        "schema": "mod_editor_apf_pants_sharing_lookup/v1",
        "game": report["scope"]["game"],
        "asset_index": asset_index,
        "texture": report["scope"]["inner_name"],
        "team_bank_use_count": len(owners),
        "team_bank_uses": owners,
        "physical_asset_writer_proved": True,
        "selector_or_roster_writer_available": False,
        "runtime_visibility_proved": report["claim_boundary"][
            "runtime_visibility_proved"
        ],
        "warning": (
            f"Editing pants asset {asset_index} changes all {len(owners)} listed "
            "team/bank uses; no selector is rewritten."
            if owners else
            f"Pants asset {asset_index} has no retail team/bank selector owner."
        ),
    }


def inspect_apf_helmet_sharing(
    asset_index: int, report_path: Path = DEFAULT_HELMET_REPORT
) -> dict[str, Any]:
    if isinstance(asset_index, bool) or not isinstance(asset_index, int) \
            or not 0 <= asset_index <= 23:
        raise ValidationError("APF helmet asset index must be an integer in 0..23")
    report = _read_helmet_report(report_path)
    rows = [row for row in report["helmets"] if row["asset_index"] == asset_index]
    if len(rows) != 1:
        raise ValidationError(f"APF helmet asset is absent: {asset_index}")
    asset = rows[0]
    owners = [
        {
            "team_index": row["team_index"],
            "team_name": row["team_name"],
            "abbreviation": row["abbreviation"],
            "slot_kind": row["slot_kind"],
            "bank": row["bank"],
        }
        for row in asset["team_bank_uses"]
    ]
    boundary = report["claim_boundary"]
    return {
        "schema": "mod_editor_apf_helmet_sharing_lookup/v1",
        "game": report["scope"]["game"],
        "asset_index": asset_index,
        "texture": report["scope"]["inner_name"],
        "team_bank_use_count": len(owners),
        "team_bank_uses": owners,
        "physical_asset_writer_proved": True,
        "selector_or_roster_writer_available": False,
        "two_channel_data_contract": {
            "stored_channels": ["R", "G"],
            "required_blue": 0,
            "required_alpha": 255,
            "shader_meanings_named": boundary[
                "helmet_color_channel_meanings_named"
            ],
        },
        "runtime_visibility_proved": boundary["runtime_visibility_proved"],
        "warning": (
            f"Editing helmet asset {asset_index} changes all {len(owners)} listed "
            "team/bank uses. R/G are raw DXN data channels with unproved shader "
            "meanings; no selector is rewritten."
            if owners else
            f"Helmet asset {asset_index} has no retail team/bank selector owner."
        ),
    }


def inspect_apf_shoulder_sharing(
    asset_index: int, report_path: Path = DEFAULT_SHOULDER_REPORT
) -> dict[str, Any]:
    if isinstance(asset_index, bool) or not isinstance(asset_index, int) \
            or not 0 <= asset_index <= 23:
        raise ValidationError("APF shoulder asset index must be an integer in 0..23")
    report = _read_shoulder_report(report_path)
    rows = [row for row in report["shoulders"] if row["asset_index"] == asset_index]
    if len(rows) != 1:
        raise ValidationError(f"APF shoulder asset is absent: {asset_index}")
    asset = rows[0]
    owners = [
        {
            "team_index": row["team_index"],
            "team_name": row["team_name"],
            "abbreviation": row["abbreviation"],
            "slot_kind": row["slot_kind"],
            "bank": row["bank"],
        }
        for row in asset["team_bank_uses"]
    ]
    return {
        "schema": "mod_editor_apf_shoulder_sharing_lookup/v1",
        "game": report["scope"]["game"],
        "asset_index": asset_index,
        "texture": report["scope"]["inner_name"],
        "paired_family": report["scope"]["paired_family"],
        "team_bank_use_count": len(owners),
        "team_bank_uses": owners,
        "physical_color_asset_writer_proved": True,
        "paired_normal_writer_available": False,
        "selector_or_roster_writer_available": False,
        "runtime_visibility_proved": report["claim_boundary"][
            "runtime_visibility_proved"
        ],
        "warning": (
            f"Editing shoulder asset {asset_index} changes all {len(owners)} "
            "listed team/bank uses. The paired normal package is preserved and "
            "no selector is rewritten."
            if owners else
            f"Shoulder asset {asset_index} has no retail team/bank selector owner."
        ),
    }


__all__ = [
    "inspect_apf_helmet_sharing",
    "inspect_apf_jersey_sharing",
    "inspect_apf_pants_sharing",
    "inspect_apf_shoulder_sharing",
    "inspect_nfl_uniform_sharing",
]
