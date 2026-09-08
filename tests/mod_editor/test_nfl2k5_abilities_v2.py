"""Standalone tier, assignment, integrity and native effect replays. UNWITNESSED."""
from pathlib import Path
import copy
import csv
import hashlib
import io
import itertools
import json
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_editor as editor
from mod_editor.core import nfl2k5_abilities_runtime as patch
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_momentum as momentum
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, league_body
from tests.mod_editor.test_nfl2k5_abilities_runtime import RETAIL, repin
try:
    from tests.nfl2k5_abilities_machine import Machine
    from unicorn import x86_const as x86
except ImportError:
    Machine = None


class AssignmentTests(unittest.TestCase):
    def test_tier_masks_preserve_every_neighbor_value(self):
        for low, high, tier in itertools.product((0, 0x1f, 0xff), range(256), range(4)):
            raw = bytes(82) + bytes((low, high))
            record = rr.PlayerRecord.decode(raw)
            record.ability_tier = tier
            self.assertEqual(record.encode(), raw[:83] + bytes(((high & 0x3f) | tier << 6,)))
            self.assertEqual(record.ability_tier, tier)
        record = rr.PlayerRecord.decode(bytes(84))
        for invalid in (-1, 4, True, 1.0, "Star"):
            with self.assertRaises(ValueError): record.ability_tier = invalid

    def test_manual_capacity_exact_replay_masked_undo_and_identity_refusal(self):
        doc = rr.load_body(synthetic_body())
        p = doc.players[0]
        for tier, limit in enumerate(editor.LIMITS):
            abilities = list(editor.MASKS)[:limit]
            plan = editor.plan_player(doc, p, tier=tier, abilities=abilities)
            before_body = doc.to_body()
            receipt = editor.apply_plan(doc, plan, require_fresh=True)
            after_body = doc.to_body()
            self.assertEqual(p.record.ability_tier, tier)
            self.assertEqual(sum(p.record.abilities.values()), limit)
            self.assertEqual(editor.apply_plan(doc, plan)["changed_bytes"], 0)
            p.record.guardian_cap = True
            p.record.set_depth_lock("rank", True)
            p.record.set("star_tag", 1)
            editor.apply_plan(doc, plan, reverse=True)
            self.assertTrue(p.record.guardian_cap)
            self.assertTrue(p.record.depth_locks["rank"])
            self.assertEqual(p.record.get("star_tag"), 1)
            self.assertEqual(receipt["changed_bytes"], sum(a != b for a,b in zip(before_body,after_body)))
        with self.assertRaisesRegex(ValueError, "permits 2"):
            editor.plan_player(doc, p, tier=1, abilities=["juke", "spin", "truck"])
        plan = editor.plan_player(doc, p, tier=1, abilities=["juke"])
        p.first = "Reused"
        before = doc.to_body()
        with self.assertRaisesRegex(ValueError, "identity"):
            editor.apply_plan(doc, plan)
        self.assertEqual(doc.to_body(), before)

    def test_auto_assignment_stable_ranking_scope_receipt_and_full_undo(self):
        doc = rr.load_body(league_body(53))
        before = doc.to_body()
        plan = editor.plan_auto_assign(doc, top_n=4)
        self.assertEqual(plan, editor.plan_auto_assign(doc, top_n=4))
        self.assertTrue(plan["rows"])
        receipt = editor.apply_plan(doc, plan, require_fresh=True)
        changed = doc.to_body()
        allowed = {p.offset+i for p in doc.players for i in (82, 83)}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(before,changed)) if a!=b))
        self.assertEqual(receipt["changed_bytes"], sum(a!=b for a,b in zip(before,changed)))
        self.assertTrue(all(sum(p.record.abilities.values()) <= editor.LIMITS[p.record.ability_tier]
                            for p in doc.players))
        self.assertEqual(editor.apply_plan(doc, plan)["changed_players"], 0)
        editor.apply_plan(doc, plan, reverse=True)
        self.assertEqual(doc.to_body(), before)
        self.assertEqual(editor.apply_plan(doc, plan, reverse=True)["changed_players"], 0)
        editor.apply_plan(doc, plan)
        self.assertEqual(doc.to_body(), changed)
        for group in {r["position"] for r in plan["rows"]}:
            tiers = [r["after"] >> 14 for r in plan["rows"] if r["position"]==group]
            self.assertEqual(tiers[:4], [3,2,1,1][:len(tiers)])
            self.assertTrue(all(t == 0 for t in tiers[4:]))

    def test_whole_transaction_refuses_stale_mixed_duplicate_and_foreign_bits(self):
        doc = rr.load_body(league_body(53))
        plan = editor.plan_auto_assign(doc, top_n=3)
        bad = copy.deepcopy(plan)
        bad["rows"][-1]["after"] |= 0x100  # cosmetic star is not ours
        before = doc.to_body()
        with self.assertRaisesRegex(ValueError, "foreign bits"): editor.apply_plan(doc, bad)
        self.assertEqual(doc.to_body(), before)
        bad = copy.deepcopy(plan)
        bad["rows"][-1] = bad["rows"][0]
        with self.assertRaisesRegex(ValueError, "identity"): editor.apply_plan(doc, bad)
        self.assertEqual(doc.to_body(), before)
        one = copy.deepcopy(plan)
        one["rows"] = [next(r for r in plan["rows"] if r["mask"])]
        editor.apply_plan(doc, one)
        before = doc.to_body()
        with self.assertRaisesRegex(ValueError, "mixed"): editor.apply_plan(doc, plan)
        self.assertEqual(doc.to_body(), before)
        with self.assertRaisesRegex(ValueError, "preview"): editor.apply_plan(doc, plan, require_fresh=True)
        self.assertEqual(doc.to_body(), before)

    def test_legacy_flags_load_losslessly_tier_downgrade_and_csv_json_export(self):
        doc = rr.load_body(synthetic_body())
        p = doc.players[0]
        for name in editor.MASKS: p.record.set_ability(name, True)
        legacy = doc.to_body()
        self.assertEqual(rr.load_body(legacy).to_body(), legacy)
        self.assertEqual(p.record.ability_tier, 0)
        plan = editor.plan_player(doc, p, tier=1, abilities=editor.fit_tier(p.record, 1))
        editor.apply_plan(doc, plan)
        self.assertEqual(sum(p.record.abilities.values()), 2)
        edits = rr.edits_document(doc)
        self.assertEqual(rr.apply_body(synthetic_body(), edits)[0], doc.to_body())
        csv_text = rr.export_csv(doc)
        self.assertEqual(rr.import_csv(doc, csv_text)["fields"], 0)
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(rows[0]["ability_tier"], "1")
        editor.apply_plan(doc, plan, reverse=True)
        self.assertEqual(doc.to_body(), legacy)

    def test_named_tier_in_save_codec_and_assignment_signed_rating_refusal(self):
        from mod_editor.core import nfl2k5_save_rost as codec
        from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
        saved = codec.decode(synthetic_franchise())
        player = saved.players[0]
        saved.edit_player(player.pool,player.index,dict(ability_tier=2,juke=1,guardian_cap=1,star_tag=1))
        raw = saved.to_bytes()
        decoded = codec.decode(raw)
        self.assertEqual(decoded.to_bytes(),raw)
        result = decoded.by_key[player.pool,player.index].record
        self.assertEqual(result.ability_tier,2)
        self.assertTrue(result.abilities['juke'])
        self.assertTrue(result.guardian_cap)
        self.assertEqual(result.get('star_tag'),1)
        doc = rr.load_body(league_body(53))
        doc.players[0].record.set('agility',128)
        before = doc.to_body()
        with self.assertRaisesRegex(ValueError,'signed'):
            editor.plan_auto_assign(doc)
        self.assertEqual(doc.to_body(),before)


@unittest.skipUnless(RETAIL.is_file(), "pinned USA retail XBE required")
class IntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("local XBE does not match the USA retail pin")

    def test_each_lock_is_strict_immutable_and_all_combinations_replay(self):
        for values in itertools.product((False, True), repeat=3):
            settings = dict(zip(patch.LOCK_MASKS, values))
            result, _ = patch.apply(self.retail, **settings)
            self.assertEqual({k: patch.read_settings(result)[k] for k in settings}, settings)
            self.assertEqual(patch.apply(result)[0], result)
            for key in settings:
                with self.assertRaisesRegex(ValueError, "different abilities settings"):
                    patch.apply(result, **{key: not settings[key]})
        for key in patch.LOCK_MASKS:
            for bad in (0, 1, "yes", None):
                with self.assertRaisesRegex(ValueError, "Boolean"):
                    patch.apply(self.retail, **{key: bad})

    def test_shared_attribute_normalization_requires_the_entire_owner(self):
        allocated = space.apply(self.retail, patch.REQUESTS + momentum.REQUESTS, scaleout=True)[0]
        good = momentum.apply(patch.apply(allocated)[0], momentum=100, momentum_contact=True)[0]
        self.assertEqual(momentum.status(good), "applied")
        for va in (0x17B011, 0x179A30, patch.allocation(good)["va"]+patch.assembly.LABELS["effect_masks"]):
            bad = bytearray(good)
            bad[XbeImage(good).offset(va)] ^= 1
            bad = repin(bad)
            self.assertEqual(momentum.status(bad), "foreign")
            before = hashlib.sha256(bad).hexdigest()
            with self.assertRaises(ValueError): momentum.apply(bad)
            self.assertEqual(hashlib.sha256(bad).hexdigest(), before)

    def test_budget_and_complete_union(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        rows = json.loads((ROOT/'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        self.assertEqual([tuple(r) for r in rows if r[0]==patch.OWNER], list(patch.REQUESTS))
        self.assertTrue(set(patch.REQUESTS) <= set(REQUESTS))
        self.assertLessEqual(patch.CODE_SIZE, patch.BUDGET)
        space.plan(rows)


@unittest.skipUnless(Machine is not None and RETAIL.is_file(), "Unicorn and pinned USA retail XBE required")
class EffectReplays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("local XBE does not match the USA retail pin")
        cls.native = space.apply(cls.retail, patch.REQUESTS, scaleout=True)[0]
        cls.payload = patch.apply(cls.native, abilities_off_week=7)[0]

    def test_each_effect_before_after_real_getter_and_both_native_clamps(self):
        baseline, changed = Machine(self.native), Machine(self.payload)
        offsets = {1:0x37, 2:0x3C, 3:0x3D, 12:0x41, 18:0x48}
        evidence = []
        for name, (attribute, bit, label) in patch.EFFECTS.items():
            getter = struct.unpack('<I', baseline.image.read(0xAA4028+attribute*32,4))[0]
            for raw, tier, permission in itertools.product((0, 50, 99, 100, 127), range(4), (False,True)):
                values = []
                native_registers = []
                flags = tier << 14 | (bit if permission else 0) | 0x211F
                for m in (baseline, changed):
                    m.flags(flags)
                    m.uc.mem_write(m.R+offsets[attribute], bytes([raw]))
                    m.run(getter, ecx=m.R, edx=1)
                    native_cache = m.pop_float()
                    m.f32(0xAA43B8+attribute*8, native_cache)
                    m.f32(0xAA43BC+attribute*8, 0)
                    m.run(0x17B010, ecx=m.R, edx=attribute, args=(0x184,))
                    native_registers.append(tuple(m.uc.reg_read(getattr(x86,'UC_X86_REG_'+name))
                                                  for name in ('EAX','EBX','ECX','EDX','ESI','EDI','EBP')))
                    values.append(m.pop_float())
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK+8)
                    self.assertEqual(bytes(m.uc.mem_read(m.R+82,2)), struct.pack('<H', flags))
                    self.assertTrue(all(m.STACK-512 <= va < m.STACK+16 or (va,size)==(m.SCRATCH+4,4)
                                        for va,size in m.writes), m.writes)  # pop_float's measurement store
                expected = min(1, values[0] + .02*tier) if tier and permission and values[0]>0 else values[0]
                self.assertEqual(native_registers[0],native_registers[1])
                self.assertAlmostEqual(values[1], expected, places=6, msg=str((name,raw,tier,permission)))
                if raw==50 and tier==3 and permission:
                    evidence.append(dict(effect=name, attribute=attribute, getter=hex(getter),
                                         before=values[0], after=values[1], unit=label))
        if os.environ.get('NFL2K5_ABILITIES_PROOF'):
            Path(os.environ['NFL2K5_ABILITIES_PROOF']).write_text(json.dumps(evidence,indent=2)+'\n')

    def test_live_scope_week_slot_limits_unrelated_attributes_and_x87_stack(self):
        m = Machine(self.payload)
        for attr, mode, stage, week, phase in itertools.product(range(28),(0,2),(7,8),(7,8),(13,14)):
            m.flags(0xC000 | patch.ABILITY_MASK)
            m.u32(0xE576A0,mode); m.u32(0xE576A4,stage); m.u32(0xE576B4,week); m.u32(0xE602B8,phase)
            m.f32(0xAA43B8+attr*8,.5); m.f32(0xAA43BC+attr*8,0)
            m.run(0x17B010,ecx=m.R,edx=attr,args=(0x184,))
            bonus = attr in (1,2,3,12,18) and phase==14 and (mode,stage,week)!=(2,8,7)
            self.assertAlmostEqual(m.pop_float(), .56 if bonus else .5, places=6)
        for tier, flags, expected in ((1,patch.JUKE|patch.TRUCK,patch.JUKE|patch.TRUCK),
                                      (1,patch.JUKE|patch.TRUCK|patch.SPIN,0),
                                      (2,patch.ABILITY_MASK,0),(3,patch.ABILITY_MASK,patch.ABILITY_MASK),
                                      (0,patch.ABILITY_MASK,patch.ABILITY_MASK)):
            m.flags(tier<<14 | flags)
            self.assertEqual(m.run('effective',ecx=m.R),expected)
        # A lower x87 value survives the wrapper unchanged.
        m.flags(0xC000|patch.JUKE)
        m.uc.mem_write(m.STOP+0x300,b'\xd9\xe8')  # fld1
        m.uc.emu_start(m.STOP+0x300,m.STOP+0x302,count=1)
        m.run(0x17B010,ecx=m.R,edx=1,args=(0x184,))
        self.assertAlmostEqual(m.pop_float(),.56,places=6)
        self.assertEqual(m.pop_float(),1)

    def test_effects_follow_native_injury_and_condition_reductions(self):
        baseline, changed = Machine(self.native), Machine(self.payload)
        offsets = {1:0x37,2:0x3C,3:0x3D,12:0x41,18:0x48}
        for attribute,bit,_label in patch.EFFECTS.values():
            getter = struct.unpack('<I',baseline.image.read(0xAA4028+attribute*32,4))[0]
            for injury,condition in itertools.product((0,.5,1),(0,.5,1)):
                values=[]
                for m in (baseline,changed):
                    m.flags(0xC000|bit)
                    m.uc.mem_write(m.R+offsets[attribute],b'\x32')
                    m.uc.mem_write(m.R+0x28,struct.pack('<H',0x20 if injury!=1 else 0))
                    m.f32(m.SCRATCH,injury)  # explicit peripheral injury-factor fixture
                    m.run(getter,ecx=m.R,edx=1)
                    m.f32(0xAA43B8+attribute*8,m.pop_float())
                    m.f32(0xAA43BC+attribute*8,-.2)
                    m.f32(m.COND+4,condition)
                    m.run(0x17B010,ecx=m.R,edx=attribute,args=(0x184,))
                    values.append(m.pop_float())
                self.assertAlmostEqual(values[1],min(1,values[0]+.06) if values[0]>0 else 0,places=6)

    def test_optional_locks_zero_flags_all_commands_speed_and_native_noncarrier_charge(self):
        for values in itertools.product((False,True),repeat=3):
            settings = dict(zip(patch.LOCK_MASKS,values))
            m = Machine(patch.apply(self.native,**settings)[0])
            unlocked = sum(mask for key,mask in patch.LOCK_MASKS.items() if not settings[key])
            for controller, (command, mask) in itertools.product((0,-1), patch.MOVE_MASKS.items()):
                m.player(abilities=0,controller=controller,command=command)
                m.run('filter',regs={'EBX':m.P})
                self.assertEqual(m.read(m.T+0x1C), command if unlocked & mask == mask else 0)
                self.assertEqual(m.number(m.T+0x10),.625)
            m.player(abilities=0,speed=127)
            m.seed_native_speed_cache()
            m.run('speed',ecx=m.R,args=(0x184,))
            self.assertAlmostEqual(m.pop_float(), .99 if settings['lock_speedster'] else 1.27, places=6)
            m.flags(0xC000)  # disabling locks must never invent a stored rating ability
            m.f32(0xAA43B8+12*8,.5); m.f32(0xAA43BC+12*8,0)
            m.run(0x17B010,ecx=m.R,edx=12,args=(0x184,))
            self.assertEqual(m.pop_float(),.5)
            m.u32(m.BALL,m.P+0x8000)  # noncarrier, outside mapped move consumer
            m.f32(m.S+0x44,1); m.u32(m.S+0x90,3)
            m.run('consume')
            native = not settings['lock_right_stick'] and not settings['lock_special_moves']
            self.assertEqual(m.read(m.S+0x90)&3,1 if native else 0)

    def test_tackle_shed_and_momentum_real_shared_getter_both_reads(self):
        from tests.mod_editor.test_nfl2k5_momentum import Machine as ContactMachine
        base = space.apply(self.retail, patch.REQUESTS+momentum.REQUESTS,scaleout=True)[0]
        payload = patch.apply(momentum.apply(base,momentum=0,momentum_collisions=True,
                                              momentum_collision_level=100)[0])[0]
        m = ContactMachine(payload,native_tick=False)
        m.data_va = momentum._sites(payload)[1]['va']
        other = m.player(m.P+0x1000,velocity=0)
        m.f32(other+0x708,100)
        # Restore the complete installed getter: the old Momentum fixture stubs
        # it. Only slider lookups remain neutral fixtures in this replay.
        m.uc.mem_write(0x17B010,XbeImage(payload).read(0x17B010,407))
        m.uc.mem_write(0x17B940,bytes.fromhex('d9eec20400'))
        m.uc.mem_write(0x17B8F0,bytes.fromhex('d9eec3'))
        team, condition = m.STOP+0x600, m.STOP+0x680
        m.u32(m.P+0xB30,team); m.u32(team+4,condition); m.u32(team+0x20,0); m.f32(condition+4,1)
        m.uc.mem_write(m.P+0xB34,b'\x01')
        m.f32(0xAA43B8+12*8,.5); m.f32(0xAA43BC+12*8,0)
        for tier in range(4):
            m.uc.mem_write(m.P+0xB52,struct.pack('<H',tier<<14|patch.TRUCK))
            expected = .5 + .02*tier + .06*900/momentum.REFERENCE_SPEED
            self.assertAlmostEqual(m.contact(),expected,places=6)
            self.assertAlmostEqual(m.contact(later=True),expected,places=6)
        m.f32(0xAA43B8+12*8,.99)
        self.assertEqual(m.contact(),1)
        self.assertEqual(m.contact(later=True),1)


class RetailAssignmentTests(unittest.TestCase):
    def test_assignment_on_retail_roster_exact_receipt_and_resource_round_trip(self):
        root = RETAIL.parent
        if not (root/'vc_53450030/0').is_file():
            self.skipTest('retail loose archive index required for roster assignment proof')
        doc = rr.load_image(root)
        before = doc.to_body()
        if hashlib.sha256(before).hexdigest()!=rr.RETAIL_BODY_SHA256:
            self.skipTest('local roster is not the pinned USA retail body')
        self.assertEqual(len(doc.players),2547)
        self.assertTrue(all(p.record.encode()[82:84]==b'\0\0' for p in doc.players))
        plan = editor.plan_auto_assign(doc,top_n=10)
        receipt = editor.apply_plan(doc,plan,require_fresh=True)
        self.assertGreater(receipt['changed_players'],100)
        edited = doc.to_body()
        self.assertEqual(len(edited),len(before))
        self.assertEqual(rr.apply_body(before,rr.edits_document(doc))[0],edited)
        self.assertEqual(rr.load_body(edited).to_body(),edited)
        editor.apply_plan(doc,plan,reverse=True)
        self.assertEqual(doc.to_body(),before)
        if os.environ.get('NFL2K5_ABILITIES_ASSIGNMENT_PROOF'):
            Path(os.environ['NFL2K5_ABILITIES_ASSIGNMENT_PROOF']).write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__': unittest.main()
