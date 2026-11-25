"""b81-seamen: the classic Seamen's own mark on the sprite scorebug.

The owner (2026-11-25, playing the 11/20 private disc): "when i use the 06 seamen, the scorebug shows miami dolphins, not the
seamen logo ... but drive summary pop ups show the seamen anchor logo".

Root cause (PROVED OFFLINE): the engine's logo() (tools/scorebug_sprite/runtime.c) names a side's panel "sb" + the
team's art code (+0x10C) + "h0". A historic team keeps its franchise's code (vb3), and the classic Seamen ride the
Dolphins' code 14, so they bound sb14h0, the Dolphins' panel. The drive summary reads the kit package's own "logo"
texture, which the Seamen kit (14h14 / 14a14) paints with the anchor. Owner revision 19 names the Seamen's panel by
their identity (+0x118, 230): "sbSEh0", the anchor, appended beside the 32 club panels. Without it the lookup falls
back to the neutral panel. Every other team binds what it bound before.

Offline evidence: the owner's compiled engine runs under Unicorn on the mapped retail executable. Not a played game.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")]
from mod_editor.core import nfl2k5_classic_teams as ct  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_resources as art  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_runtime as owner  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_teams as teams  # noqa: E402

PACK = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_CV2 = importlib.util.find_spec("cv2") is not None
HOME, AWAY = 0xB30864, 0xB30A58


class SourceTests(unittest.TestCase):
    def test_the_engine_names_the_seamen_panel_by_their_identity(self):
        source = (ROOT / "tools/scorebug_sprite/runtime.c").read_text(encoding="utf-8")
        identity = ct.own_name_identity()
        self.assertEqual(identity, 230)
        self.assertIn("if(*(u8*)(context+0x118)==%d)mid=0x00450053;" % identity, source)     # "SE"
        self.assertIn("else if(p && kind!=2) {", source)                    # vb3 rule stays
        self.assertLess(max(ct.IDENTITIES), 256)          # the engine compares the identity's low byte
        self.assertEqual(art.CLASSIC_PANELS, {"SE": {"logo": "SEAMEN", "identity": identity, "franchise": "MIA"}})
        self.assertNotIn("SEAMEN", art.TEAM_LOGOS)

    def test_revision_nineteen_fits_the_same_allocation_and_recognises_eighteen(self):
        self.assertEqual((owner.REVISION, owner.CODE_SIZE), (19, 6336))
        self.assertIn(18, owner.EARLIER_REVISIONS)
        from mod_editor.core import nfl2k5_scorebug_sprite_code as now, nfl2k5_scorebug_sprite_code_r18 as r18
        self.assertEqual(len(now.CODE) - len(r18.CODE), 1)          # logo() rewritten compactly: the owner had 10 spare
        body = len(owner.code_for(0x1000000, 0x2000000)[0].rstrip(b"\xcc"))
        self.assertLessEqual(body, owner.CODE_SIZE)
        self.assertLessEqual(len(owner.code_for(0x1000000, 0x2000000, 18)[0].rstrip(b"\xcc")), owner.CODE_SIZE)

    @unittest.skipUnless(HAVE_CV2, "OpenCV draws the anchor")
    def test_the_mark_is_what_the_authoring_tool_draws(self):
        spec = importlib.util.spec_from_file_location("ss2_scorebug", ROOT / "tools/b77/ss2_scorebug.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(tool.main(["--check"]), 0, "seamen.png differs from tools/b77/ss2_scorebug.py output")

    def test_the_mark_is_the_anchor_on_transparency(self):
        from PIL import Image
        import numpy as np
        with Image.open(ROOT / "data/nfl2k5_scorebug_mnf/logos/seamen.png") as image:
            rgba = np.asarray(image.convert("RGBA")).astype(int)
        self.assertEqual(rgba.shape[0], 64)
        self.assertEqual(rgba[0, 0, 3], 0)
        solid = rgba[rgba[..., 3] == 255][:, :3]
        teal = np.all(np.abs(solid - (2, 160, 129)) <= 12, axis=1).mean()
        self.assertGreater(teal, 0.3)                      # the anchor's teal body, its dark outline around it


@unittest.skipUnless(PACK.is_file(), "retail resources required")
class AppendixTests(unittest.TestCase):
    def test_the_appendix_carries_the_seamen_panel_after_the_club_panels(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        data, receipt = sprite.appendix(PACK.read_bytes())
        names = [c["name"] for c in receipt["components"]]
        self.assertEqual(names[33], "sbSEh0")
        self.assertEqual(receipt["texture_count"], 35)
        count, appended, _growth = sprite.probe_sizes()
        self.assertEqual((count, appended), (35, len(data)))
        at = sum(c["size"] for c in receipt["components"][:33])
        span = data[at:at + receipt["components"][33]["size"]]
        self.assertEqual(len(span), 5280)
        chunk, decoded, _ = scene.decode(span)
        texture = scene.tx.parse_texture(decoded, chunk)
        self.assertEqual((texture.name, texture.width, texture.height), ("sbSEh0", 64, 64))
        plate, wing = struct.unpack_from("<II", span, 32 + 48)
        mia = data[sum(c["size"] for c in receipt["components"][:20]):][:5280]
        self.assertEqual(names[20], "sb14h0")
        self.assertEqual((plate, wing), struct.unpack_from("<II", mia, 32 + 48))   # the franchise's colour words


@unittest.skipUnless(PACK.is_file() and HAVE_UC, "retail resources and Unicorn required")
class NativeEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview = sprite.NativePreview()
        cls.payload = owner.apply(cls.preview.payload)[0]
        code, data = owner.sites(cls.payload)
        cls.labels = owner.code_for(code["va"], data["va"])[1]

    def bound(self, home, away, *, identities=(0, 0)):
        from mod_editor.core import nfl2k5_scorebug_ingame as scene
        _, capture = self.preview.capture(dict(home="GB", away="DAL"), False)
        spans = {int(k, 16): bytes(v) for k, v in capture["texture_spans"].items()}
        m = capture["machine"]
        try:
            m.identity(home="GB", away="DAL", home_code=home[0], away_code=away[0], home_kind=home[1],
                       away_kind=away[1])
            for context, identity in zip((HOME, AWAY), identities):
                m.uc.mem_write(context + 0x118, struct.pack("<H", identity))
            m.put(0xE60280, 0xE5FC20)
            m.run(self.labels["setup"], limit=100000)
            m.run(self.labels["update"], (0x3C888889,), limit=100000)
            base = m.get(0xA95528)
            logos = {}
            for i in range(m.get(base + 0x1C)):
                at = m.get(base + 0x20) + i * 128
                name = m.read_string(m.get(at))
                if name in ("hscore_buga", "zscore_buga"):
                    chunk, decoded, _ = scene.decode(spans[m.get(at + 0x30)])
                    logos[name] = scene.tx.parse_texture(decoded, chunk).name
            compiled = self.preview.modes[False]["compiled"]
            colours = {q["name"]: m.get(capture["body"] + 0x2D20 + q["vertex"] * 10)
                       for q in compiled.quads if q.get("tint", "none") != "none" and not q["dynamic"]}
            return logos, colours
        finally:
            m.close()

    def test_the_seamen_at_home_against_the_dolphins(self):
        logos, colours = self.bound(("14", 4), ("14", 0), identities=(230, 14))
        self.assertEqual(logos, {"hscore_buga": "sbSEh0", "zscore_buga": "sb14h0"})
        mia = next(t for t in teams.load().values() if t["kind"] == 0 and t["asset_code"] == "14")
        self.assertEqual(colours["home_wing"], 0xFF000000 | int(mia["wing"][1:], 16))

    def test_the_seamen_away(self):
        logos, _ = self.bound(("10", 0), ("14", 4), identities=(10, 230))
        self.assertEqual(logos, {"hscore_buga": "sb10h0", "zscore_buga": "sbSEh0"})

    def test_every_other_identity_keeps_its_club_panel(self):
        for identity in (0, 14, 176, 229, 231, 252):
            with self.subTest(identity=identity):
                logos, _ = self.bound(("14", 4), ("07", 0), identities=(identity, identity))
                self.assertEqual(logos, {"hscore_buga": "sb14h0", "zscore_buga": "sb07h0"})
    # Revision 18 (and 17) installs read "previous": test_b780_pres2_pause_bar iterates EARLIER_REVISIONS.

if __name__ == "__main__":
    unittest.main()
