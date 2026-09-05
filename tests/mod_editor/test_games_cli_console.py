"""``python -m mod_editor.games`` survives a console that cannot encode what a lane says.

A Windows console is cp1252 unless told otherwise, and a lane message may quote a
character outside it (a flipped pnach byte decodes to U+FFFD; upstream's own
labels carry a star).  The CLI must print an escape, not die with
UnicodeEncodeError part way through a report.  Nothing here touches this tree:
the module under test is scaffolded into a scratch root.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from mod_editor.games import __main__ as cli  # noqa: E402
from mod_editor.games import scaffold  # noqa: E402
from games_fakes import cli_command  # noqa: E402

STAR = "★"  # not in cp1252
REPLACEMENT = "�"  # what a flipped byte decodes to; not in cp1252 either


class TolerantConsoleTests(unittest.TestCase):
    def test_a_strict_cp1252_stdout_is_made_to_escape_instead_of_raising(self) -> None:
        raw = io.BytesIO()
        strict = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", write_through=True)
        saved = sys.stdout
        sys.stdout = strict
        try:
            with self.assertRaises(UnicodeEncodeError):
                print(REPLACEMENT)
            cli._tolerant_console()
            print(f"byte 0x118 flipped: {REPLACEMENT} {STAR}")
        finally:
            sys.stdout = saved
        self.assertIn(b"\\ufffd \\u2605", raw.getvalue())

    def test_streams_without_reconfigure_are_left_alone(self) -> None:
        saved = sys.stdout
        sys.stdout = io.StringIO()  # has no reconfigure(); must not raise
        try:
            cli._tolerant_console()
            print(STAR)
            self.assertEqual(sys.stdout.getvalue(), STAR + "\n")
        finally:
            sys.stdout = saved


class CommandLineOnACp1252ConsoleTests(unittest.TestCase):
    """The real command line, with the console forced to cp1252, listing a module whose title it cannot encode."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(tempfile.mkdtemp(prefix="cli-console-repo-"))
        scaffold.scaffold("demo_ps2", f"Demo Game {STAR} (PlayStation 2)", "PlayStation 2", "SLUS-00000",
                          console="PS2", game=f"Demo{STAR}", year="1", repo_root=cls.repo)
        cls.games_root = cls.repo / "mod_editor" / "games"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.repo, ignore_errors=True)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "QT_QPA_PLATFORM": "offscreen"}
        # --games-root belongs to the top-level parser, so it goes before the subcommand.
        return subprocess.run(cli_command("--games-root", str(self.games_root), *args),
                              cwd=str(ROOT), capture_output=True, timeout=300, env=env)

    def test_list_prints_an_escape_for_the_star_and_exits_zero(self) -> None:
        completed = self._run("list")
        out = completed.stdout.decode("cp1252", errors="replace")
        err = completed.stderr.decode("cp1252", errors="replace")
        self.assertEqual(completed.returncode, 0, out + err)
        self.assertNotIn("UnicodeEncodeError", err)
        self.assertIn("demo_ps2", out)
        self.assertIn("\\u2605", out)

    def test_show_does_too(self) -> None:
        completed = self._run("show", "demo_ps2")
        err = completed.stderr.decode("cp1252", errors="replace")
        self.assertEqual(completed.returncode, 0, completed.stdout.decode("cp1252", "replace") + err)
        self.assertIn("\\u2605", completed.stdout.decode("cp1252", errors="replace"))


if __name__ == "__main__":
    unittest.main()
