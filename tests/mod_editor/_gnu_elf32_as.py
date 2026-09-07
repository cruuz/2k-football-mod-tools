"""Shared toolchain probe for the assembler-reproduction tests.

The shipped byte templates are the runtime input; reproducing them needs GNU x86
``as`` that emits ELF32 objects. macOS ships Apple's assembler and MinGW's ``as``
emits COFF, so those hosts skip the reproduction instead of failing on it.
"""
from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
from pathlib import Path


@functools.lru_cache(maxsize=None)
def gnu_elf32_as() -> bool:
    assembler = shutil.which("as")
    if not assembler:
        return False
    try:
        version = subprocess.run([assembler, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    if version.returncode or "GNU assembler" not in version.stdout:
        return False
    with tempfile.TemporaryDirectory(prefix="gnu-elf32-as-") as folder:
        source = Path(folder) / "probe.s"
        obj = Path(folder) / "probe.o"
        source.write_text(".text\n.globl _probe\n_probe:\n ret\n", encoding="utf-8", newline="\n")
        try:
            result = subprocess.run([assembler, "--32", "-o", str(obj), str(source)],
                                    capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode or not obj.is_file():
            return False
        head = obj.read_bytes()[:6]
    return head[:4] == b"\x7fELF" and head[4] == 1 and head[5] == 1  # ELFCLASS32, little-endian
