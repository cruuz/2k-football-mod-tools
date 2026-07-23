#!/usr/bin/env python3
"""Fast refusal-path tests for the donor-exact 49ers HOME pair writer."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nfl_uniform_color_xiso_direct_patch as common  # noqa: E402
import nfl_uniform_home_pair_donor_xiso_direct_patch as pair  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_refusal(source: Path, output: Path, manifest: Path, needle: str) -> None:
    try:
        pair.run(source, output, manifest)
    except (OSError, common.PatchError) as exc:
        require(needle in str(exc), f"unexpected refusal: {exc}")
        return
    raise AssertionError(f"writer unexpectedly accepted refusal case: {needle}")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    retail = root / "ESPN NFL 2K5 (USA).xiso.iso"
    require(retail.is_file(), "retail source missing")
    pair.validate_frozen_constants()

    with tempfile.TemporaryDirectory(prefix="nfl-home-pair-refusal-") as value:
        temp = Path(value)

        source_link = temp / "source-link.iso"
        source_link.symlink_to(retail)
        symlink_output = temp / "symlink-output.iso"
        symlink_manifest = temp / "symlink-manifest.json"
        expect_refusal(source_link, symlink_output, symlink_manifest,
                       "source pathname must not be a symbolic link")
        require(not symlink_output.exists() and not symlink_manifest.exists(),
                "source-symlink refusal left output")

        existing_output = temp / "existing-output.iso"
        existing_output.write_bytes(b"sentinel-output")
        output_manifest = temp / "output-manifest.json"
        expect_refusal(retail, existing_output, output_manifest,
                       "output already exists")
        require(existing_output.read_bytes() == b"sentinel-output" and
                not output_manifest.exists(), "existing output was modified")

        fresh_output = temp / "fresh-output.iso"
        existing_manifest = temp / "existing-manifest.json"
        existing_manifest.write_bytes(b"sentinel-manifest")
        expect_refusal(retail, fresh_output, existing_manifest,
                       "manifest already exists")
        require(not fresh_output.exists() and
                existing_manifest.read_bytes() == b"sentinel-manifest",
                "existing manifest refusal changed state")

        reserved = temp / "reserved.bin"
        owned = common.reserve_file(reserved)
        try:
            require(common.owned_path_matches(owned), "fresh O_EXCL inode not bound")
            expect_refusal(retail, reserved, temp / "reserved.json",
                           "output already exists")
        finally:
            os.close(owned.descriptor)

    print(
        "NFL_UNIFORM_HOME_PAIR_DONOR_XISO_DIRECT_PATCH_TEST_PASS "
        "constants=yes output_existing_refused=yes manifest_existing_refused=yes "
        "source_symlink_refused=yes o_excl_inode_bound=yes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
