"""Small original geometric digits; no fonts, retail art or external downloads."""
from __future__ import annotations

from PIL import Image, ImageDraw

CASES = ("crisp", "soft_off_grid", "cell_62", "cell_66", "palette_png", "premultiplied_looking")
FILL = (235, 245, 255, 255)
OUTLINE = (45, 210, 40, 255)
SEGMENTS = ("abcdef", "bc", "abged", "abgcd", "fgbc", "afgcd", "afgecd", "abc", "abcdefg", "abfgcd")


def digit_image(digit: int, *, soft: bool = False, size: int = 64) -> Image.Image:
    scale = 4 if soft else 1
    image = Image.new("RGBA", (size * scale, size * scale))
    draw = ImageDraw.Draw(image)
    positions = {"a": (19, 9, 45, 9), "g": (19, 32, 45, 32), "d": (19, 55, 45, 55),
                 "b": (48, 12, 48, 29), "c": (48, 35, 48, 52),
                 "f": (16, 12, 16, 29), "e": (16, 35, 16, 52)}
    # A fractional offset makes the AA case deliberately miss the texel grid.
    shift = 1 if soft else 0
    for width, color in ((11, OUTLINE), (6, FILL)):
        for segment in SEGMENTS[digit]:
            coords = [round(v * scale * size / 64) + shift for v in positions[segment]]
            draw.line(coords, fill=color, width=round(width * scale * size / 64))
    if soft:
        # Author at 4x, then retain exact box coverage in a straight-alpha PNG.
        from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
        image = Image.frombytes("RGBA", (size, size), make_digit_mips(image.tobytes(), size * 4, size * 4, 3)[2].rgba)
    return image


def author_sheet(path, case: str, *, layout: str = "horizontal"):
    cell = 62 if case in ("cell_62", "double_resampled62") else 66 if case == "cell_66" else 64
    columns, rows = {"horizontal": (10, 1), "vertical": (1, 10),
                     "grid_5x2": (5, 2), "grid_2x5": (2, 5)}[layout]
    sheet = Image.new("RGBA", (columns * cell, rows * cell))
    for digit in range(10):
        image = digit_image(digit, soft=case in ("soft_off_grid", "premultiplied_looking"),
                            size=64 if case == "double_resampled62" else cell)
        if case == "double_resampled62":
            image = image.resize((cell, cell), Image.Resampling.BICUBIC)
        if case == "premultiplied_looking":
            # Deliberately store darkened RGB as if an artist exported the wrong
            # alpha convention. The importer must not guess/unpremultiply it.
            data = bytearray(image.tobytes())
            for i in range(0, len(data), 4):
                for ch in range(3):
                    data[i + ch] = (data[i + ch] * data[i + 3] + 127) // 255
            image = Image.frombytes("RGBA", image.size, bytes(data))
        sheet.paste(image, (digit % columns * cell, digit // columns * cell))
    if case == "palette_png":
        palette = [(0, 0, 0, 0), OUTLINE, FILL]
        indexed = Image.new("P", sheet.size)
        indexed.putpalette([ch for c in palette for ch in c[:3]] + [0] * (768 - 9))
        lookup = {c: i for i, c in enumerate(palette)}
        indexed.putdata([lookup[c] for c in sheet.getdata()])
        indexed.info["transparency"] = bytes(c[3] for c in palette)
        sheet = indexed
    sheet.save(path, format="PNG")
    return path
