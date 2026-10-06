#!/usr/bin/env python3
"""Replay current APF situation/charge TOMLs on a pinned flat PE, offline.

This is an offline scope proof. The emitted PE is not a launchable XEX and
does not change a game folder. Install the emitted TOMLs for the matching
unmodified BASE/TU module and restart Xenia to use the repair in the game.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import apf2k8_charge_abilities as charge
from mod_editor.core import apf2k8_situation_mask as situation
from mod_editor.core import platform_compat
from mod_editor.core.apf2k8_playcall_patch import IMAGE_BASE, PROFILES, check_image
from mod_editor.core.apf2k8_xex import read_input
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio.situation_masks import FILENAME as SITUATION_FILENAME


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PatchPlan:
    kind: str
    document: object
    payload: bytes
    filename: str
    words: tuple
    originals: tuple

    @property
    def profile(self):
        return self.document.profile


def charge_plan(profile):
    document = charge.PatchDocument(profile, True)
    payload = document.as_toml().encode("utf-8")
    if charge.parse_payload(payload) != document:
        raise ValidationError("Current charge patch failed its canonical check")
    originals = dict(document.original_words)
    return PatchPlan("charge", document, payload, charge.FILENAME, document.words,
                     tuple((address, originals.get(address, 0)) for address, _ in document.words))


def situation_plan(payload):
    profile, enabled = situation.canonical_payload(payload)
    if not enabled:
        raise ValidationError("Export an enabled situation patch for the offline repair")
    parsed = tomllib.loads(payload.decode("utf-8"))
    writes = parsed["patch"][0]["be32"]
    mapped = {word["address"]: word["value"] for word in writes}
    data = b"".join(struct.pack(">I", mapped[address])
                    for address in range(situation.DATA_START, situation.DATA_LIMIT, 4))
    document = situation.SituationPatch(profile, data)
    originals = dict(zip(situation.HOOKS[profile.name], (0x38A00003, 0x38A00001)))
    originals[situation.ROW_HOOKS[profile.name]] = situation._rl(11, 11, 0, 26, 31)
    if document.version >= 4:
        originals[situation.COMPONENT_HOOKS[profile.name]] = situation.COMPONENT_ORIGINAL
    return PatchPlan("situations", document, document.as_toml().encode("utf-8"),
                     SITUATION_FILENAME, document.words,
                     tuple((address, originals.get(address, 0)) for address, _ in document.words))


def _verify_baseline(image, plan):
    if plan.kind == "charge":
        charge.verify_image(image, plan.document)
        if plan.document.revision != charge.CURRENT_REVISION:
            raise ValidationError("Export the current charge patch")
    elif plan.kind == "situations":
        data = plan.document.data
        fresh = situation.compile_patch(image, situation.decode_data(data),
                                        situation.decode_personnel_rows(data),
                                        situation.decode_formation_weights(data))
        if fresh != plan.document:
            raise ValidationError("Export a fresh current situation patch; legacy patches are not repaired implicitly")
    else:
        raise ValidationError("Unknown APF repair patch")


def _spans(addresses):
    spans = []
    for address in sorted(addresses):
        offset = address - IMAGE_BASE
        if spans and spans[-1][1] == offset:
            spans[-1][1] += 4
        else:
            spans.append([offset, offset + 4])
    return spans


def _outside_hash(image, spans):
    digest, cursor = hashlib.sha256(), 0
    view = memoryview(image)
    for start, end in spans:
        digest.update(view[cursor:start])
        cursor = end
    digest.update(view[cursor:])
    return digest.hexdigest()


def _outside_identical(before, after, spans):
    left, right, cursor = memoryview(before), memoryview(after), 0
    for start, end in spans:
        if left[cursor:start] != right[cursor:start]:
            return False
        cursor = end
    return left[cursor:] == right[cursor:]


def compose_image(image, plans):
    """Refuse foreign/partial input, normalize each owner, then hash-gate it.

    Each requested owner must be entirely retail or entirely installed.
    Owners may already be installed independently. Every byte outside their
    exact word sets must still belong to the pinned retail image.
    """
    if not plans:
        raise ValidationError("Choose charge and/or an enabled current situation patch")
    if any(plan.profile != plans[0].profile for plan in plans):
        raise ValidationError("Charge and situation patches must use the same executable profile")
    expected_profile = plans[0].profile
    normalized, targets, states = bytearray(image), {}, {}
    for plan in plans:
        originals = dict(plan.originals)
        words = dict(plan.words)
        if len(words) != len(plan.words) or set(words) != set(originals):
            raise ValidationError("Repair word ownership is incomplete or duplicated")
        if set(targets) & set(words):
            raise ValidationError("Requested APF patch owners overlap")
        for address, word in words.items():
            offset = address - IMAGE_BASE
            if (type(address) is not int or address % 4 or offset < 0 or offset + 4 > len(image)
                    or type(word) is not int or not 0 <= word <= 0xFFFFFFFF):
                raise ValidationError("Repair word lies outside the flat image")
        retail = all(image[address-IMAGE_BASE:address-IMAGE_BASE+4] == struct.pack(">I", word)
                     for address, word in originals.items())
        installed = all(image[address-IMAGE_BASE:address-IMAGE_BASE+4] == struct.pack(">I", word)
                        for address, word in words.items())
        if not retail and not installed:
            raise ValidationError(f"{plan.kind} input is partial, stale or foreign; use the pinned image or the exact requested repair")
        states[plan.kind] = "retail" if retail else "already_installed"
        for address, word in originals.items():
            struct.pack_into(">I", normalized, address - IMAGE_BASE, word)
        targets.update(words)
    baseline = bytes(normalized)
    profile = check_image(baseline)
    if profile != expected_profile:
        raise ValidationError("Requested patch does not match the pinned image profile")
    for plan in plans:
        _verify_baseline(baseline, plan)
    output = bytearray(baseline)
    for address, word in targets.items():
        struct.pack_into(">I", output, address - IMAGE_BASE, word)
    output = bytes(output)
    spans = _spans(targets)
    before_outside, after_outside = _outside_hash(image, spans), _outside_hash(output, spans)
    if before_outside != after_outside or not _outside_identical(image, output, spans):
        raise ValidationError("Offline repair changed bytes outside its declared word scope")
    receipt = {
        "schema": "b765_d3_apf_offline_repair/v1",
        "classification": "PROVED OFFLINE",
        "runtime_status": "UNWITNESSED",
        "profile": profile.name,
        "module_hash": profile.module_hash,
        "input_sha256": sha256(image),
        "normalized_retail_sha256": sha256(baseline),
        "output_sha256": sha256(output),
        "image_bytes": len(image),
        "input_owners": states,
        "outside_scope_input_sha256": before_outside,
        "outside_scope_output_sha256": after_outside,
        "outside_scope_identical": True,
        "scope_word_count": len(targets),
        "changed_byte_count": sum(a != b for a, b in zip(image, output)),
        "scope_spans": [{"file_offset": start, "bytes": end-start,
                         "input_sha256": sha256(image[start:end]),
                         "output_sha256": sha256(output[start:end])}
                        for start, end in spans],
        "patches": [{"kind": plan.kind, "file": plan.filename,
                     "sha256": sha256(plan.payload),
                     "revision": (plan.document.revision if plan.kind == "charge" else plan.document.version)}
                    for plan in plans],
        "output_pe": "repaired.pe",
        "game_files_touched": [],
        "transport": "Install the emitted TOMLs for the matching original BASE/TU module and restart Xenia. The PE is offline replay evidence, not a launchable XEX.",
    }
    return output, receipt


def prepare_repair(image, *, use_charge=False, situation_payload=None):
    situation_owner = situation_plan(situation_payload) if situation_payload is not None else None
    profiles = (situation_owner.profile,) if situation_owner else PROFILES
    errors = []
    for profile in profiles:
        plans = ([charge_plan(profile)] if use_charge else []) + ([situation_owner] if situation_owner else [])
        try:
            output, receipt = compose_image(image, plans)
            return output, receipt, plans
        except ValidationError as exc:
            errors.append(str(exc))
    raise ValidationError("No supported APF repair input: " + "; ".join(errors))


def repair(input_path, output_directory, *, use_charge=False, situation_patch=None):
    source = read_input(input_path)
    if source[:4] == b"XEX2":
        raise ValidationError("Supply the decoded flat PE. This offline repair does not rebuild an XEX")
    payload = read_input(situation_patch) if situation_patch is not None else None
    output, receipt, plans = prepare_repair(source, use_charge=use_charge, situation_payload=payload)
    # A second application must recover exactly the same output.
    reapplied, _ = compose_image(output, plans)
    if reapplied != output:
        raise ValidationError("Offline repair failed its idempotence proof")
    receipt["reapplying_same_patches_identical"] = True
    destination = Path(output_directory)
    if destination.exists() or destination.is_symlink():
        raise ValidationError("Choose a new output directory; existing files are never replaced")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".d3-repair-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "output"
        staging.mkdir()
        artifacts = {"repaired.pe": output,
                     "scope-receipt.json": (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")}
        artifacts.update({plan.filename: plan.payload for plan in plans})
        for name, contents in artifacts.items():
            with (staging / name).open("xb") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            if (staging / name).read_bytes() != contents:
                raise ValidationError("Offline repair artifact failed readback")
        # Refuse an output that appeared while staging, including a symlink.
        if destination.exists() or destination.is_symlink():
            raise ValidationError("Output directory appeared during repair; choose a new directory")
        platform_compat.publish_no_replace(staging, destination, is_directory=True)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-pe", type=Path, required=True)
    parser.add_argument("--charge", action="store_true", help="Replay the current enabled charge repair")
    parser.add_argument("--situation-patch", type=Path, help="Fresh enabled Studio situation TOML")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args(argv)
    if not args.charge and args.situation_patch is None:
        parser.error("Choose --charge and/or --situation-patch")
    try:
        receipt = repair(args.input_pe, args.output, use_charge=args.charge, situation_patch=args.situation_patch)
    except (OSError, ValidationError) as exc:
        parser.exit(1, f"APF offline repair refused: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
