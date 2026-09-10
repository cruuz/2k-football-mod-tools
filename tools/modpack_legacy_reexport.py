"""Re-export the frozen beta-60/61 ADVANCED legacy packs with the tag exporters over the current package.

Mirrors tests/mod_editor/test_modpack_growth.py::LegacyPackTests exactly (base/expected construction),
loads modpack.py + modpack_ops.py from the receipts' source commits, exports with recipe=False, then
rewrites receipts.json for the two advanced entries. Run from the beta-65 worktree root.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "mod_editor"))

FIXTURES = ROOT / "tests/fixtures/modpack_legacy"
receipts = json.loads((FIXTURES / "receipts.json").read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag_package(commit: str) -> Path:
    """A copy of the current mod_editor package with the two exporter modules from ``commit``."""
    d = Path(tempfile.mkdtemp(prefix=f"legacy-exporter-{commit[:8]}-")).resolve()
    shutil.copytree(ROOT / "mod_editor", d / "mod_editor", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("modpack.py", "modpack_ops.py"):
        blob = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:mod_editor/core/{name}"],
                              capture_output=True, check=True).stdout
        (d / "mod_editor" / "core" / name).write_bytes(blob)
    return d


def main() -> None:
    from mod_editor.core import nfl2k5_depth_chart_storage as storage
    from mod_editor.core import nfl2k5_depth_chart_rows as rows
    from mod_editor.core import modpack as current_modpack
    from nfl2k5_depth_chart_rows_test import fixture, prepare
    from test_modpack import build_xdvdfs

    with patch.object(storage, "RETAIL_CONTENT_SHA256", hashlib.sha256(bytes(storage.RETAIL_SIZE)).hexdigest()):
        retail = fixture()
        special = bytes(rows.apply(prepare(retail))[0])
    updated = []
    for receipt in receipts:
        beta, preset = receipt["file"].removesuffix(".2k5patch").split("-")[1:]
        if preset != "advanced":
            continue
        commit = receipt["source_commit"]
        pkg = tag_package(commit)
        # import the tag exporter over the current package, isolated per commit
        for mod in [m for m in list(sys.modules) if m == "mod_editor" or m.startswith("mod_editor.")]:
            del sys.modules[mod]
        sys.path.insert(0, str(pkg))
        try:
            modpack = importlib.import_module("mod_editor.core.modpack")
            ops = importlib.import_module("mod_editor.core.modpack_ops")
            assert Path(modpack.__file__).resolve().is_relative_to(pkg), modpack.__file__
            storage_mod = importlib.import_module("mod_editor.core.nfl2k5_depth_chart_storage")
            with tempfile.TemporaryDirectory() as temp, patch.object(
                    storage_mod, "RETAIL_CONTENT_SHA256", hashlib.sha256(bytes(storage_mod.RETAIL_SIZE)).hexdigest()):
                root = Path(temp).resolve()
                base, expected = root / "base.iso", root / "expected.iso"
                base.write_bytes(build_xdvdfs({"default.xbe": retail, "next.bin": b"neighbour"}, tail_pad=19))
                shutil.copyfile(base, expected)
                with expected.open("r+b") as f:
                    storage_mod.write_image_xbe(f.fileno(), special)
                    modpack._pwrite_all(f.fileno(), f"beta-{beta} {preset}".encode(), 123, "fixture marker")
                pack = root / receipt["file"]
                meta = {"name": f"beta-{beta} {preset} synthetic", "author": "tests", "version": beta,
                        "description": "frozen synthetic legacy pack"}
                modpack.export(base, expected, pack, meta, recipe=False)
                check = modpack.check(pack, base)
                assert check["state"] == "ready", check
                result = root / "result.iso"
                modpack.apply(pack, base, result, overwrite=True)
                assert result.read_bytes() == expected.read_bytes(), "re-exported pack does not reproduce expected"
                shutil.copyfile(pack, FIXTURES / receipt["file"])
                receipt["base_size"] = base.stat().st_size
                receipt["result_size"] = expected.stat().st_size
                receipt["base_sha256"] = sha(base)
                receipt["result_sha256"] = sha(expected)
                receipt["pack_sha256"] = sha(FIXTURES / receipt["file"])
                receipt["regenerated"] = ("2026-09-10: same tag exporter, re-exported after the position-pools fixture gained the "
                                          "EDGE-only creation sites (Create Player cycle callbacks, the 51-record template table, the "
                                          "long-name table and the compacted trade-needs picker)")
                updated.append(receipt["file"])
                print("re-exported", receipt["file"], "commit", commit[:8], "pack", receipt["pack_sha256"][:12])
        finally:
            sys.path.remove(str(pkg))
            for mod in [m for m in list(sys.modules) if m == "mod_editor" or m.startswith("mod_editor.")]:
                del sys.modules[mod]
            shutil.rmtree(pkg, ignore_errors=True)
    (FIXTURES / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    print("receipts updated:", updated)


if __name__ == "__main__":
    main()
