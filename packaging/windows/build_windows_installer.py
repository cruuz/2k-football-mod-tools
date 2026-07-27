"""Build a self-contained Windows installer for one of the editors.

The user installs nothing else: no Python, no pip, no `tar`, no PATH edits. A
private CPython lives inside the install directory next to the application, and
the Start Menu shortcut runs it directly.

Why a private interpreter instead of freezing with PyInstaller: this application
verifies its own integrity at runtime. ``providers.py`` reads each pinned module
from ``workspace/<relative path>`` and hashes the bytes, and the workspace is
derived from ``Path(__file__).resolve().parents[2]``. A frozen build has neither
real ``.py`` files on disk nor a meaningful ``__file__``, so freezing would mean
deleting the guarantee that makes this tool safe to point at a game. The
application therefore ships exactly as it does in the tarball -- same files, same
hashes, same pins -- and only gains an interpreter beside it.

Layout produced inside the install directory::

    runtime\\python.exe          private CPython (python.org embeddable build)
    runtime\\Lib\\site-packages  PyQt5, Pillow
    app\\...                     the staged release tree, unmodified

``runtime\\python312._pth`` puts ``..\\app`` on ``sys.path``, so ``mod_editor``
imports without ``PYTHONPATH`` and without depending on the working directory.

Usage:
    build_windows_installer.py --stage DIR --product 2k5|apf --version V --out DIR
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

# Every byte that enters the installer from outside this repository is pinned to
# an exact SHA-256 and verified before use. Version pins alone are not enough: a
# version can be re-uploaded, a mirror can serve something else, and a resolver
# can pull a transitive dependency nobody chose. Any mismatch, any unpinned file,
# or any pinned file that fails to appear stops the build. That is what lets the
# published installer claim to be reproducible rather than merely repeatable.
PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
)
PYTHON_EMBED_SHA256 = (
    "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
)

# PyQt5 pulls PyQt5-Qt5 and PyQt5-sip transitively, so those are named here too
# rather than left to whatever the resolver picks on the day.
WHEELS = (
    "PyQt5==5.15.11",
    "PyQt5-Qt5==5.15.2",
    "PyQt5-sip==12.18.0",
    "Pillow==11.3.0",
)
WHEEL_SHA256 = {
    "PyQt5-5.15.11-cp38-abi3-win_amd64.whl":
        "bdde598a3bb95022131a5c9ea62e0a96bd6fb28932cc1619fd7ba211531b7517",
    "PyQt5_Qt5-5.15.2-py3-none-win_amd64.whl":
        "750b78e4dba6bdf1607febedc08738e318ea09e9b10aea9ff0d73073f11f6962",
    "pyqt5_sip-12.18.0-cp312-cp312-win_amd64.whl":
        "9b689e02e400abd1ce0a30cd6eae8eceabcf1bbba0395cb5c86e64ba74351d68",
    "pillow-11.3.0-cp312-cp312-win_amd64.whl":
        "a6444696fce635783440b7f7a9fc24b3ad10a9ea3f0ab66c5905be1c19ccf17d",
}

PRODUCTS = {
    "2k5": {
        "name": "2K5 Mod Studio",
        "publisher": "2K Football Mod Tools",
        "module": "mod_editor",
        "args": "-m mod_editor --studio",
        "svg": "packaging/2k5-mod-studio.svg",
        "slug": "2K5-Mod-Studio",
    },
    "apf": {
        "name": "APF 2K8 Mod Studio",
        "publisher": "2K Football Mod Tools",
        "module": "mod_editor.apf_studio",
        "args": "-m mod_editor.apf_studio",
        "svg": "packaging/apf2k8-mod-studio.svg",
        "slug": "APF-2K8-Mod-Studio",
    },
}


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, dest: pathlib.Path, expected: str | None = None) -> pathlib.Path:
    if not dest.exists():
        subprocess.run(["curl", "-sSL", "-o", str(dest), url], check=True)
    if expected is not None:
        actual = sha256_file(dest)
        if actual != expected:
            raise SystemExit(
                f"{dest.name} hash mismatch\n  expected {expected}\n  actual   {actual}"
            )
    return dest


def build_runtime(work: pathlib.Path, downloads: pathlib.Path) -> pathlib.Path:
    """Unpack a private CPython and install the two GUI dependencies into it."""
    runtime = work / "runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)

    embed = fetch(PYTHON_EMBED_URL, downloads / "python-embed.zip", PYTHON_EMBED_SHA256)
    with zipfile.ZipFile(embed) as archive:
        archive.extractall(runtime)

    site_packages = runtime / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # Windows wheels, fetched on whatever platform this build runs on.
    subprocess.run(
        [
            sys.executable, "-m", "pip", "download", "--quiet",
            "--dest", str(downloads),
            "--platform", "win_amd64",
            "--python-version", "312",
            "--only-binary=:all:",
            *WHEELS,
        ],
        check=True,
    )
    # Fail closed on the exact set: nothing unpinned goes in, nothing pinned is
    # allowed to be missing, and every file must hash to what was reviewed.
    present = {path.name: path for path in downloads.glob("*.whl")}
    unpinned = sorted(set(present) - set(WHEEL_SHA256))
    if unpinned:
        raise SystemExit(
            "refusing to build: the resolver produced wheels that are not pinned: "
            + ", ".join(unpinned)
        )
    missing = sorted(set(WHEEL_SHA256) - set(present))
    if missing:
        raise SystemExit("refusing to build: pinned wheels never arrived: " + ", ".join(missing))
    for name in sorted(WHEEL_SHA256):
        actual = sha256_file(present[name])
        if actual != WHEEL_SHA256[name]:
            raise SystemExit(
                f"refusing to build: {name} hash mismatch\n"
                f"  expected {WHEEL_SHA256[name]}\n  actual   {actual}"
            )
        with zipfile.ZipFile(present[name]) as archive:
            archive.extractall(site_packages)
    print(f"      verified {len(WHEEL_SHA256)} pinned wheels + the interpreter")

    # The embeddable build ignores site-packages and the working directory unless
    # its ._pth says otherwise. Paths here are relative to python.exe.
    pth = next(runtime.glob("python*._pth"))
    pth.write_text(
        "\n".join(
            [
                pth.name.replace("._pth", ".zip"),
                ".",
                "Lib\\site-packages",
                "..\\app",
                "import site",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return runtime


def build_icon(repo: pathlib.Path, svg_rel: str, out: pathlib.Path) -> pathlib.Path | None:
    svg = repo / svg_rel
    if not svg.exists():
        return None
    png = out.with_suffix(".png")
    try:
        subprocess.run(
            ["inkscape", str(svg), "--export-type=png", "--export-filename", str(png),
             "-w", "256", "-h", "256"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["convert", str(png), "-define", "icon:auto-resize=256,128,64,48,32,16",
             str(out)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out if out.exists() else None


# NSIS records each file's mtime in the archive, and `pip` and zip extraction
# stamp the current time on everything they create. Two builds of identical
# *content* therefore produced installers with different bytes -- reproducible
# in contents but not in hash, which makes a published SHA-256 unverifiable by
# rebuild. Flattening every mtime in the staged tree to one fixed instant is
# what closes that gap; it is the same trick `build_archive.py` uses for the
# tarballs. The value is arbitrary but must never drift: 2026-07-27T00:00:00Z,
# the date this became reproducible.
SOURCE_DATE_EPOCH = 1785110400


def normalise_mtimes(root: pathlib.Path) -> int:
    """Flatten every mtime under *root* so NSIS output depends only on content.

    Directories are stamped after their children: on POSIX, writing a child
    updates the parent's mtime, so doing it in the other order would undo the
    parent's stamp. Symlinks are skipped rather than followed -- the staged tree
    has none, and following one would stamp something outside the build.
    """
    stamped = 0
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_symlink():
            continue
        os.utime(path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH))
        stamped += 1
    os.utime(root, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH))
    return stamped + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, help="staged release tree (stage_release.py output)")
    parser.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    parser.add_argument("--version", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", default=None)
    args = parser.parse_args()

    repo = pathlib.Path(__file__).resolve().parents[2]
    stage = pathlib.Path(args.stage).resolve()
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(args.work).resolve() if args.work else out / "work"
    work.mkdir(parents=True, exist_ok=True)
    downloads = work / "dl"
    downloads.mkdir(exist_ok=True)

    product = PRODUCTS[args.product]

    print(f"[1/4] private CPython + PyQt5/Pillow")
    build_runtime(work, downloads)

    print(f"[2/4] application tree from {stage}")
    app = work / "app"
    if app.exists():
        shutil.rmtree(app)
    shutil.copytree(stage, app)

    print("[3/4] icon")
    icon = build_icon(repo, product["svg"], work / f"{args.product}.ico")
    print(f"      {'ok' if icon else 'skipped (inkscape/convert unavailable)'}")

    # The warning the user reads inside the wizard, before anything is written.
    notice_src = pathlib.Path(__file__).resolve().parent / "UNSIGNED-NOTICE.txt"
    shutil.copy2(notice_src, work / "UNSIGNED-NOTICE.txt")

    print("[4/4] NSIS script")
    normalised = normalise_mtimes(work)
    print(f"      normalised {normalised} mtimes to {SOURCE_DATE_EPOCH}")
    nsi = work / "installer.nsi"
    nsi.write_text(
        render_nsis(product, args.version, work, icon, out), encoding="utf-8"
    )
    print(f"      wrote {nsi}")
    print("\nCompile with:")
    print(f"  makensis {nsi}")
    return 0


def render_nsis(
    product: dict,
    version: str,
    work: pathlib.Path,
    icon: pathlib.Path | None,
    out: pathlib.Path,
) -> str:
    name = product["name"]
    slug = product["slug"]
    installer = out / f"{slug}-{version}-Setup.exe"
    icon_lines = ""
    if icon is not None:
        icon_lines = f'!define MUI_ICON "{icon}"\n!define MUI_UNICON "{icon}"\n'

    return f"""\
; Generated by packaging/windows/build_windows_installer.py -- do not hand-edit.
Unicode true
!include "MUI2.nsh"

Name "{name}"
OutFile "{installer}"
; Per-user install: never needs administrator, never touches Program Files.
InstallDir "$LOCALAPPDATA\\Programs\\{slug}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "{product['publisher']}"

VIProductVersion "{_vi_version(version)}"
VIAddVersionKey "ProductName" "{name}"
VIAddVersionKey "FileDescription" "{name} installer"
VIAddVersionKey "FileVersion" "{version}"
VIAddVersionKey "LegalCopyright" "MIT licence. Ships no game data."

{icon_lines}!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "{name}"
!define MUI_WELCOMEPAGE_TEXT "This will install {name} {version}.$\\r$\\n$\\r$\\nEverything it needs is included -- you do not need Python, pip, or any command prompt. It installs to your own user folder and never asks for administrator rights.$\\r$\\n$\\r$\\nIt contains no game data. You supply your own legally obtained disc."
!insertmacro MUI_PAGE_WELCOME

; ---------------------------------------------------------------------------
; Windows will warn about this software because it is not code-signed. Say so
; plainly, and say it BEFORE the warning appears, rather than letting the user
; meet it cold and assume the download is malicious.
; ---------------------------------------------------------------------------
!define MUI_PAGE_HEADER_TEXT "Before you continue"
!define MUI_PAGE_HEADER_SUBTEXT "Windows will show a warning. Here is what it says and why."
!define MUI_LICENSEPAGE_TEXT_TOP "Please read this. It explains a warning you are about to see."
!define MUI_LICENSEPAGE_TEXT_BOTTOM "Tick the box below to confirm you have read this, then click Next."
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "I understand, and I know what to click"
!insertmacro MUI_PAGE_LICENSE "{work / 'UNSIGNED-NOTICE.txt'}"

!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_RUN "$INSTDIR\\runtime\\pythonw.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "{product['args']}"
!define MUI_FINISHPAGE_RUN_TEXT "Start {name} now"
!define MUI_FINISHPAGE_TEXT "{name} is installed.$\\r$\\n$\\r$\\nThe first time you start it, Windows may show the same kind of warning again. Choose More info, then Run anyway.$\\r$\\n$\\r$\\nOpen it any time from the Start Menu."
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "{work / 'runtime'}"
  File /r "{work / 'app'}"

  CreateDirectory "$SMPROGRAMS\\{product['publisher']}"
  CreateShortcut "$SMPROGRAMS\\{product['publisher']}\\{name}.lnk" \\
      "$INSTDIR\\runtime\\pythonw.exe" "{product['args']}" \\
      "$INSTDIR\\runtime\\pythonw.exe" 0 SW_SHOWNORMAL "" "{name}"
  CreateShortcut "$DESKTOP\\{name}.lnk" \\
      "$INSTDIR\\runtime\\pythonw.exe" "{product['args']}" \\
      "$INSTDIR\\runtime\\pythonw.exe" 0 SW_SHOWNORMAL "" "{name}"

  WriteUninstaller "$INSTDIR\\Uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "DisplayName" "{name}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "DisplayVersion" "{version}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "Publisher" "{product['publisher']}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "UninstallString" "$\\"$INSTDIR\\Uninstall.exe$\\""
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "NoModify" 1
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}" \\
      "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; Only what this installer created. Never recursive-delete a user-chosen path.
  RMDir /r "$INSTDIR\\runtime"
  RMDir /r "$INSTDIR\\app"
  Delete "$INSTDIR\\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\\{product['publisher']}\\{name}.lnk"
  RMDir "$SMPROGRAMS\\{product['publisher']}"
  Delete "$DESKTOP\\{name}.lnk"
  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{slug}"
SectionEnd
"""


def _vi_version(version: str) -> str:
    parts = [p for p in version.replace("-", ".").split(".") if p.isdigit()]
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])


if __name__ == "__main__":
    raise SystemExit(main())
