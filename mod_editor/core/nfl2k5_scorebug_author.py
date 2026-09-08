"""Scorebar Studio: simple controls in, a valid static scorebar template folder out.

The game's ESPN scorebar is a fixed 64x64 atlas cut into eight cells (see
``nfl2k5_scorebug_template``). This module describes each cell by plain
parameters: one colour or a two- or three-colour blend, corner rounding, a
border, opacity, and an optional picture fitted into the cell. It renders the
``1x/`` and ``2x/`` PNGs that ``compile_folder`` accepts, opens an existing
template folder losslessly (every PNG becomes a picture layer whose bytes are
written back unchanged), and previews the bar on a drawn field with stand-in
text at the game's live text positions.

It cannot add cells, fonts or hooks. The game draws every live string with its
own FONT objects and shows one bar for every team. Team colours in the preview
are preview only.

Pure Python and Pillow. No Qt, numpy, Unicorn or network imports.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import json
import math
from pathlib import Path
import sys

from . import nfl2k5_scorebug_template as template

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
SCHEMA = "nfl2k5_scorebug_author/v1"
PRESETS_SCHEMA = "nfl2k5_scorebug_studio_presets/v1"
DOCUMENT_FILE = "scorebar_studio.json"
IMAGES_DIR = "images"
PRESETS_FILE = ROOT / "data" / "nfl2k5_scorebug_studio_presets.json"
TEAMS_FILE = template.DEFAULT_FOLDER / "teams.json"
GLYPH_SHEET = template.DEFAULT_FOLDER / "glyphs" / "1x" / "broadcast_glyphs.png"
GLYPH_METRICS = template.DEFAULT_FOLDER / "glyphs" / "glyphs.json"
MAX_COLOURS = 256
DEFAULT_COLOUR_LIMIT = 128
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_PIXELS = 32 * 1024 * 1024
MAX_RADIUS = 8
MAX_BORDER = 4
HUD_SIZE = (640, 480)
WIDE_SIZE = (854, 480)
# Widescreen v3 contracts HUD x by 27/32 about x = 320 and leaves y alone
# (tools/nfl2k5_scorebug_projection.py reference_rails). The 640x480 HUD is
# then shown at 16:9, so the bar ends up 9/8 of its 4:3 width on screen.
WIDE_CONTRACTION = (27, 32)
# The pinned retail score_buga wrapper: a 2400-byte VC-LZ body after the
# 32-byte header, stream tag 1, 11 offset bits, a 128-byte texture header and
# a 16-byte overlapping-decode scratch. These are measurements, not retail
# bytes. The build's exact fixed-span check stays the authority.
SLOT_BODY_BYTES = 2400
SLOT_STREAM_TAG = 1
SLOT_OFFSET_BITS = 11
SLOT_HEADER_BYTES = 128
SLOT_HEADER_ALLOWANCE = 80
SLOT_WARNING_RATIO = 0.9

LAYER_ORDER = ("frame", "left_mark", "away_block", "away_score",
               "home_block", "home_score", "down", "clock_quarter")
LAYER_TITLES = {
    "frame": "Bar frame",
    "left_mark": "ESPN mark",
    "away_block": "Away team block",
    "away_score": "Away score",
    "home_block": "Home team block",
    "home_score": "Home score",
    "down": "Down and distance banner",
    "clock_quarter": "Clock strip",
}
LAYER_NOTES = {
    "frame": "The whole bar, behind every other part. Tiles are 64 x 8 pixels, stretched to 476 x 48 on screen.",
    "left_mark": "The network mark cell on the left. A good place for your own picture.",
    "away_block": "Behind the away team name. The game writes the name here in white, or yellow with the ball.",
    "away_score": "Behind the away score, the right part of the away block. The game writes the score in white.",
    "home_block": "Behind the home team name. The game writes the name here in white, or yellow with the ball.",
    "home_score": "Behind the home score, the left part of the home block. The game writes the score in white.",
    "down": "The banner where the game writes the down and distance, FLAG and FUMBLE in white.",
    "clock_quarter": "The strip where the game writes the quarter, clock and play clock in near-black. Keep it light.",
}
TEXT_LAYERS = ("away_block", "away_score", "home_block", "home_score", "down", "clock_quarter")
DEFAULT_SAMPLE_TEXT = {"away_block": "OAK", "away_score": "0", "home_block": "GB", "home_score": "0",
                       "down": "1st & 10", "clock_quarter": "1st|13:10|:12"}
FIT_MODES = ("tile", "contain", "cover", "stretch")
FIT_TITLES = {"contain": "Fit inside", "cover": "Fill and crop", "stretch": "Stretch to fit", "tile": "Exact pixels"}
LIVE_TEXT_COLOURS = {"team": (255, 255, 255, 255), "possession": (214, 206, 0, 255),
                     "score": (255, 255, 255, 255), "down": (255, 255, 255, 255), "clock": (17, 17, 24, 255)}
# Stand-in text cells in HUD pixels, measured from the v10 native projection
# (docs/scorebug_ingame/after_v10_640x480.png). The game's own fonts decide the
# real glyphs; these only show where the strings land.
SAMPLE_FIELDS = (
    ("away_city", (164, 400, 226, 414), "left", "team", 14),
    ("away_score", (231, 393, 274, 418), "centre", "score", 25),
    ("down", (282, 388, 430, 402), "centre", "down", 14),
    ("quarter", (284, 409, 326, 423), "left", "clock", 13),
    ("clock", (326, 409, 406, 423), "centre", "clock", 13),
    ("play_clock", (406, 409, 430, 423), "right", "clock", 13),
    ("home_score", (438, 393, 483, 418), "centre", "score", 25),
    ("home_city", (487, 400, 549, 414), "left", "team", 14),
)
TIMEOUT_RECTS = ((238, 423, 270, 425), (442, 423, 474, 425))


class AuthorError(ValueError):
    """A plain, actionable message for the Studio page and the command line."""


@dataclass(frozen=True)
class State:
    id: str
    title: str
    text: dict
    possession: str
    timeouts: bool


STATES = (
    State("first_and_ten", "1st & 10", {"down": "1st & 10", "clock_quarter": "1st|13:10|:12"}, "away", False),
    State("fourth_and_one", "4th & 1", {"down": "4th & 1", "clock_quarter": "3rd|2:47|:05"}, "home", False),
    State("timeouts", "Timeouts", {"down": "1st & 10", "clock_quarter": "2nd|8:12|:25"}, "away", True),
    State("two_minute", "Two-minute", {"down": "2nd & 7", "clock_quarter": "4th|2:00|:40"}, "home", False),
)


def state(state_id: str) -> State:
    for item in STATES:
        if item.id == state_id:
            return item
    raise AuthorError(f"Unknown sample state {state_id!r}.")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_colour(text) -> tuple[int, int, int, int]:
    """'#RRGGBB' or '#RRGGBBAA' (any case) to an RGBA tuple."""
    if isinstance(text, (tuple, list)) and len(text) == 4 and all(type(v) is int and 0 <= v <= 255 for v in text):
        return tuple(text)
    if not isinstance(text, str) or not text.startswith("#") or len(text) not in (7, 9):
        raise AuthorError(f"Colours must look like #RRGGBB or #RRGGBBAA, not {text!r}.")
    try:
        value = bytes.fromhex(text[1:])
    except ValueError as exc:
        raise AuthorError(f"Colours must look like #RRGGBB or #RRGGBBAA, not {text!r}.") from exc
    return (value[0], value[1], value[2], value[3] if len(value) == 4 else 255)


def colour_hex(colour) -> str:
    r, g, b, a = parse_colour(colour)
    return "#%02X%02X%02X%02X" % (r, g, b, a)


def _int(value, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AuthorError(f"{name} must be a whole number from {low} to {high}.")
    return value


@dataclass(frozen=True)
class Gradient:
    stops: tuple[str, ...]
    angle: int = 90

    @classmethod
    def from_json(cls, data) -> "Gradient":
        if not isinstance(data, dict):
            raise AuthorError("A blend needs its colours and a direction.")
        stops = data.get("stops")
        if not isinstance(stops, list) or not 2 <= len(stops) <= 3:
            raise AuthorError("A blend uses two or three colours.")
        return cls(tuple(colour_hex(stop) for stop in stops), _int(data.get("angle", 90), "Blend direction", 0, 359))

    def to_json(self) -> dict:
        return {"stops": list(self.stops), "angle": self.angle}


@dataclass(frozen=True)
class Border:
    colour: str
    width: int = 1

    @classmethod
    def from_json(cls, data) -> "Border":
        if not isinstance(data, dict):
            raise AuthorError("A border needs a colour and a width.")
        return cls(colour_hex(data.get("colour", "#FFFFFFFF")), _int(data.get("width", 1), "Border width", 0, MAX_BORDER))

    def to_json(self) -> dict:
        return {"colour": self.colour, "width": self.width}


@dataclass(frozen=True)
class ImageSource:
    """One picture file's bytes. scale is '1x', '2x' (exact tile art) or 'any'."""
    scale: str
    data: bytes

    @property
    def sha256(self) -> str:
        return sha(self.data)


@dataclass(frozen=True)
class ImageRef:
    sources: tuple[ImageSource, ...]
    fit: str = "contain"
    crop: tuple[int, int, int, int] | None = None
    clip: bool = False
    name: str = ""

    def source(self, scale: str) -> ImageSource | None:
        for item in self.sources:
            if item.scale == scale:
                return item
        return None

    def best_source(self, scale: int) -> ImageSource:
        for key in (f"{scale}x", "any", "2x", "1x"):
            found = self.source(key)
            if found is not None:
                return found
        raise AuthorError("This picture layer has no picture file.")

    def to_json(self, files: dict) -> dict:
        return {"fit": self.fit, "clip": self.clip, "crop": list(self.crop) if self.crop else None, "name": self.name,
                "sources": [{"scale": item.scale, "file": files[(item.scale, item.sha256)], "sha256": item.sha256}
                            for item in self.sources]}

    @classmethod
    def from_json(cls, data, read) -> "ImageRef":
        if not isinstance(data, dict):
            raise AuthorError("A picture entry must be an object.")
        fit = data.get("fit", "contain")
        if fit not in FIT_MODES:
            raise AuthorError(f"Picture fit must be one of {', '.join(FIT_MODES)}.")
        crop = data.get("crop")
        if crop is not None:
            if not isinstance(crop, list) or len(crop) != 4 or not all(type(v) is int for v in crop) \
                    or crop[0] >= crop[2] or crop[1] >= crop[3] or min(crop) < 0:
                raise AuthorError("A picture crop is [left, top, right, bottom] in source pixels.")
            crop = tuple(crop)
        sources = []
        for entry in data.get("sources", []):
            if not isinstance(entry, dict) or entry.get("scale") not in ("1x", "2x", "any") or not isinstance(entry.get("file"), str):
                raise AuthorError("Each picture source needs a scale (1x, 2x or any) and a file.")
            raw = read(entry["file"])
            if len(raw) > MAX_IMAGE_BYTES:
                raise AuthorError(f"{entry['file']} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
            expected = entry.get("sha256")
            if isinstance(expected, str) and expected != sha(raw):
                raise AuthorError(f"{entry['file']} changed since this scorebar was saved. Choose the picture again.")
            sources.append(ImageSource(entry["scale"], raw))
        if not sources:
            raise AuthorError("A picture layer needs at least one picture file.")
        return cls(tuple(sources), fit, crop, bool(data.get("clip", False)), str(data.get("name", "")))


@dataclass(frozen=True)
class Layer:
    fill: str = "#00000000"
    gradient: Gradient | None = None
    radius: int = 0
    border: Border | None = None
    opacity: int = 100
    image: ImageRef | None = None
    sample_text: str | None = None

    @classmethod
    def from_json(cls, data, read=None) -> "Layer":
        if not isinstance(data, dict):
            raise AuthorError("Each layer must be an object of simple settings.")
        image = data.get("image")
        if image is not None and read is None:
            raise AuthorError("This layer has a picture but no folder to read it from.")
        text = data.get("sample_text")
        if text is not None and not isinstance(text, str):
            raise AuthorError("Sample text must be text.")
        return cls(colour_hex(data.get("fill", "#00000000")),
                   Gradient.from_json(data["gradient"]) if data.get("gradient") is not None else None,
                   _int(data.get("radius", 0), "Corner rounding", 0, MAX_RADIUS),
                   Border.from_json(data["border"]) if data.get("border") is not None else None,
                   _int(data.get("opacity", 100), "Opacity", 0, 100),
                   ImageRef.from_json(image, read) if image is not None else None,
                   text)

    def to_json(self, files: dict | None = None) -> dict:
        return {"fill": self.fill, "gradient": self.gradient.to_json() if self.gradient else None,
                "radius": self.radius, "border": self.border.to_json() if self.border else None,
                "opacity": self.opacity, "image": self.image.to_json(files or {}) if self.image else None,
                "sample_text": self.sample_text}

    def with_(self, **changes) -> "Layer":
        return replace(self, **changes)


DEFAULT_PAINT = {
    "frame": Layer("#14161BFF", Gradient(("#23262DFF", "#0E1014FF"), 90), 1, Border("#3A3F48FF", 1)),
    "left_mark": Layer("#00000000"),
    "away_block": Layer("#1E2128FF", Gradient(("#262A32FF", "#161920FF"), 0), 0, None),
    "away_score": Layer("#0F1114FF", None, 1, None),
    "home_block": Layer("#1E2128FF", Gradient(("#161920FF", "#262A32FF"), 0), 0, None),
    "home_score": Layer("#0F1114FF", None, 1, None),
    "down": Layer("#B3121FFF", Gradient(("#C81A2AFF", "#8F0A16FF"), 90), 1, Border("#5E0510FF", 1)),
    "clock_quarter": Layer("#E9EBEFFF", Gradient(("#FFFFFFFF", "#E1E4EAFF"), 90), 2, Border("#6B7078FF", 1)),
}


def tile_size(name: str, scale: int = 1) -> tuple[int, int]:
    x, y, right, bottom = template.LAYERS[name][0]
    return ((right - x) * scale, (bottom - y) * scale)


def hud_rect(name: str) -> tuple[int, int, int, int]:
    return tuple(template.LAYERS[name][1])


def hud_size(name: str, scale: int = 1) -> tuple[int, int]:
    x, y, right, bottom = hud_rect(name)
    return ((right - x) * scale, (bottom - y) * scale)


_DECODED: dict[str, object] = {}


def decode_image(data: bytes):
    """Bytes to RGBA, cached by content hash. Refuses bombs and unreadable files."""
    from PIL import Image, UnidentifiedImageError
    key = sha(data)
    cached = _DECODED.get(key)
    if cached is not None:
        return cached
    if len(data) > MAX_IMAGE_BYTES:
        raise AuthorError(f"That picture is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.size[0] * source.size[1] > MAX_IMAGE_PIXELS:
                raise AuthorError("That picture has too many pixels. Use one under 32 million pixels.")
            image = source.convert("RGBA")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError) as exc:
        if isinstance(exc, AuthorError):
            raise
        raise AuthorError("That file is not a readable picture. Use a PNG, JPEG, BMP or GIF.") from exc
    if len(_DECODED) > 64:
        _DECODED.clear()
    _DECODED[key] = image
    return image


def load_picture(path) -> ImageSource:
    """Read a user's picture file once, as an 'any' scale source."""
    path = Path(path).expanduser()
    try:
        if path.is_symlink() or not path.is_file():
            raise AuthorError(f"{path.name} is not a regular file.")
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise AuthorError(f"{path.name} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
        data = path.read_bytes()
    except OSError as exc:
        raise AuthorError(f"Cannot read {path.name}: {exc.strerror or exc}") from exc
    decode_image(data)
    return ImageSource("any", data)


def _gradient(size: tuple[int, int], stops, angle: int):
    from PIL import Image
    w, h = size
    theta = math.radians(angle % 360)
    dx, dy = math.cos(theta), math.sin(theta)
    projections = [x * dx + y * dy for x, y in ((0, 0), (w, 0), (0, h), (w, h))]
    low, high = min(projections), max(projections)
    span = (high - low) or 1.0
    colours = [parse_colour(stop) for stop in stops]
    segments = len(colours) - 1
    pixels = []
    for y in range(h):
        for x in range(w):
            t = min(1.0, max(0.0, ((x + 0.5) * dx + (y + 0.5) * dy - low) / span)) * segments
            index = min(int(t), segments - 1)
            f = t - index
            a, b = colours[index], colours[index + 1]
            pixels.append(tuple(int(round(ca + (cb - ca) * f)) for ca, cb in zip(a, b)))
    image = Image.new("RGBA", size)
    image.putdata(pixels)
    return image


def _rounded_mask(size, radius: int):
    from PIL import Image, ImageDraw
    w, h = size
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    return mask


def _fit(image, size: tuple[int, int], mode: str):
    from PIL import Image
    w, h = size
    sw, sh = image.size
    if (sw, sh) == (w, h):
        return image
    if mode == "stretch":
        return image.resize((w, h), Image.Resampling.LANCZOS)
    if mode == "contain":
        factor = min(w / sw, h / sh)
        inner = (max(1, min(w, round(sw * factor))), max(1, min(h, round(sh * factor))))
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(image.resize(inner, Image.Resampling.LANCZOS), ((w - inner[0]) // 2, (h - inner[1]) // 2))
        return canvas
    factor = max(w / sw, h / sh)
    cover = (max(w, round(sw * factor)), max(h, round(sh * factor)))
    resized = image.resize(cover, Image.Resampling.LANCZOS)
    left, top = (cover[0] - w) // 2, (cover[1] - h) // 2
    return resized.crop((left, top, left + w, top + h))


def _picture(layer: Layer, name: str, scale: int):
    """The layer's picture at tile resolution, fitted in on-screen proportions first."""
    from PIL import Image
    ref = layer.image
    tile = tile_size(name, scale)
    if ref.fit == "tile":
        source = ref.best_source(scale)
        image = decode_image(source.data)
        if ref.crop:
            image = image.crop(ref.crop)
        return image if image.size == tile else image.resize(tile, Image.Resampling.NEAREST)
    source = ref.best_source(scale)
    image = decode_image(source.data)
    if ref.crop:
        if ref.crop[2] > image.size[0] or ref.crop[3] > image.size[1]:
            raise AuthorError(f"The crop for {LAYER_TITLES[name]} is outside the picture.")
        image = image.crop(ref.crop)
    fitted = _fit(image, hud_size(name, scale), ref.fit)
    return fitted if fitted.size == tile else fitted.resize(tile, Image.Resampling.LANCZOS)


def render_layer(layer: Layer, name: str, scale: int = 1):
    """One cell as an RGBA image at its atlas tile size times scale."""
    from PIL import Image, ImageDraw
    if name not in template.LAYERS:
        raise AuthorError(f"Unknown scorebar layer {name!r}.")
    if scale not in (1, 2):
        raise AuthorError("Scale must be 1 or 2.")
    size = tile_size(name, scale)
    w, h = size
    radius = max(0, min(layer.radius * scale, (min(w, h) - 1) // 2))
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    fill = parse_colour(layer.fill)
    mask = _rounded_mask(size, radius)
    if layer.gradient is not None:
        image.paste(_gradient(size, layer.gradient.stops, layer.gradient.angle), (0, 0), mask)
    elif fill[3]:
        image.paste(Image.new("RGBA", size, fill), (0, 0), mask)
    if layer.border is not None and layer.border.width > 0:
        colour = parse_colour(layer.border.colour)
        if colour[3]:
            ImageDraw.Draw(image).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, outline=colour,
                                                    width=min(layer.border.width * scale, max(1, min(w, h) // 2)))
    if layer.image is not None:
        picture = _picture(layer, name, scale)
        if layer.image.clip and radius:
            picture = picture.copy()
            picture.putalpha(_multiply(picture.getchannel("A"), mask))
        image.alpha_composite(picture)
    if layer.opacity < 100:
        factor = layer.opacity
        image.putalpha(image.getchannel("A").point(lambda v: v * factor // 100))
    return image


def _multiply(alpha, mask):
    from PIL import ImageChops
    return ImageChops.multiply(alpha, mask)


def passthrough_bytes(layer: Layer, name: str, scale: int) -> bytes | None:
    """The original PNG bytes, when the layer is exactly that picture and nothing else."""
    ref = layer.image
    if ref is None or ref.fit != "tile" or ref.crop or layer.opacity != 100:
        return None
    if parse_colour(layer.fill)[3] or layer.gradient is not None:
        return None
    if layer.border is not None and layer.border.width > 0 and parse_colour(layer.border.colour)[3]:
        return None
    if ref.clip and layer.radius:
        return None
    source = ref.source(f"{scale}x")
    if source is None or not source.data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if decode_image(source.data).size != tile_size(name, scale):
        return None
    return source.data


def encode_png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _quantize_together(images: list, colours: int) -> list:
    """One shared palette for several tiles, without touching passthrough art."""
    from PIL import Image
    width = max(image.size[0] for image in images)
    height = sum(image.size[1] for image in images)
    strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    y = 0
    for image in images:
        strip.paste(image, (0, y))
        y += image.size[1]
    reduced = strip.quantize(colors=max(2, colours), method=Image.Quantize.FASTOCTREE).convert("RGBA")
    result, y = [], 0
    for image in images:
        result.append(reduced.crop((0, y, image.size[0], y + image.size[1])))
        y += image.size[1]
    return result


def _default_contract() -> dict:
    return json.loads(template._read(template.DEFAULT_FOLDER / "layout.json"))


NOT_A_TEMPLATE = ("This folder is not a supported scorebar template. Open the shipped reference or a folder saved by "
                  "Scorebar Studio.")


def _read_contract(folder: Path) -> dict:
    if not (folder / "layout.json").is_file():
        raise AuthorError(NOT_A_TEMPLATE)
    try:
        raw = template._read(folder / "layout.json")
        contract = json.loads(raw)
    except (template.TemplateError, ValueError, UnicodeError) as exc:
        raise AuthorError(f"{folder.name}: layout.json is unreadable. {exc}") from exc
    if not isinstance(contract, dict) or contract.get("schema") != template.SCHEMA:
        raise AuthorError(NOT_A_TEMPLATE)
    return contract


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    kind: str
    summary: str
    folder: Path | None = None
    layers: dict | None = None
    note: str = ""


def _preset_layer_reader(file: str) -> bytes:
    path = (ROOT / file)
    try:
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise AuthorError(f"Preset picture {file} is outside the Studio folder.")
        return path.read_bytes()
    except OSError as exc:
        raise AuthorError(f"Preset picture {file} is missing: {exc.strerror or exc}") from exc


def presets(path=None) -> list[Preset]:
    """The preset registry. A folder preset needs only a JSON row, no code."""
    path = Path(path) if path else PRESETS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuthorError(f"The preset list {path.name} is unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != PRESETS_SCHEMA or not isinstance(data.get("presets"), list):
        raise AuthorError(f"The preset list {path.name} is not a supported preset registry.")
    result, seen = [], set()
    for row in data["presets"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("title"), str):
            raise AuthorError("Every preset needs an id and a title.")
        if row["id"] in seen:
            raise AuthorError(f"Preset id {row['id']} appears twice.")
        seen.add(row["id"])
        kind = row.get("kind")
        summary = str(row.get("summary", ""))
        note = str(row.get("note", ""))
        if kind == "folder":
            folder = row.get("folder")
            if not isinstance(folder, str):
                raise AuthorError(f"Preset {row['id']} needs a folder.")
            resolved = Path(folder) if Path(folder).is_absolute() else ROOT / folder
            result.append(Preset(row["id"], row["title"], kind, summary, resolved, None, note))
        elif kind == "paint":
            layers = row.get("layers")
            if not isinstance(layers, dict):
                raise AuthorError(f"Preset {row['id']} needs its layers.")
            parsed = {}
            for name in template.LAYERS:
                parsed[name] = Layer.from_json(layers[name], _preset_layer_reader) if name in layers else DEFAULT_PAINT[name]
            result.append(Preset(row["id"], row["title"], kind, summary, None, parsed, note))
        else:
            raise AuthorError(f"Preset {row['id']} has an unknown kind {kind!r}; use folder or paint.")
    return result


def preset(preset_id: str, path=None) -> Preset:
    for item in presets(path):
        if item.id == preset_id:
            return item
    raise AuthorError(f"Unknown preset {preset_id!r}.")


def teams() -> list[dict]:
    """The 32 preview palettes shipped with the reference kit."""
    try:
        rows = json.loads(TEAMS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuthorError(f"teams.json is unavailable: {exc}") from exc
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("abbr"), str)]


class Document:
    """Eight layers, the contract they render into, and the preview settings."""

    def __init__(self, layers: dict, *, contract: dict | None = None, preset_id: str = "", title: str = "Scorebar",
                 source_scale: int = 1, colour_limit: int = DEFAULT_COLOUR_LIMIT, state_id: str = "first_and_ten"):
        missing = [name for name in template.LAYERS if name not in layers]
        if missing:
            raise AuthorError("The scorebar is missing layers: " + ", ".join(LAYER_TITLES[m] for m in missing))
        self.layers = {name: layers[name] for name in template.LAYERS}
        self.contract = contract if contract is not None else _default_contract()
        self.preset_id = preset_id
        self.title = title
        self.source_scale = _int(source_scale, "source_scale", 1, 2)
        self.colour_limit = _int(colour_limit, "Colour limit", 8, MAX_COLOURS)
        self.state_id = state(state_id).id

    def __eq__(self, other) -> bool:
        return isinstance(other, Document) and self.snapshot() == other.snapshot()

    def snapshot(self) -> tuple:
        rows = []
        for name in template.LAYERS:
            layer = self.layers[name]
            image = None
            if layer.image is not None:
                image = (layer.image.fit, layer.image.crop, layer.image.clip, layer.image.name,
                         tuple((s.scale, s.sha256) for s in layer.image.sources))
            rows.append((name, layer.fill, layer.gradient, layer.radius, layer.border, layer.opacity, image, layer.sample_text))
        return (tuple(rows), self.source_scale, self.colour_limit, self.title, self.state_id)

    def copy(self) -> "Document":
        return Document(dict(self.layers), contract=json.loads(json.dumps(self.contract)), preset_id=self.preset_id,
                        title=self.title, source_scale=self.source_scale, colour_limit=self.colour_limit,
                        state_id=self.state_id)

    @classmethod
    def from_preset(cls, item: Preset | str, registry=None) -> "Document":
        if isinstance(item, str):
            item = preset(item, registry)
        if item.kind == "folder":
            document = cls.open_folder(item.folder)
            document.preset_id, document.title = item.id, item.title
            return document
        layers = {name: item.layers[name].with_(sample_text=item.layers[name].sample_text or DEFAULT_SAMPLE_TEXT.get(name))
                  for name in template.LAYERS}
        return cls(layers, preset_id=item.id, title=item.title)

    @classmethod
    def open_folder(cls, folder) -> "Document":
        """A Studio folder keeps its settings; any valid template opens as pictures."""
        folder = Path(folder).expanduser()
        if not folder.is_dir():
            raise AuthorError(f"{folder} is not a folder.")
        contract = _read_contract(folder)
        try:
            compiled = template.compile_folder(folder)
        except template.TemplateError as exc:
            raise AuthorError(str(exc)) from exc
        source_scale = compiled.receipt["source_scale"]
        saved = folder / DOCUMENT_FILE
        if saved.is_file():
            try:
                data = json.loads(saved.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise AuthorError(f"{DOCUMENT_FILE} is unreadable: {exc}") from exc
            document = cls.from_json(data, folder)
            document.contract = contract
            return document
        layers = {}
        for name in template.LAYERS:
            sources = []
            for scale in (1, 2):
                path = folder / f"{scale}x" / f"{name}.png"
                if not path.is_file():
                    continue
                try:
                    data = template._read(path)
                except template.TemplateError as exc:
                    raise AuthorError(str(exc)) from exc
                if decode_image(data).size != tile_size(name, scale):
                    if scale == source_scale:
                        raise AuthorError(f"{path.name} is not {tile_size(name, scale)[0]} x {tile_size(name, scale)[1]}.")
                    continue
                sources.append(ImageSource(f"{scale}x", data))
            layers[name] = Layer(image=ImageRef(tuple(sources), "tile", None, False, f"{name}.png"),
                                 sample_text=DEFAULT_SAMPLE_TEXT.get(name))
        return cls(layers, contract=contract, title=folder.name, source_scale=source_scale)

    @classmethod
    def from_json(cls, data, folder=None) -> "Document":
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise AuthorError("This is not a Scorebar Studio document. Open a folder saved by Scorebar Studio or the shipped reference.")
        folder = Path(folder) if folder is not None else None

        def read(file: str) -> bytes:
            if folder is None:
                raise AuthorError("This document has pictures but no folder to read them from.")
            path = folder / file
            try:
                if not path.resolve().is_relative_to(folder.resolve()):
                    raise AuthorError(f"Picture {file} is outside the scorebar folder.")
                return path.read_bytes()
            except OSError as exc:
                raise AuthorError(f"Picture {file} is missing: {exc.strerror or exc}") from exc

        layers_data = data.get("layers")
        if not isinstance(layers_data, dict):
            raise AuthorError("The document has no layers.")
        layers = {}
        for name in template.LAYERS:
            if name not in layers_data:
                raise AuthorError(f"The document is missing the {LAYER_TITLES[name]} layer.")
            layers[name] = Layer.from_json(layers_data[name], read)
        preview = data.get("preview") if isinstance(data.get("preview"), dict) else {}
        return cls(layers, preset_id=str(data.get("preset", "")), title=str(data.get("title", "Scorebar")),
                   source_scale=data.get("source_scale", 1), colour_limit=data.get("colour_limit", DEFAULT_COLOUR_LIMIT),
                   state_id=preview.get("state", "first_and_ten") if preview.get("state") in {s.id for s in STATES} else "first_and_ten")

    def to_json(self, files: dict | None = None) -> dict:
        files = files if files is not None else self.image_files()
        return {"schema": SCHEMA, "title": self.title, "preset": self.preset_id, "source_scale": self.source_scale,
                "colour_limit": self.colour_limit,
                "layers": {name: self.layers[name].to_json(files) for name in template.LAYERS},
                "preview": {"state": self.state_id},
                "notes": ["Live text, team names, scores, clocks and possession colour are drawn by the game.",
                          "One bar is shown for every team; team colours are preview only.",
                          "layout.json is the fixed cell contract; do not edit it."]}

    def image_files(self) -> dict:
        """Relative file names for every picture source, keyed by (scale, sha256)."""
        files = {}
        for name in template.LAYERS:
            ref = self.layers[name].image
            if ref is None:
                continue
            for source in ref.sources:
                key = (source.scale, source.sha256)
                if key not in files:
                    suffix = _suffix(source.data)
                    files[key] = f"{IMAGES_DIR}/{name}_{source.scale}{suffix}"
        return files

    def export_tiles(self, scale: int) -> dict:
        """name -> (RGBA tile, original PNG bytes or None), sharing at most colour_limit colours."""
        rendered, fixed = {}, set()
        for name in template.LAYERS:
            layer = self.layers[name]
            raw = passthrough_bytes(layer, name, scale)
            image = render_layer(layer, name, scale)
            rendered[name] = [image, raw]
            if raw is not None:
                fixed |= set(image.getdata())
        variable = [name for name, (_image, raw) in rendered.items() if raw is None]
        union = set(fixed)
        for name in variable:
            union |= set(rendered[name][0].getdata())
        limit = min(self.colour_limit, MAX_COLOURS)
        if len(union) > limit and variable:
            budget = limit - len(fixed)
            if budget < 2:
                raise AuthorError(f"Your exact-pixel pictures already use {len(fixed)} colours, which leaves no room "
                                  "for the painted layers. Raise the colour limit or simplify those pictures.")
            for name, image in zip(variable, _quantize_together([rendered[n][0] for n in variable], budget)):
                rendered[name][0] = image
        elif len(union) > MAX_COLOURS:
            raise AuthorError(f"Your exact-pixel pictures use {len(union)} colours together; the game allows {MAX_COLOURS}.")
        return {name: (image, raw) for name, (image, raw) in rendered.items()}

    def atlas(self):
        """The 64x64 atlas exactly as compile_folder packs the saved folder."""
        from PIL import Image
        tiles = self.export_tiles(self.source_scale)
        out = Image.new("RGBA", (64, 64))
        for name, (rect, _hud) in template.LAYERS.items():
            image = tiles[name][0]
            if self.source_scale == 2:
                image = image.resize(tile_size(name, 1), Image.Resampling.NEAREST)
            out.paste(image, rect[:2])
        return out

    def analysis(self) -> dict:
        """Colours, an estimate of the game slot, and plain warnings."""
        atlas = self.atlas()
        colours = len(set(atlas.getdata()))
        estimate = slot_estimate(atlas)
        warnings = []
        clock = _luminance(render_layer(self.layers["clock_quarter"], "clock_quarter", 1))
        if clock is not None and clock < 0.55:
            warnings.append("The clock strip is dark. The game writes the quarter, clock and play clock there in near-black; keep it light.")
        for name in ("down", "away_block", "home_block", "away_score", "home_score"):
            value = _luminance(render_layer(self.layers[name], name, 1))
            if value is not None and value > 0.72:
                warnings.append(f"The {LAYER_TITLES[name].lower()} is very light. The game writes white text there.")
        if not estimate["fits"]:
            warnings.append("Too detailed for the game's scorebar slot. Simplify blends, use fewer colours or lower the colour limit.")
        elif estimate["estimated_bytes"] > SLOT_BODY_BYTES * SLOT_WARNING_RATIO:
            warnings.append("Close to the game's scorebar slot limit. The build's exact check may still refuse it.")
        return {"colours": colours, "colour_limit": self.colour_limit, "max_colours": MAX_COLOURS,
                "slot": estimate, "warnings": warnings}

    def save_folder(self, folder) -> dict:
        """Write layout.json, 1x/, 2x/, images/ and the Studio document, then compile it."""
        folder = Path(folder).expanduser()
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            raise AuthorError(f"{folder} is not a folder.")
        if folder.exists() and folder.resolve() == template.DEFAULT_FOLDER.resolve():
            raise AuthorError("That is the shipped reference kit. Save your scorebar in a new folder.")
        exports = {scale: self.export_tiles(scale) for scale in (1, 2)}
        files = self.image_files()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for scale, tiles in exports.items():
                target = folder / f"{scale}x"
                target.mkdir(exist_ok=True)
                for name, (image, raw) in tiles.items():
                    (target / f"{name}.png").write_bytes(raw if raw is not None else encode_png(image))
            written = set()
            for name in template.LAYERS:
                ref = self.layers[name].image
                if ref is None:
                    continue
                for source in ref.sources:
                    relative = files[(source.scale, source.sha256)]
                    if relative in written:
                        continue
                    path = folder / relative
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(source.data)
                    written.add(relative)
            contract = json.loads(json.dumps(self.contract))
            contract["source_scale"] = self.source_scale
            # Bytes, so Windows cannot turn the newlines into CRLF and change the layout hash.
            (folder / "layout.json").write_bytes((json.dumps(contract, indent=2) + "\n").encode("utf-8"))
            (folder / DOCUMENT_FILE).write_bytes((json.dumps(self.to_json(files), indent=2) + "\n").encode("utf-8"))
        except OSError as exc:
            raise AuthorError(f"Cannot write to {folder}: {exc.strerror or exc}") from exc
        try:
            compiled = template.compile_folder(folder)
        except template.TemplateError as exc:
            raise AuthorError(str(exc)) from exc
        return {"folder": str(folder), "template": compiled.receipt, **self.analysis()}


def _suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:2] == b"BM":
        return ".bmp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".img"


def _luminance(image) -> float | None:
    pixels = [p for p in image.getdata() if p[3] > 64]
    if not pixels:
        return None
    return sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b, _a in pixels) / (255 * len(pixels))


def slot_estimate(atlas) -> dict:
    """How much of the fixed 2400-byte game slot this atlas would need."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import nfl_txtr as tx
    import nfl_vc_lz_fill as fill
    import nfl_tset_png_import as palettes
    pixels = list(atlas.getdata())
    palette = sorted(set(pixels))
    if len(palette) > MAX_COLOURS:
        return {"estimated_bytes": None, "budget_bytes": SLOT_BODY_BYTES, "fits": False, "colours": len(palette)}
    indices = {colour: index for index, colour in enumerate(palette)}
    linear = bytes(indices[colour] for colour in pixels)
    body = bytes(SLOT_HEADER_BYTES) + tx.swizzle_2d(linear, 64, 64, 1) + palettes.palette_bytes(palette)
    stream = fill.compress_optimal(body, stream_tag=SLOT_STREAM_TAG, offset_bits=SLOT_OFFSET_BITS)
    needed = len(stream) + SLOT_HEADER_ALLOWANCE
    return {"estimated_bytes": needed, "budget_bytes": SLOT_BODY_BYTES, "fits": needed <= SLOT_BODY_BYTES,
            "colours": len(palette)}


def check_folder(folder) -> dict:
    """compile_folder with its plain messages, for the page's Open and Use in Build."""
    try:
        return template.compile_folder(folder).receipt
    except template.TemplateError as exc:
        raise AuthorError(str(exc)) from exc


class _Glyphs:
    """The staged broadcast glyph sheet as a stand-in preview font."""
    _loaded = None

    @classmethod
    def get(cls) -> "_Glyphs":
        if cls._loaded is None:
            cls._loaded = cls()
        return cls._loaded

    def __init__(self):
        from PIL import Image
        with Image.open(GLYPH_SHEET) as sheet:
            self.alpha = sheet.convert("RGBA").getchannel("A")
        metrics = json.loads(GLYPH_METRICS.read_text(encoding="utf-8"))["metrics"]
        self.cells = {row["character"]: (tuple(row["rect"]), row["advance"]) for row in metrics.values() if row["supported"]}

    def draw(self, text: str, cap: int, colour):
        from PIL import Image
        cells = [self.cells.get(ch, self.cells[" "]) for ch in text]
        width = sum(advance for _rect, advance in cells) or 1
        strip = Image.new("L", (width, 14), 0)
        x = 0
        for (left, top, _right, _bottom), advance in cells:
            strip.paste(self.alpha.crop((left, top + 2, left + advance, top + 16)), (x, 0))
            x += advance
        if cap != 14:
            strip = strip.resize((max(1, round(width * cap / 14)), cap), Image.Resampling.LANCZOS)
        image = Image.new("RGBA", strip.size, tuple(colour[:3]) + (0,))
        image.putalpha(strip)
        return image


def _place_text(canvas, text: str, rect, align: str, colour, cap: int):
    glyph = _Glyphs.get().draw(text, cap, colour)
    left, top, right, bottom = rect
    if align == "centre":
        x = (left + right - glyph.size[0]) // 2
    elif align == "right":
        x = right - glyph.size[0]
    else:
        x = left
    canvas.alpha_composite(glyph, (x, top + (bottom - top - cap) // 2))


def field_background(size=HUD_SIZE):
    """A drawn stadium: stands, a crowd speckle, and a green field. No disc art."""
    from PIL import Image, ImageDraw
    w, h = size
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    horizon = h * 5 // 16
    for y in range(horizon):
        t = y / max(1, horizon - 1)
        draw.line((0, y, w, y), fill=(int(28 + 26 * t), int(30 + 24 * t), int(38 + 26 * t), 255))
    # Tiers of seats with a coarse, muted crowd; a fixed generator keeps it identical every time.
    crowd = ((150, 58, 62), (60, 72, 130), (190, 186, 176), (168, 142, 52), (96, 98, 106), (124, 48, 50),
             (52, 96, 78), (110, 112, 118), (74, 76, 84))
    seed = 20260907
    top = horizon // 4
    for _ in range(w * (horizon - top) // 30):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = (seed % w) & ~1
        y = top + (((seed >> 8) % (horizon - top)) & ~1)
        r, g, b = crowd[(seed >> 20) % len(crowd)]
        dim = 60 + 40 * y // max(1, horizon)
        draw.rectangle((x, y, x + 1, y + 1), fill=(r * dim // 100, g * dim // 100, b * dim // 100, 255))
    for y in range(top, horizon, 8):
        draw.line((0, y, w, y), fill=(20, 22, 28, 255))
    draw.rectangle((0, horizon - 6, w, horizon - 1), fill=(46, 50, 58, 255))
    for y in range(horizon, h):
        t = (y - horizon) / max(1, h - horizon - 1)
        draw.line((0, y, w, y), fill=(int(40 + 12 * t), int(88 + 22 * t), int(38 + 12 * t), 255))
    draw.rectangle((0, horizon, w, horizon + 3), fill=(230, 232, 228, 255))
    vanish = (w // 2, -h * 5 // 4)
    for k in range(-6, 8):
        x_bottom = w // 2 + k * w // 7
        draw.line((x_bottom, h, vanish[0] + (x_bottom - vanish[0]) * (horizon - vanish[1]) / (h - vanish[1]), horizon),
                  fill=(224, 230, 220, 255), width=1)
    for k in range(1, 6):
        y = horizon + int((h - horizon) * (k / 6) ** 1.6)
        draw.line((0, y, w, y), fill=(210, 220, 205, 255), width=1)
    return image


def _team_layer(base: Layer, primary: str, home: bool) -> Layer:
    r, g, b, _a = parse_colour(primary)
    dark = colour_hex((r * 45 // 100, g * 45 // 100, b * 45 // 100, 255))
    stops = (dark, colour_hex(primary)) if home else (colour_hex(primary), dark)
    return Layer(colour_hex(primary), Gradient(stops, 0), base.radius, base.border, base.opacity, None, base.sample_text)


def preview(document: Document, *, widescreen: bool = False, state_id: str | None = None,
            team_preview: tuple[str, str] | None = None):
    """The bar on a drawn field with stand-in text. 640x480 at 4:3, 854x480 at 16:9."""
    from PIL import Image, ImageDraw
    current = state(state_id or document.state_id)
    source = document
    text_colours = dict(LIVE_TEXT_COLOURS)
    if team_preview is not None:
        palettes = {row["abbr"]: row for row in teams()}
        away, home = team_preview
        if away not in palettes or home not in palettes:
            raise AuthorError("Choose two of the 32 teams for the preview.")
        source = document.copy()
        source.layers["away_block"] = _team_layer(document.layers["away_block"], palettes[away]["primary_hex"], False)
        source.layers["home_block"] = _team_layer(document.layers["home_block"], palettes[home]["primary_hex"], True)
        source.layers["away_block"] = source.layers["away_block"].with_(sample_text=away)
        source.layers["home_block"] = source.layers["home_block"].with_(sample_text=home)
    atlas = source.atlas()
    hud = Image.new("RGBA", HUD_SIZE, (0, 0, 0, 0))
    for name, (rect, cell) in template.LAYERS.items():
        tile = atlas.crop(rect).resize((cell[2] - cell[0], cell[3] - cell[1]), Image.Resampling.BILINEAR)
        hud.alpha_composite(tile, (cell[0], cell[1]))
    # The page writes a chosen state's centre text into the two centre layers'
    # sample text; an explicit state here (command line, guide) overrides it.
    texts = {name: (source.layers[name].sample_text or DEFAULT_SAMPLE_TEXT[name]) for name in TEXT_LAYERS}
    if state_id is not None:
        texts.update(current.text)
    clock_parts = (texts["clock_quarter"].split("|") + ["", "", ""])[:3]
    values = {"away_city": texts["away_block"], "away_score": texts["away_score"], "down": texts["down"],
              "quarter": clock_parts[0], "clock": clock_parts[1], "play_clock": clock_parts[2],
              "home_score": texts["home_score"], "home_city": texts["home_block"]}
    for field, rect, align, role, cap in SAMPLE_FIELDS:
        colour = text_colours[role]
        if role == "team" and ((field == "away_city") == (current.possession == "away")):
            colour = text_colours["possession"]
        _place_text(hud, values[field], rect, align, colour, cap)
    if current.timeouts:
        draw = ImageDraw.Draw(hud)
        for left, top, right, bottom in TIMEOUT_RECTS:
            step = (right - left) // 3
            for k in range(3):
                x = left + k * step
                draw.rectangle((x + 1, top, x + step - 3, bottom - 1), fill=(240, 240, 242, 255))
    if widescreen:
        narrow = hud.resize((HUD_SIZE[0] * WIDE_CONTRACTION[0] // WIDE_CONTRACTION[1], HUD_SIZE[1]), Image.Resampling.BILINEAR)
        contracted = Image.new("RGBA", HUD_SIZE, (0, 0, 0, 0))
        contracted.paste(narrow, ((HUD_SIZE[0] - narrow.size[0]) // 2, 0))
        hud = contracted.resize(WIDE_SIZE, Image.Resampling.BILINEAR)
        background = field_background(WIDE_SIZE)
    else:
        background = field_background(HUD_SIZE)
    background.alpha_composite(hud)
    return background.convert("RGB")


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Scorebar Studio documents: list presets, export, preview or check a folder.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("presets", help="List the preset registry")
    export = commands.add_parser("export", help="Write a template folder from a preset or a saved Studio folder")
    export.add_argument("--preset")
    export.add_argument("--open", type=Path, help="An existing template or Studio folder to start from")
    export.add_argument("--folder", type=Path, required=True, help="The folder to write")
    shot = commands.add_parser("preview", help="Render the preview PNG")
    shot.add_argument("--preset")
    shot.add_argument("--open", type=Path)
    shot.add_argument("--out", type=Path, required=True)
    shot.add_argument("--widescreen", action="store_true")
    shot.add_argument("--state", default="first_and_ten", choices=[s.id for s in STATES])
    shot.add_argument("--teams", nargs=2, metavar=("AWAY", "HOME"))
    check = commands.add_parser("validate", help="Compile a folder and print its receipt")
    check.add_argument("--folder", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "presets":
            for item in presets():
                print(f"{item.id}\t{item.title}\t{item.kind}\t{item.summary}")
            return 0
        if args.command == "validate":
            print(json.dumps(check_folder(args.folder), indent=2))
            return 0
        if args.open is not None:
            document = Document.open_folder(args.open)
        elif args.preset:
            document = Document.from_preset(args.preset)
        else:
            parser.error("choose --preset or --open")
        if args.command == "export":
            receipt = document.save_folder(args.folder)
            print(json.dumps({key: value for key, value in receipt.items() if key != "template"}, indent=2))
        else:
            image = preview(document, widescreen=args.widescreen, state_id=args.state,
                            team_preview=tuple(args.teams) if args.teams else None)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            image.save(args.out)
            print(f"{args.out} {image.size[0]}x{image.size[1]}")
    except AuthorError as exc:
        parser.exit(2, f"Scorebar Studio: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
