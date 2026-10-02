"""Neutral rectangles for public compiler tests, never official-mark image fixtures."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_official_marks as official


def synthetic_pack(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    sizes = {"nfl_chiclet.png": (64, 64), "shield_espn.png": (128, 64),
             "espnLogo1.png": (64, 64), "z_ESPN_bug.png": (64, 64),
             "playercard_znfl_shield.png": (64, 64)}
    # Use the public descriptor dimensions, avoiding assumptions about the consumer.
    from mod_editor.core import nfl2k5_espn_marks as marks
    for row in marks._pins()["marks"]:
        sizes[row["png"]] = (row["width"], row["height"])
    from mod_editor.core import nfl2k5_espn_wipes_boards as wipes
    for resource in wipes._pins()["resources"]:
        for row in resource["textures"]:
            relative = (wipes.ART_DIR / row["png"]).relative_to(official.ROOT).as_posix()
            if relative in official.CATALOG:
                sizes[official.CATALOG[relative]["name"]] = (row["width"], row["height"])
    for name in official.ASSETS:
        sizes.setdefault(name, (64, 64))
    pins = {}
    for name, size in sizes.items():
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((2, 2, size[0] - 3, size[1] - 3), fill=(80, 160, 220, 255))
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        image.save(root / name)
        pins[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps({"schema": official.SCHEMA,
        "marks": {name: {"file": name, "sha256": sha} for name, sha in pins.items()}}))
    return pins


def install_for_class(cls, root):
    """Use a real explicitly configured pack, otherwise scoped neutral test pins."""
    if os.environ.get(official.ENVIRONMENT):
        return
    stack = ExitStack()
    cls.addClassCleanup(stack.close)
    pins = synthetic_pack(root)
    stack.enter_context(mock.patch.dict(official.ASSETS, pins, clear=True))
    stack.enter_context(mock.patch.dict(os.environ, {official.ENVIRONMENT: str(root)}))


def requires_real_pack(feature):
    """Skip absent optional art, but never hide an invalid configured pack."""
    from functools import wraps
    import unittest
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not official.selected_root():
                raise unittest.SkipTest("official marks pack absent")
            official.validate_feature(feature)
            return function(*args, **kwargs)
        return wrapped
    return decorate


def softdrink_pack(root, *, memory=True, include_marks=True):
    """Tiny synthetic format-3 pack, including unrelated authoring assets."""
    from mod_editor.core import modpack_files as files, xdvdfs_compact
    from tests.mod_editor.test_modpack_files import image
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    pins = synthetic_pack(root / "marks")
    assets = {"assets/trees/logos/" + name: root / "marks" / name
              for name in (*pins, "manifest.json")} if include_marks else {}
    project = root / "project.json"
    project.write_text('{"edits": []}')
    assets["assets/documents/project.json"] = project
    overrides = {"k128_memory": memory}
    if include_marks:
        overrides["official_marks_pack"] = "@pack/assets/trees/logos"
    recipe = dict(schema="softdrink_sources/v1", preset="softdrink_experimental", overrides=overrides,
                  project="@pack/assets/documents/project.json")
    base = image(root / "base.iso", {"default.xbe": b"XBEHsynthetic", "art": b"old"})
    raw = image(root / "raw.iso", {"default.xbe": b"XBEHsynthetic", "art": b"new"})
    built = root / "built.iso"
    xdvdfs_compact.compact_copy(raw, built)
    pack = root / "softdrink.2k5patch"
    files.export(base, built, pack, name="SOFTDRINK 2K28", recipe=recipe,
                 source_assets=assets, require_retail=False)
    return pack, pins
