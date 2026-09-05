"""Commentary tab: write gating, list population and the copy-write path on a synthetic disc."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "tests", ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mod_editor.gui import commentary_panel_qt as panel_module  # noqa: E402
from mod_editor.gui.commentary_panel_qt import CommentaryPanel  # noqa: E402


class CommentaryPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_write_needs_source_stream_clip_and_a_different_target(self) -> None:
        panel = CommentaryPanel()
        try:
            self.assertFalse(panel.write_button.isEnabled())
            self.assertFalse(panel.list_button.isEnabled())
            panel.apply_source(Path("/nowhere/game.xiso.iso"), ["cutsceneaudio", "lines"], True)
            self.assertTrue(panel.list_button.isEnabled())
            self.assertFalse(panel.write_button.isEnabled())
            panel.apply_streams([{"stream": "cutsceneaudio:3", "duration_seconds": 5.605, "bytes": 69516}])
            panel.stream_list.setCurrentRow(0)
            self.assertEqual(panel.stream_field.text(), "cutsceneaudio:3")
            panel.audio_field.setText("/nowhere/me.wav")
            # a copy name is suggested beside the disc; clear it to check the no-target gate
            self.assertTrue(panel.target_field.text().endswith(" (commentary).xiso.iso"), panel.target_field.text())
            panel.target_field.setText("")
            self.assertFalse(panel.write_button.isEnabled())            # no target
            panel.target_field.setText("/nowhere/game.xiso.iso")        # same as source
            self.assertFalse(panel.write_button.isEnabled())
            panel.target_field.setText("/nowhere/copy.xiso.iso")
            self.assertTrue(panel.write_button.isEnabled())
            panel.stream_field.setText("garbage")
            self.assertFalse(panel.write_button.isEnabled())
            panel.stream_field.setText("lines:12")
            self.assertTrue(panel.write_button.isEnabled())
            panel.apply_source(Path("/nowhere/other.bin"), None, False)
            self.assertFalse(panel.write_button.isEnabled())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_perform_write_on_a_synthetic_disc(self) -> None:
        import nfl2k5_commentary_swap as cs
        import nfl2k5_commentary_swap_test as fixture
        import xbox_ima_encoder as ima

        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is not installed")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            retail_pcm = [fixture._tone(64 * 20, hz=220, seed=1), fixture._tone(64 * 40, hz=330, seed=2),
                          fixture._tone(64 * 10, hz=550, seed=3)]
            disc = fixture.SyntheticDisc(root, bank_payload=b"".join(ima.encode_stream(p, 1) for p in retail_pcm))
            clip = root / "me.wav"
            cs.write_wav(clip, fixture._tone(64 * 30, hz=880, seed=5), 1)
            target = root / "copy.xiso.iso"
            original = panel_module.swap_module
            panel_module.swap_module = lambda: _Pinned(cs, disc.descriptors)   # type: ignore[assignment]
            try:
                receipt = panel_module.perform_write(disc.path, target, "test:1", clip, disc.retail_packs)
            finally:
                panel_module.swap_module = original
            self.assertEqual(receipt["retail_gate"], "retail-packs")
            self.assertEqual(receipt["clip_frames"], 64 * 30)
            self.assertEqual(receipt["padded_silence_frames"], 64 * 10)
            self.assertTrue(target.is_file())
            # Source untouched, copy carries the clip.
            with cs.DiscBanks(disc.path, descriptors=disc.descriptors) as source:
                self.assertEqual(source.read_stream(source.stream("test", 1)), ima.encode_stream(retail_pcm[1], 1))
            with cs.DiscBanks(target, descriptors=disc.descriptors) as written:
                stream = written.stream("test", 1)
                decoded = cs.decode_payload(written.read_stream(stream), 1)
                _c, _r, clip_pcm = cs.read_wav(clip)
                # conform_clip fades 15 ms in/out, so compare the un-faded middle of the clip.
                skip = 400 * 2
                self.assertGreater(cs.snr_db(clip_pcm[skip:-skip], decoded[skip:len(clip_pcm) - skip]), 20.0)

    def test_studio_offers_the_tab(self) -> None:
        from mod_editor.gui.studio_qt import StudioMainWindow

        window = StudioMainWindow()
        try:
            self.assertEqual(len(window.findChildren(CommentaryPanel)), 1)
        finally:
            window.deleteLater()
            self.app.processEvents()


class _Pinned:
    """The swap module with the fixture's descriptor table pinned in."""

    def __init__(self, module, descriptors) -> None:
        self._module = module
        self._descriptors = descriptors

    def DiscBanks(self, path, **kwargs):  # noqa: N802 - mirrors the module API
        kwargs.setdefault("descriptors", self._descriptors)
        return self._module.DiscBanks(path, **kwargs)

    def replace_stream(self, *args, **kwargs):
        kwargs.setdefault("descriptors", self._descriptors)
        return self._module.replace_stream(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._module, name)


if __name__ == "__main__":
    unittest.main()
