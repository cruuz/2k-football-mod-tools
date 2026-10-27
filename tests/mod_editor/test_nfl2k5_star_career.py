"""b778-st2: rookie stars and stars earned/lost over a career.

The native owner is exercised under Unicorn on the pinned retail executable.  The draft-class and
offseason proofs use the real overall routine (0x246D80) and the real season-stat getter (0x14EF20);
the game's rand (0x48B50) is a deterministic xorshift fixture so a class can be replayed by seed.
"""
from __future__ import annotations

import collections
import os
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_star_career as patch  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XBE", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "default.xbe")))
DISC = Path(os.environ.get("NFL2K5_SOFTDRINK_DISC") or os.environ.get("NFL2K5_V061_DISC") or "/nonexistent")
try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover - the Studio runtime ships unicorn
    uc = None


def _retail() -> bytes:
    return RETAIL.read_bytes()


# ------------------------------------------------------------------ synthetic records (portable)
def class_records(count=380, seed=3) -> list[bytes]:
    """A draft class from the game's own create-player templates plus a per-record rating boost."""
    rng = random.Random(seed)
    weights = (6, 5, 6, 5, 2, 1, 5, 1, 10, 5, 6, 4)  # the generator's archetype weights
    out = []
    for _ in range(count):
        index = rng.randrange(len(rr.RETAIL_CREATE_PLAYER_TEMPLATES))
        _name, values = rr.RETAIL_CREATE_PLAYER_TEMPLATES[index]
        record = {field.name: 0 for field in rr.FIELDS}
        for slot, value in enumerate(values):
            record[rr.CREATE_PLAYER_TEMPLATE_SLOTS[slot]] = max(0, min(100, value))
        boost = rng.randrange(0, 22)
        for field in rr.RATING_BYTE_ORDER:
            if field not in rr.STYLE_RATINGS:
                record[field] = max(0, min(100, record[field] + boost))
        record["position"] = index // rr.CREATE_PLAYER_TEMPLATE_VARIANTS
        record["years_pro"] = 1
        record["unknown_24_high"] = rng.choices(range(12), weights=weights)[0]
        out.append(rr.PlayerRecord(record).encode())
    return out


def pool_records(count=600, seed=11) -> list[bytes]:
    """An offseason pool: mixed overalls, ages and authored star tags/tiers (no stored move flags)."""
    rng = random.Random(seed)
    records = class_records(count, seed)
    out = []
    for index, raw in enumerate(records):
        record = bytearray(raw)
        record[0x08] = 4                                   # NFL player
        record[0x25] = (record[0x25] & 0xE0) | rng.randint(2, 14)
        tagged = rng.random() < 0.15
        tier = rng.choices((0, 1, 2, 3), weights=(4, 5, 3, 1))[0]
        record[0x52] = 0
        record[0x53] = (1 if tagged else 0) | (tier << 6)
        out.append(bytes(record))
    return out


def stats_for(raw: bytes, seed: int) -> dict[int, int]:
    """A season line that follows the record's position and overall (the same shape as the retail form)."""
    position = raw[0x35]
    rng = random.Random(seed)
    stats = {0: rng.choice((5, 8, 12, 16, 17))}
    if position == 0:
        stats[8] = max(0, (raw[0x4A] - 60) * 120 + rng.randint(-800, 800))
        stats[9] = rng.randint(4, 40)
        stats[10] = rng.randint(2, 20)
    elif position in (3, 8, 9):
        stats[13] = max(0, (raw[0x4C] - 55) * 40 + rng.randint(-250, 250))
    elif position == 7:
        stats[2] = max(0, (raw[0x4C] - 55) * 45 + rng.randint(-250, 250))
    elif position in (5, 6, 10, 11):
        stats[18] = max(0, (raw[0x49] - 60) * 3 + rng.randint(-20, 20))
    elif position in (15, 16):
        stats[19] = max(0, (raw[0x4F] - 60) + rng.randint(-4, 4))
    elif position == 4:
        stats[10] = rng.randint(0, 8)
    return stats


def stream_words(raw: bytes, stats: dict[int, int]) -> list[int]:
    slot = max(0, (raw[0x25] & 0x1F) - 1)
    return [(field << 16) | (slot << 23) | (value & 0xFFFF) for field, value in stats.items()] + [0x80000000]


# ------------------------------------------------------------------ Unicorn fixture
POOL, RECORDS, STREAMS, STACK, STOP = 0x4000000, 0x4010000, 0x4200000, 0x4FF8000, 0x4FF1000


class Machine:
    def __init__(self, payload: bytes):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.image = XbeImage(payload)
        end = max(section.end for section in self.image.sections)
        self.uc.mem_map(0x10000, ((end + 4095) & -4096) - 0x10000)
        self.uc.mem_write(0x10000, payload[:self.image.headers_size])
        for section in self.image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw + section.raw_size])
        for start, size in ((POOL, 0x100000), (STREAMS, 0x200000), (0x4F00000, 0x100000)):
            self.uc.mem_map(start, size)
        rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == patch.OWNER]
        self.code = next(a for a in rows if a["kind"] == "code")
        self.data = next(a for a in rows if a["kind"] == "data")
        self.labels = patch.code_for(payload, self.code["va"], self.data["va"])[1]
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)

    def u32(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def run(self, entry: int, stop: int = STOP, regs=None, stack: int | None = None):
        sp = STACK if stack is None else stack
        if stack is None:
            self.u32(sp, STOP)
        self.uc.reg_write(x86.UC_X86_REG_ESP, sp)
        for name, value in dict(EBX=0x11111111, ESI=0x22222222, EDI=0x33333333, EBP=0x44444444,
                                ECX=0, EDX=0, EFLAGS=0x202).items():
            self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
        for name, value in (regs or {}).items():
            self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
        self.uc.emu_start(entry, stop, count=5_000_000)
        if self.uc.reg_read(x86.UC_X86_REG_EIP) != stop:
            raise AssertionError(f"instruction budget exhausted at {self.uc.reg_read(x86.UC_X86_REG_EIP):#x}")
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def stub_rand(self, seed: int = 1) -> None:
        code = bytes.fromhex("8b01 89c2c1e20d31d0 89c2c1ea1131d0 89c2c1e20531d0 8901c3")
        self.uc.mem_write(0x48B50, code)
        self.u32(0xE5FCA0, 0x9E3779B9 ^ seed)

    def load_class(self, records: list[bytes]) -> None:
        for index, raw in enumerate(records):
            self.uc.mem_write(RECORDS + index * 0x54, raw)
            self.u32(self.data["va"] + patch.PTRS + index * 4, RECORDS + index * 0x54)
        self.u32(self.data["va"] + patch.C_CLASS_COUNT, len(records))

    def overall(self, index: int) -> int:
        return self.run(self.labels["overall100"], regs={"ECX": RECORDS + index * 0x54})

    def tag(self, index: int) -> tuple[int, int]:
        value = self.uc.mem_read(RECORDS + index * 0x54 + 0x53, 1)[0]
        return value & 1, value >> 6

    def run_class(self, records: list[bytes], seed: int):
        self.stub_rand(seed)
        self.load_class(records)
        sp = STACK
        self.u32(sp, 0x12345678)          # the push ecx FUN_002BE900 leaves below the return address
        self.u32(sp + 4, STOP)
        self.run(self.labels["class_finish"], stack=sp)
        return [self.tag(index) for index in range(len(records))]

    def load_pool(self, records: list[bytes], statistic: dict[int, dict[int, int]]) -> None:
        stream = STREAMS
        for index, raw in enumerate(records):
            record = bytearray(raw)
            words = stream_words(raw, statistic[index])
            for word in words:
                self.u32(stream, word)
                stream += 4
            struct.pack_into("<I", record, 0x2C, stream - 4 * len(words))
            self.uc.mem_write(RECORDS + index * 0x54, bytes(record))
        self.u32(POOL, len(records))
        self.u32(POOL + 4, RECORDS)
        self.u32(0xB72918, POOL)



def scores_for(machine: Machine, records: list[bytes]) -> tuple[list[int], dict[int, int]]:
    """The owner's class key computed from the real overall (for rank assertions)."""
    for index, raw in enumerate(records):
        machine.uc.mem_write(RECORDS + index * 0x54, raw)
    overall = [machine.overall(index) for index in range(len(records))]
    sums, counts = collections.Counter(), collections.Counter()
    for index, raw in enumerate(records):
        sums[raw[0x35]] += overall[index]
        counts[raw[0x35]] += 1
    means = {position: sums[position] * 100 // counts[position] for position in sums}
    def trunc_div(value, divisor):
        return value // divisor if value >= 0 else -((-value) // divisor)
    scores = [trunc_div((overall[index] * 100 - means[records[index][0x35]]) * patch.VALUE[records[index][0x35]],
                        10000) for index in range(len(records))]
    order = sorted(range(len(records)), key=lambda index: (-scores[index], index))
    return scores, {index: rank + 1 for rank, index in enumerate(order)}


class Tables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RETAIL.is_file():
            raise unittest.SkipTest("set NFL2K5_RETAIL_XBE to the retail default.xbe")
        cls.payload = _retail()

    def test_code_and_data_sizes(self):
        self.assertEqual(patch.CODE_SIZE, 0x820)
        self.assertLessEqual(len(__import__("mod_editor.core.nfl2k5_star_career_code",
                                            fromlist=["CODE"]).CODE), patch.K_POT)
        self.assertEqual(patch.DATA_SIZE, 4096)
        self.assertEqual(patch.REQUESTS, ((patch.OWNER, "code", 0x820, 16), (patch.OWNER, "data", 4096, 16)))

    def test_potential_table_from_the_retail_curves(self):
        table = patch.potential_table(self.payload)
        self.assertEqual(len(table), 17 * 16)
        self.assertEqual(table[0 * 16 + 0], 48)       # QB, profile 0, sub 0
        self.assertEqual(table[3 * 16 + 2], 116)      # WR, profile 0, sub 2
        self.assertEqual(table[0 * 16 + 6], 0)        # no such archetype
        self.assertGreater(max(table), 70)

    def test_constants_in_the_code_tables(self):
        code, _ = patch.code_for(self.payload, 0x3000000, 0x3008000)
        self.assertEqual(struct.unpack_from("<4i", code, patch.K_CONST), (90, 85, 97, 93))
        self.assertEqual(struct.unpack_from("<4i", code, patch.K_CONST2), (8, 33, 160, 70))
        self.assertEqual(struct.unpack_from("<i", code, patch.K_CONST3)[0], 75)
        self.assertEqual(list(code[patch.K_LIMITS:patch.K_LIMITS + 4]), [0, 2, 4, 7])
        self.assertEqual(struct.unpack_from("<f", code, patch.K_HUNDRED)[0], 100.0)
        self.assertEqual(struct.unpack_from("<17H", code, patch.K_VALUE), patch.VALUE)


@unittest.skipUnless(uc is not None and RETAIL.is_file(), "Unicorn and the pinned USA retail XBE required")
class RetailInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = _retail()

    def test_apply_readback_and_replay(self):
        self.assertEqual(patch.status(self.payload), "retail")
        installed, receipt = patch.apply(self.payload)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(patch.status(installed), "applied")
        self.assertEqual(space.status(installed), "applied")
        self.assertEqual(patch.apply(installed)[0], installed)
        code = next(a for a in space.layout(installed)["allocations"]
                    if a["owner"] == patch.OWNER and a["kind"] == "code")
        data = next(a for a in space.layout(installed)["allocations"]
                    if a["owner"] == patch.OWNER and a["kind"] == "data")
        image = XbeImage(installed)
        self.assertEqual(image.read(code["va"], patch.CODE_SIZE),
                         patch.code_for(installed, code["va"], data["va"])[0])
        self.assertEqual(image.read(data["va"], patch.DATA_SIZE), bytes(patch.DATA_SIZE))
        for name, va, before, size in patch.HOOKS:
            self.assertNotEqual(image.read(va, size)[:len(before)], before, name)

    def test_foreign_site_refused(self):
        payload = bytearray(self.payload)
        payload[0x24857A] ^= 0xFF
        with self.assertRaises(patch.StarCareerError):
            patch.apply(bytes(payload))


@unittest.skipUnless(uc is not None and RETAIL.is_file(), "Unicorn and the pinned USA retail XBE required")
class DraftClasses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = patch.apply(_retail())[0]
        cls.records = class_records()
        cls.machine = Machine(cls.payload)
        cls.scores, cls.rank = scores_for(cls.machine, cls.records)

    def test_ten_classes_star_counts_and_gems(self):
        totals = []
        for seed in range(10):
            tags = self.machine.run_class(self.records, seed)
            stars = [index for index, (star, _tier) in enumerate(tags) if star]
            tiers = collections.Counter(tags[index][1] for index in stars)
            ranks = sorted(self.rank[index] for index in stars)
            totals.append(len(stars))
            self.assertTrue(4 <= len(stars) <= 7, (seed, len(stars), ranks))
            self.assertTrue(3 <= sum(1 for rank in ranks if rank <= 32) <= 5, (seed, ranks))
            self.assertTrue(1 <= sum(1 for rank in ranks if rank > 32) <= 2, (seed, ranks))
            self.assertTrue(all(1 <= tier <= 2 for tier in tiers), (seed, tiers))
            self.assertLessEqual(tiers.get(2, 0), 1, (seed, tiers))
            for rank in ranks:
                if rank > 32:
                    self.assertTrue(33 <= rank <= 160, (seed, rank))
        self.assertEqual(len(totals), 10)

    def test_repeated_class_clears_the_previous_class(self):
        first = self.machine.run_class(self.records, 4)
        second = self.machine.run_class(self.records, 4)
        self.assertEqual(first, second)
        # every class starts from no star/tier: a second run cannot accumulate tags
        self.assertLessEqual(sum(1 for star, _tier in second if star), 7)

    def test_generator_epilogue_appends_the_record(self):
        machine = Machine(self.payload)
        machine.u32(machine.data["va"] + patch.C_CLASS_COUNT, 0)
        record = RECORDS
        # the retail generator epilogue: four saved registers, its 8-byte frame, then the return
        sp = STACK
        for offset, value in ((0, 0x11111111), (4, 0x22222222), (8, 0x33333333), (12, 0x44444444),
                              (16, 0), (20, 0), (24, STOP)):
            machine.u32(sp + offset, value)
        machine.run(machine.labels["class_tail"], stack=sp, regs={"ESI": record})
        self.assertEqual(struct.unpack("<I", machine.uc.mem_read(machine.data["va"] + patch.C_CLASS_COUNT, 4))[0], 1)
        self.assertEqual(struct.unpack("<I", machine.uc.mem_read(machine.data["va"] + patch.PTRS, 4))[0], record)


@unittest.skipUnless(uc is not None and RETAIL.is_file(), "Unicorn and the pinned USA retail XBE required")
class Offseasons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = patch.apply(_retail())[0]
        cls.records = pool_records()
        cls.machine = Machine(cls.payload)
        cls.stats = {index: stats_for(raw, 100 + index) for index, raw in enumerate(cls.records)}
        cls.machine.load_pool(cls.records, cls.stats)

    def _run_years(self, years: int):
        history = []
        for year in range(years):
            for index, raw in enumerate(self.records):
                stats = stats_for(raw, 1000 + index + year * 7919)
                words = stream_words(raw, stats)
                stream = STREAMS + (index * 16) * 4
                for word in words:
                    self.machine.u32(stream, word)
                    stream += 4
                record = bytearray(raw)
                struct.pack_into("<I", record, 0x2C, STREAMS + (index * 16) * 4)
                self.machine.uc.mem_write(RECORDS + index * 0x54, bytes(record))
            before = [self.machine.tag(index) for index in range(len(self.records))]
            self.machine.run(self.machine.labels["offseason"])
            after = [self.machine.tag(index) for index in range(len(self.records))]
            gained = sum(1 for old, new in zip(before, after) if not old[0] and new[0])
            lost = sum(1 for old, new in zip(before, after) if old[0] and not new[0])
            history.append((sum(1 for star, _tier in after if star), gained, lost, after))
        return history

    def test_five_offseasons_total_is_stable(self):
        history = self._run_years(5)
        start = history[0][0]
        for total, _gained, _lost, _after in history[1:]:
            self.assertGreaterEqual(total, max(1, int(start * 0.75)))
            self.assertLessEqual(total, int(start * 1.25))
        self.assertTrue(any(gained for _total, gained, _lost, _after in history))
        self.assertTrue(any(lost for _total, _gained, lost, _after in history))

    def test_existing_star_keeps_his_authored_tier(self):
        machine = Machine(self.payload)
        made = []
        for tier in (0, 1, 2, 3):
            _name, row = rr.RETAIL_CREATE_PLAYER_TEMPLATES[0]
            record = {field.name: 0 for field in rr.FIELDS}
            for slot, value in enumerate(row):
                record[rr.CREATE_PLAYER_TEMPLATE_SLOTS[slot]] = max(0, min(100, value))
            record.update(position=0, player_type=4, unknown_52=0, star_tag=1,
                          unknown_53_high=tier << 5, years_pro=6)
            made.append(rr.PlayerRecord(record).encode())
        machine.load_pool(made, {index: {0: 16, 8: 4000, 9: 30, 10: 10} for index in range(len(made))})
        machine.run(machine.labels["offseason"])
        self.assertEqual([machine.tag(index) for index in range(len(made))],
                         [(1, tier) for tier in (0, 1, 2, 3)])

    def test_veteran_quarterback_keeps_a_down_year_young_quarterback_loses(self):
        machine = Machine(self.payload)
        # Pocket QB template: 81 overall before any boost.  A 1,000-yard, 2-TD, 30-INT year scores 78.
        _name, values = rr.RETAIL_CREATE_PLAYER_TEMPLATES[0]
        record = {field.name: 0 for field in rr.FIELDS}
        for slot, value in enumerate(values):
            record[rr.CREATE_PLAYER_TEMPLATE_SLOTS[slot]] = max(0, min(100, value))
        record["position"] = 0
        record["player_type"] = 4
        record["unknown_52"] = 0
        record["star_tag"] = 1
        record["unknown_53_high"] = (1 << 5) | 1       # tier 1 and the star bit
        veteran = rr.PlayerRecord(dict(record, years_pro=8)).encode()
        young = rr.PlayerRecord(dict(record, years_pro=3)).encode()
        stats = {0: {0: 16, 8: 1000, 9: 2, 10: 30}, 1: {0: 16, 8: 1000, 9: 2, 10: 30}}
        machine.load_pool([veteran, young], stats)
        machine.run(machine.labels["offseason"])
        self.assertEqual(machine.tag(0)[0], 1, "a veteran QB keeps his star after one down year")
        self.assertEqual(machine.tag(1)[0], 0, "a young QB loses it")

    def test_gain_assigns_the_tier_band(self):
        machine = Machine(self.payload)
        chosen, values = [], []

        def make(template: int, boost: int) -> bytes:
            _name, row = rr.RETAIL_CREATE_PLAYER_TEMPLATES[template]
            record = {field.name: 0 for field in rr.FIELDS}
            for slot, value in enumerate(row):
                record[rr.CREATE_PLAYER_TEMPLATE_SLOTS[slot]] = max(0, min(100, value))
            for field in rr.RATING_BYTE_ORDER:
                if field not in rr.STYLE_RATINGS:
                    record[field] = max(0, min(100, record[field] + boost))
            record.update(position=template // rr.CREATE_PLAYER_TEMPLATE_VARIANTS, player_type=4,
                          unknown_52=0, star_tag=0, unknown_53_high=0, years_pro=3)
            return rr.PlayerRecord(record).encode()

        for low, high in ((91, 92), (94, 95), (98, 100)):
            found = None
            for template in (0, 10, 9, 16, 3, 6):
                for boost in range(0, 30):
                    raw = make(template, boost)
                    machine.load_pool([raw], {0: {}})
                    value = machine.overall(0)
                    if low <= value <= high:
                        found = (raw, value)
                        break
                if found:
                    break
            self.assertIsNotNone(found, f"no template reached overall {low}..{high}")
            chosen.append(found[0])
            values.append(found[1])
        machine.load_pool(chosen, {0: {}, 1: {}, 2: {}})
        machine.run(machine.labels["offseason"])
        expected = [3 if value >= 97 else 2 if value >= 93 else 1 for value in values]
        self.assertEqual([machine.tag(index)[1] for index in range(len(chosen))], expected)
        self.assertTrue(all(machine.tag(index)[0] for index in range(len(chosen))))


@unittest.skipUnless(uc is not None and RETAIL.is_file() and DISC.is_file(),
                     "Unicorn, the retail XBE and the released SOFTDRINK disc required")
class ReleasedRoster(unittest.TestCase):
    """The received v0.6.1 roster: five offseasons keep the league's star count near today's 250."""

    def test_the_released_executable_is_retail_for_this_owner(self):
        from mod_editor.core import mod_build as build
        self.assertEqual(patch.status(build._xbe_bytes(DISC)), "retail")

    def test_apply_on_the_released_executable(self):
        from mod_editor.core import mod_build as build
        xbe = build._xbe_bytes(DISC)
        self.assertEqual(patch.status(xbe), "retail")
        installed, receipt = patch.apply(xbe)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(patch.status(installed), "applied")
        self.assertEqual(space.status(installed), "applied")
        before = {(a["owner"], a["kind"]): a for a in space.layout(xbe)["allocations"]
                  if a["owner"] != patch.OWNER}
        after = {(a["owner"], a["kind"]): a for a in space.layout(installed)["allocations"]
                 if a["owner"] != patch.OWNER}
        self.assertEqual(after, before)

    def test_five_offseasons_on_the_released_roster(self):
        payload = patch.apply(_retail())[0]
        machine = Machine(payload)
        players = [player for player in rr.load_image(DISC).players if player.pool == "primary"]
        records = [player.record.encode() for player in players]
        start = sum(1 for raw in records if raw[0x53] & 1)
        self.assertTrue(240 <= start <= 260, start)
        streams = {}
        totals, gains, losses = [], [], []
        for year in range(5):
            stats = {index: stats_for(raw, 5000 + index + year * 7919) for index, raw in enumerate(records)}
            machine.load_pool(records, stats)
            before = [machine.tag(index) for index in range(len(records))]
            machine.run(machine.labels["offseason"])
            after = [machine.tag(index) for index in range(len(records))]
            totals.append(sum(1 for star, _tier in after if star))
            gains.append(sum(1 for old, new in zip(before, after) if not old[0] and new[0]))
            losses.append(sum(1 for old, new in zip(before, after) if old[0] and not new[0]))
        for total in totals:
            self.assertTrue(225 <= total <= 275, totals)
        self.assertGreater(gains[0], 0)
        self.assertGreater(losses[0], 0)
        # a stable league: no later year moves more than a sixth of today's stars
        self.assertTrue(all(value <= 45 for value in gains[1:]), gains)
        self.assertTrue(all(value <= 45 for value in losses[1:]), losses)


@unittest.skipUnless(uc is not None and RETAIL.is_file() and DISC.is_file(),
                     "Unicorn, the retail XBE and the released SOFTDRINK disc required")
class ReleasedClasses(unittest.TestCase):
    """Ten real draft classes: the released class loop, generator, roster and the installed owner."""

    def test_ten_real_classes(self):
        from mod_editor.core import mod_build as build
        from tools.b765.p1_timeline_proof import Machine as RolloverMachine
        xbe = patch.apply(build._xbe_bytes(DISC))[0]
        body = rr.load_image(DISC).to_body()
        rows = [a for a in space.layout(xbe)["allocations"] if a["owner"] == patch.OWNER]
        code_va = next(a for a in rows if a["kind"] == "code")["va"]
        data_va = next(a for a in rows if a["kind"] == "data")["va"]
        labels = patch.code_for(xbe, code_va, data_va)[1]
        rand_code = bytes.fromhex("8b01 89c2c1e20d31d0 89c2c1ea1131d0 89c2c1e20531d0 8901c3")

        def trunc_div(value, divisor):
            return value // divisor if value >= 0 else -((-value) // divisor)

        for seed in range(10):
            machine = RolloverMachine(xbe, body)
            machine.uc.mem_write(0x48B50, rand_code)
            machine.put(0xE5FCA0, 0x9E3779B9 ^ seed)
            machine.call(0x2BE940, ecx=380, budget=120_000_000)
            pointers = [machine.word(data_va + patch.PTRS + 4 * index) for index in range(380)]
            self.assertEqual(len(set(pointers)), 380, seed)
            records = [bytes(machine.uc.mem_read(pointer, 0x54)) for pointer in pointers]
            tags = [(raw[0x53] & 1, (raw[0x53] >> 6) & 3) for raw in records]
            stars = [index for index, (star, _tier) in enumerate(tags) if star]
            overall = [machine.call(labels["overall100"], ecx=pointer) for pointer in pointers]
            sums, counts = collections.Counter(), collections.Counter()
            for index, raw in enumerate(records):
                sums[raw[0x35]] += overall[index]
                counts[raw[0x35]] += 1
            means = {position: sums[position] * 100 // counts[position] for position in sums}
            scores = [trunc_div((overall[index] * 100 - means[records[index][0x35]])
                                * patch.VALUE[records[index][0x35]], 10000) for index in range(380)]
            order = sorted(range(380), key=lambda index: (-scores[index], index))
            rank = {index: position + 1 for position, index in enumerate(order)}
            ranks = sorted(rank[index] for index in stars)
            top = sum(1 for value in ranks if value <= 32)
            gems = [value for value in ranks if value > 32]
            self.assertTrue(4 <= len(stars) <= 7, (seed, ranks))
            self.assertTrue(3 <= top <= 5, (seed, ranks))
            self.assertTrue(1 <= len(gems) <= 2, (seed, ranks))
            self.assertTrue(all(33 <= value <= 170 for value in gems), (seed, ranks))
            self.assertTrue(all(1 <= tags[index][1] <= 2 for index in stars), (seed, tags))


if __name__ == "__main__":
    unittest.main()
