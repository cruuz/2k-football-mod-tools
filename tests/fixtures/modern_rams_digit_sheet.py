"""Original geometric font fixture with Rams-style colours and a split stroke.

This is synthetic test art, not the official font or the tester's missing sheet.
"""
from PIL import Image, ImageDraw

SEGMENTS = ("abcdef", "bc", "abged", "abgcd", "fgbc", "afgcd", "afgecd", "abc", "abcdefg", "abfgcd")


def modern_rams_sheet(path, layout="horizontal"):
    columns, rows = {"horizontal": (10, 1), "grid_5x2": (5, 2)}[layout]
    sheet = Image.new("RGBA", (columns * 64, rows * 64))
    positions = {"a": (19, 9, 45, 9), "g": (19, 32, 45, 32), "d": (19, 55, 45, 55),
                 "b": (48, 12, 48, 29), "c": (48, 35, 48, 52),
                 "f": (16, 12, 16, 29), "e": (16, 35, 16, 52)}
    for digit in range(10):
        cell = Image.new("RGBA", (64, 64))
        draw = ImageDraw.Draw(cell)
        for width, colour in ((11, (0, 53, 148, 255)), (6, (255, 255, 255, 255))):
            for segment in SEGMENTS[digit]:
                draw.line(positions[segment], fill=colour, width=width)
        pixels = []
        for y in range(64):
            for x in range(64):
                r, g, b, alpha = cell.getpixel((x, y))
                if r == 255 and alpha:
                    r, g, b = 255, round(255 - y * .7), round(255 - y * 4)
                if 28 <= y <= 30:
                    alpha = 0
                pixels.append((r, g, b, alpha))
        cell.putdata(pixels)
        sheet.paste(cell, (digit % columns * 64, digit // columns * 64))
    sheet.save(path, "PNG")
    return path
