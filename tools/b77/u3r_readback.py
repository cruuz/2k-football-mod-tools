#!/usr/bin/env python3
"""Beta 77 u3r read-back: decode the redone socks from repaired packs, independently of the compile path.

  u3r_readback.py PACKS_DIR OUT_DIR COMPILED_DIR [KEY ...]

For every spec key (default all) it reads the kit package from the repaired pack files (the Studio's own pack reader),
decodes every texture with the repo's chunk decoder (``tools/b765/u1_audit.export_package``), and compares the decoded
``socks00`` / ``socks00_mud`` with the authored PNG in ``COMPILED_DIR/art``: size must be 64 x 64 and the mean absolute
RGB error at most 1.0 of 255. The kit's decoded textures are left in OUT_DIR/uniforms/<selector>/ for the renders.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b765"), str(ROOT / "tools/b77")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
import u1_audit  # noqa: E402
import u3s_alternates as ua  # noqa: E402
from nfl_txtr import decode_chunk, parse_chunks, texture_to_rgba  # noqa: E402


def sock_twins(package: bytes) -> dict[str, np.ndarray]:
    """socks00 and socks00_mud straight from chunk 4 (the exporter skips mud twins)."""
    chunk = next(c for c in parse_chunks(package) if c.index == 4)
    decoded, _ = decode_chunk(package, chunk)
    out = {}
    for i in (0, 1):
        texture = u1_audit.tset_texture(decoded, i)
        rgba = texture_to_rgba(decoded, chunk, texture)
        out[texture.name] = np.frombuffer(rgba, np.uint8).reshape(texture.height, texture.width, 4)
    return out


def kit_check(packs: Path, out: Path, art_root: Path, selectors: list[str]) -> int:
    """Authored kit art (``art_root/<selector>/*.png``) against the textures decoded from the repaired packs."""
    result = {}
    with bump._Image.open(packs, writable=False) as image:
        index = bump._parsed_index(image)
        by_id = {e.name_id: e for e in index.entries}
        for selector in selectors:
            entry = by_id[ua.name_id(selector + ".IFF")]
            data = b"".join(image.read_pack(o, off, n) for o, off, n in index.sub_extents(entry, 0, entry.size))
            u1_audit.export_package(data, {"selector": selector}, out)
            bad, good, worst = [], 0, 0.0
            for png in sorted((art_root / selector).glob("*.png")):
                got_path = out / "uniforms" / selector / png.name
                if not got_path.exists():
                    continue
                want = np.asarray(Image.open(png).convert("RGBA")).astype(int)
                got = np.asarray(Image.open(got_path).convert("RGBA")).astype(int)
                if want.shape != got.shape:
                    bad.append((png.name, "shape"))
                    continue
                m = want[..., 3] > 127
                mad = float(np.abs(want[..., :3] - got[..., :3])[m].mean()) if m.any() else 0.0
                worst = max(worst, mad)
                if mad < 14:
                    good += 1
                else:
                    bad.append((png.name, round(mad, 1)))
            result[selector] = {"checked_ok": good, "bad": bad, "worst_mad": round(worst, 2)}
            print(selector, result[selector])
    (out / "kit_check.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0 if all(not r["bad"] for r in result.values()) else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "kits":                       # kits PACKS OUT ART_ROOT SELECTOR ...
        return kit_check(Path(argv[1]), Path(argv[2]), Path(argv[3]), argv[4:])
    packs, out, compiled = Path(argv[0]), Path(argv[1]), Path(argv[2])
    spec = json.loads((ROOT / "data/nfl2k5_sock_redo_2026_u3r.json").read_text())["sets"]
    keys = argv[3:] or sorted(spec)
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    with bump._Image.open(packs, writable=False) as image:
        index = bump._parsed_index(image)
        by_id = {e.name_id: e for e in index.entries}
        for key in keys:
            selector = spec[key]["selector"]
            entry = by_id[ua.name_id(selector + ".IFF")]
            data = b"".join(image.read_pack(o, off, n) for o, off, n in index.sub_extents(entry, 0, entry.size))
            u1_audit.export_package(data, {"selector": selector}, out)
            row = {}
            twins = sock_twins(data)
            for name in ("socks00", "socks00_mud"):
                got = twins[name].astype(int)
                want = np.asarray(Image.open(compiled / "art" / f"{key.replace(':', '_')}_{name}.png").convert("RGBA")).astype(int)
                ok = got.shape == want.shape == (64, 64, 4)
                mad = float(np.abs(got[..., :3] - want[..., :3]).mean()) if ok else None
                row[name] = {"size": list(got.shape[1::-1]), "mad": mad, "ok": bool(ok and mad <= 1.0)}
            result[key] = row
            print(key, selector, row)
    (out / "readback.json").write_text(json.dumps(result, indent=1) + "\n")
    return 0 if all(v["ok"] for r in result.values() for v in r.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
