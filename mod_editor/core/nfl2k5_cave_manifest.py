"""Rebuild cave ownership by observing the real studio writers on a disposable disc.

Run in a dedicated CLI process: the scoped wrappers observe existing module
functions during a synchronous build. No writer implementation is replaced.
The JSON contains addresses, sizes and hashes, never XBE/disc byte payloads.
"""

from __future__ import annotations

from contextlib import ExitStack
import functools
import hashlib
import importlib
import inspect
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

from .nfl2k5_cave_oracle import MANIFEST_SCHEMA, RETAIL_SHA256, OracleError, XbeImage

ROOT = Path(__file__).resolve().parents[2]


def changed_runs(before: bytes, after: bytes):
    """Exact half-open file spans, including the final changed byte."""
    if len(before) != len(after):
        raise OracleError("patch resized the XBE; ownership generation refused")
    start = None
    # Skip equal pages cheaply; only enumerate changed pages in Python.
    for page in range(0, len(before), 4096):
        a, b = before[page:page + 4096], after[page:page + 4096]
        if a == b:
            if start is not None:
                yield start, page
                start = None
            continue
        for j, (x, y) in enumerate(zip(a, b)):
            off = page + j
            if x != y:
                if start is None:
                    start = off
            elif start is not None:
                yield start, off
                start = None
    if start is not None:
        yield start, len(before)


class Recorder:
    def __init__(self, retail: bytes):
        self.retail = retail
        self.image = XbeImage(retail)
        self.spans: list[dict] = []
        self.steps: list[dict] = []
        self.covered = bytearray(len(retail))

    def reserve(self, start: int, size: int, owner: str, basis: str):
        if not size:
            return
        if not self.image.base <= start < start + size <= self.image.base + self.image.image_size:
            raise OracleError(f"invalid declared reservation from {owner}")
        self.spans.append({"start": hex(start), "end": hex(start + size), "size": size,
                           "owner": owner, "basis": basis})

    def observe(self, module: ModuleType, function: str, before: bytes, after: bytes, receipt: dict):
        owner = module.__name__.split(".")[-1]
        runs = list(changed_runs(before, after))
        post_image = XbeImage(after)
        for a, b in runs:
            self.covered[a:b] = b"\x01" * (b - a)
            # Split at mapping boundaries; raw padding is retained as a file-only
            # receipt below and cannot become an offline cave candidate.
            at = a
            while at < b:
                va = post_image.va_for_offset(at)
                stop = at + 1
                while stop < b and post_image.va_for_offset(stop) == (va + stop - at if va is not None else None):
                    stop += 1
                if va is not None:
                    self.reserve(va, stop - at, owner, "observed byte diff")
                at = stop
        self.steps.append({"owner": owner, "function": function,
                           "before_sha256": hashlib.sha256(before).hexdigest(),
                           "after_sha256": hashlib.sha256(after).hexdigest(),
                           "changed_bytes": sum(b - a for a, b in runs),
                           "file_runs": [[hex(a), hex(b)] for a, b in runs]})
        if not runs:
            return
        # Include bytes in declared sites that happen to equal retail, plus cave
        # capacity beyond today's generated instructions. Diff runs alone cannot
        # reserve a zero-initialized variable or the unchanged first cave byte.
        for name, va in vars(module).items():
            if not isinstance(va, int) or not name.endswith("_VA"):
                continue
            stem = name[:-3]
            if "CAVE" in stem or stem in ("HOST", "STUB"):
                size = getattr(module, stem + "_SIZE", None)
                if isinstance(size, int) and size > 0:
                    self.reserve(va, size, owner, "declared capacity: " + name)
        for edit in receipt.get("edits", []):
            if not isinstance(edit, dict):
                continue
            size = edit.get("bytes", edit.get("size"))
            if not isinstance(size, int):
                value = edit.get("after")
                if isinstance(value, str):
                    try:
                        size = len(bytes.fromhex(value))
                    except ValueError:
                        continue
            va = edit.get("va")
            if va is not None:
                va = int(va, 0) if isinstance(va, str) else va
            elif "file_offset" in edit:
                off = edit["file_offset"]
                off = int(off, 0) if isinstance(off, str) else off
                va = post_image.va_for_offset(off)
            if isinstance(va, int) and isinstance(size, int) and size > 0:
                self.reserve(va, size, owner, "declared edit: " + str(edit.get("label", "site")))
        if owner == "nfl2k5_season_length":
            for group in receipt["groups"]:
                subowner = {"playoffs_14": "nfl2k5_playoffs14", "preseason": "nfl2k5_preseason"}.get(group, owner)
                for site in module.group_sites(group):
                    self.reserve(site.va, site.size, subowner, "season group site: " + site.label)

    def wrapper(self, module: ModuleType, name: str):
        original = getattr(module, name)

        @functools.wraps(original)
        def observe(*args, **kwargs):
            result = original(*args, **kwargs)
            if (args and isinstance(args[0], bytes) and args[0][:4] == b"XBEH"
                    and isinstance(result, tuple) and isinstance(result[0], bytes)):
                receipt = result[1] if isinstance(result[1], dict) else {}
                self.observe(module, name, args[0], result[0], receipt)
            return result

        return observe

    def finish(self, final: bytes):
        missing = [a for a, b in changed_runs(self.retail, final) if not all(self.covered[a:b])]
        if missing:
            raise OracleError(f"unattributed final XBE changes at {[hex(a) for a in missing[:8]]}")
        # Shared-page runtime storage is intentionally reserved even though zero
        # initialization makes it invisible to any offline diff.
        from . import nfl2k5_seven_on_seven as seven, nfl2k5_uniform_choice as uniform
        from . import nfl2k5_playoffs14 as playoffs
        from . import nfl2k5_boot_logo as logo
        self.reserve(seven.FLAG_VA, 1, "nfl2k5_seven_on_seven", "runtime byte, zero at retail; module declaration")
        for name in ("HOME_FLIP_VA", "AWAY_FLIP_VA", "AWAY_VALUE_VA"):
            self.reserve(getattr(uniform, name), 4, "nfl2k5_uniform_choice", "runtime dword: " + name)
        self.reserve(playoffs.LAST7_VA, 4, "nfl2k5_playoffs14", "runtime saved seed dword: LAST7_VA")
        self.reserve(logo.NEW_LOGO_VA, logo.LOGO_SIZE, "nfl2k5_boot_logo", "complete relocated loader bitmap")
        # Preserve the whole shared host, including alignment padding between owners.
        self.reserve(0xB4A60, 16, "nfl2k5_penalties", "shared host allocation including stub padding")
        self.reserve(0xB4A70, 32, "nfl2k5_prospect_names", "shared host allocation")
        self.reserve(0x2BA840, 32, "nfl2k5_position_pools", "complete helper allocation including trailing padding")
        unique = {(s["start"], s["end"], s["owner"], s["basis"]): s for s in self.spans}
        return sorted(unique.values(), key=lambda s: (int(s["start"], 0), int(s["end"], 0), s["owner"], s["basis"]))


def source_fingerprints() -> dict[str, str]:
    # Include the stack dispatcher, preset, and all NFL2K5 writer/helper sources.
    # Exclude this analysis tool to avoid its own release manifest hashing cycle.
    paths = [ROOT / "mod_editor/core/mod_build.py"]
    paths += list((ROOT / "mod_editor/core").glob("nfl2k5_*.py"))
    paths += list((ROOT / "tools").glob("nfl2k5_*.py"))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if not p.name.startswith("nfl2k5_cave_")}


def build_manifest(retail: bytes, xiso: Path, *, work_dir: Path, progress=None) -> dict:
    """Actual experimental image build plus the dormant seven-on-seven owner.

    The source disc is read-only. Only the temporary target is passed to studio
    writers. Temporary image and proprietary build receipts are not exported.
    """
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise OracleError("manifest generation requires the pinned USA retail XBE")
    from . import mod_build as build, nfl2k5_throw_tuning as tt
    from . import nfl2k5_position_pools as pools, nfl2k5_season_length as season
    from . import nfl2k5_seven_on_seven_book as seven_book
    progress = progress or (lambda _message: None)
    xiso = xiso.resolve(strict=True)
    if build._xbe_bytes(xiso) != retail:
        raise OracleError("disc default.xbe does not match the supplied pinned retail XBE")
    recorder = Recorder(retail)
    modules = {m.__name__: m for m in vars(tt).values() if isinstance(m, ModuleType)
               and m.__name__.startswith("mod_editor.core.nfl2k5_")}
    modules.update({m.__name__: m for m in (tt, pools, season)})
    for name in ("nfl2k5_scorebug_layout", "nfl2k5_scorebug_position_patch"):
        module = build._tools_module(name)
        if module is None:
            raise OracleError("required image writer unavailable: " + name)
        modules[module.__name__] = module
    hud = importlib.import_module("mod_editor.core.nfl2k5_hud_layout")
    modules[hud.__name__] = hud
    fingerprints = source_fingerprints()
    with tempfile.TemporaryDirectory(prefix="nfl2k5-oracle-", dir=work_dir) as temp:
        target = Path(temp) / "stack.xiso.iso"
        preset = dict(build.PRESETS["softdrink_experimental"])
        plan = build.BuildPlan(source=str(xiso), target=str(target), **preset)
        with ExitStack() as stack:
            # Atlas repainting cannot change any XBE address. The scorebug's real
            # image writer still refits the retail mesh and applies ALL XBE/HUD
            # patches; only optional PNG generation/import is omitted. This also
            # avoids depending on the unshipped presentation-audit asset fixture.
            scorebug = build._tools_module("nfl2k5_scorebug_layout")
            scorebug_apply = scorebug.apply_in_place
            def xbe_and_mesh_only(path, **kwargs):
                return scorebug_apply(path, **{**kwargs, "textures": False})
            stack.enter_context(patch.object(scorebug, "apply_in_place", xbe_and_mesh_only))
            for module in modules.values():
                for name in ("apply", "xbe_apply", "plan_patch", "apply_arc_table", "patch_xbe"):
                    function = getattr(module, name, None)
                    if inspect.isfunction(function) and function.__module__ == module.__name__:
                        stack.enter_context(patch.object(module, name, recorder.wrapper(module, name)))
            receipt = build.build(plan, progress=lambda message, *_: progress(message))
            preset_xbe = build._xbe_bytes(target)
            # All current owners, even the hidden opt-in patch, reserve their space.
            extra, _ = tt._apply_all(preset_xbe, None, catch_slider=False, seven_on_seven=True)
            build._write_xbe_bytes(target, extra)
            progress("Applying dormant seven-on-seven playbook to disposable image")
            seven_book.apply(target)
            final = build._xbe_bytes(target)
            if final != extra:
                raise OracleError("seven-on-seven book writer unexpectedly changed XBE bytes")
        # Validate section digest scheme on the complete, observed stack.
        from .nfl2k5_bump_strength import _sections, section_digest
        if any(section_digest(final, s) != s.stored_digest for s in _sections(final)):
            raise OracleError("final stack has stale XBE section digests")
        spans = recorder.finish(final)
        if fingerprints != source_fingerprints():
            raise OracleError("patch sources changed during manifest generation")
        # Fingerprint the loaded stack, not unrelated research tools absent from
        # installed releases. The initial broad snapshot still detects changes
        # during generation; only dependencies actually loaded are exported.
        loaded_paths = {str(Path(module.__file__).resolve()) for module in tuple(sys.modules.values())
                        if getattr(module, "__file__", None)}
        used_fingerprints = {name: digest for name, digest in fingerprints.items()
                             if str((ROOT / name).resolve()) in loaded_paths}
        return {"schema": MANIFEST_SCHEMA, "retail_sha256": RETAIL_SHA256, "complete": True,
                "model": "observed experimental disc build plus dormant seven-on-seven; exact diffs union declared capacity/runtime storage",
                "preset": "softdrink_experimental", "preset_values": preset,
                "extra_owners": ["nfl2k5_seven_on_seven", "nfl2k5_seven_on_seven_book"],
                "disc_size": xiso.stat().st_size, "disc_xbe_sha256": RETAIL_SHA256,
                "preset_xbe_sha256": hashlib.sha256(preset_xbe).hexdigest(),
                "stack_xbe_sha256": hashlib.sha256(final).hexdigest(),
                "section_digests_verified": True,
                "image_options": {"scorebug_textures": False,
                                  "reason": "PNG atlas generation/import is asset-only; actual image mesh and all XBE/HUD writers ran"},
                "image_steps": [row["step"] for row in receipt["steps"]] + ["seven_on_seven_book"],
                "source_sha256": used_fingerprints, "steps": recorder.steps, "spans": spans}
