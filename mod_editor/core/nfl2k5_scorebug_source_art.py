"""ESPN scorebug inputs, resolved from the user's own disc instead of shipped files.

The public preview and availability helpers now use the v7 reference writer and
its shipped metadata. The following legacy-art resolvers remain for older tools;
their developer overrides and generated v6 textures do not control the v7 install.

The ESPN bar needs four things that used to live as loose files in a developer-only
``mod_editor/assets/nfl2k5_scorebug_espn`` folder, which is why the step reported
"Not available in this build" on every install that was not this workstation:

  ``score_bug_retail.scne``      the decoded retail score_bug scene (chunk 78 of outer 346)
  ``score_bug_retail_span.bin``  the retail compressed span that scene refits into
  ``NAVTEXTURE_retail.png``      a retail texture decoded to PNG
  ``score_buga_modern.png``      our repaint of the retail frame atlas
  ``shield_espn_modern.png``     our repaint of the retail ESPN mark
  ``digital_font_modern.png``    our repaint of the retail digit sheet

The first three are retail bytes; they can never ship.  The last three are our art, but
they are *derived* from the retail atlases (the repaints keep the retail alpha silhouette,
the retail letter mask, and one retail glyph cell), so they cannot ship either -- and the
release checker forbids ``.png`` and any ``assets/`` component precisely to keep that true.

None of them has to ship.  Every one is reproducible from the disc image the user already
supplies to the studio:

  (b) retail bytes         read out of the image at pinned pack-relative offsets and
                           verified by SHA-256 against the audited retail digests
  (c) derived data         the retail atlases decoded to RGBA PNGs, then the modern art
                           GENERATED from them by ``tools/nfl2k5_scorebug_espn_art.py``
                           -- shipped code, deterministic, and byte-identical to the art
                           the published SOFTDRINK patches were built with (pinned below
                           as :data:`ART_REFERENCE_SHA256` and recorded in every receipt)

Everything derived is cached under the studio's private, user-XISO-derived cache root, the
same place the model index lives, so a second build does no work.  When the developer asset
folder is present it still wins, unchanged, so this workstation's builds are bit-for-bit
what they were.

The ``digital_font`` repaint is the one piece that needs a system font (DejaVu Sans Bold) to
draw its digits.  Where that font is missing the atlas is simply not produced and the step
skips it, exactly as it already did when the PNG was absent; the bar itself never depends on
it.  ``NAVTEXTURE`` (the ticker-band atlas) has no generator -- it was hand-painted -- so it
stays a developer-only extra and the receipt says so rather than pretending otherwise.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import platform_compat

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
for _entry in (ROOT, TOOLS):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))


class ScorebugArtError(RuntimeError):
    """The scorebug's inputs could not be resolved from this source."""


# ---------------------------------------------------------------- pinned retail identities
AUDIT = ROOT / "reports" / "assets" / "scorebug_presentation_audit.json"
DEVELOPER_ASSETS = ROOT / "mod_editor" / "assets" / "nfl2k5_scorebug_espn"

# The three code-bound atlases are described by the shipped presentation audit
# (outer/chunk identity, pack-relative offset, span size, span + decoded SHA-256).
TEXTURE_NAMES = ("score_buga", "shield_espn", "digital_font")

# The ticker-band atlas is not in that audit, so its identity is pinned here.  Metadata
# only: offsets and digests, never payload.
NAVTEXTURE = {
    "name": "NAVTEXTURE",
    "outer_index": 346,
    "chunk_index": 34,
    "pack_path": "vc_53450030/0",
    "pack_offset": 110_157_728,
    "span_size": 7600,
    "span_sha256": "82fe5d54d718f9312355ca73bd0ee513bbd4581226dd607994ecd39b6d9e7502",
    "decoded_sha256": "e04b81bd213a7814285356def2715c19f7c9dfa289c9278e85a764b417af8a5c",
    "width": 128,
    "height": 128,
}

# The decoded retail score_bug scene (outer 346 chunk 78) and the compressed span it lives in.
SCNE_PACK_OFFSET = 110_486_272
SCNE_SPAN_SIZE = 0x20 + 4800
SCNE_SIZE = 16512
SCNE_SHA256 = "fc22e6caab35bc0f0b61d3a1014de9dfa0acfa6b8228fccf014f5ce0a17d1735"

PACK0_PATH = "vc_53450030/0"
PACK0_SIZE = 193_710_080

# What ``tools/nfl2k5_scorebug_espn_art.py`` produces from the retail atlases on the machine
# the published SOFTDRINK patches were built on.  The generator is pure pixel arithmetic for
# the two atlases the bar needs, so these are reproduced exactly anywhere; the digit sheet
# additionally renders text through the platform's DejaVu Sans Bold, whose FreeType version
# can move an anti-aliased edge.  A mismatch is recorded in the receipt, never hidden.
ART_REFERENCE_SHA256 = {
    "score_buga": "67b7c0a11efcf210dea9d9f8e4edf142f3a46bdb4d08c720645629e78c634b70",
    "shield_espn": "e92d08d3f6217d7310fd848071db1d880a1b890f293105de0bf212639f05b827",
    "digital_font": "c82d48644da2744cbf5386a9e7d6611ddfaab28ebe5906136edf835ee13f965a",
}
ART_FILE_NAMES = {
    "score_buga": "score_buga_modern.png",
    "shield_espn": "shield_espn_modern.png",
    "digital_font": "digital_font_modern.png",
}
# The ticker atlas has no generator; it ships in the published patches only.
TICKER_FILE_NAME = "NAVTEXTURE_modern.png"

CACHE_LEAF = Path("derived") / "scorebug"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read; Windows has no ``os.pread``, so seek/read/restore there."""
    reader = getattr(os, "pread", None)
    if reader is not None:
        return reader(fd, count, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.read(fd, count)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def _tools_module(name: str):
    import importlib

    return importlib.import_module(name)


# ------------------------------------------------------------------------ audit targets
_AUDIT_CACHE: dict[str, dict[str, Any]] | None = None


def texture_targets() -> dict[str, dict[str, Any]]:
    """``{name: target}`` for the four atlases, from the shipped audit plus the ticker pin."""

    global _AUDIT_CACHE
    if _AUDIT_CACHE is None:
        if not AUDIT.exists():
            # Legacy art export remains available in a checkout without research
            # reports. The v7 writer owns its smaller, independently pinned set.
            from .nfl2k5_scorebug_resources import RESOURCES, LEGACY_DIGITAL_FONT
            return {**{n:{**RESOURCES[n], "pack_path":PACK0_PATH} for n in ("score_buga","shield_espn")},
                    "digital_font":{**LEGACY_DIGITAL_FONT,"pack_path":PACK0_PATH},
                    "NAVTEXTURE":dict(NAVTEXTURE)}
        try:
            report = json.loads(AUDIT.read_text(encoding="utf-8"))
            rows = report["nfl2k5"]["texture_targets"]
        except (OSError, ValueError, KeyError) as exc:
            raise ScorebugArtError(f"the scorebug presentation audit is unreadable: {exc}") from exc
        found = {str(row.get("name")): row for row in rows if row.get("name") in TEXTURE_NAMES}
        if set(found) != set(TEXTURE_NAMES):
            raise ScorebugArtError("the scorebug presentation audit is missing a texture target")
        found[str(NAVTEXTURE["name"])] = dict(NAVTEXTURE)
        _AUDIT_CACHE = found
    return _AUDIT_CACHE


# ------------------------------------------------------------------------ reading the disc
def is_disc_image(source: Path) -> bool:
    """Whether ``source`` is an image whose retail-sized pack 0 can be located."""

    try:
        fd = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except OSError:
        return False
    try:
        pack0_extent(fd, os.fstat(fd).st_size)
    except Exception:  # noqa: BLE001 - not an image we can read the packs of
        return False
    finally:
        os.close(fd)
    return True


def pack0_extent(fd: int, size: int) -> tuple[int, int]:
    """``(absolute byte offset, size)`` of ``vc_53450030/0`` in the open image."""

    xc = _tools_module("nfl_uniform_color_xiso_direct_patch")
    try:
        offset, pack_size = xc.pack_extent(fd, size, "0")
    except Exception as exc:  # noqa: BLE001 - not an Xbox image, or no such pack: one message
        raise ScorebugArtError(f"{PACK0_PATH} could not be located in this file: {exc}") from exc
    if int(pack_size) != PACK0_SIZE:
        raise ScorebugArtError(
            f"{PACK0_PATH} in this image is {pack_size} bytes, not the retail {PACK0_SIZE}"
        )
    return int(offset), int(pack_size)


def read_pinned_span(fd: int, size: int, pack_offset: int, span_size: int,
                     expect_sha256: str, label: str) -> bytes:
    """One pinned span out of the open image's pack 0, verified against its retail digest."""

    base, _pack_size = pack0_extent(fd, size)
    absolute = base + int(pack_offset)
    if absolute + int(span_size) > size:
        raise ScorebugArtError(f"{label} lies past the end of this image")
    span = _pread(fd, int(span_size), absolute)
    if len(span) != int(span_size) or _sha(span) != expect_sha256:
        raise ScorebugArtError(
            f"{label} in this image is not the retail resource "
            f"(read {_sha(span)[:12]}, expected {expect_sha256[:12]})"
        )
    return span


def retail_texture_span(source: Path, name: str) -> bytes:
    """The retail compressed span of one scorebug atlas, read from ``source``."""

    target = texture_targets()[name]
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        return read_pinned_span(fd, os.fstat(fd).st_size, int(target["pack_offset"]),
                                int(target["span_size"]), str(target["span_sha256"]), name)
    finally:
        os.close(fd)


def retail_scne_span(source: Path) -> bytes:
    """The retail compressed span of the score_bug scene (chunk 78), read from ``source``."""

    fd = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        base, _pack_size = pack0_extent(fd, size)
        absolute = base + SCNE_PACK_OFFSET
        if absolute + SCNE_SPAN_SIZE > size:
            raise ScorebugArtError("the score_bug span lies past the end of this image")
        return _pread(fd, SCNE_SPAN_SIZE, absolute)
    finally:
        os.close(fd)


def decode_texture_png(span: bytes, width: int, height: int) -> bytes:
    """A retail P8 atlas span decoded to a strict RGBA8 PNG (the generator's input)."""

    txtr = _tools_module("nfl_txtr")
    palette_tools = _tools_module("nfl_tset_png_import")
    chunk = txtr.parse_chunks(span, allow_trailing=True)[0]
    decoded, _info = txtr.decode_chunk(span, chunk)
    indices = txtr.unswizzle_2d(decoded[128:128 + width * height], width, height, 1)
    palette = palette_tools.parse_palette(decoded[128:], width * height)
    return txtr.encode_rgba_png(width, height, palette_tools.rgba_from_indices(indices, palette))


# ------------------------------------------------------------------------ private cache
def cache_root() -> Path:
    from . import nfl2k5_source_cache

    return nfl2k5_source_cache.default_cache_root()


def cache_dir(*, create: bool = False) -> Path:
    """Where derived scorebug art lives: beside the model index, inside the private cache.

    Created one level at a time, each owner-only and then hardened and verified, the way
    :class:`~mod_editor.core.nfl2k5_source_cache.Nfl2k5SourceCache` does it -- a single
    ``mkdir(parents=True)`` would leave the intermediate directories at the process umask.
    """

    from . import nfl2k5_source_cache

    root = cache_root()
    levels = [root, root / nfl2k5_source_cache.SOURCE_SHA256]
    for part in CACHE_LEAF.parts:
        levels.append(levels[-1] / part)
    if create:
        for level in levels:
            platform_compat.create_private_directory(level, parents=level is root, exist_ok=True)
            platform_compat.harden_private_directory(level)
        platform_compat.verify_private_root_placement(
            root, "The private NFL 2K5 source cache root")
    return levels[-1]


def _cached_read(path: Path, expect_sha256: str | None) -> bytes | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        payload = path.read_bytes()
    except OSError:
        return None
    if expect_sha256 is not None and _sha(payload) != expect_sha256:
        return None
    return payload


def _cache_write(name: str, payload: bytes) -> Path | None:
    """Best effort: a cache that cannot be written must never fail a build."""

    try:
        folder = cache_dir(create=True)
        destination = folder / name
        # A unique sibling keeps concurrent cache writes separate and paths short.
        temporary = platform_compat.temporary_sibling(destination)
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
        return destination
    except Exception:  # noqa: BLE001 - a cache that cannot be written never fails a build
        return None


GENERATOR = TOOLS / "nfl2k5_scorebug_espn_art.py"
CACHE_MARKER = "cache.json"


def _generator_digest() -> str:
    """SHA-256 of the art generator, so a changed generator invalidates cached art.

    Without this a build after an art change would keep serving the previous run's PNGs
    forever: they are derived data with no other version to compare against.
    """

    try:
        return _sha(GENERATOR.read_bytes())
    except OSError:
        return ""


def _cache_is_current() -> bool:
    marker = _cached_read(cache_dir() / CACHE_MARKER, None)
    if marker is None:
        return False
    try:
        value = json.loads(marker)
    except ValueError:
        return False
    return (isinstance(value, dict)
            and value.get("generator_sha256") == _generator_digest()
            and value.get("reference") == ART_REFERENCE_SHA256)


def _stamp_cache() -> None:
    _cache_write(CACHE_MARKER, json.dumps(
        {"generator_sha256": _generator_digest(), "reference": ART_REFERENCE_SHA256},
        indent=1, sort_keys=True).encode("utf-8"))


# ------------------------------------------------------------------------ the retail scene
def retail_scne(source: Path | None) -> bytes:
    """The decoded retail score_bug scene: developer copy, private cache, or ``source``.

    ``source`` may be ``None`` when only the cached or developer copy is wanted (the status
    probe has no image to read when the disc's own chunk is already modified).
    """

    developer = _cached_read(DEVELOPER_ASSETS / "score_bug_retail.scne", SCNE_SHA256)
    if developer is not None:
        return developer
    cached = _cached_read(cache_dir() / "score_bug_retail.scne", SCNE_SHA256)
    if cached is not None:
        return cached
    if source is None:
        raise ScorebugArtError("the retail score_bug scene is not cached and no disc image was given")
    span = retail_scne_span(Path(source))
    txtr = _tools_module("nfl_txtr")
    try:
        chunk = txtr.parse_chunks(span, allow_trailing=True)[0]
        decoded, _info = txtr.decode_chunk(span, chunk)
    except Exception as exc:  # noqa: BLE001 - one user-facing message
        raise ScorebugArtError(f"the score_bug resource in this image did not decode: {exc}") from exc
    if len(decoded) != SCNE_SIZE or _sha(decoded) != SCNE_SHA256:
        raise ScorebugArtError(
            "the score_bug scene in this image is not the retail one (already modified?)"
        )
    remember_retail_scne(decoded)
    return decoded


def remember_retail_scne(decoded: bytes) -> Path | None:
    """Keep a retail scene we have just decoded, so a later status probe needs no image."""

    if len(decoded) != SCNE_SIZE or _sha(decoded) != SCNE_SHA256:
        return None
    if (DEVELOPER_ASSETS / "score_bug_retail.scne").is_file():
        return None
    existing = cache_dir() / "score_bug_retail.scne"
    if _cached_read(existing, SCNE_SHA256) is not None:
        return existing
    return _cache_write("score_bug_retail.scne", bytes(decoded))


# ------------------------------------------------------------------------ the modern art
def _generate(name: str, retail_png: bytes) -> bytes:
    """Run the shipped generator for one atlas over its retail PNG."""

    import io

    art = _tools_module("nfl2k5_scorebug_espn_art")
    from PIL import Image

    retail = Image.open(io.BytesIO(retail_png))
    retail.load()
    if name == "score_buga":
        image = art.atlas(retail)
    elif name == "shield_espn":
        image = art.espn_mark(retail)
    elif name == "digital_font":
        if not art.have_text_font():
            raise ScorebugArtError("no DejaVu Sans Bold to draw the digit sheet with")
        image = art.digits(retail)
    else:
        raise ScorebugArtError(f"no generator for {name}")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def resolve_art(source: Path | None) -> dict[str, Any]:
    """Locate every scorebug PNG the writer needs, deriving what is missing from ``source``.

    Returns ``{"art": {role: Path}, "origin": {role: "developer"|"cache"|"derived"},
    "reference_match": {role: bool}, "skipped": {role: reason}}``.  Roles that could not be
    produced are absent from ``art`` and named in ``skipped``; the two atlases the bar itself
    needs (``score_buga``, ``shield_espn``) raise instead, because without them there is no bar.
    """

    art: dict[str, Path] = {}
    origin: dict[str, str] = {}
    match: dict[str, bool] = {}
    skipped: dict[str, str] = {}
    required = ("score_buga", "shield_espn")
    current = _cache_is_current()
    stamped = current

    for role in TEXTURE_NAMES:
        file_name = ART_FILE_NAMES[role]
        developer = DEVELOPER_ASSETS / file_name
        if developer.is_file() and not developer.is_symlink():
            art[role] = developer
            origin[role] = "developer"
            match[role] = _sha(developer.read_bytes()) == ART_REFERENCE_SHA256[role]
            continue
        cached = cache_dir() / file_name
        payload = _cached_read(cached, None) if current else None
        if payload is not None:
            art[role] = cached
            origin[role] = "cache"
            match[role] = _sha(payload) == ART_REFERENCE_SHA256[role]
            continue
        if source is None:
            reason = "no disc image to derive it from"
            if role in required:
                raise ScorebugArtError(f"{file_name}: {reason}")
            skipped[role] = reason
            continue
        try:
            target = texture_targets()[role]
            span = retail_texture_span(Path(source), role)
            retail_png = decode_texture_png(span, int(target["width"]), int(target["height"]))
            produced = _generate(role, retail_png)
        except (ScorebugArtError, OSError, ValueError, KeyError, ImportError) as exc:
            if role in required:
                raise ScorebugArtError(f"{file_name} could not be derived from this image: {exc}") from exc
            skipped[role] = str(exc)
            continue
        written = _cache_write(file_name, produced)
        if written is None:
            reason = "the private cache could not be written"
            if role in required:
                raise ScorebugArtError(f"{file_name}: {reason}")
            skipped[role] = reason
            continue
        art[role] = written
        origin[role] = "derived"
        match[role] = _sha(produced) == ART_REFERENCE_SHA256[role]
        if not stamped:
            _stamp_cache()
            stamped = True

    ticker = DEVELOPER_ASSETS / TICKER_FILE_NAME
    if ticker.is_file() and not ticker.is_symlink():
        art["NAVTEXTURE"] = ticker
        origin["NAVTEXTURE"] = "developer"
    else:
        skipped["NAVTEXTURE"] = "the ticker-band atlas is hand-painted; no generator ships"

    return {"art": art, "origin": origin, "reference_match": match, "skipped": skipped}


PREVIEW_FILE_NAME = "preview_espn.png"


def _legacy_preview_mockup(source: Path | None) -> Path | None:
    """The Presentation tab's planned-look mockup: developer copy, cache, or rendered here.

    The mockup is a render of the edited mesh with the repainted mark wrapped onto it, so it
    is as derivable as everything else -- the panel no longer has to say "mockup not shipped
    in this build" once the user has pointed the studio at their disc.  Returns ``None`` when
    it cannot be produced; a missing picture never fails anything.
    """

    developer = DEVELOPER_ASSETS / PREVIEW_FILE_NAME
    if developer.is_file() and not developer.is_symlink():
        return developer
    cached = cache_dir() / PREVIEW_FILE_NAME
    # the mockup wraps the repainted mark onto the mesh, so a changed generator restales it too
    if cached.is_file() and not cached.is_symlink() and _cache_is_current():
        return cached
    if source is None:
        return None
    try:
        layout = _tools_module("nfl2k5_scorebug_layout")
        scene = retail_scne(Path(source))
        art = resolve_art(Path(source))
        mesh = layout.Mesh(scene)
        layout.espn_layout(mesh)
        folder = cache_dir(create=True)
        # keep the .png suffix: the renderer picks its image format from the file name
        temporary = platform_compat.temporary_sibling(
            folder / PREVIEW_FILE_NAME, suffix=".png"
        )
        layout.preview(mesh, temporary, mark_png=art["art"].get("shield_espn"))
        os.replace(temporary, folder / PREVIEW_FILE_NAME)
    except Exception:  # noqa: BLE001 - a mockup is never worth failing a panel over
        return None
    return folder / PREVIEW_FILE_NAME


def _legacy_available() -> bool:
    """Whether this build can produce the scorebug's art at all (given a disc image).

    True when the generator, the audit and Pillow are present -- the retail inputs are the
    user's disc, checked when the build actually runs, not here.
    """

    try:
        _tools_module("nfl2k5_scorebug_espn_art")
        _tools_module("nfl_txtr")
        _tools_module("nfl_tset_png_import")
        import PIL.Image  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return AUDIT.is_file()


def preview_mockup(source: Path | None) -> Path | None:
    """Studio preview of the installable v7 data, without claiming live team logos."""
    if source is None:
        return None
    try:
        from . import nfl2k5_scorebug_ingame as reference
        layout = _tools_module("nfl2k5_scorebug_layout")
        mesh, texture = reference.preview_data(Path(source))
        folder = cache_dir(create=True).resolve()
        import tempfile
        fd, name = tempfile.mkstemp(prefix=".reference-", suffix=".png", dir=folder)
        os.close(fd)
        temporary = Path(name).resolve()
        try:
            layout.preview_reference(mesh, texture, temporary)
            output = folder / "preview_reference_v7.png"
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return output
    except (Exception, SystemExit):
        return None


def available() -> bool:
    """V7 uses its shipped metadata pins, independent of the old research audit."""
    try:
        from . import nfl2k5_scorebug_ingame, nfl2k5_scorebug_resources
        import PIL.Image
        return bool(nfl2k5_scorebug_resources.PATCHED_SHA256)
    except ImportError:
        return False
