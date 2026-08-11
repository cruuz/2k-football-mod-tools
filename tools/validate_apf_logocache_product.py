#!/usr/bin/env python3
"""Fast APF logo-cache product gate with an explicit full-volume mode.

The no-argument registry path validates the fixed cache contract, the
independent verifier implementation boundary, and the hash-pinned metadata-only
fixture.  It never stats historical emulator/game paths.  ``--full-volume``
requires caller-supplied real source and copied-output volumes.
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

import apf_logocache_patch as patch  # noqa: E402
import apf_logocache_verify as verifier  # noqa: E402


EVIDENCE = ROOT / "tools/apf_logocache_product_evidence.v1.json"
EVIDENCE_SHA256 = "c8f28dc54641e2c22fcdd47c42ba28182e08dcdc91bf910a4a4853d40cdba623"
FULL_VOLUME_AUTHORITY_SHA256 = (
    "a48b7b10c858716ee55ddf456665123afbfbcb635feb4b83d725a692f3b7c491"
)
EXPECTED_SOURCE_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(label: str):
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    return hook


def _load_evidence(path: Path = EVIDENCE) -> dict[str, Any]:
    payload = _read_regular(path, "logo-cache evidence")
    require(
        hashlib.sha256(payload).hexdigest() == EVIDENCE_SHA256,
        "logo-cache evidence hash differs",
    )
    try:
        document = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique("logo-cache evidence")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductValidationError("logo-cache evidence is not strict UTF-8 JSON") from exc
    require(isinstance(document, dict), "logo-cache evidence root is not an object")
    return document


def _validate_independent_boundary() -> None:
    source = _read_regular(Path(verifier.__file__), "logo-cache verifier").decode("utf-8")
    tree = ast.parse(source, filename=str(verifier.__file__))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            require(
                all(alias.name != "apf_logocache_patch" for alias in node.names),
                "logo-cache verifier imports the writer",
            )
        elif isinstance(node, ast.ImportFrom):
            require(node.module != "apf_logocache_patch", "logo-cache verifier imports the writer")
    require(callable(verifier.verify_cache_patch), "logo-cache independent verifier is unavailable")


def validate_fast(evidence_path: Path = EVIDENCE) -> dict[str, Any]:
    for name in (
        "DIR_TABLE_INDEX",
        "PAYLOAD_TABLE_INDEX",
        "DIR_PACK_OFFSET",
        "PAYLOAD_PACK_OFFSET",
        "DIR_SIZE",
        "PAYLOAD_SIZE",
        "FILE_COUNT",
    ):
        require(getattr(patch, name) == getattr(verifier, name), f"logo-cache {name} differs")
    require(patch.FILE_COUNT == 236, "logo-cache entry count differs")
    require(patch.DIR_SIZE == 0xA000, "logo-cache directory size differs")
    require(patch.PAYLOAD_SIZE == 0x9E0800, "logo-cache payload size differs")
    _validate_independent_boundary()

    report = _load_evidence(evidence_path)
    require(
        report.get("schema") == "apf_logocache_roundtrip_validation/v1",
        "logo-cache evidence schema differs",
    )
    require(
        report.get("authority") == {
            "path": "reports/assets/apf_logocache_roundtrip.json",
            "sha256": FULL_VOLUME_AUTHORITY_SHA256,
        },
        "logo-cache full-volume authority pin differs",
    )
    source = report.get("source", {})
    require(source.get("directory_sha256") == patch.EXPECTED_DIR_SHA256,
            "logo-cache directory pin differs")
    require(source.get("payload_sha256") == patch.EXPECTED_PAYLOAD_SHA256,
            "logo-cache payload pin differs")
    safety = report.get("safety_validation", {})
    for claim in (
        "source_path_as_output_refused",
        "existing_output_refused",
        "fixed_outer_allocations",
        "every_dram_part_preserved",
        "edited_mip_tails_regenerated",
        "every_unedited_mip_tail_preserved",
        "every_other_catalog_entry_preserved",
        "directory_changes_confined_to_auxiliary_records",
    ):
        require(safety.get(claim) is True, f"logo-cache evidence lost claim {claim}")
    require(safety.get("retail_source_modified") is False, "logo-cache source changed")
    require(
        safety.get("replacement_bytes_embedded_in_report") is False,
        "logo-cache evidence embeds replacement bytes",
    )
    conclusion = report.get("conclusion", {})
    require(conclusion.get("offline_cache_base_write_proved") is True,
            "logo-cache offline writer proof is absent")
    require(conclusion.get("copy_only_writer_exposed") is True,
            "logo-cache copy-only route is absent")
    require(conclusion.get("xenia_runtime_validation") is False,
            "logo-cache runtime claim widened")
    # This retained fast fixture deliberately records that it did not perform a
    # 1.1 GB copy.  The current independent verifier is checked above; callers
    # must request the separate deep gate to validate real source/output files.
    require(conclusion.get("copied_volume_roundtrip_proved") is False,
            "fast logo-cache fixture unexpectedly claims a full-volume proof")
    require(conclusion.get("independent_verifier_ran") is False,
            "fast logo-cache fixture unexpectedly claims a verifier run")
    artifacts = report.get("artifacts", {})
    require(
        artifacts.get("writer_sha256") == _sha256_file(Path(patch.__file__)),
        "logo-cache writer differs from the pinned fixture",
    )
    for key in ("writer_sha256", "verifier_sha256", "test_sha256"):
        value = artifacts.get(key)
        require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
                f"logo-cache artifact hash is malformed: {key}")
    return report


def _regular_input(path: Path | None, label: str) -> Path:
    require(path is not None, f"--{label} is required with --full-volume")
    assert path is not None
    _read_regular(path, label.replace("-", " "))
    return path


def validate_full_volume(args: argparse.Namespace) -> dict[str, Any]:
    source = _regular_input(args.source, "source")
    output = _regular_input(args.output, "output")
    require(source.resolve() != output.resolve(), "source and output volumes alias")
    require(args.catalog_index is not None, "--catalog-index is required with --full-volume")
    require(0 <= args.catalog_index < 118, "--catalog-index must be in 0..117")
    require(_sha256_file(source) == EXPECTED_SOURCE_SHA256,
            "logo-cache source volume identity differs")
    result = verifier.verify_cache_patch(
        source,
        output,
        expected_catalog_index=args.catalog_index,
        expect_l1=args.expect_l1,
    )
    require(result.ok is True, "logo-cache full-volume verifier did not pass")
    require(result.manifest["volume_diff"]["all_changes_within_extents"] is True,
            "logo-cache full-volume verifier found unrelated changes")
    return result.manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-volume", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--catalog-index", type=int)
    parser.add_argument("--expect-l1", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_fast()
        deep_values = (args.source, args.output, args.catalog_index)
        if not args.full_volume:
            require(not any(value is not None for value in deep_values) and not args.expect_l1,
                    "full-volume inputs require --full-volume")
            print(
                "APF_LOGOCACHE_PRODUCT_VALIDATION_PASS "
                "mode=fast entries=236 evidence=hash-pinned full_volume=explicit"
            )
            return 0
        report = validate_full_volume(args)
        print(
            "APF_LOGOCACHE_PRODUCT_VALIDATION_PASS "
            f"mode=full catalog={args.catalog_index} "
            f"changed={len(report['proof']['changed_vram_base_levels'])}"
        )
        return 0
    except (ProductValidationError, verifier.VerifyError, KeyError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
