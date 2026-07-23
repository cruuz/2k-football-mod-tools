#!/usr/bin/env python3
"""Render a video-ready card from the validated APF 2K6 lineage report."""

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


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    if report.get("schema") != "apf2k8_2k6_animation_lineage/v1":
        raise ValueError("unexpected lineage report schema")
    result = report["result"]
    if (result["apf_2k6_animation_identifier_count"],
            result["apf_2k6_pointer_reference_total"]) != (519, 597):
        raise ValueError("validated 2K6 counts changed")

    image = Image.new("RGB", (1920, 1080), BG)
    draw = ImageDraw.Draw(image)
    draw.text((82, 68), "RETAIL APF 2K8 EXECUTABLE", font=font(48, True), fill=ORANGE)
    draw.text((82, 142), "519 POINTER-BACKED ANIMATION IDS LITERALLY TAGGED 2K6",
              font=font(42, True), fill=TEXT)
    draw.text((82, 205), "Recovered from the shipped Xbox 360 default.xex",
              font=font(25), fill=MUTED)

    draw.rounded_rectangle((76, 275, 1190, 823), radius=22, fill=PANEL)
    draw.text((112, 307), "EXACT IDENTIFIERS", font=font(27, True), fill=BLUE)
    examples = [
        "ANM_BLOCK_2K6_PASS_LOW_B(0)",
        "ANM_2K6_QB_SCRAMBLE_MODE_START_F",
        "ANM_CATCH_2K6_RUN_SIDELINE_JUMP_L_0_2H",
        "ANM_BUMPANDRUN_JAM_L_FR_COVERED_EVEN_2K6(0)",
    ]
    y = 370
    for index, name in enumerate(examples, 1):
        draw.ellipse((112, y + 8, 128, y + 24), fill=ORANGE)
        draw.text((150, y), name, font=font(27, True), fill=TEXT)
        if index == 1:
            draw.text((150, y + 43), "string 0x84548A9C  →  pointer 0x84D7E6C4",
                      font=font(21), fill=MUTED)
            y += 106
        else:
            y += 91

    draw.text((112, 726), "Every pointer is an exact +0x04/+0x08 definition-name field.",
              font=font(24, True), fill=BLUE)
    draw.text((112, 766), "5,884 static records · 225 linked .ani filenames",
              font=font(23, True), fill=MUTED)

    draw.rounded_rectangle((1230, 275, 1844, 823), radius=22, fill=PANEL)
    draw.text((1270, 307), "ANNUAL IDENTIFIER LAYERS", font=font(27, True), fill=BLUE)
    counts = report["annual_tag_counts"]
    maximum = max(counts.values())
    y = 375
    for tag in ("2K3", "2K4", "2K5", "2K6", "2K7", "2K8"):
        count = counts[tag]
        draw.text((1270, y - 4), tag, font=font(25, True), fill=TEXT)
        draw.rounded_rectangle((1355, y, 1755, y + 30), radius=8, fill="#263b59")
        width = max(8, round(400 * count / maximum))
        draw.rounded_rectangle((1355, y, 1355 + width, y + 30), radius=8,
                               fill=ORANGE if tag == "2K6" else BLUE)
        draw.text((1773, y - 5), f"{count:,}", font=font(22, True), fill=TEXT)
        y += 70

    draw.text((82, 870), "WHAT THIS PROVES", font=font(25, True), fill=ORANGE)
    draw.text((82, 908), "A 2K6-era gameplay/animation generation survives inside APF’s compiled NFL code lineage.",
              font=font(29, True), fill=TEXT)
    draw.text((82, 968), "BOUNDARY: this is not yet an exact formal product/build ID for a complete game titled NFL 2K6.",
              font=font(23), fill=MUTED)
    draw.text((82, 1020), "Source: SHA-pinned retail XEX · 519 unique names · 597 aligned pointer references",
              font=font(20), fill="#7896bd")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="PNG", optimize=False)
    print(f"APF_2K6_VIDEO_CARD_COMPLETE output={args.output} size=1920x1080")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
