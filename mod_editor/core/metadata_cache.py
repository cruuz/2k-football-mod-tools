"""Optional versioned JSON caches for shipped metadata, never game payloads."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile


def source_key(paths, version):
    digest = hashlib.sha256(version.encode("utf-8"))
    for path in paths:
        path = Path(path)
        digest.update(path.name.encode("utf-8"))
        # Callers pass only catalog source code and shipped metadata reports.
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def cache_path(name):
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "2k5-mod-studio" / "metadata" / (name + ".json")


def read(path, key):
    try:
        if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
            return None
        doc = json.loads(path.read_bytes())
        if doc["schema"] == 1 and doc["source"] == key:
            return doc["rows"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write(path, key, rows):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(json.dumps({"schema": 1, "source": key, "rows": rows},
                                    ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
        os.replace(temporary, path)
    except OSError:
        # Read-only installation/cache locations must still open the editor.
        pass
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
