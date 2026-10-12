"""Native automatic-coach fixtures used by vp1_verify --automatic.

PLAY loading, CPU setup, statistics binding, controller transition and all
selection functions execute actual XBE instructions. The explicit environment
adds a bounded heap allocator/free service to World's roster/rating fixtures;
there are no VIP, setup, selector, RNG or compatibility stubs.
"""
from __future__ import annotations

from collections import Counter
import struct

from mod_editor.core import nfl2k5_coach_ai as ai, nfl2k5_coach_ai_code as assembly
from mod_editor.core import nfl2k5_play_scoring as s, nfl2k5_vip as vip
from pb.scoring_selectors import World


class AutoWorld(World):
    HEAP = 0x3100000

    def __init__(self, payload, *, load_route="resource"):
        super().__init__(payload)
        assert load_route in ("resource", "copy")
        self.load_route = load_route
        self.m.mem_map(self.HEAP, 0x10000)
        self.heap_live = {}
        self.heap_events = []
        self.heap_fail = False
        self.next_heap = self.HEAP
        self.owned = ai.allocations(payload) if ai.status(payload) == "applied" else None
        self.state_va = self.owned["data"]["va"] if self.owned else None
        self.visits.update()
        for pc in (0x1665A0, 0xE0D90, 0x161E30, 0xF7B30, 0xF6E60, 0xF7A90, 0xF7BE0, 0xF71E0, 0x17F1D0, 0x17DFC0):
            self.m.hook_add(self.ucmod.UC_HOOK_CODE, lambda _u, a, _n, _d: self.visits.update([hex(a)]), begin=pc, end=pc)

        def allocation(m, address, size, _):
            n = m.reg_read(self.r.UC_X86_REG_EDX)
            assert n == ai.CONTEXT_SIZE, f"Unexpected allocation {n}"
            result = 0 if self.heap_fail else self.next_heap
            if result:
                assert result + n <= self.HEAP + 0x10000
                self.next_heap += (n + 15) & ~15
                self.heap_live[result] = n
                # Deliberately dirty: the kernel must initialize every byte.
                m.mem_write(result, b"\xA5" * n)
            self.heap_events.append(dict(action="allocate", size=n, result=result))
            m.reg_write(self.r.UC_X86_REG_EAX, result)
            self._return()

        def release(m, address, size, _):
            p = m.reg_read(self.r.UC_X86_REG_ECX)
            assert p in self.heap_live, f"Invalid free {p:#x}"
            assert p not in (self.get(0xBA04B0), self.get(0xBA04B4)), "Freed a published context"
            for side in (0, 1):
                meta = self.get(0xE5FC20 + side * 64 + 12)
                assert not meta or self.get(meta) != p + 0x20B8, "Freed still-published coach statistics"
            self.heap_events.append(dict(action="free", pointer=p))
            del self.heap_live[p]
            self._return()

        self.m.hook_add(self.ucmod.UC_HOOK_CODE, allocation, begin=0x48700, end=0x48700)
        self.m.hook_add(self.ucmod.UC_HOOK_CODE, release, begin=0x48870, end=0x48870)

    def load_native_book(self, raw):
        if self.load_route == "copy":
            super().load_native_book(raw)
        else:
            # Completed disc I/O supplies the raw body in the native fixed
            # team buffer. The resource manager's +14 link points to it.
            # Execute its real PLAY callback and in-place relocation, the
            # path witnessed in cold-boot run01; no loader is stubbed.
            self.m.mem_write(s.BOOK, raw[32:])
            self.put(s.BOOK + 0x14, s.BOOK)
            self.put(0xB72918, s.SOURCE + 0x1F000)
            self.call(0x1665A0, ecx=s.BOOK)
        self.loader_witness = dict(route=self.load_route,
            visits={hex(pc): self.visits[hex(pc)] for pc in (0x1665A0, 0xE0D90, 0x161E30)},
            marker=hex(self.get(s.BOOK + ai.PROFILE_OFFSET + 28)),
            environment="Completed raw disc I/O and resource-manager body link; native callback/relocation execute")

    def _return(self):
        sp = self.m.reg_read(self.r.UC_X86_REG_ESP)
        self.m.reg_write(self.r.UC_X86_REG_EIP, self.get(sp))
        self.m.reg_write(self.r.UC_X86_REG_ESP, sp + 4)

    def initialize_native_plays(self):
        # E0D90 already executes 1A9A80 for every declared play. The raw-copy
        # path only relocates pointers, so it needs the normal extra pass.
        if self.load_route == "copy":
            super().initialize_native_plays()

    def install_roster(self, info, coach):
        root, labels = s.SOURCE + 0x1F000, s.SOURCE + 0x1F400
        self.put(0xB72918, root)
        self.put(root + 0x48, 36)
        self.put(root + 0x4C, labels)
        self.label = labels + info["book_index"] * 8
        self.info = info
        for side in (0, 1):
            front = (0xB30864, 0xB30A58)[side]
            cp = s.SOURCE + 0x1D000 + side * 0x100
            self.m.mem_write(cp, bytes(coach))
            self.put(front + 0x14C, cp)
            self.m.mem_write(front + 0x118, struct.pack("<H", info["asset"]))
            self.put(front + 0x128, 0)
            self.put(0xE5FE78 + side * 4, self.label)
        # Both actual runtime objects are also available for F7BE0 tests.
        for dst, src in ((0xE5FC20, self.defense), (0xE5FC60, s.TEAM)):
            self.m.mem_write(dst, bytes(self.m.mem_read(src, 64)))
        self.put(0xE5FC20, 0xE5FC60)
        self.put(0xE5FC60, 0xE5FC20)

    def setup(self, mode=4, *, side=1, human=False, team=s.TEAM):
        self.put(0xE5FF80, mode)
        self.put(team + 0x30, int(human))
        self.call(0xF6E60, eax=team, args=(side + 1, self.label, side))
        self.call(0xF7A90, edi=team)
        return self.get(0xBA04B0 + side * 4)

    def diagnostic(self):
        return dict(bindings=[self.get(0xBA04B0 + side * 4) for side in (0, 1)],
                    state=list(struct.unpack("<14I", self.m.mem_read(self.state_va, 56))) if self.state_va else None,
                    heap_events=self.heap_events, native_visits=dict(self.visits))


def bind_automatic(xbe, book, receipt, coach, mode=4, *, load_route="resource"):
    w = AutoWorld(xbe, load_route=load_route)
    w.load(book)
    w.install_roster(receipt["automatic_profile"], coach)
    assert w.get(0xBA04B0) == w.get(0xBA04B4) == 0, "Automatic proof must start with no VIP"
    # Snapshot all resident USR primary/supplementary bytes before setup.
    slots = bytes(w.m.mem_read(0xBDFCF0, 4 * vip.PRIMARY_SIZE))
    supplementary = bytes(w.m.mem_read(0xBC6E40, 4 * (vip.SIZE - vip.PRIMARY_SIZE)))
    # Execute the actual game-level setup, including both native side calls,
    # transient initialization and both statistics bindings. The opposite side
    # is human; World uses a separate fixture alias for subsequent selectors.
    w.put(0xE5FF80, mode)
    w.put(0xE5FC20 + 0x30, 1)
    w.put(0xE5FC60 + 0x30, 0)
    w.call(0xF7B30)
    context = w.get(0xBA04B4)
    w.put(s.TEAM + 0x38, w.get(0xE5FC60 + 0x38))
    assert w.get(0xBA04B0) == 0, "Human opposite side received a profile"
    assert context and context in w.heap_live, w.diagnostic()
    assert w.get(context + 0x38) == 2 and w.get(context + 0x10) == 1
    assert w.get(s.META + 0x100) == context + 0x20B8
    assert w.get(0xE5FF80) == mode, "Global game mode changed"
    assert bytes(w.m.mem_read(0xBDFCF0, len(slots))) == slots
    assert bytes(w.m.mem_read(0xBC6E40, len(supplementary))) == supplementary
    expected = bytearray(ai.expand_profile(book))
    # F7B30 runs native 1B1EE0/281A90: game-start history decay halves
    # large counters (including playback profiles). Compare their defined
    # integer effect, rather than pretending the raw counters survive setup.
    def halve_pair(offset):
        den, num = struct.unpack_from("<HH", expected, offset)
        if den >= 254:
            struct.pack_into("<HH", expected, offset, den >> 1, num >> 1)
    for offset in (0xE90, 0xE94, 0x2186):
        halve_pair(offset)
    for offset in (0x20B8, 0x20BA):
        value = struct.unpack_from("<H", expected, offset)[0]
        if value >= 254:
            struct.pack_into("<H", expected, offset, value >> 1)
    for offset, count in ((4, 6), (0x1C, 1), (0x20, 4), (0x30, 4), (0x40, 4), (0x50, 4)):
        at = 0x20B8 + offset
        values = struct.unpack_from("<" + "H" * (count * 2), expected, at)
        if any(v >= 254 for v in values[::2]):
            struct.pack_into("<" + "H" * (count * 2), expected, at, *(v >> 1 for v in values))
    for start, end in ((0x3C, 0xDDE), (0xDF6, 0xDFE), (0xE90, 0xE98),
                       (0x20B8, 0x2118), (0x2186, 0x218A)):
        assert bytes(w.m.mem_read(context + start, end - start)) == expected[start:end], hex(start)
    return w, context


def audit_loaders(xbe, book, receipt, coach):
    rows = []
    for route in ("resource", "copy"):
        w, context = bind_automatic(xbe, book, receipt, coach, load_route=route)
        assert w.loader_witness["marker"] == "0x314b4f43", w.loader_witness
        rows.append(dict(**w.loader_witness, binding=context, passed=True))
    return dict(passed=True, cases=rows)


def user_choice(world, book_index):
    """A declared resident user fixture, resolved by native 142370."""
    raw = bytearray(vip.SIZE)
    struct.pack_into("<I", raw, 0, 0x1255AA77)
    name = "User choice".encode("utf-16le")
    raw[4:4 + len(name)] = name
    struct.pack_into("<i", raw, vip.CONTEXT + 0x34, book_index)
    world.m.mem_write(0xBDFCF0, bytes(raw[:vip.PRIMARY_SIZE]))
    world.m.mem_write(0xBC6E40, bytes(raw[vip.PRIMARY_SIZE:]))
    return world.call(0x142370, ecx=0)


def audit_modes(xbe, baseline, retail, book, receipt, coach, *, draws=16):
    from tools.b77 import vp1_verify as v
    rows = []
    for mode in (4, 5, 6, 7):
        w, context = bind_automatic(xbe, book, receipt, coach, mode)
        rng = v.seed(w, 6182026)
        for index, source in enumerate(receipt["pools"]):
            permitted = {(c["formation"], c["play"], bool(c["flipped"])) for c in source["choices"]}
            for draw in range(draws):
                w.configure(**v.settings(index), direction=1 if draw % 2 else -1)
                w.fput(0xBF1484, rng.random())
                w.call(0x1B2D40, ecx=s.TEAM)
                out = s.SOURCE + 0x19100
                w.call(0x17F1D0, ecx=out, edx=out + 4, args=(out + 8, out + 12, out + 16))
                fv, pv = struct.unpack("<II", w.m.mem_read(out, 8))
                _, fi, pi = v.classify(w, fv, pv)
                assert (fi, pi, bool(w.get(out + 12))) in permitted
                record = w.get(context + 0xDE8)
                pool = context + 0x3C + index * 128
                assert pool + 2 <= record < pool + 128
                w.put(s.META + 0x118, fv)
                w.put(s.META + 0x11C, pv)
        automatic = w.diagnostic()
        assert w.setup(mode, human=True, team=0xE5FC60) == 0, "Human received an automatic profile"
        assert w.get(0xE5FC60 + 0x38) == 0
        assert w.get(s.META + 0x100) != context + 0x20B8
        chosen = user_choice(w, receipt["book_index"])
        w.put(0xBA04B4, chosen)
        assert w.setup(mode, team=0xE5FC60) == chosen and chosen != context, "Explicit user VIP lost"
        assert w.get(chosen + 0x38) == 2
        # An explicit different NFL coach keeps native coach statistics.
        w.put(0xBA04B4, 0)
        cp = w.get(0xB30A58 + 0x14C)
        w.m.mem_write(cp + 0x40, struct.pack("<H", 7999))
        assert w.setup(mode, team=0xE5FC60) == 0, "Explicit NFL Coach was overridden"
        assert w.get(s.META + 0x100) == 0xBA0590
        w.call(0xF7BE0)
        assert w.get(0xBA04B4) == 0, "An old VIP displaced the newer NFL Coach choice after controller reassignment"
        controls = []
        for label, executable in (("no_feature", baseline), ("retail", retail)):
            control = AutoWorld(executable)
            control.load(book)
            control.install_roster(receipt["automatic_profile"], coach)
            assert control.setup(mode) == 0 and not control.heap_events
            assert control.get(s.META + 0x100) == 0xBA0590
            controls.append(dict(kind=label, binding=0, heap_allocations=0, native_setup=True))
        alias = next((r.get("alternate_portrait") for r in ai.portrait_rows()
                      if r["team"] == receipt["team"]), None)
        alternate = None
        if alias:
            changed = bytearray(coach)
            struct.pack_into("<H", changed, 0x40, alias)
            other, _ = bind_automatic(xbe, book, receipt, bytes(changed), mode)
            alternate = dict(portrait=alias, automatic=other.diagnostic())
        rows.append(dict(mode=mode, draws=20 * draws, all_from_own_pool=True,
                         started_without_vip=True, human_clear=True, user_vip_wins=True,
                         explicit_nfl_coach_wins=True, controls=controls, automatic=automatic,
                         alternate_roster_portrait=alternate))
    return dict(rows=rows, passed=True)


def audit_exclusions(xbe, book, receipt, coach):
    cases = []
    def fresh():
        w = AutoWorld(xbe)
        w.load(book)
        w.install_roster(receipt["automatic_profile"], coach)
        return w
    # Every excluded route starts with no selected profile.
    for mode in (0, 1, 2, 3, 8, 9, 10):
        w = fresh()
        assert w.setup(mode) == 0 and not w.heap_events
        cases.append(dict(case="excluded_mode", mode=mode, passed=True))
    for kind in (1, 2, 4, 5):
        w = fresh()
        w.put(0xB30A58 + 0x128, kind)
        assert w.setup() == 0 and not w.heap_events
        cases.append(dict(case="team_kind", kind=kind, passed=True))
        for mode in (4, 7):
            w = fresh()
            w.put(0xB30A58 + 0x128, kind)
            chosen = user_choice(w, receipt["book_index"])
            w.put(0xBA04B4, chosen)
            assert w.setup(mode) == (chosen if mode == 4 else 0), "Special-team VIP behavior changed"
            assert not w.heap_events
            cases.append(dict(case="special_team_explicit_vip", kind=kind, mode=mode,
                              native_choice_preserved=mode == 4, passed=True))
    for label, address in (("celebrity", 0xE601FC), ("special_state", 0xB34300), ("replay", 0xA99884)):
        w = fresh()
        w.put(address, 1)
        assert w.setup() == 0 and not w.heap_events
        cases.append(dict(case=label, passed=True))
    w = fresh()
    career = ai.career_state_va(xbe)
    if career:
        w.put(career, 0x4251434D)
        w.put(career + 4, 0x31303030)
        w.put(0xE576A0, 2)
        for stage in range(1, 7):
            w.put(career + 24, stage)
            assert w.setup(7) == 0 and not w.heap_events
        cases.append(dict(case="mycareer", stages=list(range(1, 7)), passed=True))
    else:
        cases.append(dict(case="mycareer", passed=None, reason="MyCareer owner not present in this executable"))
    for label, modify in (
        ("book_label", lambda w: setattr(w, "label", w.label + 8)),
        ("wrong_current_asset", lambda w: w.m.mem_write(0xB30A58 + 0x118, b"\x5A\0")),
        ("missing_profile", lambda w: w.put(s.BOOK + ai.PROFILE_OFFSET, 0)),
        ("unvalidated_profile", lambda w: w.put(s.BOOK + ai.PROFILE_OFFSET + 28, 0)),
        ("bad_record_bounds", lambda w: w.m.mem_write(s.BOOK + ai.PROFILE_OFFSET + 129, b"\xFF")),
    ):
        w = fresh()
        modify(w)
        assert w.setup() == 0 and not w.heap_events, label
        cases.append(dict(case=label, passed=True))
    for label, offset in (("changed_book", 32 + 0x3400), ("changed_profile", 32 + ai.PROFILE_OFFSET + 135)):
        raw = bytearray(book)
        raw[offset] ^= 1
        w = AutoWorld(xbe)
        w.load(bytes(raw))
        w.install_roster(receipt["automatic_profile"], coach)
        assert w.get(s.BOOK + ai.PROFILE_OFFSET + 28) == 0
        assert w.setup() == 0 and not w.heap_events
        cases.append(dict(case=label, passed=True))
    w = fresh()
    w.heap_fail = True
    assert w.setup() == 0
    w.heap_fail = False
    assert w.setup() in w.heap_live
    cases.append(dict(case="allocation_failure_and_retry", passed=True))
    return dict(cases=cases, passed=all(c["passed"] is not False for c in cases))


def audit_lifecycle(xbe, book, receipt, coach):
    unloading = AutoWorld(xbe)
    unloading.load(book)
    unloading.install_roster(receipt["automatic_profile"], coach)
    for side in (0, 1):
        assert unloading.setup(7, side=side, team=0xE5FC20 + side * 64)
    unloading.call(unloading.owned["code"]["va"] + assembly.LABELS["coach_cleanup"])
    assert not unloading.heap_live
    for side in (0, 1):
        team = 0xE5FC20 + side * 64
        assert unloading.get(unloading.get(team + 12)) == 0xBA04B8 + side * 0xD8
        assert unloading.get(team + 0x38) == 0
    w = AutoWorld(xbe)
    w.load(book)
    w.install_roster(receipt["automatic_profile"], coach)
    home = w.setup(7, side=0, team=0xE5FC20)
    away = w.setup(7, side=1, team=0xE5FC60)
    assert home and away and home != away and len(w.heap_live) == 2
    w.put(0xE5FC20 + 0x30, 1)
    w.call(0xF7BE0)
    assert w.get(0xBA04B0) == 0 and w.get(0xBA04B4) == away
    assert w.get(w.get(0xE5FC20 + 12)) != home + 0x20B8
    w.put(0xE5FC20 + 0x30, 0)
    w.put(0xE5FC60 + 0x30, 1)
    w.call(0xF7BE0)
    assert w.get(0xBA04B0) == home and w.get(0xBA04B4) == 0
    chosen = user_choice(w, receipt["book_index"])
    w.put(0xBA04B0, chosen)
    assert w.setup(7, side=0, team=0xE5FC20) == chosen
    w.call(0xF7BE0)
    assert w.get(0xBA04B0) == chosen, "Controller transition discarded explicit CPU VIP"
    before = w.diagnostic()
    cleanup = w.owned["code"]["va"] + assembly.LABELS["coach_cleanup"]
    w.call(cleanup)
    assert not w.heap_live
    assert w.get(0xBA04B4) == 0 and w.get(0xBA04B0) == chosen
    assert bytes(w.m.mem_read(w.state_va, 56)) == bytes(56)
    w.put(0xBA04B0, 0)
    again = w.setup(7, side=0, team=0xE5FC20)
    assert again and again not in (home, away)
    return dict(passed=True, two_distinct_contexts=True, humans_cleared=True, cpu_rebound=True,
                explicit_choice_survived=True, contexts_freed=True, statistics_unpublished_before_free=True,
                next_game_reallocated=True,
                before_cleanup=before, after_reload=w.diagnostic(),
                scope="Actual F7BE0 controller path; owned unload callback and next setup; full franchise save/load is live-only")


def audit_portraits(xbe):
    """Execute both real renderers and E71E0; supply named resource lookups."""
    w = AutoWorld(xbe)
    lookups = []
    def string(address):
        values = []
        for n in range(40):
            unit = struct.unpack("<H", w.m.mem_read(address + n * 2, 2))[0]
            if not unit:
                return bytes().join(struct.pack("<H", u) for u in values).decode("utf-16le")
            values.append(unit)
        raise AssertionError("Unterminated portrait request")
    def resource(m, pc, size, _):
        sp = m.reg_read(w.r.UC_X86_REG_ESP)
        name = string(w.get(sp + 4))
        group = m.reg_read(w.r.UC_X86_REG_ECX)
        lookups.append(dict(function=hex(pc), name=name, group=string(group) if group else None))
        m.reg_write(w.r.UC_X86_REG_EAX, 1 if pc == 0x42FF0 else 0x311F000)
        m.reg_write(w.r.UC_X86_REG_EIP, w.get(sp))
        m.reg_write(w.r.UC_X86_REG_ESP, sp + 8)
    for pc in (0x42FF0, 0x449E0):
        w.m.hook_add(w.ucmod.UC_HOOK_CODE, resource, begin=pc, end=pc)
    control = s.SOURCE + 0x1B000
    root, teams, coaches = s.SOURCE + 0x1F000, s.SOURCE + 0x20000, s.SOURCE + 0x24000
    w.put(0xB72918, root)
    w.put(root + 0x18, 32)
    w.put(root + 0x1C, teams)
    rows = []
    for row in ai.portrait_rows():
        team = teams + row["book_index"] * 500
        cp = coaches + row["book_index"] * 0x100
        w.put(team + 0x128, 0)
        w.m.mem_write(team + 0x118, struct.pack("<H", row["asset"]))
        w.put(team + 0x14C, cp)
        for identity in (row["identity"], row["legacy_identity"]):
            w.put(0xBDFCF0, identity)
            w.m.mem_write(0xBDFCF4, row["name"].encode("utf-16le").ljust(26, b"\0"))
            for photo in dict.fromkeys((row["portrait"], row.get("alternate_portrait", row["portrait"]))):
                w.m.mem_write(cp + 0x40, struct.pack("<H", photo))
                for renderer in (0x367BD0, 0x350890):
                    lookups.clear()
                    w.put(0xCC2470, 0xBDFCF0)
                    w.put(0xCC2478, 0)
                    w.put(0xCB9208, 0)
                    w.call(renderer, edx=0, args=(control, 0))
                    assert lookups[-1]["name"] == f"{photo:04d}", lookups
                    assert lookups[-1]["group"] == "PORTRAIT", lookups
                    assert w.get(control + 0x30) == 0x311F000
                rows.append(dict(team=row["team"], identity=identity, portrait=photo, both_renderers=True))
        # A newly hired or explicit unrelated coach cannot redirect the
        # authored VIP to somebody else's face; retain its original identity.
        w.m.mem_write(cp + 0x40, struct.pack("<H", 7999))
        for renderer in (0x367BD0, 0x350890):
            lookups.clear()
            w.call(renderer, edx=0, args=(control, 0))
            assert lookups[-1]["name"] == f"{row['portrait']:04d}", lookups
    # Matching name alone never appropriates a user's personal VIP.
    w.put(0xBDFCF0, 0x1234)
    for renderer in (0x367BD0, 0x350890):
        lookups.clear()
        w.call(renderer, edx=0, args=(control, 0))
        assert lookups[-1]["name"] == "vip_logo_a1", lookups
    # Native NFL Coach path remains unmodified and uses its roster portrait.
    cp = s.SOURCE + 0x1D000
    w.m.mem_write(cp + 0x40, struct.pack("<H", 7021))
    w.put(0xCC2478, cp)
    w.put(0xCB9208, 0xFFFFFFFF)
    w.put(0xCB920C, cp)
    for renderer in (0x367BD0, 0x350890):
        lookups.clear()
        w.call(renderer, edx=0, args=(control, 0))
        assert lookups[-1]["name"] == "7021"
    return dict(passed=True, rows=rows, personal_vips_unchanged=True, nfl_coach_path_unchanged=True,
                co1_portrait_aliases=True, unrelated_roster_coach_cannot_redirect_authored_vip=True,
                scope="Native renderer and numeric formatter; named TXTR resource lookup is a fixture, not a texture/art witness")


def run(args):
    import hashlib
    import json
    from pathlib import Path
    import time
    from mod_editor.core.mod_build import _xbe_bytes
    from mod_editor.core import nfl2k5_roster_records as rr
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    from tools.b77 import vp1_verify as v
    xbe = _xbe_bytes(args.xbe or args.image)
    baseline = _xbe_bytes(args.baseline_xbe)
    retail = _xbe_bytes(args.retail_xbe)
    assert ai.status(xbe) == "applied" and ai.status(baseline) == "retail"
    specs = json.loads((v.ROOT / "data/vip/coach_sources_2026.json").read_text())
    result = dict(schema="nfl2k5_automatic_coach_native_replay/v1", status="RUNNING", runtime_witness=False,
                  xbe_sha256=hashlib.sha256(xbe).hexdigest(), baseline_xbe_sha256=hashlib.sha256(baseline).hexdigest(),
                  retail_xbe_sha256=hashlib.sha256(retail).hexdigest(),
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  replay_verifier_sha256=hashlib.sha256(Path(v.__file__).read_bytes()).hexdigest(),
                  setup="Actual disc callback 1665A0/E0D90, F7B30 game setup, both F6E60 sides, native history decay and statistics binding; no preselected VIP; separate 161E30 saved-book copy audit",
                  environment="World's explicit roster/player/kicker inputs, plus bounded heap allocate/free services; no selector, RNG, setup, compatibility or VIP accessor stubs",
                  scope="All supported modes, all offense/defense pools, optional decisions and continuous eligible tempo; synthetic field/clock state",
                  teams={})
    started = time.monotonic()
    with OuterImage(args.image) as archive, OuterImage(args.retail_image) as stock:
        roster = rr.RosterDocument(archive.read_entry(5)[32:])
        old_roster = rr.RosterDocument(stock.read_entry(5)[32:])
        for spec in specs:
            team = spec["team"]
            if args.team and team not in args.team:
                continue
            book = (args.profiles / (team + ".bin")).read_bytes()
            receipt = json.loads((args.profiles / (team + ".json")).read_text())
            info = ai.inspect_profile(book)
            source = archive.read_entry(BOOK_ENTRIES[spec["archive_book"]])
            assert ai.strip_profile(source) == ai.strip_profile(book)
            assert info == receipt["automatic_profile"]
            assert hashlib.sha256(book).hexdigest() == receipt["resource_sha256"]
            at = roster.teams[spec["native_book_index"]].coach_offset
            coach = bytes(roster.body[at:at + 0xA8])
            at = old_roster.teams[spec["native_book_index"]].coach_offset
            old_coach = bytes(old_roster.body[at:at + 0xA8])
            binder = lambda executable, resource, report: bind_automatic(executable, resource, report, coach)
            try:
                print(team, "all native setup modes and controls", flush=True)
                entry = dict(loaders=audit_loaders(xbe, book, receipt, coach),
                             modes=audit_modes(xbe, baseline, retail, book, receipt, coach))
                print(team, "offense", flush=True)
                entry["offense"] = v.native_vip(xbe, book, None, receipt, args.samples, automatic=binder)
                print(team, "defense", flush=True)
                entry["defense"] = v.native_defense(xbe, book, None, receipt, args.defense_samples, automatic=binder)
                print(team, "decisions and tempo", flush=True)
                entry["decisions"] = v.native_decisions(xbe, book, None, receipt, args.decision_samples,
                                                       args.tempo_samples, automatic=binder)
                entry["retail_control"] = v.retail_control(retail, stock.read_entry(BOOK_ENTRIES[spec["archive_book"]]),
                                                           old_coach, args.control_samples, world_factory=AutoWorld)
                entry["no_feature_control"] = v.retail_control(baseline, book, coach, args.same_book_control_samples,
                                                               world_factory=AutoWorld)
                entry["candidate"] = info
                entry["passed"] = all(entry[k]["passed"] for k in ("loaders", "modes", "offense", "defense", "decisions"))
            except Exception as exc:
                entry = dict(passed=False, error=f"{type(exc).__name__}: {exc}")
            result["teams"][team] = entry
            result["elapsed_seconds"] = time.monotonic() - started
            args.out.write_text(json.dumps(result, indent=1) + "\n")
            print(team, "PASS" if entry["passed"] else "FAIL", entry.get("error", ""), flush=True)
        # These semantic cases need one concrete current-NFL book; every team
        # already exercised human and both explicit-choice negatives per mode.
        result["exclusions"] = audit_exclusions(xbe, book, receipt, coach)
        result["lifecycle"] = audit_lifecycle(xbe, book, receipt, coach)
        result["portraits"] = audit_portraits(xbe)
    result["elapsed_seconds"] = time.monotonic() - started
    result["status"] = "PASS" if result["teams"] and all(e["passed"] for e in result["teams"].values()) else "FAIL"
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(result["status"], len(result["teams"]), "teams", round(result["elapsed_seconds"], 1), "seconds", flush=True)
    return 0 if result["status"] == "PASS" else 1
