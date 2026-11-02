"""Remember the built disc in xemu's SDL preference directory.

No emulator is started here. Call persistence only after the launch succeeds.
"""
from __future__ import annotations

import configparser
import copy
import hashlib
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


# The lab firmware pin for the modified retail Complex 4627 Flash ROM (1 MiB). The project pins this exact
# image in its xemu runtime tools; the file itself is never shipped. Other BIOS images may work, but they are
# not the combination the 128 MB startup patch was built and tested on, so Studio only warns (never edits).
KNOWN_4627_FLASHROM = ((1_048_576, "34f1c8ded59116436065783f8ad2ef0939df3cbfc76277ec9e5c41bf9ccb93cd"),)

# b780-b11: that 1 MiB file is one 256 KiB BIOS written four times, and xemu fills a 1 MiB flash by repeating a 256 KiB or
# 512 KiB image, so the same BIOS saved at 256 KiB, 512 KiB or 1 MiB is the same BIOS. This pins the 256 KiB unit.
FLASH_UNIT = 262_144
KNOWN_4627_UNITS = ((FLASH_UNIT, "e8fe407247db42f715df7640f25a91634710e8c592bb8da6eea87bb064c17f12"),)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def flash_unit_fingerprint(path: Path):
    """(unit size, sha256) of a Flash ROM image with a mirrored 256 KiB unit folded away, or None if the file is not a
    whole number of 256 KiB units between 256 KiB and 1 MiB (or cannot be read). A 512 KiB or 1 MiB file that is its first
    256 KiB repeated gives the same answer as that 256 KiB file; a larger image whose parts differ is hashed whole."""

    try:
        size = Path(path).stat().st_size
        if size < FLASH_UNIT or size > 4 * FLASH_UNIT or size % FLASH_UNIT:
            return None
        raw = Path(path).read_bytes()
    except OSError:
        return None
    unit = raw[:FLASH_UNIT]
    if len(raw) > FLASH_UNIT and raw == unit * (len(raw) // FLASH_UNIT):
        raw = unit
    return len(raw), hashlib.sha256(raw).hexdigest()


def play_problems(config: Path, *, hash_file=None) -> tuple[str, ...]:
    """Name the xemu settings a 128 MB SOFTDRINK build needs. Reads only; the caller never writes xemu.toml."""

    path = Path(config)
    hasher = _sha256 if hash_file is None else hash_file
    try:
        raw = path.read_bytes()
    except OSError:
        return ("xemu settings were not found at " + os.fspath(path)
                + "; set System Memory to 128 MiB and Flash ROM (BIOS) to Complex 4627.",)
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return ("xemu settings at " + os.fspath(path) + " could not be read; set System Memory to 128 MiB "
                "and Flash ROM (BIOS) to Complex 4627 in xemu's System settings.",)
    system = document.get("sys")
    if not isinstance(system, dict):
        system = {}
    files = system.get("files")
    if not isinstance(files, dict):
        files = {}
    problems = []
    memory = system.get("mem_limit")
    if str(memory).strip().strip("'\"") != "128":
        problems.append("System Memory is " + (repr(memory) if memory is not None else "not set")
                        + "; set it to 128 MiB (xemu.toml [sys] mem_limit = '128'), then close xemu completely and "
                        "open it again, because xemu only reads this setting when it starts.")
    flash = files.get("flashrom_path")
    if not isinstance(flash, str) or not flash.strip():
        problems.append("Flash ROM (BIOS) is not set; choose the Complex 4627 image in xemu's System settings.")
    else:
        bios = Path(flash).expanduser()
        try:
            size = bios.stat().st_size
        except OSError:
            problems.append("Flash ROM (BIOS) " + os.fspath(bios) + " was not found; choose the Complex 4627 "
                            "image in xemu's System settings.")
        else:
            known = [digest for known_size, digest in KNOWN_4627_FLASHROM if size == known_size]
            unit = flash_unit_fingerprint(bios)
            if known and hasher(bios) in known:
                pass
            elif unit is not None and unit in KNOWN_4627_UNITS:
                pass                    # the tested BIOS saved at another size (256 KiB, 512 KiB or 1 MiB)
            else:
                # b779 rv1 / b780-b11: the game only needs a 4627 kernel, and a BIOS file keeps that kernel scrambled
                # (compressed and encrypted), so its number cannot be read from the file. Only the one image the project
                # tested is recognised by its bytes; any other is "not confirmed", never "wrong". The game itself checks
                # the kernel when it starts and, if it is not 4627, stops with a screen that prints the number it found.
                fingerprint = (unit[1] if unit is not None else "")[:12]
                problems.append("Flash ROM (BIOS) " + os.fspath(bios) + " is not the Complex 4627 image this build was "
                                "tested with" + (" (its fingerprint starts " + fingerprint + ")" if fingerprint else "")
                                + ", and Studio cannot read a BIOS file's kernel number, so it cannot say whether this "
                                "one is fine. If the game starts, ignore this note. If it stops at startup with "
                                "'THIS BUILD NEEDS THE 4627 XBOX BIOS', that screen prints the kernel number it found: "
                                "choose the Complex 4627 image in xemu's Machine > Settings > System > Flash ROM (BIOS).")
    return tuple(problems)


def play_warning(config: Path, *, hash_file=None) -> str:
    """One sentence for the launch screen; empty when the settings match what 128 MB builds need."""

    problems = play_problems(config, hash_file=hash_file)
    if not problems:
        return ""
    return "xemu settings need attention: " + " ".join(problems)


def disc_help(disc: Path) -> str:
    path = disc.resolve()
    try:
        display = "~/" + path.relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        display = str(path)
    return f"Your disc: {display}. To play again later: open xemu, then Machine > Load Disc"
