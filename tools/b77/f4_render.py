#!/usr/bin/env python3
"""Job F4 report art: strings drawn from real v0.5 data in the game's own fonts (these are NOT game captures).

Needs private inputs, all read only:

* the repaired ``default.xbe`` (``tools/b77/f4_repair.py`` output),
* the extracted v0.5 ``vc_53450030/0`` (for the roster),
* a hydrated worktree for the bitmap font atlases ``assets/intermediate/nfl2k5/fonts/<font>.png``, the glyph table
  ``reports/assets/nfl_main_menu_font_glyphs.tsv`` and the resource scan ``reports/assets/nfl2k5_resource_chunks_v2.json``,
* the retail volume folder ``vc_53450030`` (all volumes, for the ``geometry_font`` scene the Player Card number is drawn from).

Team ratings and overalls come from the real game routines under Unicorn (``tests/nfl2k5_supersim_draft_fixture.Machine``),
the grades from the owner module, the glyph advances from the executable's own glyph table (``.data 0xA90F18``) and the
glyph shapes from the game's own mesh data (decoded with the repo's scene tools). Layout, colours and scale are
illustrative: the screens themselves were not captured.

  f4_render.py --xbe default.xbe --pack0 vc_53450030/0 --hydrated /path/to/hydrated/worktree --out DIR
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_letter_grades as lg  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

DEFAULT_VOLUMES = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030")
GLYPH_TABLE_VA = 0x00A90F10        # 41 entries of 12 bytes: glyph node pointer, name pointer, advance width (float at +8)
GLYPH_NAMES = {"-": "minus", "+": "plus", ":": "colon", "$": "dollar", "'": "apostrophe"}


class Fonts:
    """The ten bitmap fonts: glyph advances and atlas crops, from the shipped glyph table and atlases."""

    def __init__(self, hydrated: Path):
        import csv
        from PIL import Image
        self.Image = Image
        self.table = {(r["font"], r["character"]): r for r in
                      csv.DictReader((hydrated / "reports/assets/nfl_main_menu_font_glyphs.tsv").open(encoding="utf-8"), delimiter="\t")}
        self.root = hydrated / "assets/intermediate/nfl2k5/fonts"
        self.atlas = {}

    def space(self, font: str) -> int:
        row = self.table.get((font, " "))
        return int(row["advance"]) if row else max(4, int(self.table[(font, "I")]["advance"]))

    def width(self, font: str, text: str) -> int:
        return sum(self.space(font) if ch == " " else int(self.table[(font, ch)]["advance"]) for ch in text)

    def draw(self, canvas, font: str, text: str, x: int, y: int, color=(255, 255, 255)) -> int:
        atlas = self.atlas.setdefault(font, self.Image.open(self.root / f"{font}.png").convert("RGBA"))
        pen = 0
        for ch in text:
            if ch == " ":
                pen += self.space(font)
                continue
            row = self.table[(font, ch)]
            box = tuple(int(row[k]) for k in ("atlas_x0", "atlas_y0", "atlas_x1", "atlas_y1"))
            crop = atlas.crop(box)
            tile = self.Image.new("RGBA", crop.size, color + (255,))
            tile.putalpha(crop.split()[3])
            canvas.alpha_composite(tile, (x + pen + int(row["x0"]), y + int(row["y0"])))
            pen += int(row["advance"])
        return x + pen


class Glyphs:
    """The Player Card's 3D digit and letter set (scene ``geometry_font``, outer 3 / chunk 51), drawn flat."""

    def __init__(self, payload: bytes, volumes: Path, scan: Path):
        from nfl_outer import parse_archive, read_entry_range
        from nfl_scene_probe import decode_resource, parse_inventory
        from nfl_scne_inventory import parse_scene
        import nfl_normshort3_positions as normshort3
        self.normshort3 = normshort3
        _, resources = parse_inventory(scan)
        resource = next(r for r in resources if r.kind == "SCNE" and (r.outer_index, r.chunk_index) == (3, 51))
        archive = parse_archive(volumes / "0")
        span = read_entry_range(archive, archive.entries[resource.outer_index], resource.chunk_offset, 0x20 + resource.stored_size)
        self.output, _ = decode_resource(span, resource)
        self.scene, _, _, _ = parse_scene(0, resource, self.output, {})
        if len(self.scene["shapes"]) != 41 or self.scene["name"] != "geometry_font":
            raise ValueError("the geometry_font scene changed")
        self.names = {shape["name"]: i for i, shape in enumerate(self.scene["shapes"])}
        image = XbeImage(payload)
        self.advances = [struct.unpack("<f", image.read(GLYPH_TABLE_VA + 12 * i + 8, 4))[0] for i in range(41)]

    @staticmethod
    def glyph_index(ch: str) -> int:
        """The drawer's own mapping (FUN_000F1F20 after the F4 patch): letters 0-25, digits 26-35, minus 38, plus 39."""
        if ch.isalpha():
            return ord(ch.upper()) - ord("A")
        if ch.isdigit():
            return 26 + int(ch)
        return {"-": 38, "+": 39}[ch]

    def _shape(self, ch: str) -> int:
        if ch.isalpha():
            return self.names[ch.upper()]
        if ch.isdigit():
            return self.names["number_" + ch]
        return self.names[GLYPH_NAMES[ch]]

    def _mesh(self, shape_index: int):
        from nfl_scne_gltf import decode_batches, gltf_topology
        shape = self.scene["shapes"][shape_index]
        record = int(shape["record_offset"])
        scale = struct.unpack_from("<f", self.output, record + 0x10)[0]
        offset = struct.unpack_from("<3f", self.output, record + 0x20)
        position = next(d for d in shape["attribute_descriptors"] if d["register"] == 0)
        stream = next(s for s in shape["vertex_streams"] if int(s["stream_index"]) == int(position["stream_index"]))
        points = []
        for v in range(int(shape["vertex_count"])):
            source = int(stream["offset"]) + v * int(stream["stride"]) + int(position["byte_offset"])
            points.append(self.normshort3.decode_position(struct.unpack_from("<3h", self.output, source), scale, offset))
        triangles = []
        for sub in [s for s in self.scene["submeshes"] if s["shape_index"] == shape_index]:
            for mode, indices in decode_batches(self.output, int(sub["command_offset"]), int(sub["primary_command_word_count"])):
                gl_mode, ind, _how = gltf_topology(mode, indices)
                if gl_mode == 4:
                    triangles += [tuple(ind[i:i + 3]) for i in range(0, len(ind) - 2, 3)]
                elif gl_mode == 5:
                    triangles += [(ind[i], ind[i + 1], ind[i + 2]) for i in range(len(ind) - 2)]
                elif gl_mode == 6:
                    triangles += [(ind[0], ind[i], ind[i + 1]) for i in range(1, len(ind) - 1)]
        return points, triangles

    def width(self, text: str) -> float:
        return sum(self.advances[self.glyph_index(c)] for c in text)

    def image(self, text: str, color=(220, 220, 220), scale: float = 1.0, ss: int = 4):
        from PIL import Image, ImageDraw
        height = 108.0                                           # the glyph meshes are 108 units tall
        canvas = Image.new("RGBA", (int(self.width(text) * scale * ss) + 4, int((height + 8) * scale * ss)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        x = 0.0
        for ch in text:
            points, triangles = self._mesh(self._shape(ch))
            for a, b, c in triangles:
                area = abs((points[b][0] - points[a][0]) * (points[c][1] - points[a][1])
                           - (points[c][0] - points[a][0]) * (points[b][1] - points[a][1]))
                if area < 0.5:                                   # degenerate strip joins
                    continue
                draw.polygon([((x + points[i][0]) * scale * ss, (height + 4 - points[i][1]) * scale * ss) for i in (a, b, c)],
                             fill=color + (255,))
            x += self.advances[self.glyph_index(ch)]
        return canvas.resize((max(1, canvas.width // ss), max(1, canvas.height // ss)), Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--pack0", type=Path, required=True)
    parser.add_argument("--hydrated", type=Path, required=True)
    parser.add_argument("--volumes", type=Path, default=DEFAULT_VOLUMES)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from PIL import Image
    from tests.nfl2k5_supersim_draft_fixture import Machine
    args.out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(args.hydrated)
    payload = args.xbe.read_bytes()
    if lg.status(payload) != "applied":
        parser.error("the executable must already carry the letter grades (run tools/b77/f4_repair.py first)")
    flags = getattr(os, "O_BINARY", 0)
    fd = os.open(args.pack0, os.O_RDONLY | flags)
    with os.fdopen(fd, "rb") as handle:
        head = handle.read(0x400)
        _name, size, blocks = struct.unpack_from("<3I", head, 0x9C + 5 * 12)
        handle.seek(blocks * 0x800)
        resource = handle.read(size)
    doc = rr.RosterDocument(resource[rr.RESOURCE_HEADER_SIZE:], base=0, source="v05", resource_header=resource[:rr.RESOURCE_HEADER_SIZE])
    machine = Machine(payload, trace_writes=False)
    machine.uc.mem_write(machine.ARENA + 0x300, bytes(doc.original))
    machine.fixup_roster(machine.ARENA + 0x340)
    player_at = machine.ARENA + 0x40000

    def overall(player) -> int:
        machine.uc.mem_write(player_at, player.record.encode())
        return machine.call(0xE6660, ecx=player_at, budget=200000)

    stub, team_a, fn_a, out_a = machine.STOP + 0x100, machine.ARENA + 0x1F0010, machine.ARENA + 0x1F0014, machine.ARENA + 0x1F0020
    machine.uc.mem_write(stub, b"\x8b\x0d" + struct.pack("<I", team_a) + b"\xff\x15" + struct.pack("<I", fn_a)
                         + b"\xd9\x1d" + struct.pack("<I", out_a) + b"\xc3")

    def team_rating(fn: int, team: int) -> int:
        machine.put(team_a, team)
        machine.put(fn_a, fn)
        machine.call(stub, budget=3000000)
        return int(min(100.0, struct.unpack("<f", bytes(machine.uc.mem_read(out_a, 4)))[0] * 100.0))

    abbreviations = [doc.teams[i].abbreviation for i in range(32)]
    teams = {abbr: machine.get(0xE5786C + 4 * i) for i, abbr in enumerate(abbreviations)}
    ratings = {abbr: [team_rating(fn, ptr) for fn in (0xC4830, 0xC4860, 0xC48A0)] for abbr, ptr in teams.items()}
    BG, PANEL, GOLD, GRAY, WHITE, GREEN = (22, 24, 30, 255), (38, 42, 52, 255), (192, 192, 0), (192, 192, 192), (240, 240, 240), (120, 230, 140)
    NOTE = "Text and glyphs from game data; layout illustrative (not a capture)."

    def pair(width, height, painter, name, note=""):
        image = Image.new("RGBA", (width * 2 + 30, height + 80), BG)
        fonts.draw(image, "font9", "BEFORE (numbers)", 10, 6, GRAY)
        fonts.draw(image, "font9", "AFTER (letter grades)", width + 40, 6, GREEN)
        for k, mode in enumerate(("num", "grade")):
            panel = Image.new("RGBA", (width, height), PANEL)
            painter(panel, mode)
            image.alpha_composite(panel, (10 + k * (width + 20), 28))
        if note:
            fonts.draw(image, "font9", note, 10, height + 34, GRAY)
        fonts.draw(image, "font9", NOTE, 10, height + 56, GRAY)
        image.save(args.out / f"{name}.png")

    show = lambda v, mode: str(v) if mode == "num" else lg.grade_for(v)       # noqa: E731
    scale = Image.new("RGBA", (520, 330), BG)
    fonts.draw(scale, "font9", "2K Player Grade System (Noah, 2026-10-07)", 12, 8, WHITE)
    for i, (rng, grade) in enumerate((("95+", "A+"), ("90-94", "A"), ("85-89", "B+"), ("80-84", "B"), ("75-79", "C+"), ("70-74", "C"),
                                      ("65-69", "D+"), ("60-64", "D"), ("55-59", "F+"), ("50-54", "F"), ("0-49", "F-"))):
        y = 34 + i * 26
        fonts.draw(scale, "font9", rng, 16, y, GRAY)
        fonts.draw(scale, "font9", "=", 90, y, GRAY)
        fonts.draw(scale, "font7", grade, 130, y - 2, GOLD)
        fonts.draw(scale, "font9", grade, 282, y, WHITE)
    scale.save(args.out / "f4_grade_scale.png")

    sample = ["KC", "SF", "BUF", "DAL", "PHI", "NYG"]

    def team_panel(panel, mode):                       # team select: every string in font slot 6 (atlas font7)
        for i, abbr in enumerate(sample):
            x, y = 10 + (i % 2) * 255, 10 + (i // 2) * 92
            fonts.draw(panel, "font7", abbr, x, y, GRAY)
            for j, (label, value) in enumerate(zip(("OFFENSE", "DEFENSE", "OVERALL"), ratings[abbr])):
                fonts.draw(panel, "font7", label, x, y + 22 + j * 22, GRAY)
                text = show(value, mode)
                fonts.draw(panel, "font7", text, x + 235 - fonts.width("font7", text), y + 22 + j * 22, GOLD)
    pair(520, 290, team_panel, "f4_team_select", "Six teams shown for illustration; all text is font slot 6 in the code.")

    team = "KC"
    index = abbreviations.index(team)
    rows = sorted(((overall(p), p) for p in doc.players if p.group == "team" and index in p.teams), key=lambda r: -r[0])[:14]

    def sheet(panel, mode):                            # spreadsheet list; the sheet style's font is not traced (stand-in font9)
        fonts.draw(panel, "font9", "Team Roster - " + doc.teams[index].nickname, 8, 6, WHITE)
        for x, label in ((10, "#"), (44, "NAME"), (190, "POS"), (250, "RTG")):
            fonts.draw(panel, "font9", label, x, 30, GRAY)
        for r, (value, p) in enumerate(rows):
            y = 52 + r * 22
            fonts.draw(panel, "font9", str(p.record.values["jersey"]), 10, y, WHITE)
            fonts.draw(panel, "font9", f"{p.first[0]}. {p.last}"[:18], 44, y, WHITE)
            fonts.draw(panel, "font9", p.record.position_name, 190, y, WHITE)
            text = show(value, mode)
            fonts.draw(panel, "font9", text, 285 - fonts.width("font9", text), y, GREEN if mode == "grade" else WHITE)
    pair(300, 370, sheet, "f4_team_roster_sheet", "Rows keep the order of the number; font is a stand-in.")

    value, star = rows[0]
    other_value = next(v for v, p in rows if lg.grade_for(v) != lg.grade_for(value))      # a second player with a different grade

    def other(panel, mode):                            # panels whose font comes from their caller: stand-in font9
        grade = show(value, mode)
        fonts.draw(panel, "font9", "Depth Chart panel", 8, 6, WHITE)
        fonts.draw(panel, "font9", "OVERALL", 12, 38, GRAY)
        fonts.draw(panel, "font9", grade, 120, 38, GOLD)
        fonts.draw(panel, "font9", "Contract panel", 8, 70, WHITE)
        fonts.draw(panel, "font9", f"Overall:{grade}", 12, 92, GOLD)
        fonts.draw(panel, "font9", "Trading Block sentence", 8, 124, WHITE)
        fonts.draw(panel, "font9", f"A QB with rating {show(80, mode)} or better.", 12, 146, GOLD)
        fonts.draw(panel, "font9", "Trading Block menu", 8, 182, WHITE)
        labels = ([lg.guideline_label(t) for t in lg.GUIDELINE_THRESHOLDS] if mode == "grade"
                  else [f"{t} or better" for t in lg.GUIDELINE_THRESHOLDS]) + ["any rating"]
        for i, label in enumerate(labels):
            fonts.draw(panel, "font9", label, 24, 206 + i * 20, WHITE)
    pair(300, 380, other, "f4_other_panels", "Font is a stand-in (panels take their font from the caller).")

    card_note = None
    try:
        glyphs = Glyphs(payload, args.volumes, args.hydrated / "reports/assets/nfl2k5_resource_chunks_v2.json")
    except (OSError, StopIteration, ValueError, KeyError) as error:
        glyphs, card_note = None, f"card glyph art skipped: {error}"
    if glyphs is not None:
        def card_panel(panel, mode):
            fonts.draw(panel, "font9", f"{star.first} {star.last}", 10, 8, WHITE)
            fonts.draw(panel, "font9", f"#{star.record.values['jersey']}  {star.record.position_name}", 10, 30, GRAY)
            fonts.draw(panel, "font9", "OVERALL", 12, 70, GRAY)
            art = glyphs.image(show(value, mode), color=GRAY, scale=0.75)
            panel.alpha_composite(art, ((panel.width - art.width) // 2, 100))
            fonts.draw(panel, "font9", "attribute bars stay numbers", 10, 238, GRAY)
        pair(300, 262, card_panel, "f4_player_card", "Number drawn from the game's 3D glyph meshes (geometry_font).")
        strip = Image.new("RGBA", (1180, 330), BG)
        fonts.draw(strip, "font9", "Every grade in the Player Card's own glyph meshes (A+ and A differ by the plus mesh); 100 is the retail look", 10, 6, GRAY)
        x = 12
        for row, labels in enumerate((("A+", "A", "B+", "B", "C+", "C"), ("D+", "D", "F+", "F", "F-", "100"))):
            x = 12
            for text in labels:
                art = glyphs.image(text, color=GRAY, scale=0.8)
                strip.alpha_composite(art, (x, 34 + row * 144))
                x += art.width + 40
        strip.save(args.out / "f4_card_glyphs.png")
        table = {t: [Glyphs.glyph_index(c) for c in t] for t in [g for _m, g in lg.DEFAULT_BANDS]}
    else:
        table = {}
    (args.out / "render_data.json").write_text(json.dumps(
        {"ratings": ratings, "roster_team": team, "card_note": card_note, "card_glyph_indices_by_grade": table,
         "roster_rows": [(v, f"{p.first} {p.last}", p.record.position_name, p.record.values["jersey"]) for v, p in rows]}, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print("rendered", sorted(os.listdir(args.out)))


if __name__ == "__main__":
    main()
