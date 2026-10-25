"""b778 ai8: the CPU does not call runs on third and long (holtbolt, 10/24).

The compiled books carry run plays in every formation and the retail play selector 0x2096A0 blends run and pass
scores with one run weight, without a distance term. These tests pin the two source fixes:

* ``nfl2k5_cpu_third_down``: a late owner that lowers the native run weight to 0.05 on third and 7+; a third and
  20+ in the fourth quarter, inside five minutes, with the offense leading keeps the retail weight.
* ``nfl2k5_coach_ai``: the automatic profile defers third and 3+ to the native selector, so the 20-pool playback
  (which cannot tell 3rd and long from 1st/2nd and long) does not call the rings there. Third and 1-2 keeps the
  short-yardage rings (the QB sneaks).

Engine checks run everywhere; the native checks need the retail XBE (and the retail ISO for its book) and Unicorn.
"""
from pathlib import Path
import os
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_third_down as third
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_play_scoring as scoring
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn  # noqa: F401
    from pb.scoring_selectors import World
except ImportError:      # pragma: no cover
    World = None

EXTRACT = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
XBE = EXTRACT / "ESPN NFL 2K5 (USA)/default.xbe"
ISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
HAVE_NATIVE = World is not None and XBE.is_file() and ISO.is_file()


class Sampler(World):
    def sample(self, seed):
        rng = random.Random(seed)
        self.put(0xE5FCA0, 54)
        self.put(0xE5FCA4, 23)
        for index in range(110):
            self.put(0xE5FCA8 + 4 * index, rng.getrandbits(32))
        self.fput(0xBF1244, rng.random())
        self.fput(0xBF1484, rng.random())
        for address in (0xBF16FC, 0xBF1700):
            self.put(address, 0)
        out = 0x3000000 + 0x19100
        self.m.mem_write(out, bytes(16))
        self.call(0x20B670, ecx=0x3020000, edx=out)
        return struct.unpack("<4I", self.m.mem_read(out, 16))


def retail_book():
    from nfl2k5_playbook_position_recode import OuterImage
    from pb.verify_league import BOOK_ENTRIES
    with OuterImage(ISO) as image:
        return image.read_entry(BOOK_ENTRIES["TEN"])


def calls(machine, *, down, distance, quarter=1, seconds=300, margin=0, samples=40, seed=17):
    """Count run/pass native offensive calls for one situation."""
    run = passed = 0
    for i in range(samples):
        machine.configure(down=down, distance=distance, yard=50, quarter=quarter, seconds=seconds, margin=margin)
        try:
            _category, formation, play, _coverage = machine.sample(seed + i)
        except Exception:
            continue
        if not formation or not play:
            continue
        book = machine.book
        formation_index = (formation - scoring.BOOK - ip.FORMATION_BASE) // ip.FORMATION_SIZE
        play_index = (play - scoring.BOOK - ip.PLAY_BASE) // 96
        if not (0 <= formation_index < len(book.formations) and 0 <= play_index < len(book.plays)):
            continue
        name = book.formations[formation_index].name.strip()
        if name in ("Clock", "Hail Mary", "Prevent"):
            continue
        if book.plays[play_index].flags_or_id & 0x8000:
            run += 1
        else:
            passed += 1
    return run, passed


class Engine(unittest.TestCase):
    def test_template_and_site(self):
        self.assertEqual(third.OWNER, "nfl2k5_cpu_third_down")
        self.assertEqual((third.CODE_SIZE, third.REQUESTS), (192, ((third.OWNER, "code", 192, 16),)))
        self.assertLessEqual(len(third.CODE), third.CODE_SIZE)
        self.assertEqual(third.SITE_BEFORE.hex(), "e8fdaeffff")
        for va in (0x14DA000, 0x1500000):
            code = third.code_for(va)
            self.assertEqual(len(code), third.CODE_SIZE)
            self.assertEqual(code[third.RELOCATIONS[0][0]:third.RELOCATIONS[0][0] + 4],
                             struct.pack("<i", third.CALL_VA - (va + 0x8E + 4)))
            self.assertEqual(code[third.RELOCATIONS[1][0]:third.RELOCATIONS[1][0] + 4],
                             struct.pack("<i", third.BACK_VA - (va + 0x93 + 4)))
            self.assertEqual(third.sites(va)[0][3], b"\xe9" + struct.pack("<i", va - (third.SITE_VA + 5)))

    def test_apply_recognizes_and_replays(self):
        base = retail_xbe()
        self.assertEqual(third.status(base), "retail")
        patched, receipt = third.apply(base)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(third.status(patched), "applied")
        image = XbeImage(patched)
        row = third.allocations(patched)
        self.assertEqual((row["kind"], row["size"]), ("code", 192))
        self.assertEqual(image.read(third.SITE_VA, 5), third.sites(row["va"])[0][3])
        self.assertEqual(image.read(row["va"], 192), third.code_for(row["va"]))
        self.assertEqual(third.apply(patched)[0], patched)
        self.assertNotEqual(third.status(base + b"\0"), "applied")


@unittest.skipUnless(HAVE_NATIVE, "Unicorn and the retail XBE/ISO are required")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = retail_book()
        pack = packs.load_pack(ROOT / "data/playbooks/softdrink_ten_modern.2k5book")
        cls.book = packs.apply_pack_to_resource(retail, pack, xbe=XBE.read_bytes()).replacement
        cls.base = Sampler(XBE.read_bytes())
        cls.base.load(cls.book)
        allocated, _ = space.apply(retail_xbe(), third.REQUESTS, scaleout=True)
        patched, _ = third.apply(allocated)
        cls.patched = Sampler(patched)
        cls.patched.load(cls.book)

    def test_third_and_long_runs_are_gone(self):
        before, _ = calls(self.base, down=3, distance=10, samples=60)
        after, _ = calls(self.patched, down=3, distance=10, samples=60)
        self.assertGreater(before, 0)
        self.assertLessEqual(after, 1)

    def test_third_and_short_is_unchanged(self):
        self.assertEqual(calls(self.base, down=3, distance=2), calls(self.patched, down=3, distance=2))

    def test_late_lead_third_and_twenty_keeps_the_situational_run(self):
        # The exception leaves the retail run weight alone: the call mix must be identical before and after.
        for distance in (20, 25):
            self.assertEqual(calls(self.base, down=3, distance=distance, quarter=4, seconds=60, margin=7),
                             calls(self.patched, down=3, distance=distance, quarter=4, seconds=60, margin=7))


if __name__ == "__main__":
    unittest.main()
