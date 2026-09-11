"""Original geometric number art with deliberate AI-like noise and soft edges."""
from __future__ import annotations
import random
from PIL import Image, ImageDraw, ImageFilter

FILL = (18, 38, 65)
OUTLINE = (208, 219, 224)
SEGMENTS = ("abcdef", "bc", "abged", "abgcd", "fgbc", "afgcd", "afgecd", "abc", "abcdefg", "abfgcd")


def ai_digit(digit: int) -> Image.Image:
    alpha = Image.new("L", (64, 64))
    fill = Image.new("L", (64, 64))
    positions = {"a": (9, 7, 55, 7), "g": (9, 32, 55, 32), "d": (9, 56, 55, 56),
                 "b": (56, 9, 56, 30), "c": (56, 34, 56, 54),
                 "f": (7, 9, 7, 30), "e": (7, 34, 7, 54)}
    for image, width in ((alpha, 13), (fill, 7)):
        draw = ImageDraw.Draw(image)
        for segment in SEGMENTS[digit]:
            draw.line(positions[segment], fill=255, width=width)
    box = alpha.getbbox()
    alpha = alpha.crop(box).resize((64, 64), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(0.85))
    fill = fill.crop(box).resize((64, 64), Image.Resampling.BILINEAR)
    rng = random.Random(6600 + digit)
    pixels = []
    for i, (a, f) in enumerate(zip(alpha.tobytes(), fill.tobytes())):
        colour = FILL if f >= 128 else OUTLINE
        rgb = tuple(max(0, min(255, c + rng.randrange(-4, 5) + (i % 64)//32)) for c in colour)
        pixels.append((*rgb, a))
    result = Image.new("RGBA", (64, 64)); result.putdata(pixels)
    return result


def ai_sheet(path, layout="horizontal"):
    columns, rows = {"horizontal": (10, 1), "vertical": (1, 10), "grid_5x2": (5, 2), "grid_2x5": (2, 5)}[layout]
    result = Image.new("RGBA", (columns*64, rows*64))
    for digit in range(10):
        result.paste(ai_digit(digit), (digit % columns*64, digit//columns*64))
    result.save(path)
    return path
