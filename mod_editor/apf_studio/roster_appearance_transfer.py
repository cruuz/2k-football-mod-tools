"""Apply editor appearances to a separate raw, converted PS3, or Xenia STFS save."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import zipfile

from . import ps3_roster_convert as ps3
from .save_appearance import SaveAppearanceServiceError, appearance_writer, writer
import apf_stfs_roster_extract as stfs
import apf_stfs_roster_rehash as rehash

SCHEMA = "apf2k8_roster_appearance_transfer/v1"


@dataclass(frozen=True)
class TransferSource:
    source: Path
    member: str | None
    source_sha256: str
    kind: str
    slots: tuple
    xenia_package_supported: bool
    package_reason: str


@dataclass(frozen=True)
class TransferReceipt:
    output: Path
    manifest: Path
    changed_slots: tuple[int, ...]
    changed_byte_count: int
    output_is_package: bool
    converted_ps3: bool
    verification_passed: bool = True


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path, member: str | None) -> bytes:
    return ps3.read_source(path, member) if member is not None else writer.read_source(path)


def _prepare(data: bytes) -> tuple[bytes, str, dict | None]:
    if data[:4] in stfs.STFS_MAGICS:
        return stfs.extract_roster_payload(data).payload, "stfs", None
    # The proved PS3 converter has one precise size/layout. Detect byte order
    # before the ARGB appearance reader can mistakenly accept RGBA words.
    if len(data) == ps3.ROSTER_SIZE:
        platform = ps3.detect_platform(data)
        if platform == ps3.PLATFORM_PS3:
            raw, conversion = ps3.convert(data, apply_team_appearance=True)
            return raw, "ps3", conversion
        if platform != ps3.PLATFORM_XBOX360:
            raise SaveAppearanceServiceError("Cannot determine roster palette byte order; choose a supported raw Xbox roster or decrypted PS3 USERDATA")
    writer.parse_save(data)
    return data, "raw", None


def inspect_transfer_source(path: Path) -> TransferSource:
    path = Path(path)
    try:
        member = ps3.find_roster_member(path) if zipfile.is_zipfile(path) else None
        data = _read(path, member)
        raw, kind, _conversion = _prepare(data)
        reason, supported = "Choose an STFS source for package output", False
        if kind == "stfs":
            try:
                rehash._inventory(data)
                supported, reason = True, rehash.XENIA_ONLY
            except stfs.StfsRosterError as exc:
                reason = f"Package output refused: {exc}. Choose raw Roster.ROS output."
        return TransferSource(path, member, _sha(data), kind, writer.parse_save(raw).slots, supported, reason)
    except (OSError, ValueError, writer.SaveAppearanceError, zipfile.BadZipFile) as exc:
        raise SaveAppearanceServiceError(
            f"{exc}. Choose a supported raw Xbox roster, STFS save, or decrypted PS3 USERDATA/roster ZIP."
        ) from exc


def verify_transfer(source: bytes, output: bytes, receipt: dict) -> dict:
    """Reparse the written file, the conversion, the package and the bounded patch."""
    writer.require(receipt.get("schema") == SCHEMA, "transfer receipt schema differs")
    writer.require(receipt.get("source_sha256") == _sha(source), "transfer source hash differs")
    writer.require(receipt.get("output_sha256") == _sha(output), "transfer output hash differs")
    raw, kind, conversion = _prepare(source)
    writer.require(receipt.get("source_kind") == kind, "transfer source kind differs")
    writer.require(receipt.get("ps3_conversion") == conversion, "PS3 conversion receipt differs")
    package = receipt.get("stfs_rehash")
    if package is not None:
        writer.require(kind == "stfs", "package output needs an STFS source")
        rehash.verify_rehash(source, output, package)
        patched = stfs.extract_roster_payload(output).payload
    else:
        writer.require(output[:4] not in stfs.STFS_MAGICS, "expected raw roster output")
        patched = output
    verified = writer.verify_patch(raw, patched, receipt["appearance_patch"])
    before = {row.target.slot: row.appearance for row in writer.parse_save(raw).slots}
    after = {row.target.slot: row.appearance for row in writer.parse_save(patched).slots}
    changed_slots = sorted(slot for slot in before if before[slot] != after[slot])
    writer.require(receipt.get("changed_slots") == changed_slots, "changed slot list differs from output reparse")
    return {**verified, "changed_slots": changed_slots, "output_reparsed": True,
            "ps3_conversion_reverified": conversion is not None,
            "stfs_rehash_reverified": package is not None,
            "runtime_in_game_proved": False}


def write_transfer(document: TransferSource, replacements, output: Path, *,
                   xenia_package: bool = False, manifest: Path | None = None) -> TransferReceipt:
    """Reserve two NEW paths; verify readback before keeping either file."""
    output = Path(output)
    manifest = Path(manifest) if manifest is not None else writer.default_manifest_path(output)
    created = []
    descriptors = []
    try:
        writer.require(len({p.resolve() for p in (document.source, output, manifest)}) == 3,
                       "Source, output and receipt must be separate files; choose a new filename")
        source = _read(document.source, document.member)
        writer.require(_sha(source) == document.source_sha256,
                       "Source roster changed after inspection; choose it again before writing")
        raw, kind, conversion = _prepare(source)
        patched, patch_receipt = writer.make_patch(raw, replacements)
        package_receipt = None
        if xenia_package:
            writer.require(kind == "stfs" and document.xenia_package_supported,
                           document.package_reason)
            payload, package_receipt = rehash.rehash_roster(source, patched)
        else:
            payload = patched
        receipt = {
            "schema": SCHEMA, "source_sha256": _sha(source), "output_sha256": _sha(payload),
            "source_kind": kind, "source_member": document.member,
            "source_path": str(document.source), "output_path": str(output),
            "appearance_patch": patch_receipt, "ps3_conversion": conversion,
            "stfs_rehash": package_receipt,
            "changed_slots": [row["slot"] for row in patch_receipt["edits"] if row["before"] != row["after"]],
            "carried": "Selected slots: ten HOME/AWAY ARGB values and eight-byte helmet/crest selectors (112 bytes per slot)",
            "refused": [{"field": "jersey/shoulder/pants selectors and artwork",
                         "reason": "outside the bounded disc appearance writer; existing destination values remain"}],
            "boundary": rehash.XENIA_ONLY if xenia_package else "New raw Xbox Roster.ROS; external save placement required",
            "runtime": rehash.RUNTIME,
        }
        verify_transfer(source, payload, receipt)
        for path in (output, manifest):
            descriptors.append(writer._reserve(path))
            created.append(path)
        writer._write_all(descriptors[0], payload)
        os.fsync(descriptors[0])
        # Close before reopening, including on Windows.
        os.close(descriptors[0])
        descriptors[0] = -1
        source_now = _read(document.source, document.member)
        receipt["verification"] = verify_transfer(source_now, writer.read_source(output), receipt)
        writer._write_all(descriptors[1], writer._json_bytes(receipt))
        os.fsync(descriptors[1])
        return TransferReceipt(output, manifest, tuple(receipt["changed_slots"]),
                               patch_receipt["changed_byte_count"], xenia_package, kind == "ps3")
    except (OSError, ValueError, writer.SaveAppearanceError, zipfile.BadZipFile) as exc:
        raise SaveAppearanceServiceError(
            f"{exc}. Review the selected slots, reload a changed source, and choose new output and receipt filenames."
        ) from exc
    finally:
        import sys
        failed = sys.exc_info()[0] is not None
        for descriptor in descriptors:
            if descriptor >= 0:
                os.close(descriptor)
        if failed:
            for path in created:
                path.unlink(missing_ok=True)


__all__ = ["SCHEMA", "TransferSource", "TransferReceipt", "inspect_transfer_source",
           "write_transfer", "verify_transfer"]
