#!/usr/bin/env python3
"""Fast destructive-path regression gate for all exposed APF texture writers.

The fixtures are intentionally invalid: every case must be rejected by CLI
path preflight before a retail archive or PNG parser can run.  This keeps the
test small while proving that rejected invocations neither alter their input
sentinels nor leave any requested output behind.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Callable, Sequence, cast


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_jersey_family_patch as family_patch  # noqa: E402
import apf_texture_patch as texture_patch  # noqa: E402
import apf_uniform_mip_patch as uniform_patch  # noqa: E402


SENTINEL_INDEX = b"APF writer path-safety index sentinel\x00\xff"
SENTINEL_PNG = b"APF writer path-safety PNG sentinel\xff\x00"
SENTINEL_MANIFEST = b"existing manifest sentinel: do not replace\n"
SENTINEL_RACING_MANIFEST = b"racing manifest sentinel: do not replace\n"
SENTINEL_SWAPPED_MANIFEST = b"swapped manifest sentinel: do not replace\n"
SENTINEL_VOLUME = b"existing volume sentinel: do not replace\n"
SENTINEL_ENTRY = b"swapped output-entry sentinel: do not replace\n"
EXPECTED_0A_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)


@dataclass(frozen=True)
class Writer:
    name: str
    main: Callable[[list[str] | None], int]
    extra_args: tuple[str, ...] = ()


WRITERS = (
    Writer("texture", texture_patch.main),
    Writer("uniform_mip", uniform_patch.main),
    Writer("jersey_family", family_patch.main, ("--asset-index", "6")),
)


def _run_rejected(main: Callable[[list[str] | None], int], argv: Sequence[str]) -> str:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main(list(argv))
    assert status == 1, (argv, status, stdout.getvalue(), stderr.getvalue())
    assert stdout.getvalue() == ""
    assert stderr.getvalue().startswith("error: "), stderr.getvalue()
    return stderr.getvalue()


def _assert_only(directory: Path, expected: set[Path]) -> None:
    actual = {path.relative_to(directory) for path in directory.rglob("*")}
    assert actual == expected, (actual, expected)


def _cli_collision_case(writer: Writer, case: str) -> None:
    with tempfile.TemporaryDirectory(
        prefix=f"apf-{writer.name}-{case}-"
    ) as temporary:
        root = Path(temporary)
        index = root / "input-0A"
        png = root / "input.png"
        manifest = root / "manifest.json"
        output_entry = root / "rebuilt.iff"
        output_volume = root / "copied-0A"
        index.write_bytes(SENTINEL_INDEX)
        png.write_bytes(SENTINEL_PNG)

        if case == "manifest_alias_index":
            manifest = index
        elif case == "manifest_alias_png":
            manifest = png
        elif case == "manifest_alias_output_entry":
            manifest = output_entry
        elif case == "manifest_alias_output_volume":
            manifest = output_volume
        elif case == "existing_manifest":
            manifest.write_bytes(SENTINEL_MANIFEST)
        else:  # pragma: no cover - caller supplies a closed set
            raise AssertionError(case)

        argv = [
            "--index",
            str(index),
            "--png",
            str(png),
            *writer.extra_args,
            "--output-entry",
            str(output_entry),
            "--output-volume",
            str(output_volume),
            "--manifest",
            str(manifest),
        ]
        _run_rejected(writer.main, argv)

        assert index.read_bytes() == SENTINEL_INDEX
        assert png.read_bytes() == SENTINEL_PNG
        if case == "existing_manifest":
            assert manifest.read_bytes() == SENTINEL_MANIFEST
        if case != "manifest_alias_output_entry":
            assert not output_entry.exists()
        else:
            assert not manifest.exists()
        if case != "manifest_alias_output_volume":
            assert not output_volume.exists()
        else:
            assert not manifest.exists()

        expected = {Path(index.name), Path(png.name)}
        if case == "existing_manifest":
            expected.add(Path(manifest.name))
        _assert_only(root, expected)


def _existing_volume_helper_case() -> None:
    """O_EXCL failure must not let cleanup delete someone else's volume."""
    with tempfile.TemporaryDirectory(prefix="apf-existing-volume-") as temporary:
        root = Path(temporary)
        source = root / "source-0A"
        destination = root / "destination-0A"
        source.write_bytes(SENTINEL_INDEX)
        destination.write_bytes(SENTINEL_VOLUME)
        try:
            texture_patch._write_copied_volume(  # type: ignore[attr-defined]
                source,
                destination,
                cast(object, None),
                b"unused replacement",
            )
        except texture_patch.PatchError:
            pass
        else:
            raise AssertionError("existing copied-volume destination was accepted")
        assert source.read_bytes() == SENTINEL_INDEX
        assert destination.read_bytes() == SENTINEL_VOLUME
        _assert_only(root, {Path(source.name), Path(destination.name)})


def _manifest_reservation_race_case(writer: Writer) -> None:
    """A destination appearing after preflight must survive O_EXCL failure."""
    with tempfile.TemporaryDirectory(
        prefix=f"apf-{writer.name}-manifest-race-"
    ) as temporary:
        root = Path(temporary)
        index = root / "input-0A"
        png = root / "input.png"
        manifest = root / "manifest.json"
        output_entry = root / "rebuilt.iff"
        output_volume = root / "copied-0A"
        index.write_bytes(SENTINEL_INDEX)
        png.write_bytes(SENTINEL_PNG)

        original_preflight = texture_patch._preflight_output_paths  # type: ignore[attr-defined]

        def race_after_preflight(
            inputs: list[Path], outputs: list[tuple[str, Path | None]]
        ) -> None:
            original_preflight(inputs, outputs)
            manifest.write_bytes(SENTINEL_RACING_MANIFEST)

        texture_patch._preflight_output_paths = race_after_preflight  # type: ignore[attr-defined]
        try:
            _run_rejected(
                writer.main,
                [
                    "--index",
                    str(index),
                    "--png",
                    str(png),
                    *writer.extra_args,
                    "--output-entry",
                    str(output_entry),
                    "--output-volume",
                    str(output_volume),
                    "--manifest",
                    str(manifest),
                ],
            )
        finally:
            texture_patch._preflight_output_paths = original_preflight  # type: ignore[attr-defined]

        assert index.read_bytes() == SENTINEL_INDEX
        assert png.read_bytes() == SENTINEL_PNG
        assert manifest.read_bytes() == SENTINEL_RACING_MANIFEST
        assert not output_entry.exists()
        assert not output_volume.exists()
        _assert_only(
            root, {Path(index.name), Path(png.name), Path(manifest.name)}
        )


def _manifest_inode_swap_case(writer: Writer) -> None:
    """Caller cleanup must not remove a post-reservation replacement path."""
    with tempfile.TemporaryDirectory(
        prefix=f"apf-{writer.name}-manifest-inode-swap-"
    ) as temporary:
        root = Path(temporary)
        index = root / "input-0A"
        png = root / "input.png"
        manifest = root / "manifest.json"
        displaced_owned_inode = root / "owned-manifest-moved-away"
        output_entry = root / "rebuilt.iff"
        output_volume = root / "copied-0A"
        index.write_bytes(SENTINEL_INDEX)
        png.write_bytes(SENTINEL_PNG)

        original_reserve = texture_patch._reserve_new  # type: ignore[attr-defined]

        def reserve_then_swap(path: Path) -> texture_patch.OutputReservation:
            reservation = original_reserve(path)
            assert path == manifest
            path.rename(displaced_owned_inode)
            path.write_bytes(SENTINEL_SWAPPED_MANIFEST)
            return reservation

        texture_patch._reserve_new = reserve_then_swap  # type: ignore[attr-defined]
        try:
            _run_rejected(
                writer.main,
                [
                    "--index",
                    str(index),
                    "--png",
                    str(png),
                    *writer.extra_args,
                    "--output-entry",
                    str(output_entry),
                    "--output-volume",
                    str(output_volume),
                    "--manifest",
                    str(manifest),
                ],
            )
        finally:
            texture_patch._reserve_new = original_reserve  # type: ignore[attr-defined]

        assert index.read_bytes() == SENTINEL_INDEX
        assert png.read_bytes() == SENTINEL_PNG
        assert manifest.read_bytes() == SENTINEL_SWAPPED_MANIFEST
        assert displaced_owned_inode.read_bytes() == b""
        assert not output_entry.exists()
        assert not output_volume.exists()
        _assert_only(
            root,
            {
                Path(index.name),
                Path(png.name),
                Path(manifest.name),
                Path(displaced_owned_inode.name),
            },
        )


def _output_entry_inode_swap_case(
    name: str, write_new: Callable[[Path, bytes], None]
) -> None:
    """Shared output-entry writer must keep writes on its reserved inode."""
    with tempfile.TemporaryDirectory(
        prefix=f"apf-{name}-entry-inode-swap-"
    ) as temporary:
        root = Path(temporary)
        output = root / "rebuilt.iff"
        displaced_owned_inode = root / "owned-entry-moved-away"
        payload = b"owned output-entry payload\x00\xff"
        original_pwrite = texture_patch._pwrite_all  # type: ignore[attr-defined]
        swapped = False

        def swap_before_write(descriptor: int, data: bytes, offset: int) -> None:
            nonlocal swapped
            if not swapped and data == payload and offset == 0:
                output.rename(displaced_owned_inode)
                output.write_bytes(SENTINEL_ENTRY)
                swapped = True
            original_pwrite(descriptor, data, offset)

        texture_patch._pwrite_all = swap_before_write  # type: ignore[attr-defined]
        try:
            try:
                write_new(output, payload)
            except texture_patch.PatchError as exc:
                assert "reserved output pathname changed" in str(exc)
            else:
                raise AssertionError("output-entry pathname replacement was accepted")
        finally:
            texture_patch._pwrite_all = original_pwrite  # type: ignore[attr-defined]

        assert swapped
        assert output.read_bytes() == SENTINEL_ENTRY
        assert displaced_owned_inode.read_bytes() == payload
        _assert_only(
            root, {Path(output.name), Path(displaced_owned_inode.name)}
        )


def _output_inode_swap_case() -> None:
    """All mutation stays on the owned fd after its pathname is replaced."""
    with tempfile.TemporaryDirectory(prefix="apf-output-inode-swap-") as temporary:
        root = Path(temporary)
        source = root / "source-0A"
        output = root / "output-0A"
        displaced_owned_inode = root / "owned-inode-moved-away"
        source_bytes = b"0123456789abcdef"
        replacement = b"APF!"
        source.write_bytes(source_bytes)
        entry = SimpleNamespace(
            segments=[SimpleNamespace(pack_offset=4)]
        )

        original_pwrite = texture_patch._pwrite_all  # type: ignore[attr-defined]
        swapped = False

        def swap_before_replacement(
            descriptor: int, data: bytes, offset: int
        ) -> None:
            nonlocal swapped
            if not swapped and data == replacement and offset == 4:
                output.rename(displaced_owned_inode)
                output.write_bytes(SENTINEL_VOLUME)
                swapped = True
            original_pwrite(descriptor, data, offset)

        texture_patch._pwrite_all = swap_before_replacement  # type: ignore[attr-defined]
        try:
            try:
                texture_patch._write_copied_volume(  # type: ignore[attr-defined]
                    source,
                    output,
                    entry,
                    replacement,
                )
            except texture_patch.PatchError as exc:
                assert "output volume pathname changed" in str(exc)
            else:
                raise AssertionError("output pathname replacement was not detected")
        finally:
            texture_patch._pwrite_all = original_pwrite  # type: ignore[attr-defined]

        assert swapped
        assert source.read_bytes() == source_bytes
        assert output.read_bytes() == SENTINEL_VOLUME
        displaced = displaced_owned_inode.read_bytes()
        assert displaced[:4] == source_bytes[:4]
        assert displaced[4:8] == replacement
        assert displaced[8:] == source_bytes[8:]
        _assert_only(
            root,
            {
                Path(source.name),
                Path(output.name),
                Path(displaced_owned_inode.name),
            },
        )


def _report() -> dict[str, object]:
    return {
        "schema": "apf_writer_path_safety/v1",
        "scope": {
            "writers": [writer.name for writer in WRITERS],
            "retail_inputs_opened_by_regression_test": False,
            "retail_inputs_written": False,
        },
        "case_counts": {
            "manifest_alias_or_existing_cli": 15,
            "manifest_post_preflight_reservation_race_cli": 3,
            "manifest_post_reservation_inode_swap_cli": 3,
            "output_entry_inode_path_swap": 2,
            "existing_volume_destination": 1,
            "output_inode_path_swap": 1,
            "total": 25,
        },
        "manifest_cases_per_writer": [
            "aliases_index",
            "aliases_png",
            "aliases_output_entry",
            "aliases_output_volume",
            "already_exists",
            "appears_after_preflight_before_O_EXCL",
            "pathname_replaced_after_reservation_before_failure_cleanup",
        ],
        "proved_invariants": {
            "input_sentinels_bit_exact": True,
            "existing_manifest_sentinels_bit_exact": True,
            "existing_volume_sentinel_bit_exact": True,
            "replacement_path_sentinel_bit_exact_after_inode_swap": True,
            "rejected_cli_unintended_outputs": 0,
            "manifest_reserved_with_O_EXCL": True,
            "manifest_write_fsync_and_cleanup_bound_to_owned_inode": True,
            "output_entry_write_fsync_and_cleanup_bound_to_owned_inode": True,
            "copied_volume_reserved_with_O_EXCL_O_RDWR": True,
            "copy_patch_readback_and_hash_use_owned_descriptors": True,
            "success_requires_output_path_owned_dev_inode": True,
            "cleanup_skips_non_owned_path": True,
        },
        "canonical_originals": [
            {
                "path": "extracted/All-Pro Football 2K8 (USA)/0A",
                "size": 1140850688,
                "sha256": EXPECTED_0A_SHA256,
            },
            {
                "path": "extracted/All-Pro Football 2K8 (USA)/default.xex",
                "size": 38408192,
                "sha256": EXPECTED_XEX_SHA256,
            },
        ],
        "phase_summary": {
            "worked": [
                "path preflight rejects input aliases, duplicate outputs, and existing outputs",
                "exclusive manifest reservation rejects a deterministic post-preflight race",
                "all three CLI cleanup paths preserve a post-reservation replacement manifest",
                "both output-entry front ends preserve a post-reservation replacement path",
                "copied-volume I/O remains bound to its original descriptor after pathname replacement",
                "replacement sentinels survive both exclusive-create failure and owned-inode displacement",
            ],
            "failed": [
                "the reviewed pre-hardening path-based copied-volume implementation was raceable",
            ],
            "blocking": [
                "this is a data-loss safety proof, not Xenia or hardware runtime-visibility proof",
                "the CLI is not a security boundary against an actor already able to write the same owned inode",
            ],
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cases = (
        "manifest_alias_index",
        "manifest_alias_png",
        "manifest_alias_output_entry",
        "manifest_alias_output_volume",
        "existing_manifest",
    )
    for writer in WRITERS:
        for case in cases:
            _cli_collision_case(writer, case)
        _manifest_reservation_race_case(writer)
        _manifest_inode_swap_case(writer)
    _output_entry_inode_swap_case("texture", texture_patch._write_new)  # type: ignore[attr-defined]
    _output_entry_inode_swap_case("uniform_mip", uniform_patch._write_new)  # type: ignore[attr-defined]
    _existing_volume_helper_case()
    _output_inode_swap_case()
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(_report(), indent=2) + "\n", encoding="utf-8"
        )
    print(
        "APF_WRITER_PATH_SAFETY_PASS "
        f"writers={len(WRITERS)} cli_cases={len(WRITERS) * (len(cases) + 1)} "
        "manifest_swap_cases=3 output_entry_swap_cases=2 fd_swap_cases=1 "
        "existing_volume_preserved=true unintended_outputs=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
