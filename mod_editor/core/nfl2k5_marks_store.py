"""Keep reviewed logos from a user's SOFTDRINK pack for later Studio builds."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid
import zipfile

from . import modpack as m, modpack_files as f, platform_compat

MEMORY_TIP = ("Set xemu's System Memory to 128 MB (Settings, System). "
              "At the default 64 MB it still plays, but at some stadiums the pregame show "
              "repeats until you press A.")


def state_root():
    """Use Studio's per-user product folder, never the installation directory."""
    if platform_compat.IS_WINDOWS:
        base = platform_compat.user_private_root()
    elif sys.platform == "darwin":
        base = platform_compat.user_private_root() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or
                    platform_compat.user_private_root() / ".local" / "share").expanduser()
    return f._path(platform_compat.absolute_path(base / "2k5-mod-studio" / "official-marks"))


def registered_source():
    """Read the atomically published selection; consumers recheck image pins."""
    try:
        root = state_root()
        pointer = f._contained_path(root, "current.json")
        doc = json.loads(m._read_small_file(pointer, "saved logos", 16384))
        if not isinstance(doc, dict) or not all(isinstance(doc.get(key), str) for key in
                                               ("folder", "name", "version", "sha256", "saved_at")):
            return None
        name = doc["folder"]
        if not isinstance(name, str) or not name.startswith("logos-") or not platform_compat.portable_component(name):
            return None
        folder = f._contained_path(root, name)
        if not folder.is_dir():
            return None
        return dict(doc, folder=str(folder))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def registered_root():
    source = registered_source()
    return source["folder"] if source else ""


def register_pack(pack):
    """Extract only the declared marks tree, validate every pin, then publish it.

    Each generation is immutable. A failed extraction or pointer replacement
    leaves the previous selection intact, including across concurrent saves.
    """
    from . import nfl2k5_official_marks as marks
    pack = pack if isinstance(pack, m.Pack) else m.load(pack)
    overrides = pack.manifest.recipe.get("overrides", {})
    m._require(isinstance(overrides, dict), "SOFTDRINK recipe overrides must be an object")
    token = overrides.get("official_marks_pack")
    if not token:
        return None
    m._require(isinstance(token, str) and token.startswith("@pack/assets/trees/"),
               "Official marks must name an asset tree inside the SOFTDRINK pack")
    member = token[len("@pack/"):]
    f._asset_name(member)
    assets = [a for a in pack.manifest.raw.get("assets", []) if a["member"].startswith(member + "/")]
    m._require(bool(assets), "The SOFTDRINK pack does not contain its declared logos")
    m._require(len(assets) <= len(marks.ASSETS) + 1 and
               all(a["length"] <= marks.MAX_BYTES for a in assets), "Official marks tree is too large")
    def stamp():
        info = pack.path.stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    before = stamp()
    sha = m.hash_file(pack.path)
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    source = dict(name=pack.manifest.name, version=pack.manifest.version, sha256=sha,
                  saved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  folder="logos-" + uuid.uuid4().hex)
    # Reuse the pack extractor's path, length and streamed SHA-256 checks.
    subset = m.Pack(pack.path, replace(pack.manifest, recipe={},
                    raw=dict(pack.manifest.raw, assets=assets)), pack.size)
    with tempfile.TemporaryDirectory(prefix=".saving-", dir=root) as temporary:
        stage = f._path(temporary)
        f.extract_assets(subset, stage)
        tree = f._contained_path(stage, member)
        for name in marks.ASSETS:
            marks.asset_path(name, tree)
        m._require(before == stamp(), "SOFTDRINK pack changed while saving its logos")
        m._require(not f._path(tree / "source.json").exists(), "Official marks tree uses the reserved source record name")
        f._path(tree / "source.json").write_text(json.dumps(source, indent=2), encoding="utf-8", newline="\n")
        destination = f._contained_path(root, source["folder"])
        os.rename(tree, destination)
        try:
            with f._transaction(f._contained_path(root, "current.json"), overwrite=True) as part:
                part.write_text(json.dumps(source, indent=2), encoding="utf-8", newline="\n")
        except Exception:
            # This generation was never published, so it has no readers.
            import shutil
            shutil.rmtree(destination)
            raise
    return dict(source, folder=str(destination))


def memory_tip(pack):
    overrides = pack.manifest.recipe.get("overrides", {})
    return MEMORY_TIP if isinstance(overrides, dict) and overrides.get("k128_memory") is True else ""


def try_register(pack):
    """Save the pack's logos when possible; return (source or None, error text or "")."""
    try:
        return register_pack(pack), ""
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        return None, f"The logos could not be saved for later builds: {exc}"


def after_install(pack, receipt):
    """A saved disc stays a success even if the separate logo save fails."""
    receipt["memory_tip"] = memory_tip(pack)
    source, error = try_register(pack)
    if source:
        receipt["official_marks"] = source
    if error:
        receipt["official_marks_error"] = "Disc ready, but t" + error[1:]
    return receipt
