#!/usr/bin/env python3
"""Adversarial tests for dynamic 09H0 validation and workflow ownership."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from nfl_outer import parse_archive
from nfl_scene_probe import read_entry_range
import nfl_tset_png_import as importer
from nfl_tset_png_import_dynamic_validate import (
    DynamicValidationError,
    validate_dynamic_import,
)
import nfl_tset_png_import_xiso_generic_patch as writer
import nfl2k5_jersey_png_workflow as workflow
from nfl_txtr import TxtrError, encode_rgba_png
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"


def expect_failure(callback, exceptions: tuple[type[BaseException], ...], label: str) -> None:
    try:
        callback()
    except exceptions:
        return
    raise AssertionError(f"{label} did not fail closed")


def user_fixture() -> bytes:
    colors = (
        (0x10, 0x24, 0x48, 0xFF), (0xE8, 0xEE, 0xF8, 0xFF),
        (0x32, 0xB4, 0xD8, 0xFF), (0xF0, 0x58, 0x28, 0xFF),
        (0x78, 0x34, 0xB8, 0xFF), (0xFC, 0xC8, 0x20, 0xFF),
        (0x14, 0x9C, 0x54, 0xFF), (0xC8, 0x28, 0x58, 0xFF),
    )
    rgba = bytearray()
    for y in range(256):
        for x in range(512):
            block = ((x // 32) + 3 * (y // 16) + ((x ^ y) // 64)) % len(colors)
            rgba.extend(colors[block])
    return encode_rgba_png(512, 256, bytes(rgba))


def noise_fixture() -> bytes:
    state = 0x12345678
    rgba = bytearray()
    for _ in range(512 * 256):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        value = state & 0xFF
        rgba.extend((value, (value * 73) & 0xFF, (value * 151) & 0xFF, 0xFF))
    return encode_rgba_png(512, 256, bytes(rgba))


def main() -> int:
    archive = parse_archive(INDEX)
    source_span = read_entry_range(archive, archive.entries[3685], 0x70, 74720)

    with tempfile.TemporaryDirectory(prefix="nfl-dynamic-workflow-test-") as name:
        temporary = Path(name)
        clean = temporary / "my_noncanonical_jersey.png"
        clean.write_bytes(user_fixture())
        span = temporary / "custom.tset.bin"
        manifest = temporary / "custom.json"
        previews = temporary / "custom-previews"
        report = importer.run(
            INDEX, INVENTORY, clean, None, "darken_60", span, manifest, previews
        )
        preview_payloads = {
            child.name: child.read_bytes() for child in previews.iterdir()
        }
        validated, evidence = validate_dynamic_import(
            source_span=source_span,
            replacement_span=span.read_bytes(),
            import_manifest_payload=manifest.read_bytes(),
            clean_png_name=clean.name,
            clean_png_payload=clean.read_bytes(),
            mud_png_name=None,
            mud_png_payload=None,
            preview_payloads=preview_payloads,
            replacement_span_name=span.name,
            import_manifest_name=manifest.name,
            preview_directory_name=previews.name,
        )
        assert validated.span_sha256 == report["rebuild"]["complete_span_sha256"]
        assert validated.span_sha256 != \
            "76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8"
        assert evidence["mud_mode"] == {"kind": "derived_palette", "mode": "darken_60"}
        assert validated.encoded_bytes < 74688 and validated.preview_count == 12

        # Exercise the optional strict second-PNG branch with a distinct file
        # containing identity mud pixels.  An arbitrary independently painted
        # mud image remains intentionally fail-closed unless it shares the
        # clean P8 mapping exactly.
        strict_mud = temporary / "strict_identity_mud.png"
        strict_mud.write_bytes(clean.read_bytes())
        strict_span = temporary / "strict-mud.tset.bin"
        strict_manifest = temporary / "strict-mud.json"
        strict_previews = temporary / "strict-mud-previews"
        importer.run(
            INDEX, INVENTORY, clean, strict_mud, "identity",
            strict_span, strict_manifest, strict_previews,
        )
        strict_validated, _ = validate_dynamic_import(
            source_span=source_span,
            replacement_span=strict_span.read_bytes(),
            import_manifest_payload=strict_manifest.read_bytes(),
            clean_png_name=clean.name,
            clean_png_payload=clean.read_bytes(),
            mud_png_name=strict_mud.name,
            mud_png_payload=strict_mud.read_bytes(),
            preview_payloads={
                child.name: child.read_bytes() for child in strict_previews.iterdir()
            },
            replacement_span_name=strict_span.name,
            import_manifest_name=strict_manifest.name,
            preview_directory_name=strict_previews.name,
        )
        assert strict_validated.mud_source_kind == "second_png_exact_shared_indices"
        assert strict_validated.mud_png_sha256 == hashlib.sha256(
            strict_mud.read_bytes()
        ).hexdigest()

        base = json.loads(manifest.read_bytes())

        def forged_payload(mutator) -> bytes:
            value = json.loads(json.dumps(base))
            mutator(value)
            return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()

        def validate_payload(payload: bytes) -> None:
            validate_dynamic_import(
                source_span=source_span,
                replacement_span=span.read_bytes(),
                import_manifest_payload=payload,
                clean_png_name=clean.name,
                clean_png_payload=clean.read_bytes(),
                mud_png_name=None,
                mud_png_payload=None,
                preview_payloads=preview_payloads,
                replacement_span_name=span.name,
                import_manifest_name=manifest.name,
                preview_directory_name=previews.name,
            )

        for label, mutator in (
            ("schema", lambda value: value.__setitem__("schema", "forged")),
            ("target", lambda value: value["target"].__setitem__("outer_index", 1)),
            ("clean hash", lambda value: value["input"]["clean"].__setitem__(
                "sha256", "0" * 64)),
            ("compression", lambda value: value["compression"].__setitem__(
                "encoded_bytes", 1)),
            ("claim", lambda value: value["claims"].__setitem__(
                "runtime_visibility_proved", True)),
            ("output name", lambda value: value["outputs"].__setitem__(
                "span_file", "forged.bin")),
            ("unexpected field", lambda value: value.__setitem__("forged", True)),
        ):
            expect_failure(
                lambda mutator=mutator: validate_payload(forged_payload(mutator)),
                (DynamicValidationError,), f"forged {label} manifest",
            )
        expect_failure(
            lambda: validate_payload(b"{not-json"),
            (DynamicValidationError,), "malformed manifest",
        )
        duplicate = manifest.read_bytes().replace(
            b"{\n", b'{\n  "schema": "duplicate",\n', 1
        )
        expect_failure(
            lambda: validate_payload(duplicate),
            (DynamicValidationError,), "duplicate JSON key",
        )

        noisy = temporary / "incompressible.png"
        noisy.write_bytes(noise_fixture())
        oversized_span = temporary / "oversized.tset.bin"
        oversized_manifest = temporary / "oversized.json"
        oversized_previews = temporary / "oversized-previews"
        expect_failure(
            lambda: importer.run(
                INDEX, INVENTORY, noisy, None, "identity",
                oversized_span, oversized_manifest, oversized_previews,
            ),
            (TxtrError, importer.ImportError), "incompressible fixed-span import",
        )
        assert not oversized_span.exists() and not oversized_manifest.exists() and \
            not oversized_previews.exists()

        symlink = temporary / "symlink.png"
        symlink.symlink_to(clean.name)
        expect_failure(
            lambda: writer.pin_small_file(symlink, "symlink fixture"),
            (common.PatchError,), "generic writer symlink input",
        )
        expect_failure(
            lambda: importer.read_rgba_png(symlink),
            (importer.ImportError,), "importer symlink input",
        )

        swap = temporary / "swap.bin"
        swap.write_bytes(b"first")
        pinned = writer.pin_small_file(swap, "swap fixture")
        old = temporary / "swap-old.bin"
        swap.rename(old)
        swap.write_bytes(b"second")
        expect_failure(
            lambda: writer.verify_pin(pinned, "swap fixture"),
            (common.PatchError,), "input pathname swap",
        )

        sentinel = temporary / "already-exists.iso"
        sentinel.write_bytes(b"DO NOT OVERWRITE")
        sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        expect_failure(
            lambda: workflow.run(
                source_xiso=temporary / "not-needed.iso",
                clean_png=clean,
                mud_png=None,
                mud_mode="identity",
                output_xiso=sentinel,
                manifest_path=temporary / "unused-final.json",
                preview_dir=temporary / "unused-previews",
            ),
            (common.PatchError,), "workflow O_EXCL preflight",
        )
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
        expect_failure(
            lambda: workflow.run(
                source_xiso=temporary / "not-needed.iso",
                clean_png=clean,
                mud_png=strict_mud,
                mud_mode="darken_60",
                output_xiso=temporary / "unused.iso",
                manifest_path=temporary / "unused.json",
                preview_dir=temporary / "unused-preview-dir",
            ),
            (common.PatchError,), "mud PNG/derived mode conflict",
        )

        owned_root_path = temporary / "owned-cleanup"
        owned_root_path.mkdir()
        owned_root = workflow.track_existing(owned_root_path, True)
        known_path = owned_root_path / "known"
        known_path.write_bytes(b"known")
        known = workflow.track_existing(known_path, False)
        unknown = owned_root_path / "unknown"
        unknown.write_bytes(b"unknown")
        leftovers = workflow.cleanup_owned([known], [owned_root])
        assert not known_path.exists() and unknown.read_bytes() == b"unknown"
        assert owned_root_path.exists() and str(owned_root_path) in leftovers

    assert INDEX.stat().st_size == workflow.INDEX_SIZE
    assert INVENTORY.stat().st_size == workflow.INVENTORY_SIZE
    print(
        "NFL_TSET_PNG_IMPORT_DYNAMIC_WORKFLOW_TESTS_PASS "
        f"noncanonical_span={validated.span_sha256} encoded={validated.encoded_bytes} "
        "manifests_forged=9 oversize_refused=true symlink_refused=true "
        "path_swap_refused=true o_excl=true strict_mud=true mud_conflict_refused=true "
        "owned_cleanup=true previews=12 runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
