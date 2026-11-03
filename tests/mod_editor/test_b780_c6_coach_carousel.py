"""b780 c6-carousel: the coaching carousel (model, hiring pool, roster writer, executable owner, native row callbacks,
owner gate, and the stage-9 advance replayed on a real end-of-season league).

Private evidence (skipped when absent; nothing private is committed):
  * the USA retail default.xbe (tests.nfl2k5_supersim_draft_fixture),
  * NFL2K5_V08_XBE: the released SOFTDRINK v0.8 default.xbe (sha256 5f987568...),
  * NFL2K5_V08_ROST_BODY: the released v0.8 main ROST body (resource minus its 32-byte header),
  * NFL2K5_B780_Y0_STATE: a Unicorn RAM state at the end of a simulated v0.8 season (b4-economy sim/base3, every game
    played, stage 9 at its end week) - the "real franchise arena",
  * NFL2K5_B780_V08_SAVE: a game-written franchise save upgraded to the v0.8 roster (SAVEGAME.DAT).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import struct
import unittest
import zlib
from pathlib import Path

from mod_editor.core import nfl2k5_coach_carousel as cc
from mod_editor.core import nfl2k5_coach_carousel_code as code
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine, retail_bytes


def _env(name):
    value = os.environ.get(name, "")
    return Path(value) if value else None


V08_XBE = _env("NFL2K5_V08_XBE")
V08_XBE_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"
V08_ROST = _env("NFL2K5_V08_ROST_BODY")
Y0_STATE = _env("NFL2K5_B780_Y0_STATE")
V08_SAVE = _env("NFL2K5_B780_V08_SAVE")


def _have(path):
    return path is not None and path.is_file()


def _v08_xbe():
    raw = V08_XBE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != V08_XBE_SHA256:
        raise unittest.SkipTest("the v0.8 XBE pin differs")
    return raw


# --------------------------------------------------------------------------------------------------- model and data
class ModelTests(unittest.TestCase):
    """The decision is c5-owners' (nfl2k5_coach_owners); this job packs it for the native code and adds its settings."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_coach_owners as co
        cls.co = co
        cls.data = cc.load()
        cls.owners = co.load_owners()
        cls.params = cc.pack_params(cls.data, cls.owners)

    def test_the_settings_and_extras_are_sourced(self):
        data = self.data
        cc.validate(data)
        games = next(s for s in data["sources"] if s["file"] == "games.csv")
        self.assertEqual(len(games["sha256"]), 64)
        self.assertIn("nflverse", games["url"])
        self.assertEqual(data["settings"]["max_changes"], cc.MAX_CHANGES)
        tomlin = data["pool_extras"]["mike-tomlin"]
        self.assertEqual((tomlin["super_bowl_wins"], tomlin["super_bowl_losses"], tomlin["winning_seasons"]), (1, 1, 16))
        self.assertEqual(data["pool_extras"]["doug-pederson"]["super_bowl_wins"], 1)

    def test_parameter_block_round_trip(self):
        p = cc.read_params(self.params)
        self.assertEqual(len(self.params), cc.PARAM_SIZE)
        self.assertEqual((p["max_changes"], p["rehire_percent"]), (12, 12))
        self.assertEqual(self.params[cc.PARAM_HEADER:], self.co.pack_native(self.owners))
        cincinnati = cc.CLUBS.index("CIN")
        self.assertEqual(p["owner_q8"][cincinnati],
                         next(c["fire_scale_q8"] for c in self.owners["clubs"] if c["team"] == "CIN"))
        self.assertIsNone(cc.read_params(bytes(cc.PARAM_SIZE)))

    def test_the_club_order_is_the_roster_team_order(self):
        index = {c["team"]: c["team_index"] for c in self.owners["clubs"]}
        self.assertEqual([index[t] for t in cc.CLUBS], list(range(32)))

    def test_hazard_is_the_c5_decision(self):
        import itertools
        for club in (0, 2, 22, 31):
            q8 = next(c["fire_scale_q8"] for c in self.owners["clubs"] if c["team_index"] == club)
            for w, l, t, n in itertools.product(range(0, 18, 3), range(0, 18, 4), (0, 1), (1, 2, 3, 9)):
                if w + l + t:
                    self.assertEqual(cc.hazard(self.params, club=club, wins=w, losses=l, ties=t, tenure=n),
                                     self.co.fire_permille(self.owners["model"], q8, w, l, t, n))
        raiders, bengals = cc.CLUBS.index("LV"), cc.CLUBS.index("CIN")
        bad = cc.hazard(self.params, club=raiders, wins=3, losses=14, ties=0, tenure=4)
        self.assertGreater(bad, 600)
        self.assertLess(cc.hazard(self.params, club=bengals, wins=3, losses=14, ties=0, tenure=4), bad)
        self.assertLess(cc.hazard(self.params, club=raiders, wins=3, losses=14, ties=0, tenure=1), bad)    # patience
        self.assertLess(cc.hazard(self.params, club=raiders, wins=13, losses=4, ties=0, tenure=4), 60)

    def test_twenty_seasons_land_on_the_real_rate(self):
        """c5's table on its own record replay gives about 7 changes an offseason; a coarse check through this job's
        packed copy (binomial records, top 14 to the playoffs do not matter to the model)."""
        rnd = random.Random(2026)
        counts, fired = [], []
        tenure = [rnd.randint(1, 6) for _ in range(32)]
        for _season in range(40):
            changes = 0
            for club in range(32):
                strength = min(max(rnd.gauss(0.5, 0.17), 0.05), 0.95)
                w = sum(rnd.random() < strength for _ in range(17))
                p = cc.hazard(self.params, club=club, wins=w, losses=17 - w, ties=0, tenure=tenure[club])
                if rnd.randrange(1000) < p:
                    changes += 1
                    fired.append(w / 17)
                    tenure[club] = 1
                else:
                    tenure[club] += 1
            counts.append(changes)
        mean = sum(counts) / len(counts)
        self.assertTrue(5.0 <= mean <= 9.5, counts)
        self.assertLess(sorted(fired)[len(fired) // 2], 0.40)


# ------------------------------------------------------------------------------------------------------- the pool
class PoolBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = cc.load_pool()
        cls.block = cc.pool_block(cls.pool)

    def test_the_pool_is_c5s_real_people(self):
        from mod_editor.core import nfl2k5_coach_owners as co
        doc = co.load_pool()
        self.assertEqual([(e["first"], e["last"]) for e in self.pool], [(c["first"], c["last"]) for c in doc["candidates"]])
        self.assertTrue(all(c["sources"] for c in doc["candidates"]))
        heads = {json.loads(p.read_text(encoding="utf-8"))["roster"]["head_coach"]
                 for p in (cc.ROOT / "data/nfl2k5_teams_2026").glob("*.json")}
        self.assertFalse({f"{e['first']} {e['last']}" for e in self.pool} & heads)    # nobody already a 2026 head coach
        tomlin = next(e for e in self.pool if e["last"] == "Tomlin")
        self.assertEqual((tomlin["career"]["wins"], tomlin["career"]["losses"], tomlin["career"]["playoff_wins"],
                          tomlin["career"]["super_bowl_wins"]), (193, 114, 8, 1))
        self.assertTrue(all(set(e["ratings"].values()) == {cc.DEFAULT_RATING} for e in self.pool))

    def test_block_reads_back_and_is_found_on_a_four_byte_step(self):
        entries = cc.read_pool_block(self.block)
        self.assertEqual([(e["first"], e["last"]) for e in entries], [(e["first"], e["last"]) for e in self.pool])
        self.assertEqual(len(self.block) % 4, 0)
        self.assertLessEqual(len(self.block), 3800)
        arena = bytes(0x400) + self.block + bytes(64)
        self.assertEqual(cc.find_pool(arena, 0)[0], 0x400)
        self.assertIsNone(cc.find_pool(bytes(2) + arena, 0))                  # not on the arena's 4-byte step
        self.assertEqual(cc.find_pool(bytes(2) + arena, 2)[0], 0x402)

    def test_damage_reads_as_no_pool(self):
        for at in (8, 9, 10, 12, 20, 16 + 64 * len(self.pool) + 3, len(self.block) - 1):
            bad = bytearray(self.block)
            bad[at] ^= 0x41
            self.assertIsNone(cc.read_pool_block(bytes(bad)), at)

    def test_refusals(self):
        with self.assertRaises(cc.CoachCarouselError):
            cc.pool_block(self.pool + [self.pool[0]])                         # the same person twice
        with self.assertRaises(cc.CoachCarouselError):
            cc.pool_block([dict(self.pool[0], first="x" * 25)])                # a name longer than 24 characters
        with self.assertRaises(cc.CoachCarouselError):
            cc.pool_block([dict(self.pool[0], first=f"A{i}", last="B") for i in range(cc.MAX_POOL + 1)])

    def test_every_string_is_its_own(self):
        entries = cc.read_pool_block(self.block)
        offsets = [o for e in entries for o in e["offsets"]]
        self.assertEqual(len(offsets), len(set(offsets)))                     # one pointer per string once hired


@unittest.skipUnless(_have(V08_ROST), "private v0.8 roster body absent")
class RosterTests(unittest.TestCase):
    def test_the_pool_goes_into_the_free_tail_of_the_coach_strings(self):
        body = V08_ROST.read_bytes()
        region = cc.coach_region(body)
        self.assertEqual((region["free"], region["tail_is_zero"], region["pool_offset"]), (4278, True, None))
        out, receipt = cc.apply_body(body)
        self.assertEqual(len(out), len(body))
        at = int(receipt["pool_offset"], 16)
        self.assertEqual(at % 4, 0)
        self.assertGreaterEqual(at, region["used_end"])
        self.assertLessEqual(at + receipt["pool_bytes"] + cc.POOL_MARGIN, region["next_string"])
        diff = [i for i, (a, b) in enumerate(zip(body, out)) if a != b]
        self.assertTrue(diff and at <= diff[0] and diff[-1] < at + receipt["pool_bytes"])
        again, second = cc.apply_body(out)                                    # a rebuild replaces the block in place
        self.assertEqual(again, out)
        self.assertTrue(second["replaced"])
        self.assertEqual(cc.coach_region(out)["pool_offset"], at)

    def test_a_short_tail_leaves_out_the_lowest_weights(self):
        body = bytearray(V08_ROST.read_bytes())
        region = cc.coach_region(bytes(body))
        filler = region["next_string"] - region["used_end"] - 3000             # another writer took most of the tail
        body[region["used_end"]:region["used_end"] + filler] = b"\x41\x00" * (filler // 2)
        body[region["used_end"] + filler - 2:region["used_end"] + filler] = b"\0\0"
        table = struct.unpack_from("<i", body, cc.OBJ_OFF + 0x34)[0] + cc.OBJ_OFF + 0x34 - 1
        field = table + 34 * cc.COACH_STRIDE + 0x10                            # record 34's last line points at it
        struct.pack_into("<i", body, field, region["used_end"] - field + 1)
        out, receipt = cc.apply_body(bytes(body))
        self.assertTrue(receipt["left_out"])
        self.assertGreaterEqual(receipt["pool_entries"], 8)
        kept = {(e["first"], e["last"]) for e in cc.find_pool(out, cc.OBJ_OFF)[1]}
        self.assertIn(("Mike", "Tomlin"), kept)                               # the heaviest weights stay

    def test_a_full_region_refuses(self):
        body = bytearray(V08_ROST.read_bytes())
        region = cc.coach_region(bytes(body))
        body[region["used_end"] + 40] = 1                                     # something lives in the tail
        with self.assertRaises(cc.CoachCarouselError):
            cc.apply_body(bytes(body))


# ------------------------------------------------------------------------------------------------- the executable
class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.applied, cls.receipt = cc.apply(cls.retail)

    def test_retail_apply_status_and_sites(self):
        self.assertEqual(cc.status(self.retail), "retail")
        self.assertEqual(cc.status(self.applied), "applied")
        va = cc.allocations(self.applied)["code"]["va"]
        self.assertEqual(self.receipt["code_va"], hex(va))
        labels = cc.labels(va)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.applied)
        self.assertEqual(image.read(0x248632, 5), b"\xe8" + struct.pack("<i", labels["carousel_advance"] - 0x248637))
        self.assertEqual(image.read(0x2BA675, 6), b"\xe8" + struct.pack("<i", labels["carousel_user_gate"] - 0x2BA67A) + b"\x90")
        self.assertEqual(image.read(0x2BA6BC, 4), bytes.fromhex("49497505"))
        for label, at, _retail, entry in cc.ROW_SITES:
            self.assertEqual(struct.unpack("<I", image.read(at, 4))[0], labels[entry], label)
        self.assertEqual(cc.installed_params(self.applied), cc.pack_params())
        self.assertEqual(cc.apply(self.applied)[0], self.applied)            # idempotent

    def test_other_parameters_on_an_installed_carousel_refuse(self):
        data = cc.load()
        data["settings"]["max_changes"] = 6
        with self.assertRaises(cc.CoachCarouselError):
            cc.apply(self.applied, data)
        out, _ = cc.apply(self.retail, data)                                  # a fresh build takes them
        self.assertEqual(cc.read_params(cc.installed_params(out))["max_changes"], 6)

    def test_foreign_bytes_refuse(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.retail)
        for va in (0x248634, 0x2BA6C0, 0x500C2C, 0x0C75A8):                   # a site, the gate, the row, a dependency
            bad = bytearray(self.retail)
            bad[image.offset(va, 1)] ^= 0x01
            self.assertEqual(cc.status(bytes(bad)), "foreign", hex(va))
        mixed = bytearray(self.applied)
        at = XbeImage(self.applied).offset(0x2BA6BC, 4)
        mixed[at:at + 4] = cc.RETAIL_MARK
        self.assertEqual(cc.status(bytes(mixed)), "foreign")

    def test_the_owner_is_the_last_late_owner_and_wired_into_the_build(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as settings, nfl2k5_xbe_space as space
        # b780-int: the carousel follows every owner v0.8 carries (after season realism's state); the wave's later late
        # owners (j23's footer and history, j4's History screen, j1's standings records) are appended after it
        late = list(space.LATE_OWNERS)
        self.assertEqual(late[late.index("nfl2k5_sim_realism_state") + 1], cc.OWNER)
        self.assertEqual(late.count(cc.OWNER), 1)
        self.assertIn("coach_carousel", settings.FEATURE_KEYS)
        self.assertTrue(all(preset["coach_carousel"] is False for preset in mod_build.PRESETS.values()))
        self.assertIn(cc.OWNER, [row[0] for row in mod_build._LATE_OWNER_OPTIONS])
        import dataclasses
        field = next(f for f in dataclasses.fields(mod_build.BuildPlan) if f.name == "coach_carousel")
        self.assertIs(field.default, False)

    def test_the_player_progress_screen_accepts_the_carousel_site(self):
        """Player Progress guards 0x248628..0x24864F, which holds the carousel's rollover call; it must read applied with
        the carousel installed (it already accepted the economy's site at 0x248628 the same way)."""
        from mod_editor.core import nfl2k5_player_progress_screen as pp
        payload = pp.apply(self.retail)[0]
        payload = cc.apply(payload)[0]
        self.assertEqual((pp.status(payload), cc.status(payload)), ("applied", "applied"))
        if _have(V08_XBE):
            # b780 n6: the v0.8 executable carries the beta-79 screen (b9 moved its event site since), which reads
            # "previous"; it must keep reading so with the carousel's rollover call beside it
            released = _v08_xbe()
            self.assertEqual(pp.status(released), "previous")
            self.assertEqual(pp.status(cc.apply(released)[0]), "previous")

    def test_the_build_union_reserves_it_with_the_other_late_owners(self):
        """The Studio plans the whole late-owner union up front (b779-int1); the carousel is reserved there and installs
        after the owners before it, in LATE_OWNERS order."""
        from mod_editor.core import nfl2k5_throw_tuning as tt, nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_preseason_warning as warning, nfl2k5_sim_rb_injuries as rb
        from mod_editor.core import nfl2k5_sim_realism as sr, nfl2k5_franchise_economy as economy
        requests = tt._selected_space_requests(sim_rb_injuries=True, sim_realism=True, preseason_warning=True,
                                               coach_carousel=True)
        self.assertEqual(requests[-1][0], cc.OWNER)
        self.assertNotIn(cc.OWNER, [r[0] for r in tt._selected_space_requests(sim_realism=True)])
        payload = economy.apply(space.apply(self.retail, requests, scaleout=True)[0])[0]
        for module in (warning, rb, sr, cc):
            payload = module.apply(payload)[0]
            self.assertEqual(module.status(payload), "applied", module.OWNER)
        self.assertEqual(warning.status(payload), "applied")

    def test_the_pool_is_written_after_every_main_roster_writer(self):
        import ast
        from mod_editor.core import mod_build
        source = Path(mod_build.__file__).read_text(encoding="utf-8")
        build = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_build")
        body = ast.get_source_segment(source, build)
        pool = body.index("_apply_coach_carousel_pool(plan, target, receipt, progress)")
        self.assertLess(body.index("_apply_champions_history(plan, target, receipt, progress, capacity_records)"), pool)
        self.assertLess(body.index("_apply_coach_carousel(plan, target, receipt, progress)"), pool)
        self.assertLess(body.index("_apply_sim_realism(plan, target"), body.index("_apply_coach_carousel(plan, target"))
        self.assertLess(pool, body.index("finish_private(target"))

    @unittest.skipUnless(_have(V08_XBE), "private v0.8 XBE absent")
    def test_the_released_v08_executable_takes_it(self):
        v08 = _v08_xbe()
        self.assertEqual(cc.status(v08), "retail")
        out, _ = cc.apply(v08)
        self.assertEqual(cc.status(out), "applied")


# --------------------------------------------------------------------------------------- native code on the retail XBE
@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class NativeRowAndGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.applied, _ = cc.apply(retail_bytes())
        cls.va = cc.allocations(cls.applied)["code"]["va"]

    def machine(self):
        m = Machine(self.applied, trace_writes=False)
        return m

    def _text(self, m, p):
        return bytes(m.uc.mem_read(p, 40)).decode("utf-16-le").split("\0")[0]

    def test_owner_firing_has_three_values(self):
        m = self.machine()
        right, left, text = (m.get(0x500C40), m.get(0x500C44), m.get(0x500C48))   # +0x18 runs on RIGHT, +0x1C on LEFT
        self.assertEqual(m.get(0x500C28), 7)                                # a list row (a box with the value's text)
        m.put(0xE60144, 1)                                                  # the retail default ("On") reads CPU Teams
        self.assertEqual(self._text(m, m.call(text)), "CPU Teams")
        seen = []
        for _ in range(4):
            self.assertEqual(m.call(right), 1)
            seen.append((m.get(0xE60144), self._text(m, m.call(text))))
        self.assertEqual(seen, [(2, "All Teams"), (0, "Off"), (1, "CPU Teams"), (2, "All Teams")])
        seen = []
        for _ in range(3):
            m.call(left)
            seen.append(m.get(0xE60144))
        self.assertEqual(seen, [1, 0, 2])
        m.put(0xE60144, 7)                                                  # a foreign value reads and steps as Off
        self.assertEqual(self._text(m, m.call(text)), "Off")
        m.call(right)
        self.assertEqual(m.get(0xE60144), 1)
        self.assertEqual(m.get(0x500C3C), 0x148700)                         # the getter stays retail

    def test_a_new_franchise_starts_at_cpu_teams_and_a_career_keeps_off(self):
        m = self.machine()
        for va in range(0xE6011C, 0xE60148, 4):
            m.put(va, 0x5A)
        m.call(m.get(0x500A2C))                                             # the MyNFL Options screen's defaults
        self.assertEqual(m.get(0xE60144), 1)
        self.assertEqual((m.get(0xE6011C), m.get(0xE60124), m.get(0xE60140)), (1, 1, 0))   # the rest as retail
        m.put(0xE60144, 0x5A)
        m.call(0x148C60)                                                    # MyCareer calls the retail reset itself
        self.assertEqual(m.get(0xE60144), 0)

    def test_the_owner_never_fires_a_user_unless_all_teams(self):
        """The patched check site: with the retail "last warning" bit set, the retail code takes the firing path
        (0x2BA67B); the gate sends Off and CPU Teams to the no-warning path (0x2BA6B6) instead."""
        m = self.machine()
        stub = Machine.STOP + 0x200
        state = Machine.ARENA + 0x100
        # the patched site's 6 bytes (call gate; nop), then ret: falling through = the retail firing path (0x2BA67B);
        # the retail jump target 0x2BA6B6 is caught and returned from without touching eax
        m.uc.mem_write(stub, b"\xe8" + struct.pack("<i", cc.labels(self.va)["carousel_user_gate"] - (stub + 5)) + b"\x90\xc3")
        hits = []

        def target(*_):
            hits.append(1)
            sp = m.reg("ESP")
            m.reg("EIP", m.get(sp))
            m.reg("ESP", sp + 4)
        m.uc.hook_add(m.u.UC_HOOK_CODE, target, begin=0x2BA6B6, end=0x2BA6B6)
        results = {}
        for mode in (0, 1, 2):
            for mark in (0, 4):
                m.put(0xE60144, mode)
                m.put(state, 0x11 | mark)
                hits.clear()
                eax = m.call(stub, esi=state)
                results[(mode, mark)] = ("no_warning_path" if hits else "firing_path", eax)
        self.assertEqual(results[(2, 4)], ("firing_path", 0x15))             # All Teams: retail
        self.assertEqual(results[(2, 0)][0], "no_warning_path")
        for mode in (0, 1):
            self.assertEqual(results[(mode, 4)], ("no_warning_path", 0x11), mode)
            self.assertEqual(results[(mode, 0)][0], "no_warning_path")


# ------------------------------------------------------------------------------------- the advance on a real league
def _load_state(payload, released):
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    m = Machine(payload, trace_writes=False)
    raw = Y0_STATE.read_bytes()
    meta, blob, offset = json.loads(raw[:256]), zlib.decompress(raw[256:]), 0
    for address, size in ((0x10000, 0x1510000 - 0x10000), (Machine.ARENA, 0x200000), (0x3000000, 0x10000)):
        m.uc.mem_write(address, blob[offset:offset + size])
        offset += size
    m.team_base, m.root = meta["team_base"], meta["root"]
    new, old = XbeImage(payload), XbeImage(released)
    m.uc.mem_write(0x10000, payload[:struct.unpack_from("<I", payload, 0x108)[0]])
    for section in new.sections:                       # the saved league ran the released code: write this payload's
        if section.raw_size:
            a = new.read(section.start, section.raw_size)
            try:
                b = old.read(section.start, section.raw_size)
            except (ValueError, IndexError):
                b = None
            if a != b:
                m.uc.mem_write(section.start, a)
    m.uc.ctl_flush_tb()
    m.notices = []

    def notice():
        p = m.reg("EDX")
        m.notices.append(bytes(m.uc.mem_read(p, 1024)).decode("utf-16-le", "replace").split("\0")[0])
        m.ret()
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, notice, reason="information dialog acknowledgement only")
    return m


def _records(m):
    return [bytes(m.uc.mem_read(m.get(m.team_base + 500 * i + 0x14C), 0xA8)) for i in range(32)]


def _season(m):
    """(regular W L T, playoffs, tenure after the rollover) per club, read through the game's own counters."""
    out = []
    sb = m.uc.mem_read(0x133A41, 1)[0]
    for i in range(32):
        team = m.team_base + 500 * i
        coach = m.get(team + 0x14C)
        regular = [sum(m.call(f, ecx=team, edx=r) for r in range(sb - 3)) for f in (0xC75A0, 0xC7620, 0xC76A0)]
        post = sum(m.call(f, ecx=team, edx=r) for r in range(sb - 3, sb + 1) for f in (0xC75A0, 0xC7620))
        tenure = struct.unpack("<H", m.uc.mem_read(coach + 0x1C, 2))[0] + 1
        out.append((regular, post > 0, tenure))
    return out


MENU = Machine.ARENA + 0x1A0000


@unittest.skipUnless(HAVE_UC and _have(Y0_STATE) and _have(V08_XBE) and _have(V08_ROST),
                     "private end-of-season league state, v0.8 XBE or roster absent")
class SeasonEndTests(unittest.TestCase):
    """Advance to offseason (stage 9 of 0x2480B0, every native routine real; the two display leaves are the progress
    renderer and the information dialog) on a league at the end of a simulated v0.8 season."""

    @classmethod
    def setUpClass(cls):
        cls.released = _v08_xbe()
        cls.carousel, _ = cc.apply(cls.released)
        body = V08_ROST.read_bytes()
        pooled, receipt = cc.apply_body(body)
        cls.pool_at = int(receipt["pool_offset"], 16)
        cls.block = pooled[cls.pool_at:cls.pool_at + receipt["pool_bytes"]]
        cls.entries = cc.read_pool_block(cls.block)
        cls.params = cc.pack_params()
        m = _load_state(cls.released, cls.released)
        cls.season = _season(m)
        m.call(0xC4D30, ecx=m.team_base, edx=1)                            # club 0 is the user's (as the sim did)
        cls.ref_before = _records(m)
        m.call(0x2480B0, ecx=MENU, budget=3_000_000_000)
        cls.ref_after = _records(m)
        cls.ref_arena = hashlib.sha256(bytes(m.uc.mem_read(Machine.ARENA, 0x200000))).hexdigest()
        cls.ref_globals = hashlib.sha256(bytes(m.uc.mem_read(0xB00000, 0x400000))).hexdigest()
        cls.ref_notices = m.notices

    def run_advance(self, mode, *, pool=True, user=0, script=None):
        m = _load_state(self.carousel, self.released)
        if pool:
            m.uc.mem_write(Machine.ARENA + 0x300 + self.pool_at, self.block)
        m.put(0xE60144, mode)
        if user is not None:
            m.call(0xC4D30, ecx=m.team_base + 500 * user, edx=1)
        va = cc.allocations(self.carousel)["code"]["va"]
        if script is not None:
            values = list(script)

            def rand_hook(uc, address, size, _):
                if values and va <= m.get(m.reg("ESP")) < va + cc.CODE_SIZE:
                    m.ret(values.pop(0))                                  # the scripted draw, straight back
            m.uc.hook_add(m.u.UC_HOOK_CODE, rand_hook, begin=0x48BC0, end=0x48BC0)
        before = _records(m)
        m.call(0x2480B0, ecx=MENU, budget=3_000_000_000)
        return m, before, _records(m)

    def test_off_is_the_released_advance_byte_for_byte(self):
        m, _before, after = self.run_advance(0, pool=False)
        self.assertEqual(hashlib.sha256(bytes(m.uc.mem_read(Machine.ARENA, 0x200000))).hexdigest(), self.ref_arena)
        self.assertEqual(hashlib.sha256(bytes(m.uc.mem_read(0xB00000, 0x400000))).hexdigest(), self.ref_globals)
        self.assertEqual(m.notices, self.ref_notices)

    def test_without_a_pool_nothing_changes(self):
        m, _before, after = self.run_advance(1, pool=False)
        self.assertEqual(after, self.ref_after)
        self.assertEqual(hashlib.sha256(bytes(m.uc.mem_read(Machine.ARENA, 0x200000))).hexdigest(), self.ref_arena)
        self.assertEqual(m.notices, self.ref_notices)

    def test_the_native_decision_is_the_model(self):
        """Every eligible club's draw is scripted one below or exactly at the c5 chance (draw >> 16 = p - 1 or p): a draw
        below parts ways, one at it does not, so any difference between the native and the Python chance shows up as a
        wrong club. More than the cap come up: the twelve highest chances survive."""
        eligible = [i for i in range(32) if i != 0]
        hazards = {i: cc.hazard(self.params, club=i, wins=self.season[i][0][0], losses=self.season[i][0][1],
                                ties=self.season[i][0][2], tenure=self.season[i][2]) for i in eligible}
        want = [i for k, i in enumerate(eligible) if k % 2 == 0 and 0 < hazards[i] < 1000][:14]
        script = [((hazards[i] - 1) << 16 if i in want else min(hazards[i], 999) << 16) for i in eligible]
        never = [i for i in eligible if i not in want and hazards[i] >= 1000]  # a sure change cannot be scripted away
        m, before, after = self.run_advance(1, script=script)
        kept = []
        for i in [i for i in eligible if i in want or i in never]:   # club order, as drawn; the cap keeps the highest
            if len(kept) < 12:
                kept.append(i)
                continue
            low = min(range(len(kept)), key=lambda k: (hazards[kept[k]], k))
            if hazards[kept[low]] < hazards[i]:
                kept[low] = i
        changed = sorted(i for i in range(32) if before[i][4:8] != after[i][4:8])
        self.assertEqual(changed, sorted(kept))
        self.assertEqual(len([n for n in m.notices if n.startswith("COACHING CHANGES")]), 4)
        self.assertTrue(all(" parted ways with " in line and "), hired " in line
                            for n in m.notices if n.startswith("COACHING CHANGES") for line in n.split("\n")[1:]))

    def test_rewritten_records_follow_the_rules(self):
        m0 = _load_state(self.carousel, self.released)
        strings_before = {m0.get(m0.get(m0.team_base + 500 * i + 0x14C) + 4 * k) for i in range(32) for k in range(5)}
        teams_before = [m0.get(m0.team_base + 500 * i + 0x14C) for i in range(34)]
        m, before, after = self.run_advance(1)
        self.assertEqual([m.get(m.team_base + 500 * i + 0x14C) for i in range(34)], teams_before)   # no team pointer moves
        pool_ram = Machine.ARENA + 0x300 + self.pool_at
        root, size = m.get(0xB72918), m.get(0xB72808)
        lasts = [struct.unpack_from("<I", r, 4)[0] for r in after]
        self.assertEqual(len(set(lasts)), 32)                                # nobody coaches two clubs
        changed = 0
        for i in range(32):
            b, x, ref = before[i], after[i], self.ref_after[i]
            if b[4:8] == x[4:8]:
                self.assertEqual(x, ref, i)                                  # an unchanged club: the plain rollover
                continue
            changed += 1
            self.assertNotEqual(i, 0)                                        # never the user's club
            self.assertEqual(x[0x18:0x1A], b[0x18:0x1A])                     # the club keeps its sideline model
            self.assertEqual(x[0x1A] & 3, 2)                                 # generic announcer line, not free
            for field in (0x1C, 0x26, 0x28, 0x2A, 0x2C, 0x2E):
                self.assertEqual(x[field:field + 2], b"\0\0")
            pointers = struct.unpack_from("<5I", x, 0)
            self.assertTrue(all(root <= p < root + size for p in pointers))
            # every string is a coach string the roster already had or one of the pool block's
            self.assertTrue(all(p in strings_before or pool_ram <= p < pool_ram + len(self.block) for p in pointers))
            if pool_ram <= pointers[1] < pool_ram + len(self.block):
                entry = next(e for e in self.entries if pool_ram + e["offsets"][1] == pointers[1])
                self.assertEqual(list(pointers), [pool_ram + o for o in entry["offsets"]])
                self.assertEqual(tuple(x[0x42:0x59]), tuple(entry["ratings"][r] for r in cc.RATINGS))
                self.assertEqual([struct.unpack_from("<H", x, o)[0] for o in cc.CAREER_OFFSETS],
                                 [entry["career"][f] for f in cc.CAREER_FIELDS])
                self.assertEqual(x[0x59:0xA8], b[0x59:0xA8])                 # the club's tendencies stay
            else:
                source = [j for j in range(32) if self.ref_after[j][4:8] == x[4:8]]
                self.assertEqual(len(source), 1)
                self.assertNotEqual(source[0], i)
        self.assertGreater(changed, 0)
        notices = [n for n in m.notices if n.startswith("COACHING CHANGES")]
        self.assertEqual(sum(n.count("\n") for n in notices), changed)
        self.assertTrue(all(len(n) < 300 for n in notices))
        # the game's own save and reload of the roster keeps every pointer (a hire saves with the franchise)
        arena = bytes(m.uc.mem_read(Machine.ARENA, 0x200000))
        m.call(0xC0730, ecx=m.root, budget=50_000_000)
        saved = bytes(m.uc.mem_read(Machine.ARENA, 0x200000))
        m.call(0xC0500, ecx=m.root, budget=50_000_000)
        self.assertEqual(bytes(m.uc.mem_read(Machine.ARENA, 0x200000)), arena)
        for i in range(32):
            coach = m.get(m.team_base + 500 * i + 0x14C) - Machine.ARENA
            for k in range(5):
                field = coach + 4 * k
                target = field + struct.unpack_from("<i", saved, field)[0] - 1
                self.assertEqual(target, struct.unpack_from("<I", arena, field)[0] - Machine.ARENA)

    def test_all_teams_still_leaves_the_users_club_alone(self):
        script = [0] * 32                                                    # every eligible club draws 0: all fire
        m, before, after = self.run_advance(2, script=script)
        if m.call(0xC4D50, ecx=m.team_base):                                 # still the user's (the owner kept him)
            self.assertEqual(after[0], self.ref_after[0])
        self.assertEqual(sum(1 for i in range(32) if before[i][4:8] != after[i][4:8]), 12)


@unittest.skipUnless(_have(V08_SAVE) and _have(V08_ROST), "private v0.8 franchise save or roster absent")
class UpgradeTests(unittest.TestCase):
    def test_an_older_franchise_gets_the_pool_once(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as upgrade
        save = V08_SAVE.read_bytes()
        disc = V08_ROST.read_bytes()
        same, step = upgrade.sync_coach_pool(save, disc)                     # a disc without a pool: nothing
        self.assertEqual((same, step["changes"]), (save, []))
        pooled_disc, _ = cc.apply_body(disc)
        out, step = upgrade.sync_coach_pool(save, pooled_disc)
        self.assertEqual(len(out), len(save))
        self.assertEqual(step["changes"][0]["entries"], len(cc.find_pool(pooled_disc, cc.OBJ_OFF)[1]))
        self.assertTrue(step["outside_declared_fields_identical"])
        again, second = upgrade.sync_coach_pool(out, pooled_disc)            # kept: hired coaches may point at it
        self.assertEqual((again, second["changes"]), (out, []))


if __name__ == "__main__":
    unittest.main()
