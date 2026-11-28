"""Booth lines for the 2026 calendar: the franchise Super Bowl and Berman's sign-offs (b81 sb-booth). No emulator.

Retail-free tests use synthetic directors (the pins are swapped for theirs) and a synthetic disc image. Retail tests
need the user-owned USA disc folder and are skipped without it: they check the pins, that the retail directors say the
stale lines at exactly the 18 sites (the failing-first case), that revisions 1 (40c10fb79) and 2 (298c1fb22) are the
pinned previous states and upgrade in place, and that the ``lines`` speech table resolves every retail key to the
recordings named in the site table and every generic key to its listed streams. A line the user replaced through the
commentary replacement keeps its retail key (review S2).
The release gate runs on a built disc named by ``NFL2K5_SB_BOOTH_DISC`` (or ``python3 -m
mod_editor.core.nfl2k5_super_bowl_booth check <disc>``). Nothing here is a gameplay result.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import build_steps  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_super_bowl_booth as b  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", ROOT / "extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"
HAVE_RETAIL = (RETAIL / "0").is_file()
GATE_DISC = os.environ.get("NFL2K5_SB_BOOTH_DISC", "")


# --------------------------------------------------------------------------------------------- fixtures
def synthetic_entry(outer: int, *, applied: bool = False, revision: int | None = None,
                    keep: frozenset[int] = frozenset()) -> bytes:
    """A director entry of the pinned size: the DRCT head and a say instruction at each site, zeros elsewhere.
    ``applied`` writes every generic key (except the ``keep`` keys); ``revision=r`` what revision r wrote (revision 2
    wrote 39796 where revision 3 writes 39800)."""
    out = bytearray(b.ENTRY_PINS[outer]["size"])
    out[:4] = b"DRCT"
    for site in b.sites_for(outer):
        at = b.WRAPPER + site.body_offset
        out[at] = b.SAY
        if site.retail in keep:
            key = site.retail
        elif applied or (revision is not None and site.revision <= revision):
            key = site.generic
        elif revision is not None and revision >= 2 and site.earlier:
            key = site.earlier[0]
        else:
            key = site.retail
        out[at + 1:at + 3] = key.to_bytes(2, "big")
    return bytes(out)


def synthetic_pins() -> dict[int, dict[str, object]]:
    pins = {}
    for outer in b.OUTERS:
        pins[outer] = {"size": b.ENTRY_PINS[outer]["size"],
                       "retail": hashlib.sha256(synthetic_entry(outer)).hexdigest(),
                       "applied": hashlib.sha256(synthetic_entry(outer, applied=True)).hexdigest()}
        if "previous" in b.ENTRY_PINS[outer]:
            pins[outer]["previous"] = tuple(hashlib.sha256(synthetic_entry(outer, revision=r)).hexdigest()
                                            for r in (1, 2))
    return pins


def synthetic_image(folder: Path, entries: dict[int, bytes] | None = None):
    """A synthetic disc image whose outer archive holds the three directors at their retail indexes."""
    from nfl2k5_xiso_fixture import SyntheticXiso
    entries = entries or {outer: synthetic_entry(outer) for outer in b.OUTERS}
    payloads = [(index, entries.get(index, bytes([index & 0xFF]) * 16)) for index in range(max(b.OUTERS) + 2)]
    size = 0x800 * len(payloads) + sum(len(raw) for raw in entries.values()) + 0x8000
    size += -size % 0x800
    return SyntheticXiso(folder, payloads, pack_sizes=(size,), pack_sectors=(64,))


def lines_table(outer3: bytes) -> bytes:
    """The ``lines`` SPCI body inside outer entry 3 (found by its wrapper and name)."""
    found = []
    at = outer3.find(b"SPCI")
    while at != -1:
        stored = struct.unpack_from("<I", outer3, at + 4)[0]
        body = outer3[at + 0x20:at + 0x20 + stored]
        if body[0x0C:0x10] == b"SPCI" and body[0x20:0x2A] == "lines".encode("utf-16-le"):
            found.append(body)
        at = outer3.find(b"SPCI", at + 4)
    assert len(found) == 1, len(found)
    return found[0]


def lines_streams(table: bytes, key: int) -> tuple[int, ...]:
    """Speaker variant 0's streams of a key, as FUN_0013CBA0 walks the table. First table (rows at 0x44): {keys
    (self-relative - 1), u16 count, u16 variant mask, u8 variants}; a key at position p of a row is stream (streams of
    the earlier rows) + p * variants. Second table (at the self-relative - 1 pointer at 0x34, 16-byte rows): {keys,
    take counts, u16 count, u16 mask, u8 variants}; the u16 after the keys is the key's first stream, then its takes."""
    first = 0
    for row in range(table[0x40]):
        at = 0x44 + 12 * row
        rel, count, mask, variants = struct.unpack_from("<IHHB", table, at)
        keys = struct.unpack_from(f"<{count}H", table, at + rel - 1)
        if mask & 1 and key in keys:
            return (first + keys.index(key) * variants,)
        first += count * variants
    rows = 0x34 + struct.unpack_from("<I", table, 0x34)[0] - 1
    for row in range(table[0x41]):
        at = rows + 16 * row
        krel, trel, count, mask, variants = struct.unpack_from("<IIHHB", table, at)
        keys = struct.unpack_from(f"<{count}H", table, at + krel - 1)
        if mask & 1 and key in keys:
            p = keys.index(key)
            start = struct.unpack_from("<H", table, at + krel - 1 + 2 * (count + p))[0]
            takes = table[at + 4 + trel - 1 + variants * p]
            return tuple(range(start, start + takes))
    return ()


# --------------------------------------------------------------------------------------------- retail-free
class SiteTable(unittest.TestCase):
    def test_eighteen_sites_low_byte_only(self):
        self.assertEqual(len(b.SITES), 18)
        self.assertEqual({outer: len(b.sites_for(outer)) for outer in b.OUTERS}, {4: 7, 1194: 4, 1195: 7})
        self.assertEqual(len({(s.outer, s.body_offset) for s in b.SITES}), 18)
        self.assertEqual(sum(1 for s in b.SITES if s.revision == 2), 2)
        self.assertEqual([(s.child, s.retail, s.generic, s.earlier) for s in b.SITES if s.revision == 3],
                         [(68, 39799, 39800, (39796,)), (69, 39799, 39800, (39796,))])   # review N1
        for site in b.SITES:
            self.assertIn(site.generic, b.GENERIC_LINES)
            self.assertNotIn(site.generic, b.STALE_KEYS)
            self.assertEqual(site.retail >> 8, site.generic >> 8, site)      # one byte per site
        self.assertEqual(sorted(b.STALE_KEYS), [2956, 2957, 2958, 14047, 14048, 14049, 14050, 39795, 39797, 39799,
                                                39811, 39812, 39813])
        self.assertEqual(b.GENERIC_LINES, {14051: (1483,), 2959: (1051,), 39815: (2740,), 39796: (9440, 9441, 9442),
                                           39798: (9445, 9446), 39800: (2731,)})
        self.assertEqual(set(b.RETAIL_STREAMS), set(b.STALE_KEYS))
        self.assertEqual(b.kept_keys({9439, 5}), frozenset({39795}))
        self.assertEqual(b.WITNESSED, {"super_bowl_welcome": True, "super_bowl_coin_toss": True, "sign_offs": False})

    def test_patch_entry(self):
        with mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            for outer in b.OUTERS:
                retail = synthetic_entry(outer)
                self.assertEqual(len(b.stale_lines(outer, retail)), len(b.sites_for(outer)))      # failing first
                patched, receipt = b.patch_entry(outer, retail)
                self.assertEqual(patched, synthetic_entry(outer, applied=True))
                self.assertEqual(receipt["changed_bytes"], len(b.sites_for(outer)))
                self.assertEqual(b.stale_lines(outer, patched), [])
                self.assertEqual(b.entry_state(outer, patched), "applied")
                again, receipt = b.patch_entry(outer, patched)                                     # idempotent
                self.assertEqual((again, receipt["changed_bytes"], receipt["already_applied"]), (patched, 0, True))

    def test_revision_1_upgrades_in_place(self):
        with mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            previous = synthetic_entry(1195, revision=1)
            self.assertEqual(b.entry_state(1195, previous), "previous")
            self.assertEqual(len(b.stale_lines(1195, previous)), 4)                           # the anniversary lines
            patched, receipt = b.patch_entry(1195, previous)
            self.assertEqual(patched, synthetic_entry(1195, applied=True))
            self.assertEqual((receipt["from"], receipt["changed_bytes"]), ("previous", 4))
            # revision 1 left outer 4 and 1194 applied already: nothing more to write there
            for outer in (4, 1194):
                self.assertEqual(synthetic_entry(outer, revision=1), synthetic_entry(outer, applied=True))

    def test_revision_2_upgrades_in_place(self):
        """Revision 2 said the regular-season sign-off (39796) for the AFC wild card; revision 3 says 39800."""
        with mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            previous = synthetic_entry(1195, revision=2)
            self.assertEqual(b.entry_state(1195, previous), "previous")
            self.assertEqual(b.stale_lines(1195, previous), [])
            patched, receipt = b.patch_entry(1195, previous)
            self.assertEqual(patched, synthetic_entry(1195, applied=True))
            self.assertEqual((receipt["from"], receipt["changed_bytes"]), ("previous", 2))

    def test_the_users_own_recordings_keep_their_lines(self):
        """Review S2: a site whose retail line the user replaced keeps (or gets back) its retail key."""
        keep = b.kept_keys({1479, 9443})                                   # 14047 (Jacksonville), 39797 take 1
        self.assertEqual(keep, frozenset({14047, 39797}))
        with mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            for outer in b.OUTERS:
                want = synthetic_entry(outer, applied=True, keep=keep)
                patched, receipt = b.patch_entry(outer, synthetic_entry(outer), keep)
                self.assertEqual(patched, want)
                kept = sorted({s.retail for s in b.sites_for(outer)} & keep)
                self.assertEqual(receipt["kept_for_user_recordings"], kept)
                self.assertEqual(b.entry_state(outer, patched), "partial" if kept else "applied")
                self.assertEqual(b.stale_lines(outer, patched, keep), [])
                self.assertEqual(len(b.stale_lines(outer, patched)), sum(1 for s in b.sites_for(outer)
                                                                         if s.retail in keep))
                back, receipt = b.patch_entry(outer, synthetic_entry(outer, applied=True), keep)   # restores retail
                self.assertEqual(back, want)
                full, _ = b.patch_entry(outer, patched)                                            # and back again
                self.assertEqual(full, synthetic_entry(outer, applied=True))
            foreign = bytearray(synthetic_entry(4, applied=True, keep=keep))
            foreign[b.WRAPPER + b.sites_for(4)[0].body_offset + 2] ^= 0x40                     # a key never written
            self.assertEqual(b.entry_state(4, bytes(foreign)), "foreign")

    def test_refuses_a_foreign_director(self):
        with mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            for outer in b.OUTERS:
                foreign = bytearray(synthetic_entry(outer))
                foreign[-1] ^= 1
                self.assertEqual(b.entry_state(outer, bytes(foreign)), "foreign")
                with self.assertRaises(b.SuperBowlBoothError):
                    b.patch_entry(outer, bytes(foreign))
                self.assertEqual(b.entry_state(outer, synthetic_entry(outer)[:-1]), "foreign")

    def test_image_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            image = synthetic_image(Path(tmp))
            before = image.path.read_bytes()
            self.assertEqual(b.image_state(image.path), "retail")
            self.assertEqual(len(b.check_image(image.path)), 18)                                   # failing first
            receipt = b.apply_to_image(image.path)
            self.assertEqual((receipt["state"], receipt["changed_bytes"]), ("applied", 18))
            self.assertEqual(b.image_state(image.path), "applied")
            self.assertEqual(b.check_image(image.path), [])
            after = image.path.read_bytes()
            self.assertEqual(len(before), len(after))
            self.assertEqual(sum(1 for x, y in zip(before, after) if x != y), 18)
            self.assertEqual(b.apply_to_image(image.path)["changed_bytes"], 0)                     # idempotent
            self.assertEqual(image.path.read_bytes(), after)
            receipt = b.apply_to_image(image.path, keep_streams={1480})                             # user's 14048
            self.assertEqual((receipt["changed_bytes"], receipt["kept_for_user_recordings"]), (2, [14048]))
            self.assertEqual(b.image_state(image.path), "partial")
            self.assertEqual(b.check_image(image.path, {1480}), [])
            self.assertEqual(len(b.check_image(image.path)), 2)

    def test_image_with_a_foreign_director_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(b.ENTRY_PINS, synthetic_pins()):
            entries = {outer: synthetic_entry(outer) for outer in b.OUTERS}
            entries[1195] = entries[1195][:-1] + b"\x01"
            image = synthetic_image(Path(tmp), entries)
            before = image.path.read_bytes()
            with self.assertRaises(b.SuperBowlBoothError):
                b.apply_to_image(image.path)
            self.assertEqual(image.path.read_bytes(), before, "no director may change when one is foreign")
            self.assertEqual(b.image_state(image.path), "foreign")


class BuildWiring(unittest.TestCase):
    def test_step_is_an_optional_step_of_the_2026_season(self):
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        call = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "super_bowl_booth")' in line]
        self.assertEqual(len(call), 1)
        gate = max(i for i in range(call[0]) if re.match(r"    if \S", lines[i]))
        self.assertEqual(lines[gate].strip(), "if plan.season_2026 and tt.is_disc_image(target):")
        hosts = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "super_bowl_hosts")' in line]
        self.assertTrue(gate < hosts[0] < call[0], "the booth lines run after the Super Bowl hosts, in the same gate")
        self.assertIn("super_bowl_booth", mod_build.OPTIONAL_STEPS)
        self.assertIn("super_bowl_booth", build_steps.STEP_LABELS)
        self.assertTrue(build_steps.KEPT["super_bowl_booth"].startswith("Your "))


# --------------------------------------------------------------------------------------------- retail
@unittest.skipUnless(HAVE_RETAIL, "needs the user-owned USA disc folder")
class Retail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = b.read_entries(RETAIL)
        from nfl2k5_playbook_position_recode import OuterImage
        with OuterImage(RETAIL) as archive:
            cls.table = lines_table(archive.read_entry(3))

    def test_retail_pins_and_the_eighteen_sites(self):
        self.assertEqual(b.image_state(RETAIL), "retail")
        hits = b.check_image(RETAIL)
        self.assertEqual(sorted((h["outer"], int(h["body_offset"], 16)) for h in hits),
                         sorted((s.outer, s.body_offset) for s in b.SITES))
        for site in b.SITES:
            at = b.WRAPPER + site.body_offset
            self.assertEqual(self.entries[site.outer][at:at + 3], bytes([b.SAY]) + site.retail.to_bytes(2, "big"))

    def test_patch_reaches_the_applied_pins(self):
        changed = 0
        for outer in b.OUTERS:
            patched, receipt = b.patch_entry(outer, self.entries[outer])
            self.assertEqual(hashlib.sha256(patched).hexdigest(), b.ENTRY_PINS[outer]["applied"])
            self.assertEqual(b.stale_lines(outer, patched), [])
            changed += receipt["changed_bytes"]
        self.assertEqual(changed, 18)

    def test_revision_1_is_the_pinned_previous_state(self):
        """40c10fb79 wrote only the Super Bowl lines; its outer 1195 must be recognised and upgraded, not refused."""
        out = bytearray(self.entries[1195])
        for site in b.sites_for(1195):
            if site.revision == 1:
                at = b.WRAPPER + site.body_offset + 1
                out[at:at + 2] = site.generic.to_bytes(2, "big")
        self.assertEqual(hashlib.sha256(out).hexdigest(), b.ENTRY_PINS[1195]["previous"][0])
        patched, receipt = b.patch_entry(1195, bytes(out))
        self.assertEqual(hashlib.sha256(patched).hexdigest(), b.ENTRY_PINS[1195]["applied"])
        self.assertEqual(receipt["changed_bytes"], 4)

    def test_revision_2_is_the_pinned_previous_state(self):
        """298c1fb22 pointed 39799 at 39796; its outer 1195 upgrades to 39800 (2 bytes)."""
        out = bytearray(self.entries[1195])
        for site in b.sites_for(1195):
            at = b.WRAPPER + site.body_offset + 1
            out[at:at + 2] = (site.earlier[0] if site.earlier else site.generic).to_bytes(2, "big")
        self.assertEqual(hashlib.sha256(out).hexdigest(), b.ENTRY_PINS[1195]["previous"][1])
        patched, receipt = b.patch_entry(1195, bytes(out))
        self.assertEqual(hashlib.sha256(patched).hexdigest(), b.ENTRY_PINS[1195]["applied"])
        self.assertEqual(receipt["changed_bytes"], 2)

    def test_the_speech_table_resolves_every_key(self):
        for site in b.SITES:
            self.assertEqual(lines_streams(self.table, site.retail)[0], site.line, site)
        for key, lines in b.RETAIL_STREAMS.items():
            self.assertEqual(lines_streams(self.table, key), lines, key)
        for key, lines in b.GENERIC_LINES.items():
            self.assertEqual(lines_streams(self.table, key), lines, key)
        self.assertEqual(lines_streams(self.table, 2950), (1042,))   # "As always, I'm with Peter O'Keeffe ..." follows


@unittest.skipUnless(GATE_DISC, "set NFL2K5_SB_BOOTH_DISC to a built 2026-season disc for the release gate")
class ReleaseGate(unittest.TestCase):
    def test_no_stale_super_bowl_or_sign_off_line_is_said(self):
        self.assertEqual(b.check_image(GATE_DISC), [])
        self.assertEqual(b.image_state(GATE_DISC), "applied")


if __name__ == "__main__":
    unittest.main()
