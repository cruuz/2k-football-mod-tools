"""Stage one product's release tree from its retail-free allowlist.

This is the same copy step ``.github/workflows/ci.yml`` performs before it runs
the release gates, factored out so a release can be built the same way by hand.
Only allowlisted paths are copied, so a file that is not declared cannot reach a
release tree by accident.

Some declared inputs -- the reviewed ``reports/assets/*.json`` catalogs and the
vendored ``extract-xiso`` binaries -- are deliberately gitignored release-build
inputs, so they are absent from a lean checkout. They are reported rather than
invented; the release gate is what fails closed on an incomplete tree.

Usage: stage_release.py <allowlist> <destination> [repo-root]
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys


def stage(allowlist: pathlib.Path, dest: pathlib.Path, root: pathlib.Path) -> int:
    staged = 0
    absent: list[str] = []
    for raw in allowlist.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        src = root / line
        if not src.exists():
            absent.append(line)
            continue
        out = dest / line
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        # Launchers and the vendored extractor must stay executable.
        if os.access(src, os.X_OK):
            os.chmod(out, os.stat(out).st_mode | 0o111)
        staged += 1
    print(f"staged {staged} files; {len(absent)} declared inputs absent from this checkout")
    for item in absent:
        print(f"  absent: {item}")
    return staged


if __name__ == "__main__":
    repo_root = (
        pathlib.Path(sys.argv[3])
        if len(sys.argv) > 3
        else pathlib.Path(__file__).resolve().parent.parent
    )
    stage(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), repo_root)
