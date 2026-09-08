"""Bounded 350-edit session benchmark. Run directly; no disc data is read.

--uncached reproduces the original strict decoder on every validation.
--profile adds cProfile instrumentation, whose overhead is substantial here.
Both modes retain all real session, PNG, project ZIP and Qt table operations.
Only original generation uses synthetic pixels and an existing test provider.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import pstats
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/mod_editor")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_team_kit_bundle import _PngAssetIO, _png
from mod_editor.core.nfl2k5_asset_io import Nfl2k5AssetIO, _replacement_decode_cache, png_codec
from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
from mod_editor.studio.session import StudioSession
from mod_editor.gui.studio_qt import StudioMainWindow
from PyQt5.QtWidgets import QApplication, QTreeWidget


class SyntheticSourceIO(_PngAssetIO):
    validate_replacement = staticmethod(Nfl2k5AssetIO.validate_replacement)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uncached", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    catalog = load_nfl2k5_uniform_catalog()
    results = {"uncached": args.uncached, "instrumented": args.profile, "replacements": 350}
    with tempfile.TemporaryDirectory(prefix="profile-team-kit-") as temporary:
        root = Path(temporary).resolve()
        cache = SimpleNamespace(source=SimpleNamespace(sha256="a" * 64), root=root / "cache")

        def session(name):
            with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", SyntheticSourceIO):
                value = StudioSession(cache, catalog, root=root / "sessions", session_id=name)
            value.visual_catalog = catalog
            return value

        seed = session("seed")
        targets = catalog.assets[:351]
        for asset in targets[:350]:
            digest = hashlib.sha256(("authored:" + asset.asset_id).encode()).digest()
            path = root / "supplied.png"
            path.write_bytes(_png(asset, (*digest[:3], 255)))
            seed.replace(asset, path)
        project = seed.save_shareable_project(root / "350.2k5mod")
        _replacement_decode_cache.clear()
        if args.uncached:
            decoder = png_codec.decode_rgba_png
        else:
            decoder = _replacement_decode_cache.decode
        with patch.object(_replacement_decode_cache, "decode", decoder):
            opened = session("opened")

            def measure(name, operation):
                profiler = cProfile.Profile() if args.profile else None
                start = time.perf_counter()
                if profiler is None:
                    operation()
                else:
                    profiler.runcall(operation)
                results[name] = time.perf_counter() - start
                print(f"{name}: {results[name]:.6f} s", flush=True)
                if profiler is not None:
                    output = io.StringIO()
                    pstats.Stats(profiler, stream=output).strip_dirs().sort_stats("cumtime").print_stats(15)
                    print(output.getvalue(), flush=True)

            measure("open_350", lambda: opened.load_shareable_project(project))
            asset = targets[350]
            path = root / "next.png"
            path.write_bytes(_png(asset, (70, 90, 200, 255)))
            measure("add_351", lambda: opened.replace(asset, path))
            tree = QTreeWidget()
            tree.setColumnCount(3)

            class Facade:
                @property
                def modified_asset_ids(self):
                    return opened.modified_asset_ids

            host = SimpleNamespace(uniform_catalog=catalog, facade=Facade(),
                                   component_tree=tree, _component_items={})
            measure("refresh_components", lambda: StudioMainWindow._populate_components(
                host, catalog.uniform_sets[0],
            ))
            measure("save_351", lambda: opened.save_shareable_project(root / "351.2k5mod"))
            measure("save_351_again", lambda: opened.save_shareable_project(root / "351-again.2k5mod"))
            assert opened.modified_count == 351
            results["cache_rgba_bytes"] = _replacement_decode_cache._size
            results["cache_entries"] = len(_replacement_decode_cache._rows)
            # resource is absent on Windows; timings remain portable there.
            try:
                import resource
            except ImportError:
                pass
            else:
                results["peak_rss_native_units"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            tree.close()
    print(json.dumps(results, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
