"""b77 / a4: era-correct playbooks for the 51 ESPN 25th Anniversary moments.

* DataTests (no disc): the era data file is complete, sourced and consistent with the moments and the A1 menu facts.
* OwnerTests (the v0.5 executable from the disc): the shotgun weight owner installs, is idempotent, is refused when the
  shotgun rule is edited, composes with the stock book resolver, and the repair script touches only its declared ranges.
* NativeTests (Unicorn): the game's own book resolver picks, for all 51 moments and both sides, exactly the book kind the
  data file says; and the game's own offensive formation draw (0x20B670) calls shotgun more in a modern moment with the
  owner installed than without it, and identically in the ordinary game and in a classic moment.

b77-a4pd: the franchise weight is now one per down and distance bin (32 x 7 uint16 table, stub reads the live down and yards to
go); the tests below cover the new data, the stub bytes, the in-place completion of the a4 body (one float per franchise), the
repair on both inputs, and the native stub (every down, whole and half yards, inside the 10, historic sides, Anniversary mode).

The v0.5 disc and the retail disc are private; their tests skip when absent. Nothing here is a gameplay result.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_moment_gun_weight as gw  # noqa: E402
from mod_editor.core import nfl2k5_stock_books as sb  # noqa: E402

V05_DISC = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso")
RETAIL_ISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
BOOK_KEYS = {"ARZ", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC", "MIA", "MIN",
             "NE", "NO", "NYG", "NYJ", "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEN", "WAS"}


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = gw.load()
        cls.rows = sorted(cls.data["moments"], key=lambda r: r["row"])

    def test_all_51_rows_and_valid_weights(self):
        self.assertEqual([r["row"] for r in self.rows], list(range(1, 52)))
        values = gw.weights(self.data)
        self.assertEqual(len(values), 51)
        self.assertTrue(all(gw.MIN_WEIGHT <= v <= gw.MAX_WEIGHT for v in values))

    def test_era_follows_the_season_word_and_classic_moments_keep_the_retail_rule(self):
        for r in self.rows:
            for side in ("away", "home"):
                s = r["sides"][side]
                self.assertEqual(s["era"], "modern" if s["season"] >= self.data["modern_first_season"] else "classic", (r["row"], side))
                self.assertEqual(s["book_now_exit"] == "default", s["era"] == "modern", (r["row"], side))
                if s["era"] == "modern":
                    self.assertIn(s["franchise_key"], BOOK_KEYS)
            cpu = r["sides"][r["cpu_side"]]
            if cpu["era"] == "classic":
                self.assertEqual(r["gun_weight"], 0.05, r["row"])
                self.assertNotIn("fit", r)
            else:
                self.assertIn("fit", r)
                self.assertEqual(cpu["real"]["source"].startswith("https://github.com/nflverse/nflverse-data/"), True)

    def test_cpu_side_is_the_side_the_user_does_not_play(self):
        for r in self.rows:
            self.assertEqual({r["user_side"], r["cpu_side"]}, {"away", "home"})

    def test_the_modern_cut_is_where_the_league_changed(self):
        league = self.data["league_shotgun_pct"]
        for year in ("2000", "2001", "2003", "2004"):
            self.assertLess(league[year]["gun_pct"], 16.0)
        for year in ("2007", "2012", "2016", "2023"):
            self.assertGreater(league[year]["gun_pct"], 25.0)
        self.assertEqual(self.data["modern_first_season"], sb.MODERN_FIRST_SEASON)

    def test_mile_high_miracle_row(self):
        r = self.rows[38]
        self.assertEqual((r["title"], r["user_side"], r["cpu_side"]), ("MILE HIGH MIRACLE", "away", "home"))
        den = r["sides"]["home"]
        self.assertEqual((den["franchise_key"], den["season"], den["era"]), ("DEN", 2012, "modern"))
        self.assertGreater(den["real"]["first_down_pct"], 45.0)                         # nflverse: 46.8
        self.assertGreater(r["gun_weight"], 0.3)                                        # 0.4 on the p6x Broncos book (0.9 on the p48o book): well above the retail 0.05
        self.assertGreater(r["fit"]["fitted"]["first_down"], r["fit"]["retail_rule"]["first_down"] + 15)

    def test_matches_the_authored_moments(self):
        authored = mm.Data.load()
        for r in self.rows[25:]:                                                           # physical rows 26..51
            m = authored.moments[r["row"] - 26]
            for side in ("away", "home"):
                self.assertEqual(r["sides"][side]["season"], authored.teams[m[side]]["season"], (r["row"], side))
            self.assertEqual(r["user_side"], m["user_side"], r["row"])

    def test_table_and_stub_bytes(self):
        import hashlib
        values, teams = gw.weights(self.data), gw.team_bin_weights(self.data, keys=sb.key_order())
        va = 0x14E3BD0
        code = sb.code_for(va, weights=values, team_weights=teams)
        self.assertEqual(len(code), sb.CODE_SIZE)
        stub = code[sb.STUB_OFFSET:sb.STUB_OFFSET + gw.STUB_SPACE]
        self.assertEqual(stub, gw.stub_bytes(va + sb.STUB_OFFSET, va + sb.WEIGHT_OFFSET, va + sb.TABLE, va + sb.BIN_TABLE_OFFSET))
        # Anniversary part of the stub (unchanged since a4): cmp [mode],8 / jne team / mov eax,[row] / cmp eax,51 / jae ordinary / fld [table+eax*4] / ret
        self.assertEqual(stub[:17].hex(), "833d80ffe500087512a15818bf0083f833")
        self.assertIn((va + sb.WEIGHT_OFFSET).to_bytes(4, "little"), stub)          # the moment table
        self.assertIn((va + sb.BIN_TABLE_OFFSET).to_bytes(4, "little"), stub)       # the franchise bin table
        self.assertIn((va + sb.TABLE).to_bytes(4, "little"), stub)                  # the key rows
        self.assertIn((0xE602EC).to_bytes(4, "little"), stub)                       # the situation object (down)
        self.assertEqual(len(stub.rstrip(b"\xcc")), 252)
        # layout: stub 256 bytes, 51 moment floats, 32 x 7 uint16 bin weights, free tail
        self.assertEqual((sb.STUB_OFFSET, sb.WEIGHT_OFFSET, sb.BIN_TABLE_OFFSET), (608, 864, 1072))
        table = struct.unpack("<51f", code[sb.WEIGHT_OFFSET:sb.WEIGHT_OFFSET + 204])
        self.assertEqual([round(v, 2) for v in table], values)
        self.assertEqual(code[sb.WEIGHT_OFFSET + 204:sb.BIN_TABLE_OFFSET], b"\xcc" * (sb.BIN_TABLE_OFFSET - sb.WEIGHT_OFFSET - 204))
        units = struct.unpack("<224H", code[sb.BIN_TABLE_OFFSET:sb.BIN_TABLE_OFFSET + 448])
        self.assertEqual([[round(u * 0.05, 2) for u in units[i * 7:i * 7 + 7]] for i in range(32)], teams)
        self.assertEqual(gw.decode_bin_table(code[sb.BIN_TABLE_OFFSET:sb.BIN_TABLE_OFFSET + 448]), teams)
        self.assertEqual(code[sb.BIN_TABLE_OFFSET + 448:], b"\xcc" * (sb.CODE_SIZE - sb.BIN_TABLE_OFFSET - 448))
        self.assertLessEqual(len(code[:sb.TABLE].rstrip(b"\xcc")), sb.TABLE)
        # the 32 key rows are the 8 byte UTF-16 franchise keys, in the manifest's order
        rows = [code[sb.TABLE + 8 * i:sb.TABLE + 8 * i + 8] for i in range(32)]
        self.assertEqual([r.decode("utf-16le").rstrip("\0") for r in rows], [a["source"].removesuffix("-pb.iff") for a in sb.aliases()])
        self.assertEqual(code[sb.PREFIX_OFFSET:sb.PREFIX_OFFSET + 8].decode("utf-16le"), "E2R-")
        self.assertEqual(code[sb.SUFFIX_OFFSET:sb.SUFFIX_OFFSET + 16].decode("utf-16le"), "-pb.iff\0")
        # the a4 body's stub is kept byte for byte (digest of the a4 job's own stub for fixed addresses), so that body is recognised
        single = gw.stub_bytes_single(0x14E3E30, 0x14E3F00, 0x14E3D10, 0x14E4000)
        self.assertEqual(hashlib.sha256(single).hexdigest(), "d12a7cafb0d4d17fe5c0ad0b51ff8b70d2eeca254c04a4949ddc55a857fab2d6")

    def test_franchise_bin_weights_are_fitted_sourced_and_follow_the_real_rates(self):
        teams = self.data["teams"]
        self.assertEqual(self.data["schema"], "b77/a4_moment_playbook_eras/v2")
        self.assertEqual(sorted(teams), sorted(sb.key_order()))
        self.assertEqual(list(self.data["team_bins"]), list(gw.BIN_NAMES))
        self.assertEqual(self.data["team_bins"]["d3_short"]["downs"], [3, 4])          # 4th down is counted with the 3rd-down bins
        for key, t in teams.items():
            self.assertEqual(sorted(t["sources"]), ["2025", "2026"])
            self.assertEqual(list(t["gun_weights"]), list(gw.BIN_NAMES), key)
            self.assertEqual(list(t["bins"]), list(gw.BIN_NAMES), key)
            self.assertGreater(t["snaps"], 1000, key)
            self.assertEqual(len(t["fit"]["book_sha256"]), 64)
            for name in gw.BIN_NAMES:
                w = t["gun_weights"][name]
                self.assertAlmostEqual(gw.bin_units(w) * gw.BIN_UNIT, w, places=9, msg=(key, name))   # on the 0.05 grid, 0.05..16.0
                real, fitted, retail = t["bins"][name]["gun_pct"], t["fit"]["fitted"][name], t["fit"]["retail_rule"][name]
                self.assertGreater(t["bins"][name]["snaps"], 30, (key, name))
                self.assertLessEqual(abs(fitted - real), abs(retail - real) + 0.6, (key, name))      # never worse than the retail rule
                self.assertLess(abs(fitted - real), 6.5, (key, name))                                # the book's own limit (a book that is all gun on 3rd & 7+ cannot go lower)
            snaps = sum(b["snaps"] for b in t["bins"].values())
            real_all = sum(b["snaps"] * b["gun_pct"] for b in t["bins"].values()) / snaps
            fit_all = sum(t["bins"][n]["snaps"] * t["fit"]["fitted"][n] for n in t["bins"]) / snaps
            self.assertLess(abs(fit_all - real_all), 2.0, key)                                       # overall share within 2 points
        # per bin, not one scalar: the same franchise gets different weights for 1st down and 2nd & 8+
        self.assertTrue(all(t["gun_weights"]["d2_long"] != t["gun_weights"]["d1"] for t in teams.values()))
        self.assertGreater(teams["WAS"]["gun_pct"], teams["STL"]["gun_pct"])
        self.assertEqual(gw.team_bin_weights({"teams": {}}, keys=["DEN"]), [[0.05] * 7])        # unnamed franchise: retail in every bin
        self.assertEqual(gw.team_bin_weights({"teams": {"DEN": {"classic": True, "gun_weights": teams["DEN"]["gun_weights"]}}}, keys=["DEN"]), [[0.05] * 7])
        self.assertEqual(len(gw.team_bin_weights(self.data, keys=sb.key_order())), 32)

    def test_bin_names_and_edges_agree_between_the_tool_and_the_owner(self):
        from tools.b77 import a4_eras
        self.assertEqual(tuple(a4_eras.BIN_ORDER), gw.BIN_NAMES)
        self.assertEqual({n: a4_eras.TEAM_BINS[n][1] for n in gw.BIN_NAMES},
                         {"d1": (1, 99), "d2_short": (1, 3), "d2_mid": (4, 7), "d2_long": (8, 99), "d3_short": (1, 3), "d3_mid": (4, 6), "d3_long": (7, 99)})
        self.assertEqual(a4_eras.BIN_GRID[0], 0.05)
        self.assertEqual(a4_eras.BIN_GRID[-1], gw.BIN_MAX_WEIGHT)
        self.assertEqual([gw.bin_units(w) for w in (0.05, 1.0, 16.0)], [1, 20, 320])
        for bad in (0.0, 0.02, 0.07, 16.05, -1, 1e9):
            with self.assertRaises(gw.MomentGunWeightError, msg=bad):
                gw.bin_units(bad)
        with self.assertRaises(gw.MomentGunWeightError):
            gw.bin_table_bytes([[1.0] * 7] * 31)
        with self.assertRaises(gw.MomentGunWeightError):
            gw.decode_bin_table(b"\x00" * gw.BIN_TABLE_SIZE)            # a zero entry is outside the bounds

    def test_weights_refuse_bad_data(self):
        bad = json.loads(json.dumps(self.data))
        bad["moments"][0]["gun_weight"] = 0.01
        with self.assertRaises(gw.MomentGunWeightError):
            gw.weights(bad)
        bad = json.loads(json.dumps(self.data))
        del bad["moments"][5]
        with self.assertRaises(gw.MomentGunWeightError):
            gw.weights(bad)


@unittest.skipUnless(V05_DISC.is_file(), "the private v0.5 disc image is required")
class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        from mod_editor.core import nfl2k5_espn25_rosters as er
        cls.v05 = er.read_xbe(V05_DISC)
        if hashlib.sha256(cls.v05).hexdigest() != V05_XBE_SHA256:
            raise unittest.SkipTest("the v0.5 disc image has another executable than SOFTDRINK 2K28 v0.5")
        cls.fixed, cls.receipt = sb.apply(cls.v05)

    def test_v05_carries_the_previous_body_and_apply_completes_it_in_place(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(sb.status(self.v05), "needs_fix")
        va = sb.allocation(self.v05)["va"]
        self.assertEqual(XbeImage(self.v05).read(va, sb.CODE_SIZE), sb.code_for(va, legacy=True))      # v0.5 = the legacy body, exactly
        self.assertEqual(sb.status(self.fixed), "applied")
        self.assertEqual(len(self.fixed), len(self.v05))
        self.assertTrue(self.receipt["upgraded_moment_routing"])
        self.assertEqual(sb.allocation(self.fixed), sb.allocation(self.v05))                          # no allocation moved or added
        image = XbeImage(self.fixed)
        self.assertEqual(image.read(va, sb.CODE_SIZE), sb.code_for(va))
        self.assertEqual(image.read(gw.SITE_VA, 6), gw.sites(va + sb.STUB_OFFSET)[0][3])

    def test_idempotent_and_other_weights_replace_in_place(self):
        again, receipt = sb.apply(self.fixed)
        self.assertEqual(again, self.fixed)
        self.assertEqual(receipt["status"], "already_applied")
        values = gw.weights()
        values[38] = 1.25
        changed, _ = sb.apply(self.fixed, weights=values)
        self.assertNotEqual(changed, self.fixed)
        self.assertEqual(sb.status(changed), "applied")
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        va = sb.allocation(changed)["va"]
        installed = gw.decode_table(XbeImage(changed).read(va + sb.WEIGHT_OFFSET, gw.TABLE_SIZE))
        self.assertEqual(installed[38], 1.25)
        self.assertEqual(sb.apply(changed, weights=gw.weights())[0], self.fixed)
        rows = gw.team_bin_weights(keys=sb.key_order())
        rows[5][2] = 2.5
        rebinned, receipt = sb.apply(self.fixed, team_weights=rows)
        self.assertEqual(sb.status(rebinned), "applied")
        installed_rows = gw.decode_bin_table(XbeImage(rebinned).read(va + sb.BIN_TABLE_OFFSET, gw.BIN_TABLE_SIZE))
        self.assertEqual(installed_rows[5][2], 2.5)
        self.assertEqual(receipt["team_gun_weights"][sb.key_order()[5]]["d2_mid"], 2.5)
        self.assertEqual(sb.apply(rebinned, team_weights=gw.team_bin_weights(keys=sb.key_order()))[0], self.fixed)
        for bad_row in (0.07, 16.05, 0.0):
            wrong = [list(r) for r in rows]
            wrong[0][0] = bad_row
            with self.assertRaises(ValueError):
                sb.apply(self.fixed, team_weights=wrong)

    def _a4_image(self):
        """The a4 job's executable shape: the same hook and shotgun site, the body with one float per franchise."""
        owned = sb.allocation(self.fixed)
        single = sb.code_for(owned["va"], single_weight=True, weights=gw.weights(), team_weights=[1.0 + 0.05 * i for i in range(32)])
        return sb._write_body(self.fixed, owned, single), owned, single

    def test_the_a4_body_with_one_weight_per_franchise_is_completed_in_place(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        a4_image, owned, single = self._a4_image()
        self.assertEqual(sb.status(a4_image), "needs_fix")
        self.assertEqual(len(a4_image), len(self.fixed))
        self.assertEqual(XbeImage(a4_image).read(gw.SITE_VA, 6), XbeImage(self.fixed).read(gw.SITE_VA, 6))   # the call target does not move
        completed, receipt = sb.apply(a4_image)
        self.assertEqual(completed, self.fixed)
        self.assertTrue(receipt["upgraded_moment_routing"])
        self.assertEqual(sb.apply(completed)[0], completed)
        off, _ = sb.apply(a4_image, enabled=False)                                                         # off restores both retail sites
        self.assertEqual(sb.status(off), "retail")
        self.assertEqual(sb.apply(off)[0], self.fixed)
        bad = bytearray(single)
        bad[sb.STUB_OFFSET + 3] ^= 1                                                                        # a foreign stub in the a4 shape
        self.assertEqual(sb.status(sb._write_body(self.fixed, owned, bytes(bad))), "foreign")
        mixed = bytearray(single)
        mixed[sb.SINGLE_TEAM_OFFSET + 128] ^= 1                                                             # a byte past the a4 tables
        self.assertEqual(sb.status(sb._write_body(self.fixed, owned, bytes(mixed))), "foreign")

    def test_turning_the_option_off_restores_the_retail_sites_and_back_on_is_exact(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        off, _ = sb.apply(self.fixed, enabled=False)
        self.assertEqual(sb.status(off), "retail")
        self.assertEqual(XbeImage(off).read(gw.SITE_VA, 6), gw.RETAIL_SITE)
        self.assertEqual(XbeImage(off).read(sb.SITE, len(sb.RETAIL)), sb.RETAIL)
        on, _ = sb.apply(off)
        self.assertEqual(on, self.fixed)

    def test_a_changed_shotgun_rule_site_or_stub_is_refused(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core import nfl2k5_bump_strength as bump

        def reseal(buf):
            for section in bump._sections(buf):
                buf[section.header_offset + 36:section.header_offset + 56] = bump.section_digest(buf, section)
            return bytes(buf)

        lifted = bytearray(self.v05)                                                           # 75 20 -> EB 20: the rule lifted for everyone
        lifted[XbeImage(self.v05).offset(0x207F85, 2)] = 0xEB
        with self.assertRaises(ValueError):
            sb.apply(reseal(lifted))                                                           # refused instead of guessing
        edited = bytearray(self.fixed)
        edited[XbeImage(self.fixed).offset(gw.SITE_VA, 6) + 1] ^= 0xFF                         # a foreign call target at the site
        self.assertEqual(sb.status(reseal(edited)), "foreign")
        va = sb.allocation(self.fixed)["va"]
        for offset in (sb.STUB_OFFSET, sb.STUB_OFFSET + 200, sb.WEIGHT_OFFSET + 3, sb.BIN_TABLE_OFFSET + 5, sb.BIN_TABLE_OFFSET + 450, sb.PREFIX_OFFSET, sb.TABLE):
            bad = bytearray(self.fixed)
            bad[XbeImage(self.fixed).offset(va + offset, 1)] ^= 1
            self.assertEqual(sb.status(reseal(bad)), "foreign", offset)
        small = gw.weights()
        small[0] = 0.01
        with self.assertRaises(ValueError):
            sb.apply(self.v05, weights=small)

    def test_repair_script_scope_receipt_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in").mkdir()
            (tmp / "in" / "default.xbe").write_bytes(self.v05)
            run = lambda src, dst, *extra: subprocess.run(                                  # noqa: E731
                [sys.executable, str(ROOT / "tools/b77/a4_repair.py"), "--input-dir", str(src), "--output-dir", str(dst), *extra],
                capture_output=True, text=True)
            first = run(tmp / "in", tmp / "out")
            self.assertEqual(first.returncode, 0, first.stderr)
            fixed = (tmp / "out" / "default.xbe").read_bytes()
            self.assertEqual(fixed, self.fixed)
            receipt = json.loads((tmp / "out" / "a4_receipt.json").read_text())
            self.assertTrue(receipt["outside_scope_identical"])
            self.assertTrue(receipt["existing_allocations_unchanged"])
            self.assertEqual(receipt["before_sha256"], V05_XBE_SHA256)
            self.assertEqual(receipt["scopes_changed"], sum(1 for s in receipt["scopes"] if s["changed"]))
            self.assertEqual(receipt["changed_bytes"], sum(s["changed_bytes"] for s in receipt["scopes"]))
            site = next(s for s in receipt["scopes"] if s["label"].startswith("site"))
            self.assertEqual((site["before_hex"], site["size"]), ("d905106d4e00", 6))
            second = run(tmp / "out", tmp / "out2")                                          # idempotent: output = input
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((tmp / "out2" / "default.xbe").read_bytes(), fixed)
            refused = run(tmp / "out", tmp / "out2")                                         # never overwrites
            self.assertNotEqual(refused.returncode, 0)
            foreign = bytearray(self.v05)
            foreign[100] ^= 1
            (tmp / "bad").mkdir()
            (tmp / "bad" / "default.xbe").write_bytes(bytes(foreign))
            self.assertNotEqual(run(tmp / "bad", tmp / "out3").returncode, 0)
            # stacked on an input that already carries the a4 body (one weight per franchise): named by hash, completed in place
            import hashlib
            a4_image, _owned, _single = self._a4_image()
            (tmp / "a4in").mkdir()
            (tmp / "a4in" / "default.xbe").write_bytes(a4_image)
            self.assertNotEqual(run(tmp / "a4in", tmp / "o4").returncode, 0)                  # an unnamed stacked input is refused
            stacked = run(tmp / "a4in", tmp / "o5", "--expected-input-sha256", hashlib.sha256(a4_image).hexdigest())
            self.assertEqual(stacked.returncode, 0, stacked.stderr)
            self.assertEqual((tmp / "o5" / "default.xbe").read_bytes(), fixed)
            stacked_receipt = json.loads((tmp / "o5" / "a4_receipt.json").read_text())
            self.assertTrue(stacked_receipt["outside_scope_identical"])
            self.assertEqual(next(s for s in stacked_receipt["scopes"] if s["label"].startswith("site"))["changed"], False)   # same call target
            self.assertEqual(stacked_receipt["scopes_changed"], sum(1 for s in stacked_receipt["scopes"] if s["changed"]))


P6X_BOOKS = Path(os.environ.get("A4_BOOKS_DIR", "/home/noah/2k-worktrees/.b77-scratch/a4pd/books"))
# A4_BOOKS_DIR selects the exact books named by the committed fit hashes.
# The original a4pd scratch predates the final integrated books.
SELECTION_TREES = (ROOT, Path("/home/noah/2k-worktrees/b77-int"))              # a tree that has pb/v2/selection_model.py


@unittest.skipUnless(V05_DISC.is_file() and P6X_BOOKS.is_dir(), "the private v0.5 disc image and the extracted p6x books are required")
class RefitTests(unittest.TestCase):
    def test_refit_on_the_final_books_reproduces_the_committed_data_and_the_same_executable(self):
        tree = next((t for t in SELECTION_TREES if (t / "pb/v2/selection_model.py").is_file()), None)
        if tree is None:
            self.skipTest("no tree with pb/v2/selection_model.py")
        import hashlib
        from mod_editor.core import nfl2k5_espn25_rosters as er
        v05 = er.read_xbe(V05_DISC)
        if hashlib.sha256(v05).hexdigest() != V05_XBE_SHA256:
            self.skipTest("another v0.5 executable")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in").mkdir()
            (tmp / "in" / "default.xbe").write_bytes(v05)
            run = subprocess.run([sys.executable, str(ROOT / "tools/b77/a4_repair.py"), "--input-dir", str(tmp / "in"), "--output-dir", str(tmp / "out"),
                                  "--refit-books", str(P6X_BOOKS), "--selection-model-dir", str(tree)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            refit = json.loads((tmp / "out" / "a4_moment_playbook_eras.refit.json").read_text())
            self.assertEqual(refit, gw.load())                                             # the committed data IS the refit on the final books
            plain = subprocess.run([sys.executable, str(ROOT / "tools/b77/a4_repair.py"), "--input-dir", str(tmp / "in"), "--output-dir", str(tmp / "plain")],
                                   capture_output=True, text=True)
            self.assertEqual(plain.returncode, 0, plain.stderr)
            self.assertEqual((tmp / "out" / "default.xbe").read_bytes(), (tmp / "plain" / "default.xbe").read_bytes())
            for key in sb.key_order():
                digest = hashlib.sha256((P6X_BOOKS / f"{key}.play").read_bytes()).hexdigest()
                self.assertEqual(refit["teams"][key]["fit"]["book_sha256"], digest, key)


def _ordinary_vs_moment_cpu():
    """Shared Unicorn fixture: the v0.5 disc's own SITU, rosters and team files with the v0.5 executable."""
    import nfl2k5_b77_menu_native as nat
    from nfl2k5_espn25_more_moments_native import FastMomentsCPU
    data = mm.Data.load()
    resources, context, ids, situ_chunk, extra, retail_situ = nat.disc_inputs(V05_DISC, RETAIL_ISO, data)
    return nat, FastMomentsCPU, resources, context, ids, situ_chunk, extra


@unittest.skipUnless(HAVE_UNICORN and V05_DISC.is_file() and RETAIL_ISO.is_file(), "Unicorn and the private v0.5 and retail disc images are required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import hashlib
        from mod_editor.core import nfl2k5_espn25_rosters as er
        cls.v05 = er.read_xbe(V05_DISC)
        if hashlib.sha256(cls.v05).hexdigest() != V05_XBE_SHA256:
            raise unittest.SkipTest("the v0.5 disc image has another executable than SOFTDRINK 2K28 v0.5")
        cls.fixed, _ = sb.apply(cls.v05)
        cls.data = gw.load()
        cls.nat, cls.cpu_class, cls.resources, cls.context, cls.ids, cls.situ_chunk, cls.extra = _ordinary_vs_moment_cpu()

    def test_the_resolver_picks_the_book_kind_the_data_file_names_for_all_51_moments_and_both_sides(self):
        import nfl2k5_b77_books_native as books_native
        cpu = self.cpu_class(self.fixed, self.resources, self.context, self.ids, situ_chunk=self.situ_chunk, extra_files=self.extra)
        seen = {}
        for display_row in range(51):
            entry = books_native.resolve_moment(cpu, display_row, self.nat.record_fields)
            seen[entry["physical_row"]] = entry
        self.assertEqual(sorted(seen), list(range(1, 52)))
        for row in self.data["moments"]:
            entry = seen[row["row"]]
            self.assertEqual(entry["title"], row["title"], row["row"])
            for side in ("away", "home"):
                want, got = row["sides"][side], entry[side]
                self.assertEqual(got["franchise_key"], want["franchise_key"], (row["row"], side))
                self.assertEqual(entry["situ_season_words"][side], want["season"], (row["row"], side))
                self.assertEqual(got["category"], 4)                                         # Anniversary teams
                self.assertEqual(got["exit"], "default" if want["era"] == "modern" else "stock_alias", (row["row"], side))
                if want["era"] == "classic":
                    self.assertEqual(got["alias"], f"E2R-{want['franchise_key']}-pb.iff")

    def test_the_formation_draw_calls_more_shotgun_in_the_mile_high_miracle_and_nowhere_else(self):
        from tools.b77 import a4_callmix
        from mod_editor.core import nfl2k5_roster_records as rr
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES
        with rr._outer_image()(V05_DISC) as image:
            den = image.read_entry(BOOK_ENTRIES["DEN"])
        sits = {k: a4_callmix.SITUATIONS[k] for k in ("1st&10 own25", "2nd&8 mid")}
        before = a4_callmix.run(self.v05, den, sits, 40, 39)                                   # v0.5: no owner
        ordinary = a4_callmix.run(self.fixed, den, sits, 40, None)                             # owner, ordinary game
        classic = a4_callmix.run(self.fixed, den, sits, 40, 22)                                # owner, a classic moment (row 22)
        moment = a4_callmix.run(self.fixed, den, sits, 40, 39)                                 # owner, the Mile High Miracle
        for name in sits:
            self.assertEqual(before[name]["gun_pct"], ordinary[name]["gun_pct"], name)         # bit for bit the retail rule
            self.assertEqual(before[name]["top"], ordinary[name]["top"], name)
            self.assertEqual(before[name]["top"], classic[name]["top"], name)                  # row 22 weighs 0.05 = retail
            self.assertGreater(moment[name]["gun_pct"], before[name]["gun_pct"] + 8.0, name)
            self.assertEqual(moment[name]["faults"], 0)

    def _stub_weight(self, cpu, team):
        """Run the installed stub the way 0x207EF0 calls it: argument 1 (the team) at [esp+0x20] inside the stub; returns the float."""
        import struct as st
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        va = sb.allocation(self.fixed)["va"] + sb.STUB_OFFSET
        scratch = 0x2680000
        code = b"\xe8" + st.pack("<i", va - (scratch + 5)) + b"\xd9\x1d" + st.pack("<I", scratch + 256) + b"\xc3"
        cpu.write(scratch, code)
        cpu.uc.ctl_remove_cache(scratch, scratch + 512)
        # The selector passes a live team whose +0x1c points to this roster
        # record. Passing the roster directly concealed the shipped crash.
        live_team = scratch + 512
        cpu.write(live_team, bytes(0x3C))
        cpu.w(live_team + 0x1C, team)
        cpu.w(cpu.STACK + 0x1C, live_team)
        cpu.run(scratch)
        return cpu.f(scratch + 256)

    def test_the_stub_finds_a_real_staged_team_by_its_franchise_key_and_keeps_historic_teams_retail(self):
        cpu = self.cpu_class(self.fixed, self.resources, self.context, self.ids, situ_chunk=self.situ_chunk, extra_files=self.extra)
        want = dict(zip(sb.key_order(), (row[0] for row in gw.team_bin_weights(self.data, keys=sb.key_order()))))   # 1st down: bin 0 needs only the down word
        state = 0x2690000
        cpu.write(state, bytes(0x40))
        cpu.w(state + 4, 1)                                      # down 1
        cpu.w(0xE602EC, state)
        cpu.events.clear()
        cpu.select(36)                                           # display row 37 (physical 39): Mile High Miracle, Ravens at Broncos
        cpu.match()
        seen = {}
        for side, getter in (("home", 0x77B00), ("away", 0x77B40)):
            team = cpu.run(getter)
            key = cpu.text(cpu.r(cpu.r(team + 0x110) + 4))
            cpu.w(0xE5FF80, 0)                                   # an ordinary game
            historic = self._stub_weight(cpu, team)              # category word 4 (an Anniversary side): retail
            self.assertAlmostEqual(historic, 0.05, places=6, msg=key)
            cpu.w(team + 0x128, 0)                               # the same team record as a current franchise team
            seen[key] = self._stub_weight(cpu, team)
            self.assertAlmostEqual(seen[key], want[key], places=5, msg=key)
            cpu.w(0xE5FF80, 8)                                   # Anniversary mode: the moment table, whatever the team
            moment = self._stub_weight(cpu, team)
            self.assertAlmostEqual(moment, self.data["moments"][cpu.r(0xBF1858)]["gun_weight"], places=5)
            cpu.w(team + 0x110, 0)
            cpu.w(0xE5FF80, 0)
            self.assertAlmostEqual(self._stub_weight(cpu, team), 0.05, places=6)   # no key object: retail
        self.assertEqual(sorted(seen), ["BAL", "DEN"])
        self.assertAlmostEqual(seen["DEN"], want["DEN"], places=5)

    def test_the_stub_picks_the_bin_of_the_live_down_and_distance_in_the_games_own_formation_weight(self):
        """0x207EF0 itself (the caller of the stub) for a shotgun set on a staged team: every down 1..4 and 1..25 yards plus the half yard
        cuts return the table's weight of that bin; inside the 10 it equals v0.5; a historic side or an unknown key stays retail; Anniversary
        mode returns the moment's weight at every down and distance."""
        from tools.b77 import a4_bins_probe
        from mod_editor.core import nfl2k5_roster_records as rr
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES
        for key in ("DEN", "BAL"):
            with rr._outer_image()(V05_DISC) as image:
                book = image.read_entry(BOOK_ENTRIES[key])
            result = a4_bins_probe.check(self.fixed, book, key, before=self.v05)
            self.assertEqual(result["mismatches"], [], key)
            self.assertEqual(result["inside_the_10_differences"], [], key)
            self.assertGreater(result["cases"], 150)
            self.assertEqual(result["row"], gw.team_bin_weights(self.data, keys=sb.key_order())[sb.key_order().index(key)])

    def test_franchise_formation_draw_follows_the_team_and_leaves_anniversary_alone(self):
        from tools.b77 import a4_callmix
        from mod_editor.core import nfl2k5_roster_records as rr
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES
        with rr._outer_image()(V05_DISC) as image:
            den = image.read_entry(BOOK_ENTRIES["DEN"])
        sits = {k: a4_callmix.SITUATIONS[k] for k in ("1st&10 mid", "2nd&5 mid")}
        before = a4_callmix.run(self.v05, den, sits, 40, None, team="DEN")
        after = a4_callmix.run(self.fixed, den, sits, 40, None, team="DEN")
        historic = a4_callmix.run(self.fixed, den, sits, 40, None, team="DEN", category=4)
        stranger = a4_callmix.run(self.fixed, den, sits, 40, None, team="ZZZ")
        for name in sits:
            self.assertGreater(after[name]["gun_pct"], before[name]["gun_pct"] + 10.0, name)
            self.assertEqual(historic[name]["top"], before[name]["top"], name)        # historic side: retail draw, identical
            self.assertEqual(stranger[name]["top"], before[name]["top"], name)        # unknown franchise key: retail
        moment_with_team = a4_callmix.run(self.fixed, den, {"1st&10 own25": a4_callmix.SITUATIONS["1st&10 own25"]}, 40, 39, team="DEN")
        moment_plain = a4_callmix.run(self.fixed, den, {"1st&10 own25": a4_callmix.SITUATIONS["1st&10 own25"]}, 40, 39)
        self.assertEqual(moment_with_team, moment_plain)                               # Anniversary results do not depend on the team path



if __name__ == "__main__":
    unittest.main()
