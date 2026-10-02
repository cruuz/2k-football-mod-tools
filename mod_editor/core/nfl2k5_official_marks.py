"""Optional local official presentation art. No image payloads ship with this module."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from . import platform_compat

SCHEMA = "nfl2k5_official_marks/v1"
ENVIRONMENT = "NFL2K5_MARKS_PACK"
MISSING = ("Official marks pack missing. Click Install SOFTDRINK 2K28 on the Share tab "
           "to bring the logos, use From a SOFTDRINK pack..., or choose a folder. "
           "Turn this option off to keep retail art.")
MAX_BYTES = 4 * 1024 * 1024
# These are the reviewed original PNG identities, not image data.
ASSETS = {
    "espnLogo1.png": "42573f5a4fe96698d5470ffc3984b85127847f485c10214681e7419d7428cb2c",
    "nfl_chiclet.png": "06062f839ceffaccc1b17a35c7a7105c541a72576431be89829bf859122af14f",
    "playercard_znfl_shield.png": "4a648238b2dce79330f90cb35763eb88a9a455a8432b4b1b5a6a12d41cc89eb6",
    "shield_espn.png": "b89b5f4df374bc23b78f9b284ff4d12cf412e2a89820fe2afa8c3589204fde54",
    "z_ESPN_bug.png": "8aaa2cbc8d9c54fa52de56b1890770f896407ae4c6cab13b64957787b0971c62"
}

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / "data/nfl2k5_official_marks_catalog.json").read_text())["assets"]
ASSETS.update({row["name"]: row["sha256"] for row in CATALOG.values()})
_PACK = ContextVar("official_marks_pack", default=None)


def selected_root(root=None):
    from .nfl2k5_marks_store import registered_root
    return root or _PACK.get() or os.environ.get(ENVIRONMENT, "") or registered_root()


@contextmanager
def using_pack(root=None):
    """Scope recipe selection without changing the process environment."""
    token = _PACK.set(selected_root(root))
    try:
        yield
    finally:
        _PACK.reset(token)


def resolve_path(path, root=None):
    """Resolve a product art path through the pack when it is externalized."""
    path = Path(path)
    try:
        relative = path.absolute().relative_to(ROOT).as_posix()
    except ValueError:
        return path
    row = CATALOG.get(relative)
    return asset_path(row["name"], root) if row else path


def validate_feature(feature, root=None):
    for row in CATALOG.values():
        if row["feature"] == feature:
            asset_path(row["name"], root)


def rgba(path, root=None):
    """Reassemble a lossless split, taking only the marked region from the pack."""
    import numpy as np
    from PIL import Image
    source = resolve_path(path, root)
    with Image.open(source) as image:
        original = image.convert("RGBA")
    try:
        relative = Path(path).absolute().relative_to(ROOT).as_posix()
    except ValueError:
        return np.asarray(original)
    row = CATALOG.get(relative, {})
    if "public_base" not in row:
        return np.asarray(original)
    public = ROOT / row["public_base"]
    if hashlib.sha256(public.read_bytes()).hexdigest() != row["public_sha256"]:
        raise ValueError("Official marks public split differs from its reviewed SHA-256")
    with Image.open(public) as image:
        result = image.convert("RGBA")
    for box in row["private_rects"]:
        result.paste(original.crop(box), box)
    if hashlib.sha256(result.tobytes()).hexdigest() != row["rgba_sha256"]:
        raise ValueError("Official marks split does not reconstruct the reviewed pixels")
    return np.asarray(result)


def requires_pack(feature):
    """Validate before opening a target; also accept an explicit local pack."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, marks_pack=None, **kwargs):
            with using_pack(marks_pack):
                validate_feature(feature)
                return function(*args, **kwargs)
        return wrapped
    return decorate


def build_scope(function):
    @wraps(function)
    def wrapped(plan, *args, **kwargs):
        if type(plan.official_marks_pack) is not str:
            raise ValueError("official_marks_pack must be a folder path (text)")
        with using_pack(plan.official_marks_pack):
            for feature in {row["feature"] for row in CATALOG.values()}:
                if feature not in {"espn_marks_2026", "espn_wipes_boards_2026"} and getattr(plan, feature, False):
                    validate_feature(feature)
            receipt = function(plan, *args, **kwargs)
            if any(getattr(plan, feature, False) for feature in
                   {row["feature"] for row in CATALOG.values()} | {"espn_marks_2026", "espn_wipes_boards_2026"}):
                receipt["official_marks_pack"] = str(platform_compat.absolute_path(selected_root()))
            return receipt
    return wrapped


def run_with_pack(function, job, root):
    """Carry recipe selection to fork, forkserver and spawn process workers."""
    with using_pack(root):
        return function(job)


def asset_path(name: str, root=None) -> Path:
    """Resolve one manifest-pinned regular PNG inside a supplied pack, with no cached availability."""
    selected = selected_root(root)
    if not selected:
        raise ValueError(MISSING)
    folder = platform_compat.io_path(platform_compat.absolute_path(selected))
    manifest = platform_compat.io_path(folder / "manifest.json")
    if not manifest.is_file():
        raise ValueError(MISSING)
    try:
        if manifest.is_symlink() or manifest.stat().st_size > MAX_BYTES:
            raise ValueError("manifest must be a small regular file")
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            raise ValueError("unsupported manifest schema")
        rows = doc.get("marks")
        if not isinstance(rows, dict) or set(rows) != set(ASSETS):
            raise ValueError("manifest must name all reviewed official marks")
        row = rows[name]
        if not isinstance(row, dict) or row.get("sha256") != ASSETS[name]:
            raise ValueError(f"{name}: manifest differs from the reviewed SHA-256")
        relative = Path(row["file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{name}: path escapes the pack")
        path = platform_compat.io_path(folder / relative)
        if not platform_compat.path_is_within(path, folder):
            raise ValueError(f"{name}: path must stay inside the pack")
        child = folder
        for component in relative.parts:
            child = platform_compat.io_path(child / component)
            if platform_compat.is_reparse_point(child):
                raise ValueError(f"{name}: path must stay inside the pack without links")
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError(f"{name}: missing or oversized PNG")
        if hashlib.sha256(path.read_bytes()).hexdigest() != ASSETS[name]:
            raise ValueError(f"{name}: PNG differs from the reviewed SHA-256")
        return path
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Official marks pack invalid: {exc}. Turn this option off to keep retail art.") from exc
