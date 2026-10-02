"""Restore missing allowlisted build inputs from verified portable releases.

Uses only the standard library. Offline usage requires a NAME.sha256 sidecar
beside every --archive NAME. Existing checkout files are never overwritten.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request

from stage_release import StageError, _manifest_entries, _regular_file_without_symlink


ROOT = Path(__file__).resolve().parent.parent
ALLOWLISTS = ("packaging/release-allowlist.txt", "packaging/apf2k8-release-allowlist.txt")
DEFAULT_REPO = "cruuz/2k-football-mod-tools"
PORTABLE_NAMES = (
    re.compile(r"2K5-Mod-Studio-v[A-Za-z0-9._-]+\.tar\.gz"),
    re.compile(r"apf2k8-mod-studio-[A-Za-z0-9._-]+\.tar\.gz"),
)


class HydrationError(ValueError):
    """The inputs cannot be safely restored."""


def checkout_tag(root: Path) -> str:
    # Do not import the application: hydrating a clean clone must not need Qt.
    source = root / "mod_editor/core/update_check.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "BUILD_RELEASE_TAG"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise HydrationError(f"BUILD_RELEASE_TAG is missing: {source}")


def _request(url: str):
    return urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "2k-football-mod-tools-hydrate"},
    ), timeout=60)


def download_release(repo: str, tag: str, destination: Path) -> list[Path]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repo):
        raise HydrationError("--repo must be OWNER/REPOSITORY")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", tag):
        raise HydrationError("--tag must be a release tag without path separators")
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    with _request(url) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise HydrationError("release metadata is too large")
    document = json.loads(payload)
    if not isinstance(document, dict) or document.get("tag_name") != tag:
        raise HydrationError("GitHub returned an unexpected release")
    assets = document.get("assets")
    if not isinstance(assets, list):
        raise HydrationError("release has no asset list")
    names = [row.get("name") for row in assets if isinstance(row, dict)]
    selected = []
    for pattern in PORTABLE_NAMES:
        matches = [name for name in names if isinstance(name, str) and pattern.fullmatch(name)]
        if len(matches) != 1:
            raise HydrationError(f"expected one portable archive matching {pattern.pattern}")
        name = matches[0]
        if names.count(name + ".sha256") != 1:
            raise HydrationError(f"missing or duplicate checksum sidecar: {name}.sha256")
        selected.append(name)
    # Construct URLs from validated names; do not follow URLs supplied in JSON.
    for name in selected:
        for filename in (name + ".sha256", name):
            print(f"downloading {filename}", flush=True)
            with _request(f"https://github.com/{repo}/releases/download/{tag}/{filename}") as response:
                with (destination / filename).open("xb") as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
    return [destination / name for name in selected]


def verify_archive(archive: Path) -> None:
    sidecar = archive.with_name(archive.name + ".sha256")
    # Bind the checksum to this exact filename, not just the first hash in a file.
    with sidecar.open("rb") as source:
        text = source.read(4097)
    if len(text) > 4096:
        raise HydrationError(f"checksum sidecar is too large: {sidecar}")
    match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]([^\r\n]+)\r?\n?", text.decode("utf-8"))
    if match is None or match[2] != archive.name:
        raise HydrationError(f"invalid checksum sidecar: {sidecar}")
    with archive.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != match[1].lower():
        raise HydrationError(f"archive hash mismatch: {archive.name}")
    print(f"verified {archive.name} sha256={actual}", flush=True)


def _target(root: Path, relative: str) -> Path:
    # The shared parser covers POSIX traversal; also reject Windows drive/ADS
    # paths and version-control metadata before touching the destination.
    if any(part == ".git" or ":" in part for part in relative.split("/")):
        raise HydrationError(f"unsafe declared input: {relative}")
    target = root / relative
    # Check parents before probing the leaf, including dangling symlinks.
    for parent in target.parents:
        if parent == root:
            break
        if os.path.lexists(parent):
            mode = parent.lstat().st_mode
            if not stat.S_ISDIR(mode):
                raise HydrationError(f"declared input has an unsafe parent: {parent}")
    if os.path.lexists(target):
        _regular_file_without_symlink(target, root, "declared input")
    return target


def hydrate(root: Path, archives: list[Path]) -> int:
    root = root.resolve(strict=True)
    declared = dict.fromkeys(
        relative for manifest in ALLOWLISTS
        for relative in _manifest_entries(root / manifest)
    )
    targets = {relative: _target(root, relative) for relative in declared}
    # Verify all checksums and all members before writing any checkout files.
    for archive in archives:
        verify_archive(archive)
    with ExitStack() as stack:
        available = {}
        for archive in archives:
            bundle = stack.enter_context(tarfile.open(archive, "r:gz"))
            seen = set()
            tops = set()
            for member in bundle:
                name = member.name.rstrip("/") if member.isdir() else member.name
                parts = name.split("/")
                if len(parts) < 2 or any(
                    part in ("", ".", "..", ".git") or ":" in part or "\\" in part
                    for part in parts
                ):
                    raise HydrationError(f"unsafe archive member: {member.name}")
                tops.add(parts[0])
                relative = "/".join(parts[1:])
                if relative in seen or len(tops) != 1:
                    raise HydrationError(f"ambiguous archive member: {member.name}")
                seen.add(relative)
                if member.isdir():
                    continue
                if not member.isfile() or member.sparse is not None:
                    raise HydrationError(f"non-regular archive member: {member.name}")
                if relative in declared:
                    available.setdefault(relative, (bundle, member))
        missing = [relative for relative, target in targets.items()
                   if not target.exists() and relative not in available]
        if missing:
            raise HydrationError("declared inputs still missing:\n" + "\n".join(missing))
        copied = 0
        for relative in declared:
            target = _target(root, relative)
            if target.exists():
                continue
            bundle, member = available[relative]
            source = bundle.extractfile(member)
            if source is None:
                raise HydrationError(f"archive member cannot be read: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("xb") as output:
                try:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                except BaseException:
                    output.close()  # Windows cannot unlink an open file.
                    target.unlink()  # A partial file must not look restored on retry.
                    raise
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
            print(f"restored {relative}", flush=True)
            copied += 1
    for relative in declared:
        _regular_file_without_symlink(_target(root, relative), root, "declared input")
    print(f"restored {copied} files; 0 declared inputs absent", flush=True)
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="release tag (default: checkout's BUILD_RELEASE_TAG)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub OWNER/REPOSITORY")
    parser.add_argument("--archive", type=Path, action="append", help="offline archive with adjacent .sha256; repeat for both products")
    args = parser.parse_args(argv)
    try:
        if args.archive:
            hydrate(ROOT, args.archive)
        else:
            tag = args.tag if args.tag is not None else checkout_tag(ROOT)
            with tempfile.TemporaryDirectory(prefix="release-inputs-") as temporary:
                hydrate(ROOT, download_release(args.repo, tag, Path(temporary)))
    except (OSError, ValueError, SyntaxError, EOFError, tarfile.TarError) as exc:
        print(f"RELEASE_HYDRATION_REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
