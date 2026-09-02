"""Headless tests for the guided XMA1 encoder setup wizard.

The wizard exists because no XMA1 encoder ships with the editor: first-time
audio replacement needs a user-supplied tool.  These tests pin the validation
logic (argument template checks, the one-second tone smoke test, and the
save gating) using mock encoder scripts, never a real encoder.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402
from mod_editor.apf_studio.gui import (  # noqa: E402
    Xma1EncoderSetupWizard,
    run_xma1_smoke_test,
    write_xma1_test_tone,
    xma1_encoder_argument_problem,
)


def _make_script(root: Path, name: str, behavior: str) -> Path:
    bodies = {
        "copy": "shutil.copyfile(sys.argv[1], sys.argv[2])\n",
        "placeholders": (
            "Path(sys.argv[2]).write_text('|'.join(sys.argv[3:6]), "
            "encoding='utf-8')\n"
            "shutil.copyfile(sys.argv[1], sys.argv[2] + '.tone')\n"
        ),
        "exit-2": "raise SystemExit(2)\n",
        "silent": "pass\n",
        "sleep": "time.sleep(5)\n",
    }
    script = root / f"{name}.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import shutil\n"
        "import sys\n"
        "import time\n"
        + bodies[behavior],
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _fixture_invocation(script: Path) -> tuple[Path, tuple[str, ...]]:
    """Run Python fixtures without relying on POSIX shebangs on Windows."""

    if os.name == "nt":
        return Path(sys.executable).resolve(), (str(script),)
    return script, ()


class ArgumentTemplateTests(unittest.TestCase):
    def test_the_recommended_template_is_accepted(self) -> None:
        self.assertIsNone(
            xma1_encoder_argument_problem(("{input}", "{output}"))
        )

    def test_empty_arguments_are_refused_plainly(self) -> None:
        problem = xma1_encoder_argument_problem(())
        assert problem is not None
        self.assertIn("{input} and {output}", problem)
        self.assertIn("recommended template", problem)

    def test_a_missing_input_placeholder_is_refused_plainly(self) -> None:
        problem = xma1_encoder_argument_problem(("--encode", "{output}"))
        assert problem is not None
        self.assertIn("{input}", problem)
        self.assertIn("exactly once", problem)
        self.assertIn("PCM WAV", problem)

    def test_a_duplicated_output_placeholder_is_refused_plainly(self) -> None:
        problem = xma1_encoder_argument_problem(
            ("{input}", "{output}", "--also={output}")
        )
        assert problem is not None
        self.assertIn("{output}", problem)
        self.assertIn("2 times", problem)


class TestToneTests(unittest.TestCase):
    def test_the_tone_is_one_second_of_pcm16_mono(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tone = write_xma1_test_tone(Path(directory) / "tone.wav")
            with wave.open(str(tone), "rb") as opened:
                self.assertEqual(opened.getnchannels(), 1)
                self.assertEqual(opened.getsampwidth(), 2)
                self.assertEqual(opened.getframerate(), 44100)
                self.assertEqual(opened.getnframes(), 44100)


class SmokeTestTests(unittest.TestCase):
    """The smoke test runs the user's tool on a private one-second tone."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xma1-wizard-")
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        self.addCleanup(self.temporary.cleanup)

    def test_a_working_encoder_passes_and_reports_its_output(self) -> None:
        script = _make_script(self.root, "good-encoder", "copy")
        encoder, leading = _fixture_invocation(script)
        result = run_xma1_smoke_test(
            executable=encoder,
            arguments=(*leading, "{input}", "{output}"),
            work_dir=self.work,
        )
        self.assertTrue(result.testable)
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)
        # One second of stereo-free PCM16 is exactly 88,200 bytes; the mock
        # copies the WAV, so the "XMA1" output must match the tone size.
        self.assertEqual(result.output_bytes, 44100 * 2 + 44)
        self.assertIn("Success", result.summary)

    def test_optional_placeholders_are_substituted(self) -> None:
        script = _make_script(self.root, "placeholder-encoder", "placeholders")
        encoder, leading = _fixture_invocation(script)
        result = run_xma1_smoke_test(
            executable=encoder,
            arguments=(
                *leading,
                "{input}",
                "{output}",
                "{channels}",
                "{sample_rate}",
                "{sample_count}",
            ),
            work_dir=self.work,
        )
        self.assertTrue(result.passed)
        output = self.work / "tone-output.xma"
        self.assertEqual(output.read_text(encoding="utf-8"), "1|44100|44100")

    def test_a_failing_exit_code_is_reported_with_a_fix(self) -> None:
        script = _make_script(self.root, "bad-encoder", "exit-2")
        encoder, leading = _fixture_invocation(script)
        result = run_xma1_smoke_test(
            executable=encoder,
            arguments=(*leading, "{input}", "{output}"),
            work_dir=self.work,
        )
        self.assertTrue(result.testable)
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 2)
        self.assertIn("exited with code 2", result.summary)
        self.assertIn("Fix:", result.summary)

    def test_a_clean_exit_without_output_is_reported_with_a_fix(self) -> None:
        script = _make_script(self.root, "silent-encoder", "silent")
        encoder, leading = _fixture_invocation(script)
        result = run_xma1_smoke_test(
            executable=encoder,
            arguments=(*leading, "{input}", "{output}"),
            work_dir=self.work,
        )
        self.assertFalse(result.passed)
        self.assertIn("did not write the {output} file", result.summary)
        self.assertIn("Fix:", result.summary)

    def test_an_encoded_size_template_cannot_be_tested_but_can_be_saved(self) -> None:
        script = _make_script(self.root, "sized-encoder", "copy")
        encoder, leading = _fixture_invocation(script)
        result = run_xma1_smoke_test(
            executable=encoder,
            arguments=(*leading, "{input}", "{output}", "{encoded_size}"),
            work_dir=self.work,
        )
        self.assertFalse(result.testable)
        self.assertFalse(result.passed)
        self.assertIn("{encoded_size}", result.summary)
        self.assertIn("can still save", result.summary)

    def test_a_missing_executable_is_reported_with_a_fix(self) -> None:
        result = run_xma1_smoke_test(
            executable=self.root / "does-not-exist",
            arguments=("{input}", "{output}"),
            work_dir=self.work,
        )
        self.assertTrue(result.testable)
        self.assertFalse(result.passed)
        self.assertIn("could not be started", result.summary)
        self.assertIn("Fix:", result.summary)

    def test_a_hung_encoder_times_out_with_a_fix(self) -> None:
        script = _make_script(self.root, "slow-encoder", "sleep")
        encoder, leading = _fixture_invocation(script)
        result = run_xma1_smoke_test(
            executable=encoder,
            arguments=(*leading, "{input}", "{output}"),
            work_dir=self.work,
            timeout_seconds=1,
        )
        self.assertFalse(result.passed)
        self.assertIn("did not finish", result.summary)
        self.assertIn("Fix:", result.summary)


@unittest.skipIf(
    os.name == "nt",
    "PyQt5 offscreen wizard construction is unstable on hosted Windows; "
    "the shell-free encoder smoke tests remain active there",
)
class WizardDialogTests(unittest.TestCase):
    """The dialog gates saving on a passed smoke test."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="xma1-wizard-ui-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def _wizard(self) -> Xma1EncoderSetupWizard:
        wizard = Xma1EncoderSetupWizard()
        self.addCleanup(wizard.deleteLater)
        return wizard

    def test_save_is_locked_until_the_tone_test_passes(self) -> None:
        script = _make_script(self.root, "ui-encoder", "copy")
        encoder, leading = _fixture_invocation(script)
        wizard = self._wizard()
        # Never silent-gray: buttons stay clickable with disableReason walls.
        self.assertTrue(wizard.save_button.isEnabled())
        self.assertTrue(
            str(wizard.save_button.property("disableReason") or "").strip()
        )
        self.assertTrue(wizard.test_button.isEnabled())
        self.assertTrue(
            str(wizard.test_button.property("disableReason") or "").strip()
        )

        wizard.encoder_path.setText(str(encoder))
        wizard.arguments_editor.setPlainText(
            "\n".join((*leading, "{input}", "{output}"))
        )
        self.assertTrue(wizard.test_button.isEnabled())
        self.assertFalse(
            str(wizard.test_button.property("disableReason") or "").strip()
        )
        # Still blocked for Save: no test run yet (disableReason, not gray).
        self.assertTrue(wizard.save_button.isEnabled())
        self.assertTrue(
            str(wizard.save_button.property("disableReason") or "").strip()
        )

        wizard._run_smoke_test()
        self.assertIn("Success", wizard.test_result.text())
        self.assertTrue(wizard._smoke_passed)
        self.assertTrue(wizard.save_button.isEnabled())
        self.assertFalse(
            str(wizard.save_button.property("disableReason") or "").strip()
        )

        # Changing the arguments voids the passed test.
        wizard.arguments_editor.setPlainText("{input}")
        self.assertFalse(wizard._smoke_passed)
        self.assertTrue(wizard.save_button.isEnabled())
        self.assertTrue(
            str(wizard.save_button.property("disableReason") or "").strip()
        )

    def test_accepting_builds_a_validated_encoder(self) -> None:
        script = _make_script(self.root, "accept-encoder", "copy")
        encoder, leading = _fixture_invocation(script)
        wizard = self._wizard()
        wizard.encoder_path.setText(str(encoder))
        wizard.arguments_editor.setPlainText(
            "\n".join((*leading, "{input}", "{output}"))
        )
        wizard._run_smoke_test()
        self.assertTrue(wizard._smoke_passed)
        wizard._accept_configuration()
        configured = wizard.encoder
        self.assertEqual(configured.executable, encoder.resolve())
        self.assertEqual(
            configured.arguments, (*leading, "{input}", "{output}")
        )
        self.assertIsNone(configured.wine_executable)

    def test_recommended_template_button_fills_the_placeholders(self) -> None:
        wizard = self._wizard()
        wizard.arguments_editor.setPlainText("nonsense")
        wizard._use_recommended_template()
        self.assertEqual(
            wizard.arguments_editor.toPlainText(), "{input}\n{output}"
        )
        self.assertEqual(
            wizard._current_arguments(), ("{input}", "{output}")
        )

    def test_an_untestable_template_unlocks_saving_with_an_explanation(self) -> None:
        script = _make_script(self.root, "sized-ui-encoder", "copy")
        encoder, leading = _fixture_invocation(script)
        wizard = self._wizard()
        wizard.encoder_path.setText(str(encoder))
        wizard.arguments_editor.setPlainText(
            "\n".join((*leading, "{input}", "{output}", "{encoded_size}"))
        )
        wizard._run_smoke_test()
        self.assertFalse(wizard._smoke_passed)
        self.assertFalse(wizard._smoke_testable)
        self.assertIn("{encoded_size}", wizard.test_result.text())
        # Untestable does not mean refused: saving stays possible because the
        # real exact-slot gates still validate every genuine encode.
        self.assertTrue(wizard.save_button.isEnabled())

    def test_ffmpeg_status_reports_conversion_availability(self) -> None:
        with mock.patch.object(
            gui.audio_conform, "conversion_available", return_value=True
        ):
            wizard = self._wizard()
            self.assertIn("FFmpeg was found", wizard.ffmpeg_status.text())
        with mock.patch.object(
            gui.audio_conform, "conversion_available", return_value=False
        ):
            wizard = self._wizard()
            self.assertIn("FFmpeg was not found", wizard.ffmpeg_status.text())
            self.assertIn("Exact PCM16 WAVs work without it",
                          wizard.ffmpeg_status.text())


if __name__ == "__main__":
    unittest.main()
