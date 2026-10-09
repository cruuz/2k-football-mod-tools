#!/usr/bin/env python3
"""Beta 77 sh1: Team Select cards of the Seahawks' helmets, re-rendered from the corrected helmet art.

The unif and helm cards of a kit are pre-rendered images of the jersey, pants and the helmet's side; they carried the
old hawk (head toward the front). Same layout, cameras and light as the Patriots and all-teams jobs
(``tools/b77/u1_cards.py``, job k2's renderer), for any kit selector of the shell C helmet:

  sh1_cards.py export --source KITX_OUT/vc_53450030 --out CARDS_DIR 26H0 26A0 ...   # the shipped card textures
  sh1_cards.py render --art KIT_ART --helmet-master M4 --bars CARDS_DIR --shellc SHELLC.json --models MODELS --out OUT 26H0 ...

``--art``: the kit folders as exported (torso, sleeve, pants and digits of each selector). ``--helmet-master``: folders
``<sel>/helmet_helmet02.png`` (the corrected helmet at 4x or native). ``--bars``: the shipped helm cards, whose rows
from 158 down are the retail UI bar. Blender and the Studio's model exports are authoring inputs only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import u1_cards as C  # noqa: E402
from u1_cards import (BODY_HIDE, HEAD_HIDE, HELM_BAR_TOP, LAYOUT, M, SHELLC_PARTS, UV_SCALE, box_reduce,  # noqa: E402
                      saturate, torso_card, view)

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b765")]
CARD_FAMILIES = (("unif", 256), ("helm", 256), ("helm", 128))


def split_selector(selector: str) -> tuple[str, str, int]:
    return selector[:2], selector[2], int(selector[3:])


def export_cards(source: Path, index_source: Path, out: Path, selectors: list[str]) -> list[dict]:
    """The shipped card textures of ``selectors`` (outer 3102: unif/helm 256, outer 3105: helm 128), read only from
    ``source`` (an extracted vc_53450030 folder or an image); the index comes from ``index_source``."""
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    from nfl_txtr import HEADER, Chunk, decode_chunk, encode_rgba_png, parse_texture, texture_to_rgba
    wanted = {3102: set(), 3105: set()}
    for sel in selectors:
        code, side, style = split_selector(sel)
        for fam in ("unif", "helm"):
            wanted[3102].add(f"{fam}_{side.lower()}{code}_{style}")
        wanted[3105].add(f"helm_{side.lower()}{code}_{style}")
    rows = []
    (out / "cards").mkdir(parents=True, exist_ok=True)
    with bump._Image.open(index_source, writable=False) as ix_img:
        index = bump._parsed_index(ix_img)
        src_img = bump._Image.open(source, writable=False) if Path(source).is_dir() else ix_img
        try:
            for outer, names in wanted.items():
                entry = index.entries[outer]
                data = b"".join(src_img.read_pack(o, off, ln) for o, off, ln in index.sub_extents(entry, 0, entry.size))
                off, idx = 0, 0
                while off + HEADER.size <= len(data):
                    f = HEADER.unpack_from(data, off)
                    if f[0] == b"\0\0\0\0":
                        off += 16
                        continue
                    ch = Chunk(idx, off, f[0].decode("ascii"), *f[1:])
                    idx += 1
                    off = ch.end_offset
                    if ch.kind != "TXTR":
                        continue
                    dec, _ = decode_chunk(data, ch)
                    try:
                        tex = parse_texture(dec, ch)
                    except Exception:
                        continue
                    if tex.name in names:
                        rgba = texture_to_rgba(dec, ch, tex)
                        span = data[ch.offset:ch.end_offset]
                        png = f"{tex.name}_{tex.width}.png"
                        (out / "cards" / png).write_bytes(encode_rgba_png(tex.width, tex.height, rgba))
                        rows.append(dict(outer_index=outer, name=tex.name, width=tex.width, chunk_index=ch.index,
                                         chunk_offset=ch.offset, span_size=len(span),
                                         span_sha256=hashlib.sha256(span).hexdigest(), png=png))
        finally:
            if src_img is not ix_img:
                src_img.close()
    (out / "cards" / "cards.json").write_text(json.dumps(rows, indent=1), encoding="utf-8", newline="\n")
    return rows


def render(selectors: list[str], art: Path, helmet_master: Path, bars: Path, shellc: Path, models: Path, out: Path,
           facemask: str | dict = "00143F", number: str = "30") -> dict:
    """``facemask``: one colour (hex) for every kit, or {selector: hex} (the kit's facemask word, ``unif`` chunk)."""
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)
    items, plans = [], []
    for sel in selectors:
        a = art / sel
        tex = {"UNIF_jersey": torso_card(a / "torso.png", work / f"torso_card_{sel}.png"),
               "UNIF_sleeve": str(a / "sleeve.png"), "UNIF_pants": str(a / "pants.png")}
        helmet = str(helmet_master / sel / "helmet_helmet02.png")
        tex.update({k: helmet for k in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C")})
        for pos, digit in (("L", number[0]), ("R", number[1])):
            tex[f"NUMBER_{pos}"] = str(a / f"digit_jersey_{digit}.png")
            for sh in ("shoulder_A", "shoulder_B"):
                tex[f"NUMBER_{sh}_{pos}"] = str(a / f"digit_arm_{digit}.png")
        layers = {n: work / f"{sel}_{n}.png" for n in ("jersey", "pants", "helmet", "helm_card")}
        h = (facemask[sel] if isinstance(facemask, dict) else facemask).lstrip("#")[-6:]
        items.append({"tex": tex, "hide": ["NUMBER_M", "NUMBER_shoulder_A_M", "NUMBER_shoulder_B_M"] + BODY_HIDE + HEAD_HIDE,
                      "uv_scale": UV_SCALE, "facemask_rgb": [int(h[i:i + 2], 16) for i in (0, 2, 4)],
                      "facemask": "FACEMASK12", "shell": "C", "views": [view(n, sel[2], p) for n, p in layers.items()]})
        plans.append((sel, layers))
    job = {"head": str(models / "hi_head_o3c115.gltf"), "body": str(models / "hi_body_o3c114.gltf"),
           "arms_down": LAYOUT["arms_down"], "morphs": LAYOUT["morphs"],
           "replace_parts": C.native_shellc(shellc), "items": items}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=work) as handle:
        json.dump(job, handle)
        job_path = handle.name
    r = subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1", "-P", str(C.BLENDER_SCRIPT), "--", job_path],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"blender failed: {r.stdout[-2000:]}{r.stderr[-1000:]}")
    size, manifest, edits = 256 * M, {}, []
    for sel, layers in plans:
        code, side, style = split_selector(sel)
        mdir, ndir = out / "master4x" / sel, out / sel
        mdir.mkdir(parents=True, exist_ok=True)
        ndir.mkdir(parents=True, exist_ok=True)
        card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        for name in ("pants", "jersey", "helmet"):
            card = Image.alpha_composite(card, saturate(Image.open(layers[name])))
        card.save(mdir / "team-select_unif_256.png")
        box_reduce(card, 256).save(ndir / "team-select_unif_256.png")
        helm = np.asarray(saturate(Image.open(layers["helm_card"]))).copy()
        bar = np.asarray(Image.open(bars / "cards" / f"helm_{side.lower()}{code}_{style}_256.png").convert("RGBA")
                         .resize((size, size), Image.NEAREST))
        helm[HELM_BAR_TOP * M:] = bar[HELM_BAR_TOP * M:]
        hm = Image.fromarray(helm)
        hm.save(mdir / "team-select_helm_256.png")
        box_reduce(hm, 256).save(ndir / "team-select_helm_256.png")
        h128 = box_reduce(hm, 512)
        h128.save(mdir / "team-select_helm_128.png")
        box_reduce(h128, 128).save(ndir / "team-select_helm_128.png")
        manifest[sel] = [str(ndir / f"team-select_{k}.png") for k in ("unif_256", "helm_256", "helm_128")]
        for family, resolution in CARD_FAMILIES:
            edits.append({"kind": "team_select", "asset_code": code, "side": "home" if side == "H" else "away",
                          "style": style, "family": family, "resolution": resolution,
                          "png": str(ndir / f"team-select_{family}_{resolution}.png")})
    (out / "cards_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    (out / "card_edits.json").write_text(json.dumps(edits, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("export")
    s.add_argument("--source", type=Path, required=True)
    s.add_argument("--index-source", type=Path, required=True, help="image or folder whose pack 0 holds the index")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("selectors", nargs="+")
    s = sub.add_parser("render")
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--helmet-master", type=Path, required=True)
    s.add_argument("--bars", type=Path, required=True)
    s.add_argument("--shellc", type=Path, required=True)
    s.add_argument("--models", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--facemask", default="00143F", help="hex colour for every kit")
    s.add_argument("--facemask-for", action="append", default=[], metavar="SEL=HEX", help="per-kit facemask colour")
    s.add_argument("selectors", nargs="+")
    a = p.parse_args(argv)
    if a.command == "export":
        rows = export_cards(a.source, a.index_source, a.out, a.selectors)
        print(json.dumps({"cards": len(rows)}))
    else:
        mask = dict(pair.split("=", 1) for pair in a.facemask_for)
        render(a.selectors, a.art, a.helmet_master, a.bars, a.shellc, a.models, a.out,
               {sel: mask.get(sel, a.facemask) for sel in a.selectors})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
