#!/usr/bin/env python3
"""Beta 77 u3e: paint a 2026 alternate's textures with the team art tool, for ``u3s_alternates.py author --overlay``.

The art tool (``tools/nfl2k5_team_2026_art.py``) authors a whole kit from a spec (the same spec format as the teams'
2026 primary kits in ``data/nfl2k5_teams_2026/``). An alternate has the same needs, so its spec
(``data/nfl2k5_uniform_alt_specs_2026/<TEAM>_<style>.json``) is a small ``nfl2k5_team_2026/v1`` document whose ``kits``
name the slot's two sets (for example ``29H9`` and ``29A9``); the retail textures it reads are the slot's own v0.5
textures, exported by ``u3s_alternates.py export``. This wrapper

  1. lays the export out the way the art tool expects (set folders with the Team Select cards beside the textures,
     an equipment folder named ``tset_<outer>_<chunk>_<index>_<name>.png`` / ``p8_<outer>_<name>.png``),
  2. runs the art tool's own ``author`` on the spec, and
  3. copies the result into ``OVERLAY/<selector>/<file>.png`` under the export's file names (``nameplate`` is the
     export's ``names``; the art tool's cards and scope masks are not part of the overlay: the cards are rendered
     by ``u3s_alternates.py cards``, the mud twins come from the clean textures).

  u3e_paint.py --spec SPEC --export EXPORT --marks MARKS --uniform-marks MANIFEST --out OVERLAY [--work WORK]

Nothing retail is written to the repository; the overlay and the work folder stay in private scratch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import nfl2k5_team_2026_art as art  # noqa: E402

SPEC_SCHEMA = "nfl2k5_team_2026/v1"
CARD_NAMES = {"unif_256": "team-select_unif_256.png", "helm_256": "team-select_helm_256.png",
              "helm_128": "team-select_helm_128.png"}


def link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.symlink_to(src.resolve())


def lay_out(export: Path, work: Path) -> tuple[Path, Path, dict]:
    """The art tool's ``--retail`` and ``--equipment`` folders from a u3s export; returns them with each set's outer."""
    doc = json.loads((export / "export.json").read_text())
    retail, equipment = work / "retail", work / "equipment"
    outers = {}
    for selector, kit in doc["kits"].items():
        outers[selector] = kit["outer_index"]
        for asset in kit["assets"]:
            src = export / "uniforms" / selector / asset["file"]
            link(src, retail / selector / asset["file"])
            if asset["file"] == "names.png":
                link(src, retail / selector / "nameplate.png")       # the art tool's name for the export's names
            if asset["kind"] == "TSET" and asset["chunk"] >= 4:
                link(src, equipment / f"tset_{kit['outer_index']}_{asset['chunk']}_{asset['tset_index']}_{asset['name']}.png")
            elif asset["kind"] == "TXTR" and asset["file"] == "splayer.png":
                link(src, equipment / f"p8_{kit['outer_index']}_splayer.png")
        side = selector[2].lower()
        for card in doc.get("cards", []):
            code, style = selector[:2], selector[3:]
            if card["name"].endswith(f"{side}{code}_{style}"):
                family = card["name"].split("_")[0]
                key = f"{family}_{card['width']}"
                if key in CARD_NAMES:
                    link(export / "cards" / card["png"], retail / selector / CARD_NAMES[key])
    return retail, equipment, outers


def copy_regions(spec: dict, export: Path, out: Path) -> int:
    """``copy_regions`` of a kit ({"from": set, "files": [...], "box": [x0, y0, x1, y1]} in texture pixels): that box
    of the named set's shipped texture goes into the painted texture unchanged (the helmet's back plate keeps the
    2026 club's own lettering, which the retail slot does not have)."""
    from PIL import Image
    done = 0
    for kit in spec["kits"].values():
        for rule in kit.get("copy_regions", ()):
            x0, y0, x1, y1 = rule["box"]
            for name in rule["files"]:
                target = out / kit["selector"] / name
                donor = Image.open(export / "uniforms" / rule["from"] / name).convert("RGBA")
                base = Image.open(target).convert("RGBA")
                base.paste(donor.crop((x0, y0, x1, y1)), (x0, y0))
                base.save(target)
                done += 1
    return done


def modernize(spec: dict, export: Path, uniform_marks: Path, out: Path) -> int:
    """``modernize`` entries ({"selector", "donor", "swoosh": "#hex", "pants_swoosh": "#hex"}): the donor kit's torso,
    sleeve and pants with the 2026 league marks the retail art lacks: the NFL shield under the collar V, the maker's
    swoosh on both sleeves, the swoosh and shield on the pants (the same placements as the art tool's 2026 kits;
    the masters are the pinned official ones). Everything else of the donor is untouched."""
    art.use_uniform_marks(uniform_marks)
    M = art.MASTER
    count = 0
    for entry in spec.get("modernize", ()):
        base = export / "uniforms" / entry["donor"]
        dest = out / entry["selector"]
        dest.mkdir(parents=True, exist_ok=True)
        torso = art.upscale(art.load(base / "torso.png"))
        if entry.get("collar_shield", True):
            sh = art.COLLAR_SHIELD
            top = art.TORSO_V_TIP[1] + sh["gap_px"]
            art.place_mark(torso, "nfl_shield", (art.TORSO_V_TIP[0] * M, (top + sh["height_px"] / 2.0) * M),
                           sh["width_px"] * M, sh["height_px"] * M)
        for box in art.TORSO_SLEEVE_MARKS:
            if entry.get("clear_shoulder_marks", True):
                torso = art._clear_old_mark(torso, box)
        art.save(art.downscale(torso), dest / "torso.png")
        sleeve = art.upscale(art.load(base / "sleeve.png"))
        for arm in ("R", "L"):
            art.sleeve_swoosh(sleeve, art.rgb(entry["swoosh"]), arm)
        art.save(art.downscale(sleeve), dest / "sleeve.png")
        pants = art.upscale(art.load(base / "pants.png"))
        for box in (art.PANTS_SHIELD_BOX, art.PANTS_MAKER_BOX):
            pants = art._clear_old_mark(pants, box)
        ps, sh = art.PANTS_SWOOSH, art.PANTS_SHIELD
        art.place_mark(pants, "nike_swoosh", (ps["centre"][0] * M, ps["centre"][1] * M), ps["width_px"] * M,
                       ps["height_px"] * M, colour=art.rgb(entry["pants_swoosh"]))
        art.place_mark(pants, "nfl_shield", (sh["centre"][0] * M, sh["centre"][1] * M), sh["width_px"] * M,
                       sh["height_px"] * M)
        pants[..., 3] = 1.0
        art.save(art.downscale(pants), dest / "pants.png")
        count += 3
    return count


def paint(spec_path: Path, export: Path, marks: Path, uniform_marks: Path, out: Path, work: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    if spec.get("schema") != SPEC_SCHEMA:
        raise SystemExit(f"{spec_path}: expected schema {SPEC_SCHEMA}")
    work.mkdir(parents=True, exist_ok=True)
    retail, equipment, outers = lay_out(export, work)
    mod_count = modernize(spec, export, uniform_marks, out) if spec.get("modernize") else 0
    for kit in spec["kits"].values():
        if kit["selector"] not in outers:
            raise SystemExit(f"{kit['selector']} is not in the export; export it first")
        kit.setdefault("outer_index", outers[kit["selector"]])
        kit.setdefault("card", {"recolour": []})
        if kit.get("splayer") is not None:
            kit["splayer"].setdefault("torso_donor_outer", kit["outer_index"])
    if not spec["kits"]:
        return {"overlay_files": mod_count, "sets": sorted(e["selector"] for e in spec.get("modernize", ()))}
    resolved = work / "spec.json"
    resolved.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8", newline="\n")
    art_out = work / "art"
    if art_out.exists():
        shutil.rmtree(art_out)
    ns = argparse.Namespace(spec=str(resolved), retail=str(retail), marks=str(marks), uniform_marks=str(uniform_marks),
                            equipment=str(equipment), outer_home=0, outer_away=0, out=str(art_out))
    code = art.cmd_author(ns)
    if code:
        raise SystemExit(f"art tool author failed with {code}")
    count = 0
    for folder in sorted((art_out / "retail").iterdir()):
        dest = out / folder.name
        dest.mkdir(parents=True, exist_ok=True)
        for png in sorted(folder.glob("*.png")):
            name = png.name
            if name.startswith("team-select_") or name.endswith("_scope.png") or name.endswith("_mud.png"):
                continue
            if name == "nameplate.png":
                name = "names.png"
            shutil.copyfile(png, dest / name)
            count += 1
    count += copy_regions(spec, export, out) + mod_count
    # the 4x masters are kept beside the overlay for the helmet card renders and the report
    shutil.copytree(art_out / "master4x", out / "master4x", dirs_exist_ok=True)
    return {"overlay_files": count, "sets": sorted(p.name for p in (art_out / "retail").iterdir())}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--marks", type=Path, required=True)
    p.add_argument("--uniform-marks", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--work", type=Path, default=None)
    a = p.parse_args(argv)
    print(json.dumps(paint(a.spec, a.export, a.marks, a.uniform_marks, a.out, a.work or a.out.parent / (a.out.name + "_work"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
