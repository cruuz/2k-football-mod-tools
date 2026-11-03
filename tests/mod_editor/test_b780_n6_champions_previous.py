"""b780 n6: a beta-79 / SOFTDRINK 2K28 v0.8 honors + champions install reads "previous" and is upgraded in place.

beta-80 changed the champions runtime (j4-history: the Player Card game log page goes through the champions page cycle),
so the champions code a v0.8 executable carries no longer matched ``code_for`` and read "foreign champions code". The
honors owner links four card calls into the champions labels, so it read foreign too; defensive_try tolerates the honors
history-fold edit only while honors validates, and the CPU scrambles, QB reads and passer IQ owners pin defensive_try,
so an incremental build or an inspect on a v0.8 disc refused them all ("Foreign CPU scramble neighbor").

The fix keeps the beta-79 champions runtime frozen (``nfl2k5_champions_code_b779``): both owners read that exact install
as "previous" and ``nfl2k5_honors.apply`` rewrites the two code allocations in place (same addresses, same sizes, same
nine sites). Static checks run everywhere; the retail cases need the retail USA ``default.xbe``; the release cases need
``NFL2K5_V08_XBE`` (the default.xbe of the released v0.8 disc).
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_champions_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_champions_code_b779 as runtime_b779  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import _retail  # noqa: E402

# sha256 of the beta-79 champions template (e8c1de3a8's generated nfl2k5_champions_code.CODE, 5,516 bytes)
B779_CODE_SHA256 = "184dcdeac19b8589c5ad229eaa3a7507f9633593c6d3841d93c5c7df4f23be03"
V08_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"
CHAMPION_LINKS = ("champions_ratings", "champions_bio", "champions_flip", "champions_enter")


def v08_xbe() -> bytes:
    path = os.environ.get("NFL2K5_V08_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_V08_XBE (the default.xbe of the released v0.8 disc) is not set")
    with Path(path).open("rb") as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    if hashlib.sha256(payload).hexdigest() != V08_SHA256:
        raise unittest.SkipTest("NFL2K5_V08_XBE does not match the v0.8 release pin")
    return payload


def as_previous(current: bytes) -> bytes:
    """A current honors + champions install turned back into the exact beta-79 one: both code allocations get the
    beta-79 bodies (the allocator's exact-body path, run backwards), every other byte is resealed the same way."""

    found, champs = honors.allocations(current), champions.allocations(current)
    code_va, data_va, champs_va = found["code"]["va"], found["data"]["va"], champs["code"]["va"]
    out, _ = space.install_code(current, honors.OWNER,
                                honors.code_for(code_va, data_va, champs_va, champions_previous=True),
                                previous=honors.code_for(code_va, data_va, champs_va))
    out, _ = space.install_code(out, champions.OWNER, champions.code_for(champs_va, previous=True),
                                previous=champions.code_for(champs_va))
    return out


def write_code(payload: bytes, owner_va: int, size: int, body: bytes) -> bytes:
    """Overwrite raw owner bytes without resealing (a foreign edit)."""

    buf = bytearray(payload)
    at = XbeImage(payload).offset(owner_va, size)
    buf[at:at + size] = body
    return bytes(buf)


class StaticTests(unittest.TestCase):
    """Run everywhere."""

    def test_the_frozen_runtime_is_the_beta79_one(self):
        self.assertEqual(hashlib.sha256(runtime_b779.CODE).hexdigest(), B779_CODE_SHA256)
        self.assertEqual(len(runtime_b779.CODE), 5516)
        self.assertLessEqual(len(runtime_b779.CODE), champions.CODE_SIZE)
        self.assertEqual({symbol for _o, _k, symbol, _v in runtime_b779.RELOCATIONS}, {"code"})
        self.assertNotEqual(runtime_b779.CODE, runtime.CODE)

    def test_both_revisions_share_the_size_and_the_two_sites(self):
        for code_va in (0x14DA000, 0x14ED560):
            self.assertEqual(champions.sites(code_va, previous=True), champions.sites(code_va))
            self.assertEqual(len(champions.code_for(code_va, previous=True)), champions.CODE_SIZE)
            self.assertNotEqual(champions.code_for(code_va, previous=True), champions.code_for(code_va))
            for entry in ("champions_advance", "champions_awards"):
                self.assertEqual(champions.labels(code_va, previous=True)[entry], champions.labels(code_va)[entry])

    def test_the_honors_code_differs_only_in_its_four_champions_links(self):
        code_va, data_va, champs_va = 0x14E01B0, 0x14D9FF0, 0x14ED560
        now = honors.code_for(code_va, data_va, champs_va)
        then = honors.code_for(code_va, data_va, champs_va, champions_previous=True)
        links = [off for off, _kind, symbol, _v in honors.runtime.RELOCATIONS if symbol.startswith("champ_")]
        self.assertTrue(links)
        changed = {i for i, (a, b) in enumerate(zip(now, then)) if a != b}
        self.assertTrue(changed)
        self.assertLessEqual(changed, {off + i for off in links for i in range(4)})
        old, new = champions.labels(champs_va, previous=True), champions.labels(champs_va)
        absolute = {struct.unpack_from("<I", then, off)[0] for off, kind, symbol, _v in honors.runtime.RELOCATIONS
                    if kind == 1 and symbol.startswith("champ_")}
        self.assertEqual(absolute, {old[name] for name in CHAMPION_LINKS})
        self.assertTrue(all(old[name] != new[name] for name in CHAMPION_LINKS))
        # no champions owner: no links, so the two revisions are the same bytes
        self.assertEqual(honors.code_for(code_va, data_va), honors.code_for(code_va, data_va, champions_previous=True))


class RetailUpgradeTests(unittest.TestCase):
    """The retail USA executable with the honors option: this release's install and the beta-79 one."""

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        if cls.retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.current, _ = honors.apply(cls.retail)
        cls.previous = as_previous(cls.current)
        cls.upgraded, cls.receipt = honors.apply(cls.previous)

    def test_a_beta79_install_reads_previous(self):
        self.assertEqual(champions.status(self.previous), "previous")
        self.assertEqual(honors.status(self.previous), "previous")
        self.assertEqual(space.status(self.previous), "applied")
        settings = honors.read_settings(self.previous)
        self.assertEqual((settings["status"], settings["honors_page"], settings["champions"], settings["needs_update"]),
                         ("previous", True, True, True))
        self.assertEqual(settings["revision"], "beta-79")
        self.assertEqual(len(honors.fold_site_edit(self.previous)), 1)   # defensive_try still tolerates the fold hook

    def test_the_upgrade_is_byte_identical_to_a_fresh_install(self):
        self.assertEqual(self.upgraded, self.current)
        self.assertEqual(honors.status(self.upgraded), "applied")
        self.assertEqual(champions.status(self.upgraded), "applied")
        self.assertEqual(self.receipt["upgraded_from"], "beta-79")
        self.assertFalse(self.receipt["already_applied"])
        self.assertEqual(self.receipt["champions"]["upgraded_from"], "beta-79")
        self.assertTrue(self.receipt["code_install"]["upgraded_from_previous"])
        again, receipt = honors.apply(self.upgraded)
        self.assertEqual(again, self.upgraded)
        self.assertTrue(receipt["already_applied"])

    def test_the_upgrade_moves_nothing(self):
        self.assertEqual(space.layout(self.previous)["allocations"], space.layout(self.upgraded)["allocations"])
        self.assertEqual(len(self.previous), len(self.upgraded))
        retail_image, image = XbeImage(self.previous), XbeImage(self.upgraded)
        for label, va, _before, after in honors.sites(honors.allocations(self.upgraded)["code"]["va"]):
            self.assertEqual(retail_image.read(va, len(after)), image.read(va, len(after)), label)

    def test_half_upgraded_or_changed_installs_stay_foreign(self):
        found, champs = honors.allocations(self.previous), champions.allocations(self.previous)
        code_va, data_va, champs_va = found["code"]["va"], found["data"]["va"], champs["code"]["va"]
        # honors relinked to this release, champions still beta-79
        half, _ = space.install_code(self.previous, honors.OWNER, honors.code_for(code_va, data_va, champs_va),
                                     previous=honors.code_for(code_va, data_va, champs_va, champions_previous=True))
        self.assertEqual(champions.status(half), "previous")
        self.assertEqual(honors.status(half), "foreign")
        with self.assertRaises(ValueError):
            honors.apply(half)
        # champions upgraded, honors still linked to the beta-79 labels
        other, _ = space.install_code(self.previous, champions.OWNER, champions.code_for(champs_va),
                                      previous=champions.code_for(champs_va, previous=True))
        self.assertEqual(champions.status(other), "applied")
        self.assertEqual(honors.status(other), "foreign")
        # one byte of the beta-79 champions body changed (resealed, so only the body check can refuse it)
        body = bytearray(champions.code_for(champs_va, previous=True))
        body[100] ^= 0x01
        changed, _ = space.install_code(self.current, champions.OWNER, bytes(body), previous=champions.code_for(champs_va))
        self.assertEqual(champions.status(changed), "foreign")
        self.assertEqual(honors.status(changed), "foreign")
        self.assertEqual(honors.fold_site_edit(changed), [])
        # an unsealed rewrite is foreign at the allocator already
        raw = write_code(self.current, champs_va, champions.CODE_SIZE, champions.code_for(champs_va, previous=True))
        self.assertEqual(champions.status(raw), "foreign")

    def test_the_allocator_upgrade_path_takes_only_the_named_previous_body(self):
        champs_va = champions.allocations(self.current)["code"]["va"]
        new, old = champions.code_for(champs_va), champions.code_for(champs_va, previous=True)
        with self.assertRaises(ValueError):          # the allocation holds neither padding, `new`, nor this `previous`
            space.install_code(self.current, champions.OWNER, old, previous=b"\x90" * len(old))
        with self.assertRaises(ValueError):          # an upgrade keeps the size
            space.install_code(self.previous, champions.OWNER, new, previous=old[:-16])
        with self.assertRaises(ValueError):          # without `previous` a filled allocation is still immutable
            space.install_code(self.previous, champions.OWNER, new)
        same, receipt = space.install_code(self.current, champions.OWNER, new, previous=old)
        self.assertEqual(same, self.current)
        self.assertNotIn("upgraded_from_previous", receipt)

    def test_the_build_path_upgrades_a_selected_previous_install_and_refuses_to_drop_it(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        upgraded, receipt = tt._apply_all(self.previous, None, False, honors_page=True)
        self.assertEqual(honors.status(upgraded), "applied")
        self.assertEqual(receipt["honors_patch"]["upgraded_from"], "beta-79")
        with self.assertRaisesRegex(ValueError, "is installed; rebuild from a verified base"):
            tt._apply_all(self.previous, None, False)


class ReleaseV08Tests(unittest.TestCase):
    """The released v0.8 executable: the chain from champions to the CPU passer reads as it did in beta-79."""

    @classmethod
    def setUpClass(cls):
        cls.v08 = v08_xbe()
        cls.upgraded, cls.receipt = honors.apply(cls.v08)

    def test_the_release_reads_previous_and_its_dependants_applied(self):
        from mod_editor.core import (nfl2k5_cpu_qb_reads as reads, nfl2k5_cpu_scrambles as scrambles,
                                     nfl2k5_defensive_try as defensive_try)
        self.assertEqual(champions.status(self.v08), "previous")
        self.assertEqual(honors.status(self.v08), "previous")
        for module in (defensive_try, scrambles, reads):
            self.assertEqual(module.status(self.v08), "applied", module.__name__)

    def test_the_upgrade_rewrites_only_the_two_code_allocations_and_the_seals(self):
        self.assertEqual(honors.status(self.upgraded), "applied")
        self.assertEqual(champions.status(self.upgraded), "applied")
        self.assertEqual(self.receipt["upgraded_from"], "beta-79")
        self.assertEqual(len(self.upgraded), len(self.v08))
        before = space.layout(self.v08)["allocations"]
        self.assertEqual(before, space.layout(self.upgraded)["allocations"])
        old, new = XbeImage(self.v08), XbeImage(self.upgraded)
        rewritten = {(honors.OWNER, "code"), (champions.OWNER, "code")}
        for row in before:
            if row["owner"] == space.DIRECTORY_OWNER:
                continue
            same = old.read(row["va"], row["size"]) == new.read(row["va"], row["size"])
            self.assertEqual(same, (row["owner"], row["kind"]) not in rewritten, (row["owner"], row["kind"]))
        champs_va = champions.allocations(self.v08)["code"]["va"]
        self.assertEqual(old.read(champs_va, champions.CODE_SIZE), champions.code_for(champs_va, previous=True))
        self.assertEqual(new.read(champs_va, champions.CODE_SIZE), champions.code_for(champs_va))
        again, receipt = honors.apply(self.upgraded)
        self.assertEqual(again, self.upgraded)
        self.assertTrue(receipt["already_applied"])

    def test_every_other_installed_owner_reads_the_same_after_the_upgrade(self):
        import importlib
        names = [owner for owner in space.LATE_OWNERS if owner not in (honors.OWNER, champions.OWNER)]
        names += ["nfl2k5_defensive_try", "nfl2k5_cpu_scrambles", "nfl2k5_cpu_money_downs", "nfl2k5_k128",
                  "nfl2k5_my_career", "nfl2k5_espn25_more_moments", "nfl2k5_abilities_runtime", "nfl2k5_coverage_trail"]
        checked = 0
        for name in dict.fromkeys(names):
            try:
                module = importlib.import_module("mod_editor.core." + name)
            except ImportError:
                continue
            if not callable(getattr(module, "status", None)):
                continue
            with self.subTest(owner=name):
                self.assertEqual(module.status(self.upgraded), module.status(self.v08))
                checked += 1
        self.assertGreater(checked, 30)

    def test_the_cpu_passer_takes_the_release_and_the_upgraded_release(self):
        from mod_editor.core import nfl2k5_cpu_passer_iq as passer
        for base in (self.v08, self.upgraded):
            final, _ = passer.apply(base)
            self.assertEqual(passer.status(final), "applied")
            self.assertEqual(honors.status(final), honors.status(base))



# ---------------------------------------------------------------------------------------------------------------
# The same "previous" path for the other installed owners beta-80 changed in place: the camera (v7 -> v8, the punt
# snap eye) and K128 (the 128 MB stop screen's text).

class CameraAndK128RetailTests(unittest.TestCase):
    """Retail installs of this release turned back into the beta-79 bytes, then upgraded again."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_camera as camera, nfl2k5_k128 as k128
        cls.camera, cls.k128 = camera, k128
        cls.retail = _retail()
        if cls.retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.cam_now, _ = camera.apply(cls.retail)
        va = camera.allocation(cls.cam_now)["va"]
        cls.cam_then, _ = space.install_code(cls.cam_now, camera.OWNER, camera.code_for(va, camera.PREVIOUS_VERSION),
                                             previous=camera.code_for(va))
        cls.k_now, _ = k128.apply(cls.retail, roster_heap=True, require=True)
        kva = k128.allocations(cls.k_now)["code"]["va"]
        flags = k128.options_word(roster_heap=True, require=True)
        cls.k_then, _ = space.install_code(cls.k_now, k128.OWNER, k128.code_for(kva, flags, previous=True),
                                           previous=k128.code_for(kva, flags))
        buf = bytearray(cls.k_then)
        k128._repin(buf)
        cls.k_then = bytes(buf)

    def test_the_v7_camera_differs_only_in_the_punt_snap_eye(self):
        camera = self.camera
        now, then = camera.kick_sets(), camera.kick_sets(camera.PREVIOUS_VERSION)
        size = camera.KICK_SET_SIZE
        for index in range(4):
            same = now[size * index:size * (index + 1)] == then[size * index:size * (index + 1)]
            self.assertEqual(same, index != camera.KICK_PUNT_GROUND, index)
        self.assertEqual(camera.kick_values(camera.PREVIOUS_VERSION)[camera.KICK_PUNT_GROUND][2], (0.0, 550.0, -3287.0))

    def test_a_v7_camera_reads_previous_and_upgrades_to_a_fresh_install(self):
        camera = self.camera
        self.assertEqual(camera.status(self.cam_then), "previous")
        self.assertEqual(camera.detect_preset(self.cam_then), camera.detect_preset(self.cam_now))
        upgraded, receipt = camera.apply(self.cam_then)
        self.assertEqual(upgraded, self.cam_now)
        self.assertEqual(receipt["upgraded_from"], "v7")
        changed = bytearray(self.cam_then)
        changed[camera.allocation(self.cam_then)["raw"] + 100] ^= 1
        self.assertEqual(camera.status(bytes(changed)), "foreign")

    def test_the_previous_k128_stop_screen_reads_previous_and_upgrades_to_a_fresh_install(self):
        k128 = self.k128
        self.assertEqual(k128.PREVIOUS_REQUIRE_CODE[:k128.REQUIRE_STARTUP_BYTES], k128.REQUIRE_CODE[:k128.REQUIRE_STARTUP_BYTES])
        self.assertEqual(k128.status(self.k_then), "previous")
        settings = k128.read_settings(self.k_then)
        self.assertEqual((settings["k128"], settings["roster_heap"], settings["require_128"]), (True, True, True))
        upgraded, receipt = k128.apply(self.k_then, roster_heap=True, require=True)
        self.assertEqual(upgraded, self.k_now)
        self.assertEqual(receipt["upgraded_from"], "beta-79")
        with self.assertRaises(ValueError):          # other options: still a rebuild
            k128.apply(self.k_then, roster_heap=False, require=True)
        # without the 128 MB stop both revisions are the same bytes, so "previous" needs it
        kva = k128.allocations(self.k_now)["code"]["va"]
        flags = k128.options_word(roster_heap=True)
        self.assertEqual(k128.code_for(kva, flags), k128.code_for(kva, flags, previous=True))


class CameraAndK128ReleaseTests(unittest.TestCase):
    """The released v0.8 executable."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_camera as camera, nfl2k5_k128 as k128
        cls.camera, cls.k128 = camera, k128
        cls.v08 = v08_xbe()

    def test_the_release_camera_is_v7_and_upgrades_in_place(self):
        camera = self.camera
        self.assertEqual(camera.status(self.v08), "previous")
        upgraded, receipt = camera.apply(self.v08)
        self.assertEqual(camera.status(upgraded), "applied")
        self.assertEqual(len(upgraded), len(self.v08))
        self.assertEqual(space.layout(upgraded)["allocations"], space.layout(self.v08)["allocations"])
        again, receipt = camera.apply(upgraded)
        self.assertEqual((again, receipt["status"]), (upgraded, "already_applied"))

    def test_the_release_k128_is_the_beta79_stop_and_upgrades_in_place(self):
        k128 = self.k128
        self.assertEqual(k128.status(self.v08), "previous")
        settings = k128.read_settings(self.v08)
        upgraded, _ = k128.apply(self.v08, roster_heap=settings["roster_heap"], early=settings["early"],
                                 require=settings["require_128"])
        self.assertEqual(k128.status(upgraded), "applied")
        self.assertEqual(k128.read_settings(upgraded), {**settings, "status": "applied"})
        self.assertEqual(space.layout(upgraded)["allocations"], space.layout(self.v08)["allocations"])
        kva = k128.allocations(self.v08)["code"]["va"]
        self.assertEqual(hashlib.sha256(XbeImage(self.v08).read(kva + k128.REQUIRE_OFFSET, len(k128.PREVIOUS_REQUIRE_CODE)))
                         .hexdigest(), k128.PREVIOUS_REQUIRE_CODE_SHA256)



# ---------------------------------------------------------------------------------------------------------------
# Simulated season realism grew (832 -> 896 code bytes), so a beta-79 install cannot be upgraded in place: it reads
# "previous" (not foreign), the build refuses it in plain words, and the cornerback tackle owner, whose merge-context
# check restores this owner's installed hook, reads applied again on a v0.8 executable.

def realism_b779_install(base: bytes, extra=()) -> bytes:
    """The beta-79 install, made the way e8c1de3a8's apply() made it: its own request, code and ten sites (``extra``:
    other owners' requests reserved in the same union)."""
    from mod_editor.core import nfl2k5_sim_realism_b779 as old
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    payload, _ = space.apply(base, tuple(extra) + old.REQUESTS, scaleout=True)
    rows = {r["kind"]: r for r in space.layout(payload)["allocations"] if r["owner"] == old.OWNER}
    payload, _ = space.install_code(payload, old.OWNER, old.code_for(rows["code"]["va"], rows["data"]["va"]))
    image, buf = XbeImage(payload), bytearray(payload)
    for _label, va, before, after in old.sites(rows["code"]["va"]):
        at = image.offset(va, len(before))
        assert bytes(buf[at:at + len(before)]) == before
        buf[at:at + len(after)] = after
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


class SimRealismPreviousTests(unittest.TestCase):

    def test_the_frozen_revision_is_the_smaller_one(self):
        from mod_editor.core import nfl2k5_sim_realism as realism, nfl2k5_sim_realism_b779 as old
        self.assertEqual((old.CODE_SIZE, realism.CODE_SIZE), (832, 896))
        self.assertEqual(old.OWNER, realism.OWNER)
        self.assertNotEqual(old.sites(0x1500000), realism.sites(0x1500000))
        self.assertNotIn("\u2014", realism.PREVIOUS_REFUSAL)

    def test_a_beta79_install_on_retail_reads_previous_and_is_refused_in_plain_words(self):
        from mod_editor.core import nfl2k5_sim_realism as realism, nfl2k5_sim_cb_tackles as cb
        retail = _retail()
        if retail is None:
            self.skipTest("retail XBE pin differs")
        then = realism_b779_install(retail, cb.REQUESTS)
        self.assertEqual(realism.status(then), "previous")
        with self.assertRaisesRegex(ValueError, "beta 79 revision"):
            realism.apply(then)
        with_cb, _ = cb.apply(then)
        self.assertEqual(cb.status(with_cb), "applied")
        self.assertEqual(realism.status(with_cb), "previous")
        # one changed byte of the beta-79 body is foreign, not previous
        code = [r for r in space.layout(then)["allocations"] if r["owner"] == realism.OWNER and r["kind"] == "code"][0]
        buf = bytearray(then)
        buf[code["raw"] + 3] ^= 1
        self.assertEqual(realism.status(bytes(buf)), "foreign")

    def test_the_release_reads_previous_and_cornerback_tackles_applied(self):
        from mod_editor.core import nfl2k5_sim_realism as realism, nfl2k5_sim_cb_tackles as cb
        v08 = v08_xbe()
        self.assertEqual(realism.status(v08), "previous")
        self.assertEqual(cb.status(v08), "applied")
        with self.assertRaisesRegex(ValueError, "cannot be updated in place"):
            realism.apply(v08)



# ---------------------------------------------------------------------------------------------------------------
# Recognition only (b780-int, 11-03): MyCareer and its companions, Player Progress, pass rush stats and the scorebug
# runtime changed in ways an in-place update cannot carry safely (linked labels, chain targets, bigger allocations).
# On a v0.8 executable each reads "previous" and its apply() refuses in plain words; every owner that validates them
# (Auto Save, Franchise Practice, Practice reserves, the star decal, Edit Player, the playlist, the attribute grades,
# the module loader, the scorebug scene) reads applied again, as it did in beta-79.

class PreviousRecognitionStaticTests(unittest.TestCase):

    def test_the_frozen_mycareer_runtime_differs_and_builds_the_beta79_strings(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career_mode_code_b779 as old
        self.assertEqual(len(old.CODE), 16452)
        self.assertNotEqual(old.CODE, mode.assembly.CODE)
        now = mode.code_for(0x1600000, 0x1700000)[1]
        then = mode.code_for(0x1600000, 0x1700000, previous=True)[1]
        key = "m3_rating_" + mode_rating_key()
        self.assertIn(now[key], range(mode.EXTRA_VA, mode.EXTRA_VA + 4096))              # the M3 RW pool now
        self.assertIn(then[key], range(0x1600000, 0x1600000 + mode.CODE_SIZE))          # RX strings in beta-79
        self.assertNotEqual(mode.sites(0x1600000, 0x1700000), mode.sites(0x1600000, 0x1700000, previous=True))

    def test_every_refusal_is_plain_and_names_the_way_out(self):
        from mod_editor.core import (nfl2k5_my_career_mode as mode, nfl2k5_player_progress_screen as pp,
                                     nfl2k5_pass_rush_stats as rush, nfl2k5_scorebug_runtime as scorebug,
                                     nfl2k5_sim_realism as realism)
        for module in (mode, pp, rush, scorebug, realism):
            text = module.PREVIOUS_REFUSAL
            self.assertIn("beta 79", text, module.__name__)
            self.assertIn("retail game", text, module.__name__)
            self.assertNotIn("\u2014", text, module.__name__)


def mode_rating_key():
    from mod_editor.core import nfl2k5_my_career_progression as progression
    return progression.FIELDS[0][1]


class PreviousRecognitionReleaseTests(unittest.TestCase):
    """The released v0.8 executable as beta-80 reads it."""

    @classmethod
    def setUpClass(cls):
        cls.v08 = v08_xbe()

    def test_the_changed_owners_read_previous(self):
        import importlib
        for name in ("nfl2k5_my_career_mode", "nfl2k5_my_career", "nfl2k5_my_career_home", "nfl2k5_player_progress_screen",
                     "nfl2k5_pass_rush_stats", "nfl2k5_scorebug_runtime", "nfl2k5_sim_realism"):
            with self.subTest(owner=name):
                self.assertEqual(importlib.import_module("mod_editor.core." + name).status(self.v08), "previous")

    def test_their_companions_read_applied_again(self):
        import importlib
        for name in ("nfl2k5_franchise_autosave", "nfl2k5_franchise_practice", "nfl2k5_practice_reserves",
                     "nfl2k5_player_star", "nfl2k5_franchise_edit_player", "nfl2k5_music_playlist",
                     "nfl2k5_letter_grades_attributes", "nfl2k5_module_loader", "nfl2k5_sim_cb_tackles"):
            with self.subTest(owner=name):
                self.assertEqual(importlib.import_module("mod_editor.core." + name).status(self.v08), "applied")
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        self.assertEqual(scene.xbe_status(self.v08), "applied")

    def test_apply_refuses_each_in_plain_words(self):
        from mod_editor.core import (nfl2k5_my_career_mode as mode, nfl2k5_my_career_home as home,
                                     nfl2k5_player_progress_screen as pp, nfl2k5_pass_rush_stats as rush,
                                     nfl2k5_scorebug_runtime as scorebug)
        for module, text in ((mode, mode.PREVIOUS_REFUSAL), (home, mode.PREVIOUS_REFUSAL), (pp, pp.PREVIOUS_REFUSAL),
                             (rush, rush.PREVIOUS_REFUSAL), (scorebug, scorebug.PREVIOUS_REFUSAL)):
            with self.subTest(owner=module.__name__):
                with self.assertRaises(ValueError) as caught:
                    module.apply(self.v08)
                self.assertEqual(str(caught.exception), text)

    def test_the_franchise_footer_host_never_chains_to_the_beta79_mycareer(self):
        from mod_editor.core import nfl2k5_franchise_footer as footer
        self.assertIsNone(footer._my_career_handlers(self.v08))
        self.assertNotEqual(footer.status(self.v08), "applied")


if __name__ == "__main__":
    unittest.main()
