#!/usr/bin/env python3
"""Fast APF Field Art product gate with an explicit full-volume mode.

The registry invokes this file without arguments.  That default validates the
six shipped writer contracts, the independent verifier boundary, and the
hash-pinned metadata-only receipt.  It never opens a retail volume or a cleaned
temporary build.  ``--full-volume`` is deliberately opt-in and requires every
real input needed by the independent whole-volume verifier.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_field_art_patch as patch  # noqa: E402
import apf_field_art_verify as verifier  # noqa: E402


EVIDENCE = ROOT / "tools/apf_field_art_product_evidence.v1.json"
EVIDENCE_SHA256 = "39cc2fb4c7c457c516fff75d7663b075d607389f43ece4b2fdc7ed629f4a3a13"
FULL_VOLUME_AUTHORITY_SHA256 = (
    "135c8cb20b631d7a9e0c03848f25046a47e49144e2db64bb30967963691b56d5"
)
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_TARGETS = {
    (6, 0): ("endzone_l0", "dxt1", 2048, 512),
    (6, 1): ("endzone_l1", "dxt1", 2048, 512),
    (53, 0): ("divots", "rgba8888", 64, 64),
    (659, 18): ("pc_field_goal", "dxt1", 256, 256),
    (659, 23): ("Field_Pass_text", "bc3", 128, 128),
    (659, 252): ("Stride_number_field", "bc3", 128, 128),
}


class ProductValidationError(ValueError):
    """The fast product contract or explicit deep proof is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProductValidationError(message)


def _read_regular(path: Path, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ProductValidationError(f"{label} is unavailable: {path}") from exc
    require(stat.S_ISREG(metadata.st_mode), f"{label} is not a regular file: {path}")
    require(metadata.st_nlink == 1, f"{label} must have one hard link: {path}")
    return path.read_bytes()


def _unique(label: str):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    return hook


def _load_evidence(path: Path = EVIDENCE) -> dict[str, Any]:
    payload = _read_regular(path, "field-art evidence")
    require(
        hashlib.sha256(payload).hexdigest() == EVIDENCE_SHA256,
        "field-art evidence hash differs",
    )
    try:
        document = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique("field-art evidence")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductValidationError("field-art evidence is not strict UTF-8 JSON") from exc
    require(isinstance(document, dict), "field-art evidence root is not an object")
    return document


def _validate_independent_boundary() -> None:
    source = _read_regular(Path(verifier.__file__), "field-art verifier").decode("utf-8")
    tree = ast.parse(source, filename=str(verifier.__file__))
    writer_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "apf_field_art_patch":
            writer_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            require(
                all(alias.name != "apf_field_art_patch" for alias in node.names),
                "field-art verifier imports the writer module",
            )
    require(
        writer_imports == {"FieldArtContract", "_CONTRACTS"},
        "field-art verifier must share only the frozen contract type/table",
    )
    for forbidden in ("build_field_art_patch", "_write_copied_volume"):
        require(forbidden not in source, f"field-art verifier references writer {forbidden}")
    require(callable(verifier.verify), "field-art independent verifier is unavailable")


def validate_fast(evidence_path: Path = EVIDENCE) -> dict[str, Any]:
    require(set(patch._CONTRACTS) == set(EXPECTED_TARGETS), "field-art target set differs")
    for key, expected in EXPECTED_TARGETS.items():
        contract = patch._CONTRACTS[key]
        observed = (contract.name, contract.codec, contract.width, contract.height)
        require(observed == expected, f"field-art contract differs for {key}: {observed}")
        require(
            len(contract.entry_sha256) == len(contract.base_sha256) == 64,
            f"field-art hash pins are malformed for {key}",
        )
    _validate_independent_boundary()

    report = _load_evidence(evidence_path)
    require(report.get("schema") == "apf_field_art_verify/v1", "field-art schema differs")
    require(
        report.get("authority") == {
            "path": "reports/assets/apf_field_art_roundtrip.json",
            "sha256": FULL_VOLUME_AUTHORITY_SHA256,
        },
        "field-art full-volume authority pin differs",
    )
    require(report.get("mode") == "patched", "field-art evidence is not a changed proof")
    source = report.get("source", {})
    require(
        source.get("sha256_before") == source.get("sha256_after") == EXPECTED_VOLUME_SHA256,
        "field-art source identity differs",
    )
    require(source.get("modified") is False, "field-art evidence says the source changed")
    validation = report.get("validation", {})
    for claim in (
        "source_is_pinned_retail",
        "fixed_outer_allocation_preserved",
        "descriptor_preserved",
        "descriptor_pad_preserved",
        "packed_mip_tail_preserved",
        "name_footer_preserved",
        "only_target_base_part_changed",
        "output_edit_within_png_footprint",
        "all_other_volume_bytes_identical",
        "source_opened_read_only",
    ):
        require(validation.get(claim) is True, f"field-art evidence lost claim {claim}")
    require(validation.get("runtime_visibility_proved") is False, "runtime claim widened")
    require(
        report.get("contains_game_or_replacement_bytes") is False,
        "field-art evidence embeds private or replacement bytes",
    )
    diff = report.get("whole_volume_diff", {})
    require(
        diff.get("changed_byte_count") == diff.get("changed_bytes_inside_target_entry")
        and diff.get("all_other_bytes_identical") is True,
        "field-art whole-volume evidence differs",
    )
    return report


def _regular_input(path: Path | None, label: str) -> Path:
    require(path is not None, f"--{label} is required with --full-volume")
    assert path is not None
    _read_regular(path, label.replace("-", " "))
    return path


def validate_full_volume(args: argparse.Namespace) -> dict[str, Any]:
    source = _regular_input(args.source_volume, "source-volume")
    output = _regular_input(args.output_volume, "output-volume")
    png = _regular_input(args.png, "png")
    manifest = _regular_input(args.manifest, "manifest")
    require(source.resolve() != output.resolve(), "source and output volumes alias")
    require(args.entry_index is not None, "--entry-index is required with --full-volume")
    require(args.file_index is not None, "--file-index is required with --full-volume")
    report = verifier.verify(
        source,
        output,
        png,
        args.entry_index,
        args.file_index,
        manifest,
    )
    require(report["validation"]["all_other_volume_bytes_identical"] is True,
            "full-volume verifier found unrelated changes")
    require(report["source"]["modified"] is False, "full-volume verifier found source drift")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-volume", action="store_true")
    parser.add_argument("--source-volume", type=Path)
    parser.add_argument("--output-volume", type=Path)
    parser.add_argument("--png", type=Path)
    parser.add_argument("--entry-index", type=int)
    parser.add_argument("--file-index", type=int)
    parser.add_argument("--manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_fast()
        deep_values = (
            args.source_volume,
            args.output_volume,
            args.png,
            args.entry_index,
            args.file_index,
            args.manifest,
        )
        if not args.full_volume:
            require(not any(value is not None for value in deep_values),
                    "full-volume inputs require --full-volume")
            print(
                "APF_FIELD_ART_PRODUCT_VALIDATION_PASS "
                "mode=fast targets=6 evidence=hash-pinned full_volume=explicit"
            )
            return 0
        report = validate_full_volume(args)
        print(
            "APF_FIELD_ART_PRODUCT_VALIDATION_PASS "
            f"mode=full target={report['target']['entry_index']}:{report['target']['file_index']} "
            f"changed={report['whole_volume_diff']['changed_byte_count']}"
        )
        return 0
    except (ProductValidationError, verifier.VerifyError, KeyError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
