#!/usr/bin/env python3
"""Render a video-ready APF franchise-code evidence/boundary card."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BG = "#0b1424"
PANEL = "#14233a"
TEXT = "#f5f7fb"
MUTED = "#a9bdd9"
ORANGE = "#ff7b32"
BLUE = "#4fb3ff"
GREEN = "#69d39c"
RED = "#ff7f7f"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def bullet(draw: ImageDraw.ImageDraw, x: int, y: int, lines: list[str], color: str) -> int:
    draw.ellipse((x, y + 8, x + 15, y + 23), fill=color)
    draw.text((x + 34, y), lines[0], font=font(24, True), fill=TEXT)
    for line in lines[1:]:
        y += 35
        draw.text((x + 34, y), line, font=font(21), fill=MUTED)
    return y + 62


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("schema") != "vc_apf_franchise_runtime_ownership/v1":
        raise ValueError("unexpected franchise ownership schema")
    scope = report["scope"]
    required = {
        "franchise_code_compiled_proved": True,
        "franchise_assets_only": False,
        "retail_season_old_franchise_gameplan_link_proved": True,
        "standalone_franchise_static_owner_proved": False,
        "half_finished_franchise_playable_proved": False,
    }
    if any(scope[key] is not value for key, value in required.items()):
        raise ValueError("validated franchise claim boundary changed")

    image = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(image)
    draw.text((82, 62), "APF 2K8 FRANCHISE CODE SURVIVED", font=font(53, True), fill=ORANGE)
    draw.text((82, 137), "NOT ASSETS-ONLY — NOT YET A PLAYABLE HIDDEN MODE",
              font=font(35, True), fill=TEXT)

    panels = [
        (76, 240, 626, 780, "COMPILED", GREEN),
        (685, 240, 1235, 780, "CONNECTED", BLUE),
        (1294, 240, 1844, 780, "SEVERED / UNPROVED", RED),
    ]
    for x0, y0, x1, y1, title, color in panels:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=PANEL)
        draw.text((x0 + 35, y0 + 32), title, font=font(28, True), fill=color)

    y = 320
    y = bullet(draw, 111, y, ["9 FranchiseMenu_* states", "Coach’s Desk, Weekly, Team Select…"], GREEN)
    y = bullet(draw, 111, y, ["Coach’s Desk initializer", "0x849DF2F0 → state stack push"], GREEN)
    bullet(draw, 111, y, ["Exact archive loaders", "franchise / Season / ESPN show"], GREEN)

    y = 320
    y = bullet(draw, 720, y, ["Retail Main → Season", "0x84E57408 → 0x820F4308"], BLUE)
    y = bullet(draw, 720, y, ["Season → old Gameplan", "0x84E55F10 → FranchiseMenu_CoachGameplan"], BLUE)
    bullet(draw, 720, y, ["Wrapup callbacks", "Own franchise_show + conditional franchise requests"], BLUE)

    y = 320
    y = bullet(draw, 1329, y, ["No Main-menu Franchise row", "Standalone route not found"], RED)
    y = bullet(draw, 1329, y, ["Initializer has no static owner", "0 callers · 0 non-PDATA pointers"], RED)
    bullet(draw, 1329, y, ["Wrapup root remains unowned", "Callback graph exact; retail entry unproved"], RED)

    draw.rounded_rectangle((76, 824, 1844, 987), radius=22, fill="#101e32")
    draw.text((112, 851), "RETAIL XEX STRING", font=font(22, True), fill=ORANGE)
    draw.text((112, 892),
              '“Congratulations for completing the All-Pro Football 2K8 franchise.”',
              font=font(31, True), fill=TEXT)
    draw.text((112, 944),
              "Exact presence proves APF adaptation; its retail display path is not proved.",
              font=font(21), fill=MUTED)

    draw.text((82, 1022),
              "Source: SHA-pinned retail default.xex · read-only Ghidra · exact addresses in machine report",
              font=font(20), fill="#7896bd")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="PNG", optimize=False)
    print(f"APF_FRANCHISE_RUNTIME_VIDEO_CARD_COMPLETE output={args.output} size=1920x1080")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
