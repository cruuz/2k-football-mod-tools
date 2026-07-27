"""Build a deterministic, byte-for-byte reproducible release tarball.

Everything that would otherwise vary between builds is pinned: entries are
sorted, mtimes are fixed to the release date, uid/gid/uname/gname are zeroed,
modes are normalised, and the gzip member carries no embedded timestamp or
filename. Two builds of the same staged tree therefore produce identical bytes,
which is what makes a published SHA-256 meaningful rather than decorative.

The published ``beta-2`` assets were built with this script; ``STATUS.md``
records their exact sizes, hashes and the epoch used, so anyone can reproduce
those bytes and compare rather than trust them.

Usage: build_archive.py <staged-dir> <top-level-name> <output.tar.gz> <epoch>

  e.g.  python3 packaging/build_archive.py stage/apf \\
            apf2k8-mod-studio-0.1.0-alpha.36 \\
            apf2k8-mod-studio-0.1.0-alpha.36.tar.gz $(date -u -d 2026-07-25 +%s)
"""

from __future__ import annotations

import gzip
import hashlib
import io
import pathlib
import sys
import tarfile


def build(staged: pathlib.Path, top: str, out: pathlib.Path, epoch: int) -> str:
    paths = sorted(
        (p for p in staged.rglob("*") if p.is_file() or p.is_dir()),
        key=lambda p: p.relative_to(staged).as_posix(),
    )
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in paths:
            rel = path.relative_to(staged).as_posix()
            info = tar.gettarinfo(str(path), arcname=f"{top}/{rel}")
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            # Normalise the mode: 0o755 for directories and anything the source
            # marked executable, 0o644 for every other regular file.
            if info.isdir():
                info.mode = 0o755
            else:
                info.mode = 0o755 if (info.mode & 0o111) else 0o644
            if info.isfile():
                with open(path, "rb") as handle:
                    tar.addfile(info, handle)
            else:
                tar.addfile(info)
    payload = raw.getvalue()
    with open(out, "wb") as handle:
        # mtime=0 and no filename in the gzip header, so the container adds no
        # nondeterminism of its own.
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=handle, compresslevel=9, mtime=0
        ) as gz:
            gz.write(payload)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    sidecar = out.with_name(out.name + ".sha256")
    sidecar.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    print(f"{out.name}  {out.stat().st_size} bytes  sha256={digest}")
    return digest


if __name__ == "__main__":
    build(
        pathlib.Path(sys.argv[1]),
        sys.argv[2],
        pathlib.Path(sys.argv[3]),
        int(sys.argv[4]),
    )
