#!/usr/bin/env python3
"""b772-i3: write (or check) the reviewed modern-art PNG catalog the 2K5 release gate pins.

  python3 tools/b77/modern_art_png_catalog.py [--repo .] [--check]

The release gate (packaging/check_2k5_mod_studio_release.py) forbids every .png except exact reviewed files. The 2026
coaches (co1/co2), the 2026 fans (fr1) and the 2025-26 officials (rf1) ship authored PNG art under three data folders.
This tool lists every .png the release allowlist declares under those folders, records path, byte size, SHA-256 and
PNG dimensions, and writes packaging/nfl2k5_modern_art_pngs.json. It then prints the catalog's own SHA-256, which the
checker pins as MODERN_ART_PNG_CATALOG_SHA256 (change both together).

A file goes into the catalog only after it was reviewed as authored art: no photograph or crop of one, and no
retail-extracted pixels. Files that failed that review are listed in NOT_AUTHORED below with the reason; they stay out
of the catalog, so the release gate keeps refusing them until they are replaced or the decision changes. Each entry's
SHA-256 is pinned here, so a replaced file is reviewed again instead of inheriting the old verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

CATALOG = "packaging/nfl2k5_modern_art_pngs.json"
SCHEMA = "nfl2k5_modern_art_pngs/v1"
FOLDERS = ("data/nfl2k5_modern_coaches/", "data/nfl2k5_modern_fans/", "data/nfl2k5_modern_officials/",
           "data/nfl2k5_super_bowl_walls/", "data/nfl2k5_era_ball/", "data/nfl2k5_modern_venues_2026/numbers/",
           "data/nfl2k5_super_bowl_fields/",
           "data/nfl2k5_hair_styles/art/",  # b775-hs1
           "data/nfl2k5_glyph_fixes_2026/")  # b776-fn2 (int2)
CLASSIFICATION = ("Reviewed authored 2026/2025-26 art for the modern coaches (co1/co2), the modern fans (fr1) and the "
                  "modern officials (rf1), plus fa1 authored block yard numerals (fn1): painted textures, team marks and lettering at the native slot size. Coach "
                  "faces are painted from the official headshots onto the 2004 head layout (Noah 2026-10-12: authored "
                  "likeness textures ship, the reference photos never do). Coach Matchup pictures are supplied by the "
                  "external SOFTDRINK league project; no portrait PNG ships in these folders. The accessories atlas "
                  "ships only its authored headset half (headset.png); the shoe and clipboard come from the user's disc. "
                  "The Super Bowl event walls (me1, redesigned "
                  "by sb2) are drawn by tools/nfl2k5_super_bowl_walls_art.py from type, shapes and team colours with "
                  "an original event plate (no Super Bowl or broadcaster logo is copied); each surface's .marks.png "
                  "layer holds its authored slot marks, including the mod's own 2026 team logos "
                  "(data/nfl2k5_scorebug_assets/logos, as the modern fans use them) at slot size. The NFL shield is "
                  "added at build time (the mod's 2008 field shield, or the period shield from the user's disc), and "
                  "areas a surface keeps from the venue are transparent in the PNG and filled from the user's disc. "
                  "The modern game ball (me1) is drawn by tools/nfl2k5_era_ball_art.py: leather, laces, lettering "
                  "and a generic shield; its plain leather is taken from the user's disc ball at build time. "
                  "b77 cm1 repainted eighteen coach heads (WAS, DAL, CIN, CAR, GB, TEN, LAR, SF, MIN, NYJ, TB, MIA, DET, CLE, "
                  "NE, ATL, JAX, NYG) in 3D on the head mesh: one painted skin tone, painted hair and facial hair, and only "
                  "the fine feature detail of co2's authored faces. "
                  "b775 hs1's nine 64 x 64 hair textures (locs, twists, braids, strands, curls, bun) are drawn "
                  "procedurally by tools/nfl2k5_hair_styles_generate.py. "
                  "No photograph or photo crop and no "
                  "retail-extracted pixels are listed; retail details are taken from the user's own disc at build time."
                  " sb1's Super Bowl field flank marks (data/nfl2k5_super_bowl_fields/marks) are drawn by "
                  "tools/nfl2k5_super_bowl_marks_art.py from geometry, gradients and system type in each game's design "
                  "system (no logo is copied, traced or read); LXII to LXV are generic current-system marks for franchise "
                  "seasons whose logo is not revealed; the club marks of the three team-flank games are the mod's own 2026 "
                  "team logos at mark size or a plain club roundel."
                  " b776 fn2's four Titans 7 digit textures (data/nfl2k5_glyph_fixes_2026) are flat two-colour shapes drawn from "
                  "measurements of 2026 club photos (constant-width stem, block foot), not traced from a font file or photo pixels.")

# Reviewed by i3 on 2026-10-14 (contact sheets in the i3 scratch png_review/). Not authored art, so not catalogued.
# path or (folder, name) -> (SHA-256 of the reviewed bytes, reason). A different SHA-256 at the path needs a new review.
# pr2 removed both rejected rendered portraits. Real headshots live in the external league data.
# co3 replaced the 32 accessories atlases with authored headset halves; retail details come from the user's disc.
NOT_AUTHORED: dict[str, tuple[str, str]] = {}
NOT_AUTHORED_BY_NAME: dict[tuple[str, str], tuple[str, str]] = {}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_size(data: bytes, relative: str) -> tuple[int, int]:
    if len(data) < 24 or data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    return struct.unpack_from(">II", data, 16)


def declared_pngs(repo: Path) -> list[str]:
    out = []
    for line in (repo / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#") and entry.lower().endswith(".png") and entry.startswith(FOLDERS):
            out.append(entry)
    return sorted(set(out))


def excluded(relative: str, digest: str) -> str | None:
    """The review verdict for a file that is not authored art, or None. Refuses a changed file at a reviewed path."""
    row = NOT_AUTHORED.get(relative)
    if row is None:
        row = next((v for (folder, name), v in NOT_AUTHORED_BY_NAME.items()
                    if relative.startswith(folder) and relative.rsplit("/", 1)[-1] == name), None)
    if row is None:
        return None
    if row[0] != digest:
        raise SystemExit(f"{relative} changed since its review (was {row[0][:12]}, now {digest[:12]}): review it again")
    return row[1]


def build(repo: Path) -> tuple[dict, dict]:
    files, refused = {}, {}
    for relative in declared_pngs(repo):
        data = (repo / relative).read_bytes()
        width, height = png_size(data, relative)
        reason = excluded(relative, sha256(data))
        if reason is not None:
            refused[relative] = dict(sha256=sha256(data), size=len(data), reason=reason)
            continue
        files[relative] = dict(height=height, sha256=sha256(data), size=len(data), width=width)
    on_disk = sorted(p.relative_to(repo).as_posix() for folder in FOLDERS for p in (repo / folder).rglob("*.png"))
    undeclared = sorted(set(on_disk) - set(files) - set(refused))
    if undeclared:
        raise SystemExit("PNG files under the reviewed folders are not in the release allowlist: " + ", ".join(undeclared))
    return dict(classification=CLASSIFICATION, files=files, schema=SCHEMA), refused


def render(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--check", action="store_true", help="refuse when the committed catalog differs")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    document, refused = build(repo)
    data = render(document)
    target = repo / CATALOG
    stale = (target.read_bytes() if target.is_file() else b"") != data
    if not args.check:
        with open(target, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data.decode("utf-8"))
    by_folder = {}
    for relative in document["files"]:
        key = relative.split("/")[1]
        by_folder[key] = by_folder.get(key, 0) + 1
    print(json.dumps(dict(catalog=CATALOG, sha256=sha256(data), files=len(document["files"]), by_folder=by_folder,
                          not_catalogued=len(refused)), sort_keys=True))
    for relative, row in sorted(refused.items()):
        print(f"NOT_AUTHORED {relative} {row['sha256'][:12]} {row['reason']}")
    if args.check and stale:
        print("MODERN_ART_PNG_CATALOG_STALE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
