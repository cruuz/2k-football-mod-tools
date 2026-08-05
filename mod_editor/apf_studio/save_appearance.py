"""User-facing service for APF raw-save custom-team appearance edits."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .backend import ensure_tools_importable


ensure_tools_importable()
import apf_custom_team_appearance_patch as appearance_writer  # type: ignore  # noqa: E402
import apf_save_custom_team_appearance as writer  # type: ignore  # noqa: E402


SIGNED_SAVE_BOUNDARY = (
    "Xbox 360 STFS package (CON, LIVE, or PIRS) detected. Mod Studio verifies and "
    "reads its Roster.ROS payload, and can write either an exact extracted payload "
    "or a patched raw handoff. It does not write the signed container. Reinject the "
    "new raw file, then rehash/resign with the same external save manager. LIVE/PIRS "
    "retail signatures require Microsoft's unavailable private keys; CON signing "
    "requires the owning console's private keyvault."
)
RAW_SAVE_BOUNDARY = (
    "Raw Roster.ROS detected. User-facing teams 24–31 map to ROST slots 32–39. "
    "Mod Studio writes a separate payload and independently verified receipt; the "
    "selected source is never opened for writing."
)


class SaveAppearanceServiceError(ValueError):
    """A selected save or staged appearance cannot be handled safely."""


@dataclass(frozen=True)
class RawSaveAppearanceSlot:
    slot: int
    user_team_id: int
    display_name: str
    occupied: bool
    appearance: appearance_writer.CustomTeamAppearance

    @property
    def label(self) -> str:
        state = "occupied" if self.occupied else "empty"
        name = self.display_name if self.display_name.strip("*") else "unused"
        return (
            f"User team {self.user_team_id} · ROST slot {self.slot} · "
            f"{name} ({state})"
        )


@dataclass(frozen=True)
class RawSaveAppearanceDocument:
    source: Path
    source_sha256: str
    file_size: int
    layout: str
    signed_container: bool
    slots: tuple[RawSaveAppearanceSlot, ...]
    container_kind: str | None = None
    payload_path: str | None = None
    payload_sha256: str | None = None
    container_hash_tree_verified: bool = False
    container_rsa_signature_verified: bool = False

    @property
    def write_supported(self) -> bool:
        return True

    @property
    def boundary_message(self) -> str:
        return SIGNED_SAVE_BOUNDARY if self.signed_container else RAW_SAVE_BOUNDARY


@dataclass(frozen=True)
class SaveAppearanceWriteReceipt:
    output: Path
    manifest: Path
    output_sha256: str
    edit_count: int
    changed_byte_count: int
    authorized_byte_count: int
    verification_passed: bool
    runtime_in_game_proved: bool = False
    output_is_raw_payload: bool = True
    source_was_signed_container: bool = False
    external_reinjection_required: bool = False


@dataclass(frozen=True)
class StfsRosterExtractReceipt:
    output: Path
    manifest: Path
    output_sha256: str
    payload_path: str
    verification_passed: bool
    output_is_raw_payload: bool = True
    external_reinjection_required: bool = True


def inspect_save(path: Path) -> RawSaveAppearanceDocument:
    source = Path(path)
    try:
        data = writer.read_source(source)
        parsed = writer.parse_save(data)
    except (OSError, writer.SaveAppearanceError) as exc:
        raise SaveAppearanceServiceError(str(exc)) from exc
    slots = tuple(
        RawSaveAppearanceSlot(
            slot=row.target.slot,
            user_team_id=row.target.user_team_id,
            display_name=row.target.display_name,
            occupied=row.target.occupied,
            appearance=row.appearance,
        )
        for row in parsed.slots
    )
    if len(slots) != len(appearance_writer.USER_SLOTS):
        raise SaveAppearanceServiceError("the complete user-team appearance table did not parse")
    return RawSaveAppearanceDocument(
        source=source,
        source_sha256=hashlib.sha256(data).hexdigest(),
        file_size=len(data),
        layout=parsed.layout,
        signed_container=parsed.signed_container,
        slots=slots,
        container_kind=parsed.container_kind,
        payload_path=parsed.payload_path,
        payload_sha256=parsed.payload_sha256,
        container_hash_tree_verified=parsed.container_hash_tree_verified,
        container_rsa_signature_verified=parsed.container_rsa_signature_verified,
    )


def default_manifest_path(output: Path) -> Path:
    return writer.default_manifest_path(output)


def default_extract_manifest_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.stfs-extract.json")


def extract_raw_save(
    document: RawSaveAppearanceDocument,
    output: Path,
    *,
    manifest: Path | None = None,
) -> StfsRosterExtractReceipt:
    if not document.signed_container:
        raise SaveAppearanceServiceError("choose a CON, LIVE, or PIRS STFS package")
    output = Path(output)
    manifest = (
        Path(manifest)
        if manifest is not None
        else default_extract_manifest_path(output)
    )
    try:
        value = writer.write_stfs_extract(
            document.source,
            output,
            manifest,
            expected_source_sha256=document.source_sha256,
        )
    except (OSError, writer.SaveAppearanceError) as exc:
        raise SaveAppearanceServiceError(str(exc)) from exc
    verification = value.get("verification")
    if not isinstance(verification, dict) or verification.get("verified") is not True:
        raise SaveAppearanceServiceError("independent STFS extraction verification did not pass")
    return StfsRosterExtractReceipt(
        output=output,
        manifest=manifest,
        output_sha256=str(value["output_sha256"]),
        payload_path=str(value["payload_path"]),
        verification_passed=True,
    )


def write_new_save(
    document: RawSaveAppearanceDocument,
    appearance: appearance_writer.CustomTeamAppearance,
    output: Path,
    *,
    manifest: Path | None = None,
) -> SaveAppearanceWriteReceipt:
    try:
        value = appearance_writer.validate_appearance(appearance)
    except appearance_writer.CustomTeamAppearanceError as exc:
        raise SaveAppearanceServiceError(str(exc)) from exc
    valid_slots = {row.slot for row in document.slots}
    if value.slot not in valid_slots:
        raise SaveAppearanceServiceError("choose one parsed user-team slot 32–39")
    output = Path(output)
    manifest = Path(manifest) if manifest is not None else default_manifest_path(output)
    try:
        patch_manifest = writer.write_patch(
            document.source,
            output,
            (value,),
            manifest,
            expected_source_sha256=document.source_sha256,
        )
        source_data = writer.read_source(document.source)
        output_data = writer.read_source(output)
        if patch_manifest.get("schema") == writer.STFS_HANDOFF_SCHEMA:
            verification = writer.verify_stfs_handoff(
                source_data, output_data, patch_manifest
            )
        else:
            verification = writer.verify_patch(source_data, output_data, patch_manifest)
    except (OSError, writer.SaveAppearanceError) as exc:
        raise SaveAppearanceServiceError(str(exc)) from exc
    if verification.get("verified") is not True:
        raise SaveAppearanceServiceError("independent appearance verification did not pass")
    return SaveAppearanceWriteReceipt(
        output=output,
        manifest=manifest,
        output_sha256=str(patch_manifest["output_sha256"]),
        edit_count=int(verification["edit_count"]),
        changed_byte_count=int(verification["changed_byte_count"]),
        authorized_byte_count=int(verification["authorized_byte_count"]),
        verification_passed=True,
        source_was_signed_container=document.signed_container,
        external_reinjection_required=document.signed_container,
    )


__all__ = [
    "RAW_SAVE_BOUNDARY",
    "SIGNED_SAVE_BOUNDARY",
    "RawSaveAppearanceDocument",
    "RawSaveAppearanceSlot",
    "SaveAppearanceServiceError",
    "SaveAppearanceWriteReceipt",
    "StfsRosterExtractReceipt",
    "default_extract_manifest_path",
    "default_manifest_path",
    "extract_raw_save",
    "inspect_save",
    "write_new_save",
]
