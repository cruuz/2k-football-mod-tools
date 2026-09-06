"""Retail stat writers/readers in bounded Unicorn. No disc, GUI or game boot."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_defensive_try as patch
from mod_editor.core import nfl2k5_team_column as team_column
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_defensive_try import Machine, XBE, uc, Cs, reseal
if uc is not None:
    from unicorn.x86_const import *  # noqa: F403


class StatsMachine(Machine):
    ROSTER, RECORDS, POOL, TEAMS, MAPS = (0x3030000, 0x3031000, 0x3032000, 0x3034000, 0x3036000)

    def __init__(self, payload):
        super().__init__(payload)
        self.data = patch._sites(payload)[1]["va"]
        self.ro = patch._stats_sites(payload)[1]["va"]
        self.labels = patch.assembled(payload)[3]
        self.u.mem_protect(self.ro & ~4095, ((self.ro % 4096 + patch.STATS_RO_SIZE + 4095) & ~4095), uc.UC_PROT_READ)
        self.set(0xB72918, self.ROSTER)
        self.set(self.ROSTER, 4)
        self.set(self.ROSTER + 4, self.RECORDS)
        self.set(self.ROSTER + 0x18, 2)
        self.set(self.ROSTER + 0x1C, self.TEAMS)
        self.set(self.ROSTER + 0x44, self.POOL)
        self.set(0xBD7F98, 0)
        for team in (0, 1):
            self.set((0xE5FE68, 0xE5FE6C)[team], self.MAPS + 0x100 * team)
            live_team = patch.LIVE_TEAMS[team]
            self.set(live_team + 0x11C, 2)
            self.set(self.TEAMS + 0x1F4 * team + 0x11C, 2)
            for index in (0, 1):
                live = self.live(team, index)
                saved = self.saved(team, index)
                self.set(self.MAPS + 0x100 * team + index * 4, saved)
                self.set(live_team + index * 4, live)
                self.set(self.TEAMS + 0x1F4 * team + index * 4, saved)
                self.set(live + 0x24, 3 << 8)
                self.set(live + 0x30, live_team)
                self.u.mem_write(live + 0x34, bytes((team + 1,)))
                self.set(saved + 0x24, 3 << 8)
                self.set(saved + 0x30, self.TEAMS + 0x1F4 * team)
            self.set(self.PLAYER[team] + 0x3C, self.live(team))
        self.reg(UC_X86_REG_FPCW, 0x37F)

    def live(self, team, index=0):
        return patch.LIVE_ROSTERS[team] + 0x54 * index

    def saved(self, team, index=0):
        return self.RECORDS + (team * 2 + index) * 0x54

    def count(self, team, index=0):
        return struct.unpack("<H", self.u.mem_read(self.data + (2 + 2 * index + team) * 2, 2))[0]

    def history(self, drive, team, *, index=0, event=5, outcome=1, kick=False):
        self.set(0xE53800, drive)
        slot = patch.DRIVE_RING + 4 * (drive & 127)
        td_team = 1 - team
        drive_team = td_team ^ (outcome == 6)
        self.set(slot, (drive_team << 21) | (outcome << 26))
        self.set(self.SNAPSHOT + 0x354, event)
        self.set(self.SNAPSHOT + 0x358, self.TEAM[team])
        self.set(self.SNAPSHOT + 0x35C, self.PLAYER[team])
        self.set(self.SNAPSHOT + 0x40, 3 if kick else 1)
        self.set(self.PLAYER[team] + 0x3C, self.live(team, index))
        self.run(0xCD88A, registers={UC_X86_REG_EAX: slot, UC_X86_REG_ESI: self.SNAPSHOT,
                                   UC_X86_REG_EBP: drive}, stop=0xCD909)

    def value(self, player, bank=0, *, team=False, stat=patch.STAT_ID):
        self.run(0xCB2D0 if team else 0xCB240, (bank,),
                 {UC_X86_REG_ECX: player, UC_X86_REG_EDX: stat})
        self.u.mem_write(self.STOP + 0x100, b"\xD9\x1D" + struct.pack("<I", self.STOP + 0x180) + b"\xC3")
        self.run(self.STOP + 0x100)
        return struct.unpack("<f", self.u.mem_read(self.STOP + 0x180, 4))[0]

    def write_history(self, player, field, slot, value, history_class=0):
        self.set(0xBD7F98, history_class)
        return self.run(0x14F3B0, (slot, value), {UC_X86_REG_ECX: player, UC_X86_REG_EDX: field})

    def merge(self, team, index=0, history_class=0):
        self.set(0xBD7F98, history_class)
        self.run(0x1336B2, registers={UC_X86_REG_EBP: self.live(team, index),
                                    UC_X86_REG_EDI: self.saved(team, index)}, stop=0x1336B9)


@unittest.skipUnless(XBE.is_file(), "private USA retail default.xbe is absent")
class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = patch.apply(cls.retail)

    def test_field_is_unmapped_and_native_fold_rule_is_sum(self):
        image = XbeImage(self.retail)
        fields = {struct.unpack("<7I", image.read(0xA8A510 + i * 28, 28))[3] for i in range(183)}
        self.assertNotIn(patch.HISTORY_FIELD, fields)
        # Every ordinary postgame sum, conditional count and threshold merge.
        for start, end, stride in ((0x4FC528, 0x4FC760, 8), (0x4FC760, 0x4FC7A8, 12), (0x4FC7A8, 0x4FC7F0, 12)):
            field_offset = 0 if stride == 8 else 4
            self.assertNotIn(patch.HISTORY_FIELD, [struct.unpack("<I", image.read(va + field_offset, 4))[0]
                                                for va in range(start, end, stride)])
        self.assertEqual(image.read(0xAA26C0 + 4 * patch.HISTORY_FIELD, 4), b"\1\0\0\0")
        self.assertNotEqual(patch.HISTORY_FIELD, team_column.TEAM_FIELD)

    def test_request_union_preserves_legacy_budgets_and_fits_complete_plan(self):
        self.assertEqual(patch.REQUESTS[:2], ((patch.OWNER, "code", 1440, 16), (patch.OWNER, "data", 1040, 16)))
        from tests.nfl2k5_allocator_stack import REQUESTS
        for request in patch.REQUESTS:
            self.assertIn(request, REQUESTS)
        rows = json.loads((Path(__file__).resolve().parents[1] / "fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertTrue(set(patch.REQUESTS) <= {tuple(r) for r in rows})
        space.plan(tuple(tuple(r) for r in rows))

    def test_streamed_retail_roster_has_no_field_59_in_any_used_word(self):
        from mod_editor.core import nfl2k5_team_history as history
        if not (XBE.parent / "vc_53450030/0").is_file():
            self.skipTest("private USA roster archive is absent")
        # The descriptor-backed reader loads only this 594 KB resource.
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            self.assertEqual(entry.size, history.RESOURCE_SIZE)
            body = archive.read(entry.virtual_offset, entry.size)[history.RESOURCE_HEADER_SIZE:]
        roster = history.parse_body(body)
        pool = body[roster.pool:roster.pool + roster.used * 4]
        self.assertEqual(roster.used, history.RETAIL_POOL_USED)
        self.assertEqual(history.pool_digest(roster), history.RETAIL_POOL_SHA256)
        self.assertNotIn(patch.HISTORY_FIELD, [(word >> 16) & 127 for word, in struct.iter_unpack("<I", pool)])

    def test_immutable_tables_preserve_all_original_box_rows_and_card_columns(self):
        image, original = XbeImage(self.patched), XbeImage(self.retail)
        ro = patch._stats_sites(self.patched)[1]
        self.assertFalse(image.runtime_writable(ro["va"], ro["size"]))
        self.assertEqual(image.read(ro["va"], 456), original.read(0xAED668, 456))
        self.assertEqual(struct.unpack("<3I", image.read(ro["va"] + 456, 12)), (patch.STAT_ID, 0, ro["va"] + 480))
        _, variants = patch.stat_tables(self.patched, ro["va"])
        for with_team, lists in enumerate(variants):
            for (_, source, pointers), va in zip(team_column.COLUMN_LISTS, lists):
                self.assertEqual(image.read(va, 156), original.read(source, 156))
                expected = pointers[:1] + ((team_column.DESCRIPTOR_VA,) if with_team else ()) + pointers[1:]
                actual = struct.unpack("<" + "I" * (len(expected) + 2), image.read(va + 156, 4 * (len(expected) + 2)))
                self.assertEqual(actual[:-2], expected)
                self.assertEqual(actual[-1], 0)
                self.assertEqual(struct.unpack("<I", image.read(actual[-2] + 0xA0, 4))[0], patch.STAT_ID + 0xEA)

    def test_all_pins_and_partial_owned_installs_refuse_resealed_foreign_input(self):
        for start, size, digest in patch.CONTEXT_PINS:
            self.assertEqual(hashlib.sha256(patch._read(self.retail, start, size)).hexdigest(), digest)
        image = XbeImage(self.retail)
        for va in (0xAED668, 0x5350D0, 0x14F400, 0xAA27AC, 0x4FC600, 0x247C1B):
            bad = bytearray(self.retail)
            bad[image.offset(va)] ^= 1
            self.assertEqual(patch.status(reseal(bad)), "foreign")
            with self.assertRaises(ValueError):
                patch.apply(reseal(bad))
        allocated, _ = space.apply(self.retail, patch.REQUESTS)
        main, stats, tables, _ = patch.assembled(allocated)
        for owner, content, installer in ((patch.OWNER, main, space.install_code),
                                          (patch.STATS_OWNER, stats, space.install_code),
                                          (patch.STATS_OWNER, tables, space.install_read_only)):
            partial, _ = installer(allocated, owner, content)
            self.assertEqual(patch.status(partial), "foreign")

    def test_team_column_installation_order_is_identical(self):
        one = team_column.apply(self.patched)[0]
        two = patch.apply(team_column.apply(self.retail)[0])[0]
        self.assertEqual(one, two)
        self.assertEqual(patch.status(one), "applied")
        self.assertEqual(team_column.status(one), "applied")


@unittest.skipUnless(XBE.is_file() and uc is not None, "private USA retail XBE or Unicorn is absent")
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched = patch.apply(cls.retail)[0]

    def test_native_player_ids_reject_aliases_and_non_roster_pointers(self):
        m = StatsMachine(self.patched)
        for team in (0, 1):
            for index in (0, 1, 64):
                player = m.live(team, index)
                m.u.mem_write(player + 0x34, bytes((team + 1,)))
                self.assertEqual(m.run(m.labels["player_id"], registers={UC_X86_REG_ECX: player}), 2 + team + index * 2)
        for player in (0, m.saved(0), m.PLAYER[0], m.live(0) + 1, m.live(1, 65)):
            self.assertEqual(m.run(m.labels["player_id"], registers={UC_X86_REG_ECX: player}), 0)

    def test_ordinary_reader_prologues_preserve_native_registers_flags_and_stack(self):
        for name in ("player_stat", "team_stat"):
            va, original, _ = patch.HOOKS[name]
            raw = bytearray(self.patched)
            raw[va - 0x10000:va - 0x10000 + len(bytes.fromhex(original))] = bytes.fromhex(original)
            old, new = StatsMachine(reseal(raw)), StatsMachine(self.patched)
            for stat in (0, 7, 59, 69, 87, 182, 0x3FFF, 0x4001):
                snapshots = []
                for machine in (old, new):
                    machine.run(va, (11,), {UC_X86_REG_ECX: machine.saved(1), UC_X86_REG_EDX: stat,
                                           UC_X86_REG_EAX: 123, UC_X86_REG_EFLAGS: 0x247},
                                stop=va + len(bytes.fromhex(original)))
                    snapshots.append(tuple(machine.reg(r) for r in (UC_X86_REG_EAX, UC_X86_REG_EBX,
                        UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EFLAGS,
                        UC_X86_REG_ESP)) + (bytes(machine.u.mem_read(machine.reg(UC_X86_REG_ESP), 16)),))
                self.assertEqual(*snapshots)

    def test_cpu_override_requires_try_defender_live_ball_and_cpu_control(self):
        for phase, defense, holder, cpu, expected in ((3, True, True, True, 0),
                (0, True, True, True, 1), (1, True, True, True, 1), (2, True, True, True, 1),
                (4, True, True, True, 1), (99, True, True, True, 1), (3, False, True, True, 1),
                (3, True, False, True, 1), (3, True, True, False, 1)):
            m = StatsMachine(self.patched)
            player = m.PLAYER[0]
            m.set(patch.PHASE, phase)
            m.set(patch.ORIGINAL_TEAM, m.TEAM[1 if defense else 0])
            m.set(m.BALL, player if holder else m.PLAYER[1])
            m.set(player, 1)
            m.set(player + 0xC, player + 0x400)
            m.set(player + 0x400, -1 if cpu else 0)
            m.stub(0x2E2A90, 1)  # existing suite executes the real selector and full transition
            self.assertEqual(m.run(m.labels["cpu_return"], registers={UC_X86_REG_ECX: player,
                                                                    UC_X86_REG_ESI: player}), expected)

    def test_history_replay_reassignment_failure_and_ring_wrap(self):
        m = StatsMachine(self.patched)
        m.history(0, 0)
        m.history(0, 0)
        self.assertEqual(m.count(0), 1)
        m.history(0, 1, index=1, outcome=6)
        self.assertEqual((m.count(0), m.count(1, 1)), (0, 1))
        m.history(0, 1, index=1, event=0)
        self.assertEqual(m.count(1, 1), 0)
        for drive in range(130):
            m.history(drive, drive & 1, outcome=1 if drive & 2 else 6)
        self.assertEqual((m.count(0), m.count(1)), (65, 65))
        m.history(129, 1)
        self.assertEqual(m.count(1), 65)
        for team in (0, 1):
            self.assertEqual(m.value(m.live(team)), 65)
            self.assertEqual(m.value(patch.LIVE_TEAMS[team], team=True), 65)

    def test_safeties_kicks_offensive_tries_and_wrong_outcomes_do_not_credit_defense(self):
        for event in (0, 2, 4):
            m = StatsMachine(self.patched)
            m.history(0, 1, event=event)
            self.assertEqual(m.count(1), 0)
        for outcome in (0, 2, 3, 4, 5, 7):
            m = StatsMachine(self.patched)
            m.history(0, 1, outcome=outcome)
            self.assertEqual(m.count(1), 0)

    def test_real_season_writer_reader_class_career_and_repeated_merge(self):
        for history_class in (0, 1):
            m = StatsMachine(self.patched)
            saved = m.saved(1)
            self.assertEqual(m.write_history(saved, 59, 2, 4, history_class), 1)
            self.assertEqual(m.write_history(saved, 59, 3, 2, history_class), 1)
            self.assertEqual(m.write_history(saved, 59, 3, 9, 1 - history_class), 1)
            self.assertEqual(m.write_history(saved, 87, 2, 7, history_class), 1)
            m.history(0, 1)
            m.set(0xBD7F98, history_class)
            self.assertEqual([m.value(m.live(1), bank) for bank in (0, 8, 9, 10, 11, 12, 13)], [1, 6, 7, 2, 3, 4, 0])
            m.merge(1, history_class=history_class)
            self.assertEqual(m.count(1), 0x8001)
            self.assertEqual(m.get(0xBD7F98), 0)
            m.set(0xBD7F98, history_class)
            self.assertEqual([m.value(saved, bank) for bank in (9, 10, 11, 12)], [7, 3, 3, 4])
            self.assertEqual(m.value(m.live(1), 11), 3)
            m.merge(1, history_class=history_class)
            m.set(0xBD7F98, history_class)
            self.assertEqual(m.value(saved, 11), 3)
            m.set(0xBD7F98, 1 - history_class)
            self.assertEqual(m.value(saved, 11), 9)

    def test_native_box_count_label_format_and_team_value(self):
        m = StatsMachine(self.patched)
        m.history(0, 0)
        m.history(1, 0, index=1)
        m.history(2, 1)
        self.assertEqual(m.run(0x363690), 39)
        label = m.run(0x3636A0, registers={UC_X86_REG_ECX: 38})
        self.assertEqual(bytes(m.u.mem_read(label, 50)).decode("utf-16-le").split("\0")[0], "Defensive 2pt Conversions")
        # Run the actual cell's value acquisition and format selector. The
        # native string formatter is separately reached in the next assertion.
        for team, expected in ((0, 2), (1, 1)):
            m.run(0x3636B0, registers={UC_X86_REG_ECX: patch.LIVE_TEAMS[team], UC_X86_REG_EDX: 38}, stop=0x3636E1)
            self.assertEqual(m.reg(UC_X86_REG_ESI), 0)
            self.assertEqual(struct.unpack("<f", m.u.mem_read(m.reg(UC_X86_REG_ESP) + 4, 4))[0], expected)
            result = m.run(0x3636B0, registers={UC_X86_REG_ECX: patch.LIVE_TEAMS[team], UC_X86_REG_EDX: 38})
            self.assertEqual(bytes(m.u.mem_read(result, 16)).decode("utf-16-le").split("\0")[0], str(expected))

    def test_card_callback_and_native_season_row_builder_with_or_without_team(self):
        for with_team in (False, True):
            payload = team_column.apply(self.patched)[0] if with_team else self.patched
            m = StatsMachine(payload)
            m.write_history(m.saved(1), 59, 2, 4)
            m.set(0xC90248, m.saved(1))
            m.run(0x320B90, stop=0x320B95)
            expected_lists = patch.stat_tables(payload, m.ro)[1][int(with_team)]
            for i, va in enumerate(expected_lists):
                self.assertEqual(m.get(0x53572C + i * 256), va)
            # Only the new stat is nonzero, so the real row callback must
            # discover the season even when no ordinary game entry exists.
            widget, ids = m.STOP + 0x2000, m.STOP + 0x2100
            m.set(widget + 0xA0, 1)
            m.set(widget + 0x44, ids)
            m.set(ids, patch.STAT_ID + 0xEA)
            self.assertEqual(m.run(0x320C60, registers={UC_X86_REG_ECX: widget}), 2)
            self.assertEqual((m.get(0xC90254), m.get(0xC90258)), (12, 9))
            m.run(0x320430, registers={UC_X86_REG_ECX: 0, UC_X86_REG_EDX: patch.STAT_ID + 0xEA})
            m.u.mem_write(m.STOP + 0x100, b"\xD9\x1D" + struct.pack("<I", m.STOP + 0x180) + b"\xC3")
            m.run(m.STOP + 0x100)
            self.assertEqual(struct.unpack("<f", m.u.mem_read(m.STOP + 0x180, 4))[0], 4)

    def test_stat_reset_clears_old_game_and_simulation_counts(self):
        m = StatsMachine(self.patched)
        m.history(0, 1)
        m.run(0x1ECAF0)
        self.assertEqual(bytes(m.u.mem_read(m.data, patch.DATA_SIZE)), bytes(patch.DATA_SIZE))
        self.assertEqual(m.value(m.live(1)), 0)

    def test_failed_offensive_attempt_is_retained_for_return_or_safety(self):
        for team in (0, 1):
            for outcome in (1, 6):
                for event in (2, 5):
                    for kick in (False, True):
                        m = StatsMachine(self.patched)
                        m.history(0, team, outcome=outcome, event=event, kick=kick)
                        self.assertEqual(m.run(0x250D10, registers={UC_X86_REG_ECX: 1 - team}), int(not kick))
                        self.assertEqual(m.run(0x250D10, registers={UC_X86_REG_ECX: team}), 0)
                        first, second = m.STOP + 0x1000, m.STOP + 0x1400
                        # The real commit's subtype and TD-beneficiary branches.
                        m.run(0x1EEA16, registers={UC_X86_REG_ESI: 0, UC_X86_REG_EDI: first,
                                                 UC_X86_REG_EBX: second}, stop=0x1EEA60)
                        self.assertEqual(m.get((first if outcome == 1 else second) + 0x250), int(not kick))

    def test_native_player_points_tail_adds_two_without_changing_other_totals(self):
        m = StatsMachine(self.patched)
        m.history(0, 1)
        for team, points in ((0, 13), (1, 15)):
            m.set(m.STACK + 12, m.STOP)
            self.assertEqual(m.run(0x24FFCB, registers={UC_X86_REG_EAX: 2, UC_X86_REG_EDI: 9,
                                                       UC_X86_REG_ESI: m.live(team), UC_X86_REG_EBX: 0}), points)

    def test_native_banner_classifier_beneficiary_and_label_for_all_custom_subtypes(self):
        for drive_team in (0, 1):
            for outcome in (1, 6):
                for subtype in (5, 6, 7):
                    m = StatsMachine(self.patched)
                    m.set(patch.DRIVE_RING, (drive_team << 21) | (outcome << 26) | (subtype << 29))
                    # A scored try: play type 2, down 0, drive index 0.
                    m.set(0xE53874, 2 | (1 << 28))
                    event = m.run(m.labels["summary_event"], registers={UC_X86_REG_EBX: 0})
                    self.assertEqual(event, 15 if subtype == 5 else 16)
                    beneficiary = drive_team ^ (outcome == 6) ^ (subtype != 6)
                    self.assertEqual(m.get(0xB9C264), patch.LIVE_TEAMS[beneficiary])
                    m.run(0xEBD35, registers={UC_X86_REG_EAX: event}, stop=0xEBD3C)
                    label = m.reg(UC_X86_REG_EDX)
                    expected = "DEFENSIVE 2PT RETURN" if subtype == 5 else "SAFETY ON TRY (+1)"
                    self.assertEqual(bytes(m.u.mem_read(label, 48)).decode("utf-16-le").split("\0")[0], expected)
                    # Continue through the banner's actual UTF-16 copy and
                    # epilogue with its two saved registers and three args.
                    m.set(m.STACK + 8, m.STOP)
                    m.run(0xEBD3C, registers={UC_X86_REG_EDX: label, UC_X86_REG_EDI: m.SPOT})
                    self.assertEqual(bytes(m.u.mem_read(m.SPOT, 2 * (len(expected) + 1))).decode("utf-16-le"), expected + "\0")
        m = StatsMachine(self.patched)
        for event in range(15):
            m.run(0xEBD35, registers={UC_X86_REG_EAX: event}, stop=0xEBD3C)
            self.assertEqual(m.reg(UC_X86_REG_EDX), m.get(0xA905CC + event * 4))

    def test_native_roster_save_reload_preserves_field_and_season_readers(self):
        m = StatsMachine(self.patched)
        m.history(0, 1)
        m.merge(1)
        m.write_history(m.saved(1), 59, 2, 4)
        m.write_history(m.saved(1), 87, 2, 2)
        used = m.get(m.ROSTER + 0x40)
        pool = bytes(m.u.mem_read(m.POOL, used * 4))
        m.run(0xC0730, registers={UC_X86_REG_ECX: m.ROSTER})
        serialized = bytes(m.u.mem_read(m.ROSTER, 0x7000))
        # Fresh process, different addresses, and no owned runtime counts.
        fresh = StatsMachine(self.patched)
        base = 0x4000000
        fresh.u.mem_map(base, 0x8000)
        fresh.u.mem_write(base, serialized)
        fresh.set(0xB72918, base)
        # Post-relocation runtime team/cache setup is an engine boundary. The
        # whole roster and every player/team/pool pointer relocator execute.
        fresh.stub(0x10E9D0)
        fresh.stub(0x10E990)
        fresh.run(0xC0500, registers={UC_X86_REG_ECX: base})
        self.assertEqual(fresh.get(base + 0x44), base + (m.POOL - m.ROSTER))
        self.assertEqual(bytes(fresh.u.mem_read(fresh.get(base + 0x44), used * 4)), pool)
        player = base + m.saved(1) - m.ROSTER
        self.assertEqual([fresh.value(player, bank) for bank in (9, 11, 12)], [5, 1, 4])
        self.assertEqual(bytes(fresh.u.mem_read(fresh.data, patch.DATA_SIZE)), bytes(patch.DATA_SIZE))

    def test_native_fold_and_delete_keep_other_fields_and_class(self):
        m = StatsMachine(self.patched)
        player = m.saved(0)
        for slot, value in ((1, 2), (2, 3), (3, 4)):
            m.write_history(player, 59, slot, value)
        m.write_history(player, 59, 1, 6, 1)
        m.write_history(player, 7, 2, 17)
        m.set(0xBD7F98, 0)
        m.stub(0x177990, pop=4)  # progress callback only
        self.assertEqual(m.run(0x14EFE0, (2,)), 1)
        self.assertEqual([m.value(player, bank) for bank in (9, 11, 12, 13)], [9, 4, 5, 0])
        m.write_history(player, 59, 2, 0)
        self.assertEqual(m.value(player, 9), 4)
        m.set(0xBD7F98, 1)
        self.assertEqual(m.value(player, 9), 6)

    def test_merge_preserves_registers_flags_x87_sse_and_saturates_signed_storage(self):
        m = StatsMachine(self.patched)
        m.write_history(m.saved(0), 59, 3, 32767)
        m.history(0, 0)
        # Keep this separate from value()'s stable fstp shim: Unicorn caches
        # translated blocks, including bytes changed through host mem_write.
        m.u.mem_write(m.STOP + 0x200, bytes.fromhex("d9e8 d9eb d9ea c3"))
        m.run(m.STOP + 0x200)
        for i in range(8):
            m.reg(UC_X86_REG_XMM0 + i, 0x123456789ABCDEF + i)
        regs = (UC_X86_REG_FPSW, UC_X86_REG_FPCW, UC_X86_REG_FPTAG)
        regs += tuple(UC_X86_REG_FP0 + i for i in range(8))
        regs += tuple(UC_X86_REG_XMM0 + i for i in range(8))
        before = tuple(m.reg(r) for r in regs)
        m.merge(0)
        self.assertEqual(tuple(m.reg(r) for r in regs), before)
        self.assertEqual(m.reg(UC_X86_REG_EBP), m.live(0))
        self.assertEqual(m.reg(UC_X86_REG_EDI), m.saved(0))
        self.assertEqual(m.reg(UC_X86_REG_ESP), m.STACK)
        self.assertEqual(m.value(m.saved(0), 11), 32767)


if __name__ == "__main__":
    unittest.main()
