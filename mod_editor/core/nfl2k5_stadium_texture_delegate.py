"""Private edit-state delegate for the bounded NFL 2K5 stadium writer.

The delegate implements :class:`StadiumTextureEditDelegate` without wiring the
writer into the shared build backend.  A generation contains only the user's
PNG, its quantized preview, and metadata; rebuilt SCNE bytes remain in memory.
Publishing ``current.json`` is the single atomic commit point, so a failed
replace leaves the previous edit active.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import RLock
from uuid import uuid4

from .errors import ValidationError
from .json_stream import require_regular_file
from .nfl2k5_stadium_studio import StadiumTexture
from .nfl2k5_stadium_texture_writer import (
    CompiledStadiumTextureEdit,
    Nfl2k5StadiumTextureWriter,
    SHARED_OWNERSHIP_NOTE,
    TARGET_TEXTURE_ID,
)
from .platform_compat import fsync_directory


EDIT_SCHEMA = "2k5_mod_studio_private_stadium_texture_edit/v1"
POINTER_SCHEMA = "2k5_mod_studio_private_stadium_texture_pointer/v1"
TARGET_DIRECTORY = "o3280-c0005-scene2648-texture0002"
GENERATION_RE = re.compile(r"^[0-9a-f]{32}$")
COPY_BLOCK = 1024 * 1024


class StadiumTextureDelegateError(ValidationError):
    """Private stadium edit state is missing, unsafe, or inconsistent."""


@dataclass(frozen=True)
class StadiumTextureReplacement:
    texture_id: str
    authored_png: Path
    preview_png: Path
    replacement_png_sha256: str
    quantized_preview_png_sha256: str
    encoded_bytes: int
    scratch_after: int
    shared_ownership_note: str = SHARED_OWNERSHIP_NOTE


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StadiumTextureDelegateError(message)


def _safe_directory(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise StadiumTextureDelegateError(f"{label} is missing: {path}") from exc
    _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             f"{label} must be a private, non-link directory")
    return path.resolve(strict=True)


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            _require(written > 0, f"Short private edit write: {path.name}")
            position += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Nfl2k5Cement01TextureDelegate:
    """Exact ``cement01`` Replace/Revert bridge for Stadium Studio."""

    def __init__(
        self,
        writer: Nfl2k5StadiumTextureWriter,
        private_edit_root: Path | None = None,
    ) -> None:
        self.writer = writer
        cache_root = writer.cache.root.resolve(strict=True)
        selected = (
            private_edit_root.expanduser()
            if private_edit_root is not None
            else cache_root / "derived" / "stadium-texture-edits-v1"
        )
        selected.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if selected.exists():
            self.root = _safe_directory(selected, "private stadium edit directory")
        else:
            selected.mkdir(mode=0o700)
            self.root = selected.resolve(strict=True)
        os.chmod(self.root, 0o700)
        try:
            self.root.relative_to(cache_root)
        except ValueError as exc:
            raise StadiumTextureDelegateError(
                "Stadium edit state must stay inside the private SourceCache"
            ) from exc
        self.target_root = self.root / TARGET_DIRECTORY
        if self.target_root.exists():
            _safe_directory(self.target_root, "private stadium target directory")
        else:
            self.target_root.mkdir(mode=0o700)
        os.chmod(self.target_root, 0o700)
        self.generations = self.target_root / "generations"
        if self.generations.exists():
            _safe_directory(self.generations, "private stadium generations directory")
        else:
            self.generations.mkdir(mode=0o700)
        os.chmod(self.generations, 0o700)
        self.pointer = self.target_root / "current.json"
        self._compiled: dict[str, CompiledStadiumTextureEdit] = {}
        self._lock = RLock()

    def supports(self, texture: StadiumTexture) -> bool:
        return self.writer.supports(texture)

    def current_png(self, texture: StadiumTexture) -> Path:
        self._require_supported(texture)
        with self._lock:
            current = self._load_current()
            return current.preview_png if current is not None else texture.png_path

    def authored_png(self, texture: StadiumTexture) -> Path | None:
        """Return the user-authored PNG used for a later build, if modified."""

        self._require_supported(texture)
        with self._lock:
            current = self._load_current()
            return current.authored_png if current is not None else None

    def compiled_edit(self, texture: StadiumTexture) -> CompiledStadiumTextureEdit | None:
        """Compile the current generation, retaining retail bytes only in memory."""

        self._require_supported(texture)
        with self._lock:
            current = self._load_current()
            if current is None:
                return None
            cached = self._compiled.get(current.replacement_png_sha256)
            if cached is not None:
                return cached
            compiled = self.writer.compile(texture, current.authored_png)
            _require(
                compiled.replacement_png_sha256 == current.replacement_png_sha256,
                "Private stadium authored PNG changed before build",
            )
            self._compiled = {compiled.replacement_png_sha256: compiled}
            return compiled

    def replace(
        self, texture: StadiumTexture, supplied_png: Path
    ) -> StadiumTextureReplacement:
        self._require_supported(texture)
        # Compilation happens before the first edit-state mutation.  A PNG that
        # cannot fit the fixed SCNE allocation therefore leaves the current
        # generation untouched.
        compiled = self.writer.compile(texture, supplied_png)
        source = supplied_png.expanduser().resolve(strict=True)
        require_regular_file(source, "replacement stadium PNG")
        authored_payload = source.read_bytes()
        _require(
            hashlib.sha256(authored_payload).hexdigest()
            == compiled.replacement_png_sha256,
            "Replacement stadium PNG changed during compilation",
        )
        generation_name = uuid4().hex
        generation = self.generations / generation_name
        with self._lock:
            generation.mkdir(mode=0o700)
            published = False
            try:
                authored = generation / "authored.png"
                preview = generation / "preview.png"
                metadata = generation / "metadata.json"
                _write_exclusive(authored, authored_payload)
                _write_exclusive(preview, compiled.quantized_preview_png)
                document = {
                    "schema": EDIT_SCHEMA,
                    "texture_id": TARGET_TEXTURE_ID,
                    "generation": generation_name,
                    "authored_png": "authored.png",
                    "preview_png": "preview.png",
                    "replacement_png_sha256": compiled.replacement_png_sha256,
                    "quantized_preview_png_sha256": compiled.quantized_preview_png_sha256,
                    "compiled_metadata": compiled.public_metadata(),
                    "contains_retail_bytes": False,
                    "shareable": False,
                    "shared_ownership_note": SHARED_OWNERSHIP_NOTE,
                }
                _write_exclusive(metadata, _canonical_json(document))
                pointer_payload = _canonical_json({
                    "schema": POINTER_SCHEMA,
                    "texture_id": TARGET_TEXTURE_ID,
                    "generation": generation_name,
                })
                temporary_pointer = self.target_root / f".current.{generation_name}.tmp"
                _write_exclusive(temporary_pointer, pointer_payload)
                os.replace(temporary_pointer, self.pointer)
                # Commit the pointer rename's directory entry where the platform
                # provides that.  POSIX runs the same ``O_DIRECTORY`` flush this
                # opened by hand; Windows has no directory-flush primitive and
                # the helper reports that rather than pretending it committed.
                fsync_directory(self.target_root)
                published = True
                self._compiled = {compiled.replacement_png_sha256: compiled}
                result = self._load_current()
                _require(result is not None, "Published stadium edit could not be reloaded")
                return result
            finally:
                if not published:
                    self._remove_generation(generation_name)

    def revert(self, texture: StadiumTexture) -> bool:
        self._require_supported(texture)
        with self._lock:
            current = self._load_current()
            if current is None:
                return False
            pointer_info = self.pointer.lstat()
            _require(stat.S_ISREG(pointer_info.st_mode) and not stat.S_ISLNK(pointer_info.st_mode),
                     "Private stadium edit pointer is unsafe")
            self.pointer.unlink()
            self._compiled.clear()
            self._remove_generation(current.authored_png.parent.name)
            return True

    def _require_supported(self, texture: StadiumTexture) -> None:
        if not self.supports(texture):
            raise StadiumTextureDelegateError(
                "That stadium texture does not have a bounded replacement delegate"
            )

    def _load_current(self) -> StadiumTextureReplacement | None:
        if not self.pointer.exists():
            return None
        require_regular_file(self.pointer, "private stadium edit pointer")
        try:
            pointer = json.loads(self.pointer.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StadiumTextureDelegateError(
                f"Private stadium edit pointer is unreadable ({exc})"
            ) from exc
        _require(
            isinstance(pointer, dict)
            and pointer.get("schema") == POINTER_SCHEMA
            and pointer.get("texture_id") == TARGET_TEXTURE_ID,
            "Private stadium edit pointer is incompatible",
        )
        generation_name = pointer.get("generation")
        _require(
            isinstance(generation_name, str) and GENERATION_RE.fullmatch(generation_name),
            "Private stadium edit pointer has an unsafe generation",
        )
        generation = _safe_directory(
            self.generations / generation_name, "private stadium edit generation"
        )
        try:
            generation.relative_to(self.generations.resolve(strict=True))
        except ValueError as exc:
            raise StadiumTextureDelegateError(
                "Private stadium generation escapes its edit store"
            ) from exc
        metadata_path = generation / "metadata.json"
        authored = generation / "authored.png"
        preview = generation / "preview.png"
        for path, label in (
            (metadata_path, "private stadium edit metadata"),
            (authored, "private authored stadium PNG"),
            (preview, "private stadium preview PNG"),
        ):
            require_regular_file(path, label)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StadiumTextureDelegateError(
                f"Private stadium edit metadata is unreadable ({exc})"
            ) from exc
        _require(
            isinstance(metadata, dict)
            and metadata.get("schema") == EDIT_SCHEMA
            and metadata.get("texture_id") == TARGET_TEXTURE_ID
            and metadata.get("generation") == generation_name
            and metadata.get("authored_png") == "authored.png"
            and metadata.get("preview_png") == "preview.png"
            and metadata.get("contains_retail_bytes") is False
            and metadata.get("shareable") is False,
            "Private stadium edit metadata is incompatible",
        )
        authored_hash = metadata.get("replacement_png_sha256")
        preview_hash = metadata.get("quantized_preview_png_sha256")
        _require(
            isinstance(authored_hash, str) and _sha256(authored) == authored_hash,
            "Private authored stadium PNG no longer matches metadata",
        )
        _require(
            isinstance(preview_hash, str) and _sha256(preview) == preview_hash,
            "Private stadium preview no longer matches metadata",
        )
        compiled = metadata.get("compiled_metadata")
        _require(isinstance(compiled, dict), "Private stadium compiled metadata is missing")
        encoded_bytes = compiled.get("encoded_bytes")
        scratch_after = compiled.get("scratch_after")
        _require(
            isinstance(encoded_bytes, int) and not isinstance(encoded_bytes, bool)
            and isinstance(scratch_after, int) and not isinstance(scratch_after, bool),
            "Private stadium compression metadata is invalid",
        )
        return StadiumTextureReplacement(
            texture_id=TARGET_TEXTURE_ID,
            authored_png=authored,
            preview_png=preview,
            replacement_png_sha256=authored_hash,
            quantized_preview_png_sha256=preview_hash,
            encoded_bytes=encoded_bytes,
            scratch_after=scratch_after,
        )

    def _remove_generation(self, generation_name: str) -> None:
        if not GENERATION_RE.fullmatch(generation_name):
            raise StadiumTextureDelegateError("Refusing unsafe stadium generation cleanup")
        generation = self.generations / generation_name
        if not generation.exists():
            return
        resolved = _safe_directory(generation, "private stadium edit generation")
        _require(resolved.parent == self.generations.resolve(strict=True),
                 "Refusing stadium generation cleanup outside private store")
        allowed = {"authored.png", "preview.png", "metadata.json"}
        names = {path.name for path in resolved.iterdir()}
        _require(names <= allowed, "Private stadium generation has unexpected files")
        for name in sorted(names):
            path = resolved / name
            require_regular_file(path, f"private stadium generation {name}")
            path.unlink()
        resolved.rmdir()


__all__ = [
    "Nfl2k5Cement01TextureDelegate",
    "StadiumTextureDelegateError",
    "StadiumTextureReplacement",
]
