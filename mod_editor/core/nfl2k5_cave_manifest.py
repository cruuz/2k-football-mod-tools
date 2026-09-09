"""Rebuild cave ownership by observing the real studio writers on a disposable disc.

Run in a dedicated CLI process: the scoped wrappers observe existing module
functions during a synchronous build. No writer implementation is replaced.
The JSON contains addresses, sizes and hashes, never XBE/disc byte payloads.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
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


def changed_runs(before: bytes, after: bytes, *, allow_append: bool = False):
    """Exact half-open file spans, including the final changed byte."""
    if len(before) != len(after) and not (allow_append and len(after) > len(before)):
        raise OracleError("patch resized the XBE; ownership generation refused")
    start = None
    # Skip equal pages cheaply; only enumerate changed pages in Python.
    for page in range(0, len(before), 4096):
        end = min(page + 4096, len(before))
        a, b = before[page:end], after[page:end]
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
    if len(after) > len(before) and start is None:
        start = len(before)
    if start is not None:
        yield start, len(after)


class Recorder:
    def __init__(self, retail: bytes):
        self.retail = retail
        self.image = XbeImage(retail)
        self.spans: list[dict] = []
        self.steps: list[dict] = []
        self.covered = bytearray(len(retail))
        self.mapping_end = self.image.base + self.image.image_size

    def reserve(self, start: int, size: int, owner: str, basis: str):
        if not size:
            return
        if not self.image.base <= start < start + size <= self.mapping_end:
            raise OracleError(f"invalid declared reservation from {owner}")
        self.spans.append({"start": hex(start), "end": hex(start + size), "size": size,
                           "owner": owner, "basis": basis})

    def observe(self, module: ModuleType, function: str, before: bytes, after: bytes, receipt: dict):
        owner = module.__name__.split(".")[-1]
        if owner in ("nfl2k5_qb_spy_runtime", "nfl2k5_my_career_mode"):
            owner = module.OWNER  # allocator budget retains the research owner name
        post_image = XbeImage(after)
        allow_append = False
        if len(before) != len(after):
            from . import nfl2k5_depth_chart_storage as storage
            from . import nfl2k5_xbe_space as space
            allow_append = (owner == "nfl2k5_depth_chart_rows" and storage.state(before) == "retail"
                            and storage.state(after) == "applied")
            allow_append |= (owner in (space.OWNER, "nfl2k5_camera", "nfl2k5_dynamic_kickoff_relocated", "nfl2k5_scorebug_runtime", "nfl2k5_momentum", "nfl2k5_defensive_try", "nfl2k5_zone_drop", "nfl2k5_roster_storage", "nfl2k5_coverage_slider", "nfl2k5_scramble_tuning", "nfl2k5_music_playlist", "nfl2k5_practice_squad_screen", "nfl2k5_abilities_runtime", "nfl2k5_qb_spy", "nfl2k5_calendar_engine", "nfl2k5_read_option_runtime", "nfl2k5_franchise_2026", "nfl2k5_senior_bowl", "nfl2k5_guardian_overlay", "nfl2k5_my_career", "nfl2k5_screen_hooks", "nfl2k5_xbe_space", "nfl2k5_music_metadata", "nfl2k5_seven_on_seven", "nfl2k5_seven_on_seven_book", "nfl2k5_roster_arena_growth", "nfl2k5_franchise_autosave", "nfl2k5_coverage_trail", "nfl2k5_deep_zone", "nfl2k5_playbook_pair", "nfl2k5_weekly_prep", "nfl2k5_cpu_money_downs", "nfl2k5_franchise_edit_player")
                             and space.status(before) == "retail" and space.status(after) == "applied")
            if owner == 'nfl2k5_music_metadata':
                from . import nfl2k5_music_metadata as music
                allow_append |= music.status(before) == 'retail' and music.status(after) == 'applied'
        from . import nfl2k5_xbe_space as space
        grown_regions = space.layout(after)["regions"] if space.status(after) == "applied" else []
        runs = list(changed_runs(before, after, allow_append=allow_append))
        self.mapping_end = max(self.mapping_end, post_image.base + post_image.image_size)
        if len(after) > len(self.covered):
            self.covered.extend(bytes(len(after) - len(self.covered)))
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
                    from . import nfl2k5_xbe_space as space
                    page_owner = space.OWNER if any(r["va"] <= va < r["va"] + r["size"]
                        for r in grown_regions if not r.get("music")) else owner
                    self.reserve(va, stop - at, page_owner, "observed byte diff")
                at = stop
        self.steps.append({"owner": owner, "function": function,
                           "before_sha256": hashlib.sha256(before).hexdigest(),
                           "after_sha256": hashlib.sha256(after).hexdigest(),
                           "changed_bytes": sum(b - a for a, b in runs),
                           "file_runs": [[hex(a), hex(b)] for a, b in runs]})
        # MyCareer M3's second RW page and defensive_try's stat extension are
        # named children of their complete request unions. finish() publishes
        # them from the final layout, never from a different probe layout.
        # defensive_try is one writer with two named allocator owners. finish()
        # publishes both children, including the immutable stat descriptors.
        if owner in ("nfl2k5_xbe_space", "nfl2k5_camera", "nfl2k5_dynamic_kickoff_relocated", "nfl2k5_scorebug_runtime", "nfl2k5_music_metadata", "nfl2k5_momentum", "nfl2k5_defensive_try", "nfl2k5_zone_drop", "nfl2k5_roster_storage", "nfl2k5_coverage_slider", "nfl2k5_scramble_tuning", "nfl2k5_music_playlist", "nfl2k5_practice_squad_screen", "nfl2k5_abilities_runtime", "nfl2k5_qb_spy", "nfl2k5_calendar_engine", "nfl2k5_read_option_runtime", "nfl2k5_franchise_2026", "nfl2k5_senior_bowl", "nfl2k5_guardian_overlay", "nfl2k5_my_career", "nfl2k5_screen_hooks", "nfl2k5_seven_on_seven", "nfl2k5_seven_on_seven_book", "nfl2k5_roster_arena_growth", "nfl2k5_franchise_autosave", "nfl2k5_coverage_trail", "nfl2k5_deep_zone", "nfl2k5_playbook_pair", "nfl2k5_weekly_prep", "nfl2k5_cpu_money_downs", "nfl2k5_franchise_edit_player") and space.status(after) == "applied":
            # Owners that can also run on a retail-space image (seven-on-seven in the
            # gate composition, before the allocator) have no allocator reservations
            # yet; the allocator's planned pages lie outside that image's mapping.
            from . import nfl2k5_xbe_space as space
            for reservation in space.reservations(after):
                # The preset and the dormant-owner probe can assign different
                # offsets within the same owned pages. Keep their byte writes
                # covered here; publish named children from the final layout.
                if reservation["basis"].startswith("named "):
                    continue
                self.reserve(int(reservation["start"], 0), reservation["size"],
                             reservation["owner"], reservation["basis"])
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
                if owner == "nfl2k5_camera" and edit.get("label") == "owned_camera_wrappers":
                    allocation = module.allocation(after)
                    if allocation is None or (va, size) != (allocation["va"], allocation["size"]):
                        raise OracleError("camera wrapper receipt differs from its named allocation")
                # An owner's write into its own named allocation is published from the
                # FINAL layout by finish(); the dormant-owner probe can place the same
                # owner at a different offset, so a declared edit inside a grown page
                # would pin a stale address (the camera owner's wrapper slot did).
                if any(r["va"] <= va < r["va"] + r["size"] for r in grown_regions if not r.get("music")):
                    continue
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
        if len(final) > len(self.covered):
            raise OracleError("unattributed final XBE growth")
        missing = [a for a, b in changed_runs(self.retail, final, allow_append=True) if not all(self.covered[a:b])]
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
        self.reserve(logo._fields(final)[0], logo.LOGO_SIZE, "nfl2k5_boot_logo", "complete relocated loader bitmap")
        from . import nfl2k5_xbe_space as space
        if space.status(final) == "applied":
            for reservation in space.reservations(final):
                self.reserve(int(reservation["start"], 0), reservation["size"],
                             reservation["owner"], reservation["basis"])
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


def build_manifest(retail: bytes, xiso: Path, *, work_dir: Path, progress=None, synthetic_owner_bytes=0) -> dict:
    """Actual experimental image build plus the dormant seven-on-seven owner.

    The source disc is read-only. Only the temporary target is passed to studio
    writers. Temporary image and proprietary build receipts are not exported.
    """
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise OracleError("manifest generation requires the pinned USA retail XBE")
    from . import mod_build as build, nfl2k5_throw_tuning as tt
    from . import nfl2k5_position_pools as pools, nfl2k5_season_length as season
    from . import nfl2k5_seven_on_seven as seven
    from . import nfl2k5_seven_on_seven_book as seven_book
    from . import nfl2k5_xbe_space as space, nfl2k5_dynamic_kickoff_relocated as relocated
    from . import nfl2k5_scorebug_runtime as runtime, nfl2k5_scorebug_ingame as scorebug_ingame
    from . import nfl2k5_music_metadata as music
    from . import nfl2k5_momentum as momentum
    from . import nfl2k5_defensive_try as defensive_try, nfl2k5_zone_drop as zone_drop
    from . import nfl2k5_roster_storage as roster_storage
    from . import nfl2k5_coverage_slider as coverage, nfl2k5_scramble_tuning as scramble
    from . import nfl2k5_throw_arc as flight
    from . import nfl2k5_music_playlist as playlist
    from . import nfl2k5_practice_squad_screen as practice_screen
    from . import nfl2k5_practice_squad as ps, nfl2k5_franchise_practice as fp
    from . import nfl2k5_practice_reserves as pr
    from . import nfl2k5_abilities_runtime as abilities
    from . import nfl2k5_qb_spy_runtime as qb_spy
    from . import nfl2k5_calendar_engine as calendar
    from . import nfl2k5_read_option_runtime as read_option
    from . import nfl2k5_franchise_2026 as franchise_2026
    from . import nfl2k5_senior_bowl as senior_bowl
    from . import nfl2k5_animation_xbe as animation_xbe
    from . import nfl2k5_guardian_overlay as guardian
    from . import nfl2k5_my_career_mode as my_career, nfl2k5_crib_reclaim as crib_reclaim
    # Includes defensive_try's scale-out stat code/RO requests, atomically
    # installed by the existing defensive_try entry in both owner lists below.
    from . import nfl2k5_screen_hooks as screen_hooks
    from . import nfl2k5_roster_arena_growth as arena_growth
    from . import nfl2k5_franchise_autosave as autosave
    from . import nfl2k5_coverage_trail as coverage_trail
    from . import nfl2k5_deep_zone as deep_zone
    from . import nfl2k5_playbook_pair as playbook_pair
    from . import nfl2k5_weekly_prep as weekly_prep
    from . import nfl2k5_cpu_money_downs as money_downs
    from . import nfl2k5_franchise_edit_player as edit_player
    from . import nfl2k5_camera as camera
    from . import nfl2k5_espn25_rosters as espn25
    all_requests = camera.REQUESTS + relocated.REQUESTS + runtime.REQUESTS + momentum.REQUESTS + defensive_try.REQUESTS + zone_drop.REQUESTS + roster_storage.REQUESTS + coverage.REQUESTS + scramble.REQUESTS + playlist.REQUESTS + practice_screen.REQUESTS + abilities.REQUESTS + qb_spy.REQUESTS + calendar.REQUESTS + read_option.REQUESTS + franchise_2026.REQUESTS + senior_bowl.REQUESTS + animation_xbe.REQUESTS + guardian.REQUESTS + my_career.REQUESTS + screen_hooks.REQUESTS + arena_growth.REQUESTS + autosave.REQUESTS + espn25.REQUESTS + coverage_trail.REQUESTS + deep_zone.REQUESTS + seven.REQUESTS + playbook_pair.REQUESTS + weekly_prep.REQUESTS + money_downs.REQUESTS + edit_player.REQUESTS
    if type(synthetic_owner_bytes) is not int or synthetic_owner_bytes < 0:
        raise OracleError("synthetic owner size must be a nonnegative integer")
    probe_requests = (("synthetic_scaleout", "code", synthetic_owner_bytes, space.PAGE),) if synthetic_owner_bytes else ()
    space.plan(all_requests + probe_requests)  # refuse before any disc build
    progress = progress or (lambda _message: None)
    xiso = xiso.resolve(strict=True)
    work_dir = work_dir.resolve(strict=True)
    if build._xbe_bytes(xiso) != retail:
        raise OracleError("disc default.xbe does not match the supplied pinned retail XBE")
    recorder = Recorder(retail)
    modules = {m.__name__: m for m in vars(tt).values() if isinstance(m, ModuleType)
               and m.__name__.startswith("mod_editor.core.nfl2k5_")}
    modules.update({m.__name__: m for m in (tt, pools, season, space, relocated, runtime, scorebug_ingame, music, momentum, defensive_try, zone_drop, roster_storage)})
    modules.update({m.__name__: m for m in (camera, coverage, scramble, flight, playlist, practice_screen, ps, fp, pr, abilities, qb_spy, calendar, read_option, franchise_2026, senior_bowl, animation_xbe, guardian, my_career, crib_reclaim, screen_hooks, arena_growth, autosave, espn25, coverage_trail, deep_zone, seven, playbook_pair, weekly_prep, money_downs, edit_player)})
    for name in ("nfl2k5_scorebug_layout", "nfl2k5_scorebug_position_patch"):
        module = build._tools_module(name)
        if module is None:
            raise OracleError("required image writer unavailable: " + name)
        modules[module.__name__] = module
    hud = importlib.import_module("mod_editor.core.nfl2k5_hud_layout")
    modules[hud.__name__] = hud
    fingerprints = source_fingerprints()
    with tempfile.TemporaryDirectory(prefix="nfl2k5-oracle-", dir=work_dir) as temp:
        target = (Path(temp) / "stack.xiso.iso").resolve()
        preset = dict(build.PRESETS["softdrink_experimental"])
        plan = build.BuildPlan(source=str(xiso), target=str(target), **preset)
        with ExitStack() as stack:
            # v7 requires its matching atlas. Observe its actual fixed-span
            # writer, then the runtime XBE owner after all ordinary build passes.
            for module in modules.values():
                for name in ("apply", "apply_xbe", "xbe_apply", "plan_patch", "apply_arc_table", "patch_xbe", "apply_chop_block"):
                    function = getattr(module, name, None)
                    if inspect.isfunction(function) and function.__module__ == module.__name__:
                        stack.enter_context(patch.object(module, name, recorder.wrapper(module, name)))
            receipt = build.build(plan, progress=lambda message, *_: progress(message))
            preset_xbe = build._xbe_bytes(target)
            # The dormant-owner probe needs an XBE WITHOUT an allocator directory: an installed request
            # set is immutable, so every preset option that selects an allocator owner is turned off
            # here and the complete union is installed below by the probe itself.
            if plan.scorebug_runtime or space.status(preset_xbe) != "retail":
                target.unlink()
                progress("Building the separate dormant-owner allocation probe")
                build.build(replace(plan, camera=False, scorebug_runtime=False, xbe_space=False, kickoff_relocated=False,
                                    scorebug=bool(plan.scorebug or plan.scorebug_runtime),
                                    season_cap=False, calendar_engine=False, momentum=0, momentum_contact=False,
                                    defensive_try=False, zone_drop_cap=False, all_stadiums=False, coverage_slider=False,
                                    scramble_tuning=False, music_shuffle=False, music_shuffle_selection=None,
                                    practice_squad_screen=False, abilities=False, abilities_off_week=None, qb_spy=False,
                                    franchise_autosave=False, coverage_trail=False, franchise_edit_player=False),
                            progress=lambda message, *_: progress(message))
            owner_base = build._xbe_bytes(target)
            # All current owners, even the hidden opt-in patch, reserve their space.
            extra, _ = tt._apply_all(owner_base, None, catch_slider=False, seven_on_seven=True)
            build._write_xbe_bytes(target, extra)
            progress("Applying dormant seven-on-seven playbook to disposable image")
            try:
                seven_book.apply(target)
                book_note = "applied"
            except Exception as exc:  # noqa: BLE001 - the book writer wants a retail practice book; the depth-roles
                # pass (ADVANCED+) rewrites its personnel bytes first. The book carries no XBE bytes, so the
                # reservation picture is complete without it; record the refusal instead of failing the manifest.
                book_note = f"refused: {exc}"
            final = build._xbe_bytes(target)
            if final != extra:
                raise OracleError("seven-on-seven book writer unexpectedly changed XBE bytes")
            # The separate probe adds dormant owners using the complete union.
            # Observe their real pure-byte writers after every disc/XBE pass.
            # The generalized writer resolves the grown extent directly, so
            # manifest generation does not depend on the protected dispatcher.
            final, _ = ps.apply(final)
            final, _ = fp.apply(final)
            final, _ = pr.apply(final)
            allocation_base = final
            final, _ = space.apply(final, all_requests, scaleout=True)
            final, _ = seven.apply(final)
            final, _ = espn25.apply_xbe(final)
            final, _ = autosave.apply(final)
            final, _ = coverage_trail.apply(final)
            final, _ = deep_zone.apply(final)
            final, _ = playbook_pair.apply(final)
            final, _ = weekly_prep.apply(final)
            final, _ = money_downs.apply(final)
            final, _ = edit_player.apply(final)
            final, _ = camera.apply(final)
            final, _ = roster_storage.apply(final)
            final, _ = defensive_try.apply(final)
            final, _ = zone_drop.apply(final)
            final, _ = relocated.apply(final)
            final, _ = runtime.apply(final)
            final, _ = momentum.apply(final, momentum=100, momentum_contact=True, momentum_collisions=True, momentum_collision_level=100)
            final, _ = coverage.apply(final)
            final, _ = scramble.apply(final)
            final, _ = playlist.apply(final)
            final, _ = practice_screen.apply(final)
            final, _ = abilities.apply(final, abilities_off_week=7)
            final, _ = qb_spy.apply(final)
            final, _ = calendar.apply(final)
            final, _ = read_option.apply(final)
            final, _ = franchise_2026.apply(final)
            final, _ = senior_bowl.apply(final)
            final, _ = animation_xbe.apply(final)
            final, _ = guardian.apply(final)
            final, _ = my_career.apply(final)
            final, _ = crib_reclaim.apply(final)
            final, _ = screen_hooks.apply(final)
            final, _ = arena_growth.apply(final, created_teams_extra=2)
            # Flatter flight and the old relocated high-arc band are mutually
            # exclusive. Observe the exact alternative's table span too; this
            # reservation union does not claim both flight modes run together.
            flight.apply(retail)
            # Ownership probe only, on a disposable oracle disc. Presets never
            # enable a personal music library; no playback claim is made here.
            final, _ = music.apply(final, [dict(title=f'Tone {i+1:03}', artist='Synthetic', frames=256)
                                           for i in range(200)])
            from . import nfl2k5_depth_chart_storage as storage, platform_compat as io
            import os
            descriptor = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                storage.write_image_xbe(descriptor, final)
                offset, length = tt._xdvdfs_module().xbe_extent(descriptor, os.fstat(descriptor).st_size)
                if io.pread(descriptor, length, offset) != final:
                    raise OracleError("grown manifest XBE read-back differs")
            finally:
                os.close(descriptor)
        # Validate section digest scheme on the complete, observed stack.
        from .nfl2k5_bump_strength import _sections, section_digest
        if any(section_digest(final, s) != s.stored_digest for s in _sections(final)):
            raise OracleError("final stack has stale XBE section digests")
        spans = recorder.finish(final)
        synthetic_proof = None
        if synthetic_owner_bytes:
            progress(f"Building synthetic {synthetic_owner_bytes}-byte owner on the real disposable disc")
            probe, _ = space.apply(allocation_base, all_requests + probe_requests, scaleout=True)
            for module, kwargs in ((seven, {}), (money_downs, {}), (espn25.XbePatch, {}), (autosave, {}), (playbook_pair, {}), (weekly_prep, {}), (edit_player, {}), (camera, {}), (defensive_try, {}), (zone_drop, {}), (relocated, {}), (runtime, {}),
                                   (momentum, dict(momentum=100, momentum_contact=True, momentum_collisions=True, momentum_collision_level=100)),
                                   (roster_storage, {}), (coverage, {}), (scramble, {}), (playlist, {}),
                                   (practice_screen, {}), (abilities, dict(abilities_off_week=7)), (qb_spy, {}), (calendar, {}), (read_option, {}),
                                   (screen_hooks, {}),
                                   (arena_growth, dict(created_teams_extra=2)),
                                   (music, dict(song_records=[dict(title=f'Tone {i+1:03}', artist='Synthetic', frames=256) for i in range(200)]))):
                probe, _ = module.apply(probe, **kwargs)
            probe, _ = space.install_code(probe, "synthetic_scaleout", b"\xc3" + b"\x90" * (synthetic_owner_bytes - 1))
            if any(module.status(probe) != "applied" for module in (space, seven, camera, relocated, runtime, momentum, defensive_try, zone_drop, music, roster_storage, coverage, scramble, playlist, practice_screen, abilities, qb_spy, calendar, read_option, screen_hooks, arena_growth, autosave, espn25.XbePatch, playbook_pair, weekly_prep, money_downs, edit_player)):
                raise OracleError("synthetic owner does not compose with the complete real owner union")
            descriptor = os.open(target, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                written = storage.write_image_xbe(descriptor, probe)
                offset, length = tt._xdvdfs_module().xbe_extent(descriptor, os.fstat(descriptor).st_size)
                if io.pread(descriptor, length, offset) != probe:
                    raise OracleError("synthetic real-disc read-back differs")
                replay = storage.write_image_xbe(descriptor, probe)
                synthetic_proof = dict(owner_bytes=synthetic_owner_bytes, xbe_sha256=hashlib.sha256(probe).hexdigest(),
                    xbe_bytes=len(probe), disc_bytes=os.fstat(descriptor).st_size, write=written, replay=replay,
                    kickoff_relocated=relocated.status(probe), section_digests_verified=True,
                    allocation=space.layout(probe), runtime_witnessed=False)
                storage.write_image_xbe(descriptor, final)
                if io.pread(descriptor, len(final), offset) != final:
                    raise OracleError("synthetic owner removal read-back differs")
                synthetic_proof["removed_from_final_disc"] = True
            finally:
                os.close(descriptor)
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
                "stack_image_size": XbeImage(final).image_size,
                "model": "observed experimental disc build plus dormant seven-on-seven, grown kickoff, scorebug runtime music metadata, Momentum, defensive try and zone drop; exact diffs union owned pages and named allocations",
                "preset": "softdrink_experimental", "preset_values": preset,
                "extra_owners": ["nfl2k5_seven_on_seven", "nfl2k5_seven_on_seven_book", space.OWNER, relocated.OWNER, runtime.OWNER, music.OWNER, momentum.OWNER, defensive_try.OWNER, zone_drop.OWNER, roster_storage.OWNER, coverage.OWNER, scramble.OWNER, flight.OWNER, playlist.OWNER, practice_screen.OWNER, abilities.OWNER, qb_spy.OWNER, calendar.OWNER, read_option.OWNER, franchise_2026.OWNER, senior_bowl.OWNER, animation_xbe.OWNER, guardian.OWNER, my_career.OWNER, my_career.EXTRA_OWNER, crib_reclaim.OWNER, screen_hooks.OWNER, arena_growth.OWNER, autosave.OWNER, espn25.OWNER, coverage_trail.OWNER, deep_zone.OWNER, coverage_trail.OWNER, playbook_pair.OWNER, weekly_prep.OWNER, money_downs.OWNER, edit_player.OWNER],
                "alternative_flight_probe": "flatter flight on retail; final stack keeps the selected existing flight mode",
                "seven_on_seven_book": book_note,
                "disc_size": xiso.stat().st_size, "disc_xbe_sha256": RETAIL_SHA256,
                "preset_xbe_sha256": hashlib.sha256(preset_xbe).hexdigest(),
                "stack_xbe_sha256": hashlib.sha256(final).hexdigest(),
                "section_digests_verified": True, "allocator_layout": space.layout(final),
                "momentum_settings": momentum.read_settings(final),
                "synthetic_disc_proof": synthetic_proof,
                "image_options": {"scorebug_textures": True, "runtime_panel_resources": False,
                                  "reason": "Manifest proves XBE ownership only; panel transport has its own resource tests"},
                "image_steps": [row["step"] for row in receipt["steps"]] + ["seven_on_seven_book", "xbe_space", "kickoff_relocated", "scorebug_runtime", "music_metadata", "momentum", "defensive_try", "zone_drop_cap", "all_stadiums"],
                "source_sha256": used_fingerprints, "steps": recorder.steps, "spans": spans}
