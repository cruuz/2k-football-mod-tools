#!/usr/bin/env python3
"""Generate the two editors' application icons from geometry, not from art files.

Both marks are the same object -- a dark navy plate carrying the product's
scoreboard number in the accent colour that product already uses for its sidebar
badge -- so the two editors read as siblings while the hue and the trailing digit
tell them apart at a glance.  Every colour here is lifted from the running UI
(``mod_editor/gui/studio_qt.py`` and ``mod_editor/apf_studio/gui.py``) rather than
invented, which is why the icon matches the window it opens.

Two things drive the implementation:

* **Determinism.**  A release gate pins these bytes by SHA-256, so a rebuild that
  produced a different file would be indistinguishable from tampering.  Nothing
  here reads the clock, the environment, or a random source, and Pillow writes no
  timestamp chunks, so re-running this script overwrites each file with the bytes
  it already had.
* **Small sizes are drawn, not shrunk.**  Blindly downscaling the 512 px plate
  gives 16 px under four pixels of width per glyph, which closes every counter
  and smears the K's diagonals into a grey blob.  Sizes up to 32 px therefore get
  hand-set geometry in whole device pixels (see ``DRAWN_TIERS``), and 16 px goes
  further and drops the K entirely -- the digits are all axis-aligned bars and
  stay crisp, where the K has no horizontal run left to resolve in.

Usage:
    make_app_icons.py [--out-root DIR] [--check] [--print-pins]

``--check`` regenerates into a temporary tree and reports whether the committed
assets already match, which is what a CI job wants; it writes nothing.
``--print-pins`` emits the size/SHA-256 rows the two release gates declare.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import io
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]

# Emitted raster sizes.  16 and 24 are the two that actually decide whether the
# icon works, because that is what a title bar and a taskbar hand it.
PNG_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)
# Windows reads the .ico for the shortcut and the installer chrome.  512 is left
# out: no Windows surface asks for it and it would double the file for nothing.
ICO_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)


@dataclass(frozen=True)
class Product:
    """One editor's icon identity."""

    slug: str
    title: str
    #: Full wordmark, used from 24 px up.
    wordmark: str
    #: Two-glyph reduction for the 16 px plate.
    compact: str
    #: The sidebar brand-badge colour from that product's stylesheet.
    accent: tuple[int, int, int]
    description: str


PRODUCTS: tuple[Product, ...] = (
    Product(
        slug="2k5-mod-studio",
        title="2K5 Mod Studio",
        wordmark="2K5",
        compact="25",
        # QLabel#brandMark background in mod_editor/gui/studio_qt.py.
        accent=(0x32, 0xD5, 0xC6),
        description="2K5 in teal on the studio's navy plate.",
    ),
    Product(
        slug="apf2k8-mod-studio",
        title="APF 2K8 Mod Studio",
        wordmark="2K8",
        compact="28",
        # QLabel#brandMark background in mod_editor/apf_studio/gui.py.
        accent=(0xF0, 0x8A, 0x4B),
        description="2K8 in orange on the studio's navy plate.",
    ),
)

# The plate is the products' shared chrome: #101827/#0f1827 sidebar over the
# #0c1220/#0b111c workspace, opened into a diagonal ramp so the tile has a light
# source instead of reading as a flat swatch.
PLATE_TOP = (0x17, 0x26, 0x3E)
PLATE_BOTTOM = (0x0A, 0x11, 0x1D)
# Sidebar border colour (#253249 / #26344a), used to keep the plate's edge from
# dissolving into a dark desktop before the accent keyline is drawn over it.
PLATE_EDGE = (0x25, 0x32, 0x49)

CORNER_RADIUS = 0.215  # of the tile edge

# Wordmark metrics as multiples of cap height, so the drawn tiers below and the
# solved tier above stay the same typeface rather than merely the same letters.
# The widths are not uniform for a reason: the 8's two counters are the first
# thing to close up, and the K needs horizontal run or its arms leave no notch
# between them and it stops reading as a K at all.
GLYPH_WIDTH = {"2": 0.58, "K": 0.68, "5": 0.58, "8": 0.62}
GLYPH_TRACKING = 0.20
STROKE = 0.205
# The wordmark sits above centre and this rule takes the space underneath, the
# way a scoreboard number sits over its yard line.  Only the solved tier draws
# it: at 32 px and below the two or three rows it would cost are worth more as
# cap height, so those plates centre the wordmark instead.
UNDERLINE_THICKNESS = 0.135
UNDERLINE_GAP = 0.32
UNDERLINE_WIDTH = 0.78  # of the wordmark's own width


def _supersample(size: int) -> int:
    """Pick a scale factor that keeps the working canvas near 2k pixels square."""
    if size <= 256:
        return 8
    return 4


# ---------------------------------------------------------------------------
# Glyphs
#
# Each glyph is a set of axis-aligned bars plus, for K, two arms.  Bars beat
# outlines here: a bar has one thickness that survives being scaled to nine
# pixels tall, where a drawn outline would lose its thin side entirely.
# ---------------------------------------------------------------------------


def _glyph_parts(
    char: str, x: float, y: float, w: float, h: float, t: float
) -> list[tuple]:
    """Return draw primitives for *char* inside the box at (x, y, w, h).

    Primitives are ``("rect", x0, y0, x1, y1)`` or ``("poly", [(x, y), ...])``.
    """
    mid_y0 = y + (h - t) / 2.0
    mid_y1 = mid_y0 + t
    top = ("rect", x, y, x + w, y + t)
    bottom = ("rect", x, y + h - t, x + w, y + h)
    middle = ("rect", x, mid_y0, x + w, mid_y1)
    left_upper = ("rect", x, y, x + t, mid_y1)
    right_upper = ("rect", x + w - t, y, x + w, mid_y1)
    left_lower = ("rect", x, mid_y0, x + t, y + h)
    right_lower = ("rect", x + w - t, mid_y0, x + w, y + h)

    if char == "2":
        return [top, right_upper, middle, left_lower, bottom]
    if char == "5":
        return [top, left_upper, middle, right_lower, bottom]
    if char == "8":
        return [top, left_upper, right_upper, middle, left_lower, right_lower, bottom]
    if char == "K":
        # Both arms are stroked to the same thickness ``t`` as the bars, then
        # cut vertically so their terminals match a bar's flat end.  A cut like
        # that spans ``t * length / run`` vertically, which is where the two
        # ratios below come from; measuring the arm vertically instead would
        # leave it visibly thinner than the 5 standing next to it.
        stem = ("rect", x, y, x + t, y + h)
        joint_y = y + h * 0.52
        arm_x = x + t * 0.70
        tip_x = x + w
        run = tip_x - arm_x
        upper_v = t * math.hypot(run, joint_y - y) / run
        lower_v = t * math.hypot(run, y + h - joint_y) / run
        upper = (
            "poly",
            [
                (arm_x, joint_y),
                (arm_x, joint_y - upper_v),
                (tip_x, y),
                (tip_x, y + upper_v),
            ],
        )
        lower = (
            "poly",
            [
                (arm_x, joint_y),
                (arm_x, joint_y + lower_v),
                (tip_x, y + h),
                (tip_x, y + h - lower_v),
            ],
        )
        return [stem, upper, lower]
    raise ValueError(f"no glyph for {char!r}")


@dataclass(frozen=True)
class Plan:
    """Device-pixel geometry for one plate, resolved before supersampling."""

    size: int
    text: str
    cap: float
    stroke: float
    tracking: float
    widths: dict[str, float]
    keyline: float
    underline: bool

    @property
    def wordmark_width(self) -> float:
        return (
            sum(self.widths[char] for char in self.text)
            + (len(self.text) - 1) * self.tracking
        )


# Hand-drawn tiers.  Below 48 px the solved metrics land on fractional strokes,
# and a 2.4-pixel bar is a 2-pixel bar wearing a grey fringe -- the exact mush
# that makes a shrunk icon unreadable.  These rows are therefore stated in whole
# device pixels instead of derived, and 16 goes further and drops the K: at five
# pixels of width its diagonals have no run to resolve in, while the digits stay
# perfectly crisp because every stroke in them is axis-aligned.
DRAWN_TIERS: dict[int, dict] = {
    16: {
        "compact": True,
        "cap": 10,
        "stroke": 2,
        "tracking": 1,
        "widths": {"2": 5, "K": 5, "5": 6, "8": 6},
        "keyline": 1,
    },
    24: {
        "compact": False,
        "cap": 12,
        "stroke": 2,
        "tracking": 2,
        "widths": {"2": 5, "K": 5, "5": 5, "8": 6},
        "keyline": 1,
    },
    32: {
        "compact": False,
        "cap": 15,
        "stroke": 3,
        "tracking": 2,
        "widths": {"2": 7, "K": 8, "5": 7, "8": 8},
        "keyline": 1,
    },
}


def _plan(product: Product, size: int) -> Plan:
    """Resolve the layout for one plate."""
    drawn = DRAWN_TIERS.get(size)
    if drawn is not None:
        text = product.compact if drawn["compact"] else product.wordmark
        return Plan(
            size=size,
            text=text,
            cap=float(drawn["cap"]),
            stroke=float(drawn["stroke"]),
            tracking=float(drawn["tracking"]),
            widths={char: float(drawn["widths"][char]) for char in drawn["widths"]},
            keyline=float(drawn["keyline"]),
            underline=False,
        )

    text = product.wordmark
    margin = size * 0.10
    available = size - 2 * margin
    span = sum(GLYPH_WIDTH[char] for char in text) + (len(text) - 1) * GLYPH_TRACKING
    cap = available / span
    return Plan(
        size=size,
        text=text,
        cap=cap,
        stroke=STROKE * cap,
        tracking=GLYPH_TRACKING * cap,
        widths={char: GLYPH_WIDTH[char] * cap for char in GLYPH_WIDTH},
        keyline=max(1.0, round(size / 24.0)),
        underline=True,
    )


def _origin(plan: Plan) -> tuple[float, float]:
    """Centre the wordmark block, snapping to whole pixels on the drawn tiers."""
    block_h = plan.cap
    if plan.underline:
        block_h += (UNDERLINE_GAP + UNDERLINE_THICKNESS) * plan.cap
    x = (plan.size - plan.wordmark_width) / 2.0
    y = (plan.size - block_h) / 2.0
    if plan.size in DRAWN_TIERS:
        return round(x), round(y)
    return x, y


def _diagonal_plate(edge: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """A corner-to-corner linear ramp between two colours.

    Built at 64x64 and resized: the ramp is smooth by construction, so sampling
    it densely would cost time without changing a pixel of the result.
    """
    ramp = Image.new("L", (64, 64))
    pixels = ramp.load()
    for y in range(64):
        for x in range(64):
            pixels[x, y] = round(255 * (1.0 - (x + y) / 126.0))
    ramp = ramp.resize((edge, edge), Image.BICUBIC)
    return Image.composite(
        Image.new("RGB", (edge, edge), top),
        Image.new("RGB", (edge, edge), bottom),
        ramp,
    )


def _dim(colour: tuple[int, int, int], toward: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(c + (t - c) * amount) for c, t in zip(colour, toward))  # type: ignore[return-value]


def render(product: Product, size: int) -> Image.Image:
    """Render one plate at *size* device pixels."""
    scale = _supersample(size)
    edge = size * scale
    plan = _plan(product, size)

    canvas = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))

    # 1. The plate itself: a rounded square filled with the navy ramp.
    radius = CORNER_RADIUS * edge
    mask = Image.new("L", (edge, edge), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, edge - 1, edge - 1), radius=radius, fill=255
    )
    canvas.paste(_diagonal_plate(edge, PLATE_TOP, PLATE_BOTTOM), (0, 0), mask)

    # 2. Keyline.  A navy tile on a dark desktop has no silhouette; a hairline of
    #    the accent gives the icon an outline that also states which editor it is
    #    before any glyph is resolvable.
    keyline = plan.keyline * scale
    outline = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
    draw = ImageDraw.Draw(outline)
    draw.rounded_rectangle(
        (keyline / 2, keyline / 2, edge - 1 - keyline / 2, edge - 1 - keyline / 2),
        radius=max(1.0, radius - keyline / 2),
        outline=(*_dim(product.accent, PLATE_EDGE, 0.34), 255),
        width=int(round(keyline)),
    )
    canvas.alpha_composite(outline)

    # 3. Wordmark.
    ink = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
    pen = ImageDraw.Draw(ink)
    accent = (*product.accent, 255)
    origin_x, origin_y = _origin(plan)
    cursor = origin_x
    for char in plan.text:
        width = plan.widths[char]
        for part in _glyph_parts(char, cursor, origin_y, width, plan.cap, plan.stroke):
            if part[0] == "rect":
                _, x0, y0, x1, y1 = part
                pen.rectangle(
                    (x0 * scale, y0 * scale, x1 * scale - 1, y1 * scale - 1), fill=accent
                )
            else:
                pen.polygon([(px * scale, py * scale) for px, py in part[1]], fill=accent)
        cursor += width + plan.tracking

    # 4. The rule under the wordmark, dimmed so it supports the number instead of
    #    competing with it.  Dropped on the drawn tiers, where the vertical space
    #    it needs is worth more as cap height.
    if plan.underline:
        width = plan.wordmark_width * UNDERLINE_WIDTH
        thickness = UNDERLINE_THICKNESS * plan.cap
        y0 = origin_y + plan.cap + UNDERLINE_GAP * plan.cap
        x0 = (size - width) / 2.0
        pen.rounded_rectangle(
            (
                x0 * scale,
                y0 * scale,
                (x0 + width) * scale - 1,
                (y0 + thickness) * scale - 1,
            ),
            radius=thickness * scale / 2.0,
            fill=(*_dim(product.accent, PLATE_BOTTOM, 0.42), 255),
        )

    canvas.alpha_composite(ink)

    # Area-average downsampling.  The source is flat vector fill, so BOX is the
    # exact answer; LANCZOS would add ringing to edges that were already right.
    return canvas.resize((size, size), Image.BOX)


# ---------------------------------------------------------------------------
# SVG (the Linux icon theme's scalable entry)
# ---------------------------------------------------------------------------


def _svg_rect(x0: float, y0: float, x1: float, y1: float) -> str:
    return f'M{x0:.2f} {y0:.2f}H{x1:.2f}V{y1:.2f}H{x0:.2f}Z'


def _svg_poly(points: Sequence[tuple[float, float]]) -> str:
    head = f'M{points[0][0]:.2f} {points[0][1]:.2f}'
    rest = "".join(f'L{x:.2f} {y:.2f}' for x, y in points[1:])
    return head + rest + "Z"


def render_svg(product: Product, edge: int = 512) -> str:
    """Emit the same plate as scalable vector art.

    The Linux desktop entry resolves ``Icon=`` through the hicolor theme, whose
    scalable slot takes SVG; keeping it generated from the same geometry is what
    stops the packaged icon and the window icon from drifting apart.
    """
    plan = _plan(product, edge)
    cap = plan.cap
    radius = CORNER_RADIUS * edge
    keyline = plan.keyline
    origin_x, origin_y = _origin(plan)

    paths: list[str] = []
    cursor = origin_x
    for char in plan.text:
        width = plan.widths[char]
        for part in _glyph_parts(char, cursor, origin_y, width, cap, plan.stroke):
            if part[0] == "rect":
                paths.append(_svg_rect(*part[1:]))
            else:
                paths.append(_svg_poly(part[1]))
        cursor += width + plan.tracking

    under_w = plan.wordmark_width * UNDERLINE_WIDTH
    under_t = UNDERLINE_THICKNESS * cap
    under_x = (edge - under_w) / 2.0
    under_y = origin_y + cap + UNDERLINE_GAP * cap

    accent = "#%02x%02x%02x" % product.accent
    keyline_colour = "#%02x%02x%02x" % _dim(product.accent, PLATE_EDGE, 0.34)
    under_colour = "#%02x%02x%02x" % _dim(product.accent, PLATE_BOTTOM, 0.42)
    top = "#%02x%02x%02x" % PLATE_TOP
    bottom = "#%02x%02x%02x" % PLATE_BOTTOM

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by tools/make_app_icons.py; do not hand-edit. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {edge} {edge}" width="{edge}" height="{edge}" role="img" aria-labelledby="title desc">
  <title id="title">{product.title}</title>
  <desc id="desc">{product.description}</desc>
  <defs>
    <linearGradient id="plate" x1="0" y1="0" x2="{edge}" y2="{edge}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="{top}"/>
      <stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{edge}" height="{edge}" rx="{radius:.2f}" fill="url(#plate)"/>
  <rect x="{keyline / 2:.2f}" y="{keyline / 2:.2f}" width="{edge - keyline:.2f}" height="{edge - keyline:.2f}" rx="{radius - keyline / 2:.2f}" fill="none" stroke="{keyline_colour}" stroke-width="{keyline:.2f}"/>
  <path fill="{accent}" d="{' '.join(paths)}"/>
  <rect x="{under_x:.2f}" y="{under_y:.2f}" width="{under_w:.2f}" height="{under_t:.2f}" rx="{under_t / 2:.2f}" fill="{under_colour}"/>
</svg>
"""


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def _write_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    # optimize= is deliberate and compress_level is pinned: both feed the zlib
    # settings, and leaving them to the default would tie the committed bytes to
    # whatever Pillow ships next.
    image.save(buffer, format="PNG", optimize=True, compress_level=9)
    path.write_bytes(buffer.getvalue())


def _write_ico(images: dict[int, Image.Image], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [images[size] for size in sorted(ICO_SIZES)]
    buffer = io.BytesIO()
    ordered[-1].save(
        buffer,
        format="ICO",
        sizes=[(size, size) for size in sorted(ICO_SIZES)],
        append_images=ordered[:-1],
    )
    path.write_bytes(buffer.getvalue())


def emit(product: Product, out_root: Path) -> list[Path]:
    """Write every asset for one product; return the paths in emission order."""
    icons = out_root / "packaging" / "icons"
    written: list[Path] = []
    rendered: dict[int, Image.Image] = {}
    for size in PNG_SIZES:
        rendered[size] = render(product, size)
        target = icons / f"{product.slug}-{size}.png"
        _write_png(rendered[size], target)
        written.append(target)
    ico = icons / f"{product.slug}.ico"
    _write_ico(rendered, ico)
    written.append(ico)
    svg = out_root / "packaging" / f"{product.slug}.svg"
    svg.parent.mkdir(parents=True, exist_ok=True)
    # newline= is not optional: Windows text mode would turn every \n into
    # \r\n, and the release gate pins this file by size and SHA-256.
    svg.write_text(render_svg(product), encoding="utf-8", newline="\n")
    written.append(svg)
    return written


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate into a temporary tree and diff against the committed assets",
    )
    parser.add_argument(
        "--print-pins",
        action="store_true",
        help="print the size/SHA-256 pins the release gates declare",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check:
        with tempfile.TemporaryDirectory() as scratch:
            scratch_root = Path(scratch)
            stale: list[str] = []
            for product in PRODUCTS:
                for fresh in emit(product, scratch_root):
                    relative = fresh.relative_to(scratch_root)
                    committed = args.out_root / relative
                    if not committed.is_file() or not filecmp.cmp(
                        fresh, committed, shallow=False
                    ):
                        stale.append(relative.as_posix())
            if stale:
                print("icons are stale; re-run tools/make_app_icons.py:", file=sys.stderr)
                for entry in stale:
                    print(f"  {entry}", file=sys.stderr)
                return 1
            print("icons match the committed assets")
            return 0

    for product in PRODUCTS:
        for path in emit(product, args.out_root):
            relative = path.relative_to(args.out_root).as_posix()
            if args.print_pins:
                print(f'    "{relative}": ({path.stat().st_size}, "{_sha256(path)}"),')
            else:
                print(f"{relative}  {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
