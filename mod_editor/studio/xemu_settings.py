"""Remember the built disc in xemu's SDL preference directory.

No emulator is started here. Call persistence only after the launch succeeds.
"""
from __future__ import annotations

import configparser
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

APP_ID = "app.xemu.xemu"


def is_flatpak(command):
    return (len(command) >= 3 and Path(command[0]).name == "flatpak"
            and command[1] == "run" and APP_ID in command[2:])


def config_path(command, *, platform=None, home=None, environ=None):
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else Path(home)
    env = os.environ if environ is None else environ
    for index, argument in enumerate(command):
        if argument == "-config_path" and index + 1 < len(command):
            return Path(command[index + 1]).expanduser().resolve()
        if argument.startswith("-config_path="):
            return Path(argument.split("=", 1)[1]).expanduser().resolve()
    if is_flatpak(command):
        root = home / ".var/app" / APP_ID / "data"
    elif platform == "win32":
        executable = Path(shutil.which(command[0]) or command[0]).resolve()
        portable = executable.parent / "xemu.toml"
        if portable.is_file():
            return portable
        root = Path(env.get("APPDATA") or home / "AppData/Roaming")
    elif platform == "darwin":
        root = home / "Library/Application Support"
    else:
        root = Path(env.get("XDG_DATA_HOME") or home / ".local/share")
    return root / "xemu/xemu/xemu.toml"


def remember_disc(path: Path, disc: Path) -> None:
    """Atomically change only dvd_path; reparse and compare every other setting.

    xemu emits ordinary TOML sections and single-line strings. Unusual hand-
    authored layouts are refused if a surgical edit cannot preserve them.
    """
    path = Path(path)
    original = path.read_bytes() if path.exists() else b""
    text = original.decode("utf-8")
    before = tomllib.loads(text)
    wanted = copy.deepcopy(before)
    if not isinstance(wanted.get("sys", {}), dict) or not isinstance(wanted.get("sys", {}).get("files", {}), dict):
        raise ValueError("xemu settings need a [sys.files] table to remember the disc")
    wanted.setdefault("sys", {}).setdefault("files", {})["dvd_path"] = str(disc.resolve())
    line = "dvd_path = " + json.dumps(str(disc.resolve()), ensure_ascii=False) + "\n"
    section = re.search(r"(?m)^\s*\[\s*sys\s*\.\s*files\s*\][ \t]*(?:#[^\n]*)?\r?$", text)
    if section:
        start = section.end()
        following = re.search(r"(?m)^[ \t]*\[", text[start:])
        end = start + following.start() if following else len(text)
        body = text[start:end]
        key = re.search(r'(?m)^[ \t]*(?:dvd_path|"dvd_path"|\x27dvd_path\x27)[ \t]*=.*(?:\n|$)', body)
        body = (body[:key.start()] + line + body[key.end():] if key
                else body.rstrip("\r\n") + "\n" + line)
        text = text[:start] + body + text[end:]
    else:
        text = text.rstrip("\r\n") + "\n\n[sys.files]\n" + line
    if tomllib.loads(text) != wanted:
        raise ValueError("xemu settings use a layout that cannot be safely updated")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".xemu-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text.encode("utf-8"))
        if (path.read_bytes() if path.exists() else b"") != original:
            raise ValueError("xemu settings changed while saving the disc path; try Launch again")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def grant_build_folder(command, folder: Path, *, runner=None) -> str:
    """Persist read-only access once per folder; keep per-run argv as fallback."""
    if not is_flatpak(command):
        return ""
    runner = subprocess.run if runner is None else runner
    folder = folder.resolve()
    grant = f"{folder}:ro"
    kwargs = dict(stdin=subprocess.DEVNULL, capture_output=True, text=True,
                  timeout=10, check=False)
    try:
        existing = runner((command[0], "override", "--user", "--show", APP_ID), **kwargs)
        config = configparser.ConfigParser(interpolation=None)
        if existing.returncode == 0:
            config.read_string(existing.stdout)
        permissions = config.get("Context", "filesystems", fallback="").split(";")
        if grant in permissions:
            return ""
        result = runner((command[0], "override", "--user", f"--filesystem={grant}", APP_ID), **kwargs)
        if result.returncode:
            return (f"Could not remember Flatpak read-only access to {folder}. "
                    "This launch has access; later launches may need the folder allowed in Flatpak settings.")
    except (OSError, subprocess.TimeoutExpired, configparser.Error) as exc:
        return f"Could not remember Flatpak read-only access to {folder}: {exc}."
    return f"Granted persistent Flatpak read-only access to the build folder: {folder}."


def disc_help(disc: Path) -> str:
    path = disc.resolve()
    try:
        display = "~/" + path.relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        display = str(path)
    return f"Your disc: {display}. To play again later: open xemu, then Machine > Load Disc"
