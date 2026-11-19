"""The picture the game draws for a player's Photo id (b81 R11, Finn's header portrait and photo picker).

A roster record's Photo id (+0x06) selects one of three kinds of picture:

* ``0000``-``9999`` that the shipped portrait catalogue lists (``reports/assets/nfl2k5_player_portrait_compatibility.json``,
  4,303 ids): a 128 x 128 P8 texture in the disc's pack 0. It is read from the private source cache the Studio makes when
  you open your original disc. An enabled artwork project or a staged session replacement supplies the authored
  PNG for its selected ids. The preview uses the same 256-colour RGBA palette as the game writer.
* ``30000``-``31199``: the real NFL headshots ``nfl2k5_real_portraits`` ships (data/nfl2k5_real_portraits), and the
  fictional draft faces ``nfl2k5_rookie_faces`` ships (data/nfl2k5_rookie_faces, ids 10000-21695 and their legacy ids).
  Both are added to the disc by the Rookie faces Build option, which is also what writes those ids into a roster.
* ``7100`` and ``21696`` and above (the no-photo selectors), and any other id: the game draws its ``nophoto`` silhouette.

Nothing here writes anything; a preview that cannot be read says why instead of guessing.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from functools import lru_cache
from dataclasses import dataclass
import io
import json
from pathlib import Path
import sys
from typing import Any

from .errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
SIZE = 128
CACHE_PICTURES = 256
CACHE_ATLASES = 4


@dataclass(frozen=True)
class Portrait:
    photo: int
    kind: str                  # catalogue | real | rookie | none
    rgba: bytes | None         # SIZE * SIZE * 4 bytes, or None when there is no picture to show
    note: str                  # where the picture comes from, or why there is none

    @property
    def available(self) -> bool:
        return self.rgba is not None


def _tools() -> None:
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))


def _file_version(path: Path) -> tuple[int, ...]:
    from .platform_compat import change_time_identity

    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, *change_time_identity(info)


@lru_cache(maxsize=2)
def _project_portraits(path: Path, version: tuple[int, ...]) -> dict[int, Path]:
    from .nfl2k5_build_service import Nfl2k5BuildService

    source, document = Nfl2k5BuildService._project_document(path)
    portraits: dict[int, Path] = {}
    for row in document["edits"]:
        if row["kind"] != "player_portrait":
            continue
        number = row.get("portrait_id")
        png = row.get("png")
        if (not isinstance(number, str) or len(number) != 4 or not number.isascii() or not number.isdigit()
                or not isinstance(png, str) or not png):
            raise ValueError("the selected project has an invalid player portrait")
        photo = int(number)
        if photo in portraits:
            raise ValueError(f"the selected project repeats portrait {number}")
        portraits[photo] = source.parent / png
    return portraits


@lru_cache(maxsize=CACHE_PICTURES)
def _authored_rgba(path: Path, version: tuple[int, ...]) -> bytes:
    """Project PNG after the portrait writer's weighted median-cut and nearest RGBA palette mapping."""
    _tools()
    import nfl_player_portrait_png_import as writer
    import numpy as np

    _, _, raw = writer.read_png(path)
    pixels = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)
    colors, inverse, counts = np.unique(pixels, axis=0, return_inverse=True, return_counts=True)
    histogram = Counter(dict(zip(map(tuple, colors.tolist()), counts.tolist())))
    palette = np.asarray(writer.palette_tools.median_cut_palette(histogram, 256), dtype=np.int32)
    # The square of the source pixel is constant across the palette. Integer argmin preserves the
    # writer's first-index tie rule. Work a few hundred colours at a time on the UI thread.
    squared = (palette * palette).sum(axis=1, dtype=np.int32)
    nearest = np.empty(len(colors), dtype=np.intp)
    for start in range(0, len(colors), 512):
        batch = colors[start:start + 512].astype(np.int32)
        nearest[start:start + len(batch)] = (squared - 2 * (batch @ palette.T)).argmin(axis=1)
    return palette.astype(np.uint8)[nearest[inverse.reshape(-1)]].tobytes()


class PortraitPreviews:
    """Decoded pictures by Photo id, cached. ``pack0`` is the source cache's pack 0 (None: catalogue ids unavailable)."""

    def __init__(self, pack0: Path | str | None = None, *, report: Path | str | None = None,
                 pack0_reason: str = "") -> None:
        from . import nfl2k5_roster_records as rr
        self.pack0 = Path(pack0) if pack0 else None
        self.report = Path(report) if report else rr.PORTRAIT_REPORT
        self.pack0_reason = pack0_reason or "open your original game disc in the Studio (top right) to see these photos"
        self._pictures: OrderedDict[int, Portrait] = OrderedDict()
        self._atlases: OrderedDict[str, Any] = OrderedDict()
        self._targets: dict[int, Any] | None = None
        self._archive = None
        self._real: dict[int, dict[str, Any]] | None = None
        self._rookie: dict[int, dict[str, Any]] | None = None
        self._failure: dict[str, str] = {}

    # ------------------------------------------------------------------ lookups
    def _catalogue(self) -> dict[int, Any]:
        if self._targets is None:
            self._targets = {}
            try:
                _tools()
                import nfl_player_portrait_targets as targets  # noqa: PLC0415
                _path, _payload, value = targets.load_report(self.report)
                for record in value["targets"]:
                    target = targets.PortraitTarget.from_record(record)
                    self._targets[target.portrait_id] = target
            except (OSError, ValueError, KeyError) as exc:
                self._failure["catalogue"] = f"the portrait catalogue could not be read ({exc})"
        return self._targets

    def _real_rows(self) -> dict[int, dict[str, Any]]:
        if self._real is None:
            self._real = {}
            try:
                from . import nfl2k5_real_portraits as real  # noqa: PLC0415
                doc = real.load_manifest()
                self._real = {int(row["id"]): {**row, "_dir": real.DATA_DIR, "_pins": {
                    a["file"]: a["sha256"] for a in doc["atlases"]}, "_rgba": True} for row in doc["portraits"]}
            except (OSError, ValueError, KeyError) as exc:
                self._failure["real"] = f"the real portrait set could not be read ({exc})"
        return self._real

    def _rookie_rows(self) -> dict[int, dict[str, Any]]:
        if self._rookie is None:
            self._rookie = {}
            try:
                from . import nfl2k5_rookie_faces as rookie  # noqa: PLC0415
                bank = json.loads(rookie.BANK_JSON.read_text(encoding="utf-8"))
                pins = {a["file"]: a["sha256"] for a in bank["atlases"]}
                for face in bank["faces"]:
                    row = {**face, "_dir": rookie.DATA_DIR, "_pins": pins, "_rgba": False}
                    for key in ("id", "legacy_id"):
                        if face.get(key) is not None:
                            self._rookie[int(face[key])] = row
            except (OSError, ValueError, KeyError) as exc:
                self._failure["rookie"] = f"the draft face bank could not be read ({exc})"
        return self._rookie

    def kind(self, photo: int) -> str:
        from . import nfl2k5_real_portraits as real
        photo = int(photo)
        if photo in self._catalogue():
            return "catalogue"
        if real.ID_BASE <= photo < real.ID_LIMIT and photo in self._real_rows():
            return "real"
        if photo in self._rookie_rows():
            return "rookie"
        return "none"

    # ------------------------------------------------------------------ pictures
    def picture(self, photo: int, *, league_project: Path | None = None,
                staged_png: Path | None = None, rookie_faces: bool | None = None) -> Portrait:
        photo = int(photo)
        if 0 <= photo <= 9999 and (league_project is not None or staged_png is not None):
            try:
                if staged_png is not None and league_project is not None:
                    raise ValueError("both the open project and the league artwork have edits; select one in Build & Share")
                art = staged_png
                if art is None and league_project is not None:
                    art = _project_portraits(league_project, _file_version(league_project)).get(photo)
                if art is not None:
                    if photo not in self._catalogue():
                        raise ValueError(f"portrait {photo:04d} has no target in the game catalogue")
                    return Portrait(photo, "catalogue", _authored_rgba(art, _file_version(art)),
                                    f"Portrait {photo:04d} from the selected project, in the game's 256-colour palette.")
            except (OSError, ValueError, ValidationError) as exc:
                return Portrait(photo, "catalogue", None, f"Photo {photo}: cannot read selected artwork ({exc}).")
        if rookie_faces is False and self.kind(photo) in ("real", "rookie"):
            return Portrait(photo, "none", None, "No photo: the selected disc uses the original portrait bank.")
        cached = self._pictures.get(photo)
        if cached is not None:
            self._pictures.move_to_end(photo)
            return cached
        kind = self.kind(photo)
        try:
            if kind == "catalogue":
                result = self._catalogue_picture(photo)
            elif kind in ("real", "rookie"):
                row = (self._real_rows() if kind == "real" else self._rookie_rows())[photo]
                words = ("Real NFL headshot" if kind == "real" else "Draft prospect face")
                result = Portrait(photo, kind, self._atlas_cell(row),
                                  f"{words} {photo}, on discs built with the Rookie faces option.")
            else:
                reason = self._failure.get("catalogue", "")
                result = Portrait(photo, "none", None,
                                  "No photo: the game shows its 'no photo' picture for this id."
                                  + (f" ({reason})" if reason else ""))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            result = Portrait(photo, kind, None, f"Photo {photo}: the picture could not be read ({exc}).")
        if result.rgba is not None or kind == "none":
            self._pictures[photo] = result
            while len(self._pictures) > CACHE_PICTURES:
                self._pictures.popitem(last=False)
        return result

    def _catalogue_picture(self, photo: int) -> Portrait:
        if self.pack0 is None or not self.pack0.is_file():
            return Portrait(photo, "catalogue", None, f"Portrait {photo:04d} is on the disc; {self.pack0_reason}.")
        _tools()
        from nfl_outer import parse_archive, read_entry_range  # noqa: PLC0415
        import nfl_player_portrait_png_import as portrait_import  # noqa: PLC0415
        from nfl_txtr import texture_to_rgba  # noqa: PLC0415
        target = self._catalogue()[photo]
        if self._archive is None:
            self._archive = parse_archive(self.pack0)
        entry = self._archive.entries[target.outer_index]
        if entry.name_id != target.outer_id or entry.size != target.outer_size:
            raise ValueError("this archive's portrait block differs from the catalogue")
        span = read_entry_range(self._archive, entry, target.chunk_offset, target.span_size)
        chunk, decoded, texture = portrait_import.validate_span(span, target)
        rgba = texture_to_rgba(decoded, chunk, texture)
        if len(rgba) != SIZE * SIZE * 4:
            raise ValueError("the portrait is not 128 x 128")
        return Portrait(photo, "catalogue", bytes(rgba),
                        f"Portrait {photo:04d} from your original disc.")

    def _atlas(self, folder: Path, name: str, pin: str):
        from PIL import Image  # noqa: PLC0415
        key = str(folder / name)
        image = self._atlases.get(key)
        if image is None:
            import hashlib  # noqa: PLC0415
            data = (folder / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != pin:
                raise ValueError(f"{name} does not match its pin")
            image = Image.open(io.BytesIO(data))
            image.load()
            self._atlases[key] = image
            while len(self._atlases) > CACHE_ATLASES:
                self._atlases.popitem(last=False)
        else:
            self._atlases.move_to_end(key)
        return image

    def _atlas_cell(self, row: dict[str, Any]) -> bytes:
        folder, pins = row["_dir"], row["_pins"]
        atlas = str(row["atlas"])
        index = self._atlas(folder, atlas, pins[atlas])
        palette_name = atlas[:-4] + "_pal.png"
        palette = self._atlas(folder, palette_name, pins[palette_name])
        if index.mode != "L":
            raise ValueError("a face atlas must be 8-bit indices")
        col, line = row["cell"]
        cell = index.crop((col * SIZE, line * SIZE, col * SIZE + SIZE, line * SIZE + SIZE)).tobytes()
        strip = palette.convert("RGBA" if row["_rgba"] else "RGB").crop((0, line * 16 + col, 256, line * 16 + col + 1))
        colours = strip.tobytes()
        if row["_rgba"]:
            return b"".join(colours[4 * i:4 * i + 4] for i in cell)
        return b"".join(colours[3 * i:3 * i + 3] + b"\xff" for i in cell)


_SHARED: dict[tuple[str, str], PortraitPreviews] = {}


def previews_for(pack0: Path | str | None, *, reason: str = "") -> PortraitPreviews:
    """One cache per source pack (the catalogue and atlases are read once a session)."""

    key = (str(pack0 or ""), reason)
    if key not in _SHARED:
        _SHARED.clear()                 # a newly opened disc replaces the old one
        _SHARED[key] = PortraitPreviews(pack0, pack0_reason=reason)
    return _SHARED[key]


__all__ = ["Portrait", "PortraitPreviews", "previews_for", "SIZE"]


def _main(argv: list[str]) -> int:      # python -m mod_editor.core.nfl2k5_portrait_preview PACK0 ID OUT.png
    from PIL import Image  # noqa: PLC0415
    previews = PortraitPreviews(argv[0] or None)
    picture = previews.picture(int(argv[1]))
    print(picture.kind, picture.note)
    if picture.rgba is not None:
        Image.frombytes("RGBA", (SIZE, SIZE), picture.rgba).save(argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
