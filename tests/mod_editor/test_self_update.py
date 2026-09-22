"""The in-app updater: what it installs, what it refuses, and how it hands off.

Nothing here touches the network or the real install. Downloads come from a
fake opener that streams local bytes, the "install" is a temp folder laid out
like a release, and every hand-off (installer start, relaunch, quit) is a stub
that records what it was asked to do.
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import self_update as U  # noqa: E402
from mod_editor.core import update_check  # noqa: E402

HOST = "https://github.com/cruuz/2k-football-mod-tools/releases/download/beta-99/"


class _FakeResponse:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self._buffer = io.BytesIO(payload)
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _opener(files: dict[str, bytes]):
    def open_url(url: str, timeout: float):
        name = url.rsplit("/", 1)[-1]
        if name not in files:
            raise U.urllib.error.URLError(f"no such asset {name}")
        return _FakeResponse(files[name])
    return open_url


def _sidecar(name: str, payload: bytes) -> bytes:
    return f"{hashlib.sha256(payload).hexdigest()}  {name}\n".encode()


def _document(files: dict[str, bytes], tag: str = "beta-99") -> dict:
    return {
        "tag_name": tag,
        "assets": [
            {"name": name, "browser_download_url": HOST + name, "size": len(payload)}
            for name, payload in files.items()
        ],
    }


def _make_tarball(top: str, files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(top)
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        archive.addfile(info)
        for relative, payload in files.items():
            info = tarfile.TarInfo(f"{top}/{relative}")
            info.size = len(payload)
            info.mode = 0o755 if relative.endswith(".sh") else 0o644
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


RELEASE_FILES = {
    "mod_editor/__init__.py": b"__version__ = 'test-version'\n",
    "mod_editor/__main__.py": b"print('new')\n",
    "mod_editor/gui/__init__.py": b"",
    "mod_editor/gui/studio_qt.py": b"",
    "tools/launch_2k5_mod_studio.sh": b"#!/bin/sh\n",
    "2K5-Mod-Studio.bat": b"@echo off\n",
}


def _tarball_install(parent: Path, name: str = "2K5-Mod-Studio-v1.0-RC80-2026-09-03") -> Path:
    root = parent / name
    for relative, payload in RELEASE_FILES.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload.replace(b"new", b"old"))
    return root


class InstallKindTests(unittest.TestCase):
    def test_a_git_checkout_is_never_self_updated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "repo"
            (root / ".git").mkdir(parents=True)
            (root / "tools").mkdir()
            (root / "tools" / "launch_2k5_mod_studio.sh").write_text("")
            kind = U.detect_install(root)
        self.assertEqual(kind.kind, "checkout")
        with self.assertRaises(U.SelfUpdateError):
            U.plan_update(_document({}), kind)

    def test_this_repository_is_detected_as_a_checkout(self) -> None:
        self.assertEqual(U.detect_install().kind, "checkout")

    def test_the_windows_installer_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve() / "2K5-Mod-Studio"
            (base / "runtime").mkdir(parents=True)
            (base / "runtime" / "pythonw.exe").write_bytes(b"MZ")
            (base / "app" / "mod_editor").mkdir(parents=True)
            (base / "app" / "mod_editor" / "__main__.py").write_text("")
            windows = U.detect_install(base / "app", platform="win32")
            posix = U.detect_install(base / "app", platform="linux")
        self.assertEqual(windows.kind, "windows-installer")
        self.assertEqual(windows.relaunch[0], str(base / "runtime" / "pythonw.exe"))
        self.assertEqual(windows.relaunch[1:], ("-m", "mod_editor", "--studio"))
        self.assertEqual(posix.kind, "unknown")

    def test_an_unpacked_release_folder_on_every_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _tarball_install(Path(tmp).resolve())
            for platform in ("linux", "darwin", "win32"):
                kind = U.detect_install(root, platform=platform, executable="/usr/bin/python3")
                self.assertEqual(kind.kind, "tarball", platform)
                self.assertEqual(kind.relaunch, ("/usr/bin/python3", "-m", "mod_editor", "--studio"))

    def test_the_apf_studio_uses_its_own_launcher_and_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "apf"
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "launch_apf2k8_mod_studio.sh").write_text("")
            kind = U.detect_install(root, "apf", platform="linux", executable="py")
        self.assertEqual(kind.kind, "tarball")
        self.assertEqual(kind.relaunch, ("py", "-m", "mod_editor.apf_studio"))


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _tarball_install(Path(self.tmp.name).resolve())
        self.tarball = U.detect_install(self.root, platform="linux")
        base = Path(self.tmp.name).resolve() / "win" / "2K5-Mod-Studio"
        (base / "runtime").mkdir(parents=True)
        (base / "runtime" / "pythonw.exe").write_bytes(b"MZ")
        (base / "app").mkdir()
        self.windows = U.detect_install(base / "app", platform="win32")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _assets(self) -> dict[str, bytes]:
        return {
            "2K5-Mod-Studio-1.0.0rc104-Setup.exe": b"exe",
            "2K5-Mod-Studio-1.0.0rc104-Setup.exe.sha256": b"x",
            "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz": b"tgz",
            "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz.sha256": b"x",
            "APF-2K8-Mod-Studio-0.9.0-Setup.exe": b"apf",
            "apf2k8-mod-studio-0.9.0.tar.gz": b"apf",
            "SOFTDRINK-patch-notes.md": b"...",
        }

    def test_each_install_kind_picks_its_own_file_and_sidecar(self) -> None:
        document = _document(self._assets())
        tar = U.plan_update(document, self.tarball)
        self.assertEqual(tar.asset.name, "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz")
        self.assertEqual(tar.sidecar.name, tar.asset.name + ".sha256")
        win = U.plan_update(document, self.windows)
        self.assertEqual(win.asset.name, "2K5-Mod-Studio-1.0.0rc104-Setup.exe")
        self.assertEqual(win.sidecar.name, win.asset.name + ".sha256")
        self.assertEqual(win.tag, "beta-99")

    def test_the_apf_product_never_takes_a_2k5_file(self) -> None:
        document = _document(self._assets())
        apf_root = Path(self.tmp.name).resolve() / "apf"
        (apf_root / "tools").mkdir(parents=True)
        (apf_root / "tools" / "launch_apf2k8_mod_studio.sh").write_text("")
        document["assets"].append({
            "name": "apf2k8-mod-studio-0.9.0.tar.gz.sha256",
            "browser_download_url": "https://example.invalid/apf.sha256",
            "size": 1,
        })
        plan = U.plan_update(document, U.detect_install(apf_root, "apf", platform="linux"), "apf")
        self.assertEqual(plan.asset.name, "apf2k8-mod-studio-0.9.0.tar.gz")

    def test_a_release_without_the_right_file_is_refused(self) -> None:
        document = _document({"SOFTDRINK-patch-notes.md": b"..."})
        with self.assertRaises(U.SelfUpdateError):
            U.plan_update(document, self.tarball)

    def test_an_unknown_layout_is_refused_with_advice(self) -> None:
        kind = U.InstallKind("unknown", self.root, ("python",), "no launcher")
        with self.assertRaises(U.SelfUpdateError) as caught:
            U.plan_update(_document(self._assets()), kind)
        self.assertIn("GitHub", str(caught.exception))

    def test_only_repository_hosted_assets_survive_the_check(self) -> None:
        document = {
            "tag_name": "beta-99",
            "assets": [
                {"name": "2K5-Mod-Studio-v1.0-RC100-x.tar.gz", "browser_download_url": "https://evil.invalid/a.tar.gz", "size": 3},
                {"name": "2K5-Mod-Studio-v1.0-RC100-y.tar.gz", "browser_download_url": HOST + "y.tar.gz", "size": 3},
            ],
        }
        rows = update_check._assets(document)
        self.assertEqual([row["name"] for row in rows], ["2K5-Mod-Studio-v1.0-RC100-y.tar.gz"])
        status = update_check.UpdateStatus(True, "beta-56", "beta-99", assets=rows, checked=True)
        self.assertEqual(status.release_document()["assets"][0]["size"], 3)


class DownloadTests(unittest.TestCase):
    def test_a_download_is_verified_against_its_sidecar(self) -> None:
        payload = os.urandom(3 * U.CHUNK + 17)
        files = {"a.tar.gz": payload, "a.tar.gz.sha256": _sidecar("a.tar.gz", payload)}
        document = _document(files)
        assets = U.release_assets(document)
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            plan = U.UpdatePlan("2k5", "beta-99", U.InstallKind("tarball", Path(tmp).resolve(), ("x",)), assets[0], assets[1])
            path = U.fetch_update(plan, Path(tmp).resolve() / "work", progress=lambda *a: seen.append(a), opener=_opener(files))
            self.assertEqual(path.read_bytes(), payload)
            self.assertFalse(path.with_name(path.name + ".part").exists())
        self.assertEqual(seen[-1][0], "Verified")
        self.assertTrue(any(done == len(payload) for _m, done, _t in seen))

    def test_a_tampered_download_is_discarded(self) -> None:
        payload = b"good" * 1000
        files = {"a.tar.gz": b"evil" * 1000, "a.tar.gz.sha256": _sidecar("a.tar.gz", payload)}
        assets = U.release_assets(_document(files))
        with tempfile.TemporaryDirectory() as tmp:
            plan = U.UpdatePlan("2k5", "beta-99", U.InstallKind("tarball", Path(tmp).resolve(), ("x",)), assets[0], assets[1])
            with self.assertRaises(U.SelfUpdateError) as caught:
                U.fetch_update(plan, Path(tmp).resolve() / "work", opener=_opener(files))
            self.assertFalse((Path(tmp).resolve() / "work" / "a.tar.gz").exists())
        self.assertIn("SHA-256", str(caught.exception))

    def test_a_short_download_is_refused(self) -> None:
        payload = b"x" * 100
        files = {"a.tar.gz": payload[:50], "a.tar.gz.sha256": _sidecar("a.tar.gz", payload)}
        document = _document({"a.tar.gz": payload, "a.tar.gz.sha256": files["a.tar.gz.sha256"]})
        assets = U.release_assets(document)
        with tempfile.TemporaryDirectory() as tmp:
            plan = U.UpdatePlan("2k5", "beta-99", U.InstallKind("tarball", Path(tmp).resolve(), ("x",)), assets[0], assets[1])
            with self.assertRaises(U.SelfUpdateError) as caught:
                U.fetch_update(plan, Path(tmp).resolve() / "work", opener=_opener(files))
        self.assertIn("100", str(caught.exception))

    def test_no_sidecar_means_no_install(self) -> None:
        files = {"a.tar.gz": b"x"}
        assets = U.release_assets(_document(files))
        with tempfile.TemporaryDirectory() as tmp:
            plan = U.UpdatePlan("2k5", "beta-99", U.InstallKind("tarball", Path(tmp).resolve(), ("x",)), assets[0], None)
            with self.assertRaises(U.SelfUpdateError):
                U.fetch_update(plan, Path(tmp).resolve() / "work", opener=_opener(files))

    def test_the_sidecar_must_name_the_file(self) -> None:
        digest = hashlib.sha256(b"x").hexdigest()
        self.assertEqual(U.parse_sidecar(f"{digest}  a.tar.gz\n", "a.tar.gz"), digest)
        self.assertEqual(U.parse_sidecar(f"{digest} *a.tar.gz\n", "a.tar.gz"), digest)
        with self.assertRaises(U.SelfUpdateError):
            U.parse_sidecar(f"{digest}  other.tar.gz\n", "a.tar.gz")


class TarballApplyTests(unittest.TestCase):
    def test_the_folder_is_swapped_and_the_new_copy_started(self) -> None:
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC100-2026-09-09", RELEASE_FILES)
        name = "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz"
        files = {name: payload, name + ".sha256": _sidecar(name, payload)}
        started = []
        with tempfile.TemporaryDirectory() as tmp:
            root = _tarball_install(Path(tmp).resolve())
            install = U.detect_install(root, platform="linux", executable=sys.executable)
            plan = U.run_update(_document(files), install=install, work=Path(tmp).resolve() / "dl",
                                opener=_opener(files), spawn_tarball=lambda cmd, cwd: started.append((cmd, cwd)))
            self.assertEqual((root / "mod_editor" / "__main__.py").read_text(), "print('new')\n")
            previous = root.with_name(root.name + ".previous")
            self.assertEqual((previous / "mod_editor" / "__main__.py").read_text(), "print('old')\n")
            self.assertTrue(os.access(root / "tools" / "launch_2k5_mod_studio.sh", os.X_OK))
            self.assertFalse((Path(tmp).resolve() / (root.name + ".new")).exists())
        self.assertEqual(started, [([str(Path(sys.executable)), "-m", "mod_editor", "--studio"], root)])
        self.assertTrue(any("previous" in note for note in plan.notes))

    def test_a_second_update_keeps_both_previous_copies(self) -> None:
        payload = _make_tarball("top", RELEASE_FILES)
        with tempfile.TemporaryDirectory() as tmp:
            root = _tarball_install(Path(tmp).resolve())
            previous = root.with_name(root.name + ".previous")
            previous.mkdir()
            (previous / "stale").write_text("")
            plan = U.UpdatePlan("2k5", "beta-99", U.detect_install(root, platform="linux"), U.ReleaseAsset("t", HOST + "t", 1), None)
            tarball = Path(tmp).resolve() / "t.tar.gz"
            tarball.write_bytes(payload)
            U.apply_tarball(plan, tarball, spawn=lambda *_a: None)
            self.assertTrue((previous / "stale").exists())
            backups = list(root.parent.glob(root.name + ".previous-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0] / "2K5-Mod-Studio.bat").exists())

    def test_a_folder_that_cannot_be_renamed_stays_usable(self) -> None:
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC100-2026-09-09", RELEASE_FILES)
        started = []
        with tempfile.TemporaryDirectory() as tmp:
            root = _tarball_install(Path(tmp).resolve())
            plan = U.UpdatePlan("2k5", "beta-99", U.detect_install(root, platform="linux"), U.ReleaseAsset("t", HOST + "t", 1), None)
            tarball = Path(tmp).resolve() / "t.tar.gz"
            tarball.write_bytes(payload)
            real_rename = os.replace

            def refuse(src, dst):
                if Path(src) == root:
                    raise PermissionError("in use")
                return real_rename(src, dst)

            with unittest.mock.patch.object(U.os, "replace", refuse):
                with self.assertRaisesRegex(U.SelfUpdateError, "old version is unchanged"):
                    U.apply_tarball(plan, tarball, spawn=lambda cmd, cwd: started.append(cwd))
            self.assertEqual((root / "mod_editor" / "__main__.py").read_text(), "print('old')\n")
            self.assertEqual(started, [])

    def test_hostile_archives_are_refused(self) -> None:
        def archive_with(name: str, link: bool = False) -> bytes:
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                info = tarfile.TarInfo("top/mod_editor/__main__.py")
                info.size = 0
                archive.addfile(info, io.BytesIO(b""))
                info = tarfile.TarInfo(name)
                if link:
                    info.type = tarfile.SYMTYPE
                    info.linkname = "/etc/passwd"
                else:
                    info.size = 0
                archive.addfile(info, io.BytesIO(b""))
            return buffer.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            for bad, link in (("top/../escape", False), ("/abs", False), ("other/x", False), ("top/link", True)):
                tarball = Path(tmp).resolve() / "t.tar.gz"
                tarball.write_bytes(archive_with(bad, link))
                with self.assertRaises(U.SelfUpdateError, msg=bad):
                    U.unpack_tarball(tarball, Path(tmp).resolve() / "out")

    def test_an_unwritable_parent_is_explained(self) -> None:
        if sys.platform.startswith("win"):
            self.skipTest("a read-only folder bit does not stop writes on Windows")
        if getattr(os, "geteuid", lambda: -1)() == 0:
            self.skipTest("root can write anywhere")
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve() / "locked"
            root = _tarball_install(parent)
            parent.chmod(0o555)
            try:
                plan = U.UpdatePlan("2k5", "beta-99", U.detect_install(root, platform="linux"), U.ReleaseAsset("t", HOST + "t", 1), None)
                with self.assertRaises(U.SelfUpdateError) as caught:
                    U.apply_tarball(plan, Path(tmp).resolve() / "missing.tar.gz", spawn=lambda *_a: None)
            finally:
                parent.chmod(0o755)
        self.assertIn("not writable", str(caught.exception))


class WindowsApplyTests(unittest.TestCase):
    def test_the_installer_is_started_silently_with_wait_and_relaunch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve() / "Programs" / "2K5 Mod Studio"
            (base / "runtime").mkdir(parents=True)
            (base / "runtime" / "pythonw.exe").write_bytes(b"MZ")
            (base / "app").mkdir()
            install = U.detect_install(base / "app", platform="win32")
            installer = Path(tmp).resolve() / "dl" / "2K5-Mod-Studio-1.0.0rc104-Setup.exe"
            installer.parent.mkdir()
            installer.write_bytes(b"MZ")
            plan = U.UpdatePlan("2k5", "beta-99", install, U.ReleaseAsset(installer.name, HOST + installer.name, 2), None)
            spawned = []
            command = U.apply_windows_installer(plan, installer, pid=4242, spawn=spawned.append)
        self.assertEqual(spawned, [command])
        self.assertEqual(command, f'"{installer}" /S /WAITPID=4242 /RELAUNCH /D={base}')
        # NSIS rules: /D= is last and unquoted even though the path has a space.
        self.assertTrue(command.endswith(f"/D={base}"))
        self.assertNotIn(f'"/D=', command)

    def test_the_installer_template_implements_both_switches(self) -> None:
        sys.path.insert(0, str(REPO / "packaging" / "windows"))
        import build_windows_installer as B  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            script = B.render_nsis(B.PRODUCTS["2k5"], "1.0.0rc104", Path(tmp).resolve(), None, Path(tmp).resolve())
        self.assertIn('!include "FileFunc.nsh"', script)
        self.assertIn('${GetOptions} $R0 "/WAITPID=" $R1', script)
        self.assertIn("kernel32::WaitForSingleObject", script)
        self.assertIn('${GetOptions} $R0 "/RELAUNCH" $R1', script)
        self.assertIn("Function .onInstSuccess", script)
        self.assertIn('Exec \'"$INSTDIR\\runtime\\pythonw.exe" -m mod_editor --studio\'', script)
        apf = B.render_nsis(B.PRODUCTS["apf"], "0.9.0", Path("/w"), None, Path("/o"))
        self.assertIn('Exec \'"$INSTDIR\\runtime\\pythonw.exe" -m mod_editor.apf_studio\'', apf)


class BannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from mod_editor.gui import update_ui
        self.update_ui = update_ui
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _tarball_install(Path(self.tmp.name).resolve())
        self.install = U.detect_install(self.root, platform="linux", executable=sys.executable)

    def tearDown(self) -> None:
        self.app.processEvents()
        self.tmp.cleanup()

    def _banner(self):
        banner = self.update_ui.UpdateBanner()
        banner._install = self.install
        banner.confirm = lambda plan: True
        banner.quits = []
        banner.request_quit = lambda: banner.quits.append(True)
        return banner

    def _status(self, files: dict[str, bytes]) -> update_check.UpdateStatus:
        rows = update_check._assets(_document(files))
        return update_check.UpdateStatus(True, "beta-56", "beta-99", title="notes", checked=True, assets=rows)

    def test_update_now_is_only_offered_when_the_release_fits_this_install(self) -> None:
        banner = self._banner()
        banner.show_status(self._status({"SOFTDRINK-patch-notes.md": b"..."}))
        self.assertFalse(banner.update_button.isVisibleTo(banner))
        name = "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz"
        banner.show_status(self._status({name: b"x", name + ".sha256": b"y"}))
        self.assertTrue(banner.update_button.isVisibleTo(banner))
        checkout = self.update_ui.UpdateBanner()
        self.assertEqual(checkout.install.kind, "checkout")
        self.assertFalse(checkout.can_self_update(self._status({name: b"x", name + ".sha256": b"y"})))
        banner.deleteLater()
        checkout.deleteLater()

    def test_the_whole_flow_runs_off_the_gui_thread_and_asks_to_quit(self) -> None:
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC100-2026-09-09", RELEASE_FILES)
        name = "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz"
        files = {name: payload, name + ".sha256": _sidecar(name, payload)}
        banner = self._banner()
        banner.show_status(self._status(files))
        started = []
        ready = []
        banner.update_ready.connect(ready.append)
        real_run = U.run_update

        def run_update(document, product="2k5", **kw):
            kw["opener"] = _opener(files)
            kw["spawn_tarball"] = lambda cmd, cwd: started.append((cmd, cwd))
            kw["work"] = Path(self.tmp.name).resolve() / "dl"
            return real_run(document, product, **kw)

        with unittest.mock.patch.object(self.update_ui.self_update, "run_update", run_update):
            self.assertTrue(banner.start_update())
            self.assertFalse(banner.update_button.isEnabled())
            self.assertTrue(banner.wait_idle())
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].tag, "beta-99")
        self.assertEqual(started, [([str(Path(sys.executable)), "-m", "mod_editor", "--studio"], self.root)])
        self.assertEqual((self.root / "mod_editor" / "__main__.py").read_text(), "print('new')\n")
        self.assertIn("beta-99 is installed", banner.message.text())
        # The quit is a timer so the message is seen; fire it.
        deadline = 3000
        while not banner.quits and deadline > 0:
            self.app.processEvents()
            import time
            time.sleep(0.05)
            deadline -= 50
        self.assertEqual(banner.quits, [True])
        banner.deleteLater()

    def test_a_failed_update_is_one_sentence_and_the_buttons_come_back(self) -> None:
        name = "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz"
        files = {name: b"evil", name + ".sha256": _sidecar(name, b"good")}
        banner = self._banner()
        banner.show_status(self._status(files))
        real_run = U.run_update

        def run_update(document, product="2k5", **kw):
            kw["opener"] = _opener(files)
            kw["work"] = Path(self.tmp.name).resolve() / "dl"
            return real_run(document, product, **kw)

        with unittest.mock.patch.object(self.update_ui.self_update, "run_update", run_update):
            self.assertTrue(banner.start_update())
            self.assertTrue(banner.wait_idle())
        self.assertIn("SHA-256", banner.last_error)
        self.assertIn("did not install", banner.message.text())
        self.assertTrue(banner.update_button.isEnabled())
        self.assertEqual(banner.quits, [])
        self.assertEqual((self.root / "mod_editor" / "__main__.py").read_text(), "print('old')\n")
        banner.deleteLater()

    def _release_files(self) -> dict[str, bytes]:
        name = "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz"
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC100-2026-09-09", RELEASE_FILES)
        return {name: payload, name + ".sha256": _sidecar(name, payload)}

    def test_the_window_is_asked_about_unsaved_work_before_anything_is_spawned(self) -> None:
        # The installer waits for this process to exit, so the question has to
        # be answered before the hand-off, not underneath a banner that has
        # already said the studio is closing.
        window = _ParentWindow()
        banner = self._banner()
        banner.setParent(window)
        banner.show_status(self._status(self._release_files()))
        order: list[str] = []
        answered = window.prepare_for_update_quit

        def watched(proceed):
            order.append("asked")
            answered(proceed)

        window.prepare_for_update_quit = watched
        with unittest.mock.patch.object(self.update_ui.self_update, "run_update") as run:
            run.side_effect = lambda *a, **k: order.append("ran")
            self.assertTrue(banner.start_update())
            self.assertTrue(banner.wait_idle())
        self.assertEqual(order, ["asked", "ran"])
        self.assertEqual(window.asked, 1)
        banner.setParent(None)
        banner.deleteLater()
        window.deleteLater()

    def test_cancelling_the_unsaved_question_spawns_nothing(self) -> None:
        window = _ParentWindow(answer=False)
        banner = self._banner()
        banner.setParent(window)
        banner.show_status(self._status(self._release_files()))
        with unittest.mock.patch.object(self.update_ui.self_update, "run_update") as run:
            self.assertFalse(banner.start_update())
        run.assert_not_called()
        self.assertEqual(window.asked, 1)
        self.assertTrue(banner.update_button.isEnabled())
        banner.setParent(None)
        banner.deleteLater()
        window.deleteLater()

    def test_declining_the_confirmation_does_nothing(self) -> None:
        name = "2K5-Mod-Studio-v1.0-RC100-2026-09-09.tar.gz"
        banner = self._banner()
        banner.confirm = lambda plan: False
        banner.show_status(self._status({name: b"x", name + ".sha256": b"y"}))
        with unittest.mock.patch.object(self.update_ui.self_update, "run_update") as run:
            self.assertFalse(banner.start_update())
        run.assert_not_called()
        self.assertTrue(banner.update_button.isEnabled())
        banner.deleteLater()


import unittest.mock  # noqa: E402  (used by the apply tests)


def _installer_builder():
    sys.path.insert(0, str(REPO / "packaging" / "windows"))
    import build_windows_installer as B  # noqa: E402

    return B


class InstallerReplacesTheTreeTests(unittest.TestCase):
    """The installer must replace the installed trees, not merge into them.

    ``File /r`` overwrites what it ships and removes nothing else, so an update
    used to leave the previous release's ``__pycache__`` behind. With every
    staged file's mtime flattened to one constant that every release shared,
    CPython read that stale bytecode instead of the new source and the studio
    came back reporting the version it had just replaced.
    """

    def _script(self, product: str = "2k5") -> str:
        B = _installer_builder()
        with tempfile.TemporaryDirectory() as tmp:
            return B.render_nsis(B.PRODUCTS[product], "1.0.0rc102",
                                 Path(tmp).resolve(), None, Path(tmp).resolve())

    def test_the_install_section_clears_both_trees_before_extracting(self) -> None:
        for product in ("2k5", "apf"):
            with self.subTest(product=product):
                section = self._script(product).split('Section "Install"', 1)[1]
                section = section.split("SectionEnd", 1)[0]
                first_file = section.index("File /r ")
                self.assertLess(section.index(r'RMDir /r "$INSTDIR\app"'), first_file)
                self.assertLess(section.index(r'RMDir /r "$INSTDIR\runtime"'), first_file)

    def test_the_uninstaller_still_removes_only_what_it_created(self) -> None:
        # The delete above must not have been copied out of the Uninstall
        # section: that one is still the only place $INSTDIR itself goes.
        section = self._script().split('Section "Uninstall"', 1)[1]
        self.assertIn(r'RMDir "$INSTDIR"', section)
        self.assertNotIn(r'RMDir /r "$INSTDIR"' + "\n", section)


class SourceDateEpochTests(unittest.TestCase):
    """Every release gets its own stamp, and the same version always its own."""

    def test_each_version_gets_a_different_instant(self) -> None:
        B = _installer_builder()
        versions = ("1.0.0rc99", "1.0.0rc100", "1.0.0rc101", "1.0.0rc102", "0.9.0")
        stamps = {version: B.source_date_epoch(version) for version in versions}
        self.assertEqual(len(set(stamps.values())), len(versions))

    def test_one_version_always_rebuilds_to_the_same_instant(self) -> None:
        B = _installer_builder()
        self.assertEqual(B.source_date_epoch("1.0.0rc101"), B.source_date_epoch("1.0.0rc101"))

    def test_no_stamp_is_in_the_future(self) -> None:
        B = _installer_builder()
        for version in ("1.0.0rc101", "1.0.0rc102", "0.9.0", "2.0"):
            stamp = B.source_date_epoch(version)
            self.assertLessEqual(stamp, B.SOURCE_DATE_EPOCH_ANCHOR)
            self.assertGreater(stamp, B.SOURCE_DATE_EPOCH_ANCHOR - B.SOURCE_DATE_EPOCH_WINDOW)

    def test_the_whole_staged_tree_is_flattened_to_it(self) -> None:
        B = _installer_builder()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "work"
            (root / "app" / "mod_editor").mkdir(parents=True)
            (root / "app" / "mod_editor" / "__init__.py").write_text("x\n")
            (root / "runtime").mkdir()
            (root / "runtime" / "python.exe").write_bytes(b"MZ")
            stamp = B.source_date_epoch("1.0.0rc102")
            B.normalise_mtimes(root, stamp)
            for path in [root, *root.rglob("*")]:
                self.assertEqual(int(path.stat().st_mtime), stamp, path)


class StaleBytecodeTests(unittest.TestCase):
    """Why a shared stamp broke the update, in one interpreter and no Windows.

    ``mod_editor/core/update_check.py`` is 8334 bytes in every release from
    beta 68 to beta 74, because only the tag inside ``BUILD_RELEASE_TAG``
    changes and every published tag is the same length. A timestamp ``.pyc``
    is validated on the source's mtime and size alone, so a release that
    landed with its predecessor's mtime was invisible to the import system.
    """

    OLD = 'TAG = "beta-73"\n'
    NEW = 'TAG = "beta-74"\n'

    def _import_tag(self, folder: Path, text: str, stamp: int) -> str:
        source = folder / "pinned.py"
        source.write_text(text, encoding="utf-8")
        os.utime(source, (stamp, stamp))
        environment = dict(os.environ)
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                "import pinned; sys.stdout.write(pinned.TAG)")
        result = subprocess.run([sys.executable, "-c", code, str(folder)],
                                capture_output=True, text=True, env=environment, check=True)
        return result.stdout.strip()

    def test_the_two_releases_are_the_same_size(self) -> None:
        self.assertEqual(len(self.OLD), len(self.NEW))

    def test_a_same_size_same_stamp_rewrite_keeps_the_old_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            shared = 1785110400  # the one constant every release used to share
            self.assertEqual(self._import_tag(folder, self.OLD, shared), "beta-73")
            self.assertTrue((folder / "__pycache__").is_dir())
            # Exactly what the merged install produced: new source on disk,
            # previous release's bytecode still considered valid.
            self.assertEqual(self._import_tag(folder, self.NEW, shared), "beta-73")

    def test_a_per_release_stamp_lets_the_new_source_win(self) -> None:
        B = _installer_builder()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            self.assertEqual(
                self._import_tag(folder, self.OLD, B.source_date_epoch("1.0.0rc100")), "beta-73")
            self.assertEqual(
                self._import_tag(folder, self.NEW, B.source_date_epoch("1.0.0rc101")), "beta-74")

    def test_the_release_tag_can_never_change_the_module_size(self) -> None:
        # This is why update_check.py was the guaranteed casualty rather than
        # an unlucky one, and why the stamp had to carry the difference. The
        # live tag can itself now be a longer hotfix tag (beta-74.1 onward),
        # so this compares same-length samples against each other rather
        # than against the live file, whose own tag length is no longer fixed.
        text = (REPO / "mod_editor" / "core" / "update_check.py").read_text(encoding="utf-8")
        lengths = set()
        for tag in ("beta-68", "beta-73", "beta-74", "beta-99"):
            rewritten = re.sub(r'BUILD_RELEASE_TAG = "[^"]*"',
                               f'BUILD_RELEASE_TAG = "{tag}"', text, count=1)
            lengths.add(len(rewritten.encode("utf-8")))
        self.assertEqual(len(lengths), 1)


def _ParentWindow(answer: bool = True):
    """A window that answers the banner's prepare_for_update_quit contract."""

    from PyQt5.QtWidgets import QMainWindow

    class ParentWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.asked = 0

        def prepare_for_update_quit(self, proceed) -> None:
            self.asked += 1
            if answer:
                proceed()

    return ParentWindow()


class StudioUpdateQuitTests(unittest.TestCase):
    """The real 2K5 window: asked once, then closes with nothing in the way."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, folder: Path):
        # The same lean construction tests/mod_editor/test_beta69_studios_offscreen.py
        # uses: metadata-only catalogs and no disc.
        from mod_editor.gui.studio_qt import StudioMainWindow, BrowseOnlyFacade
        from mod_editor.core import nfl2k5_uniform_catalog as uniform_module
        from mod_editor.core.nfl2k5_uniform_catalog import Nfl2k5UniformCatalog
        from mod_editor.core.nfl2k5_extended_visual_catalog import (
            Nfl2k5ExtendedVisualCatalog, VisualReportPaths,
        )
        with unittest.mock.patch.object(uniform_module, "EXPECTED_SET_COUNT", 0):
            return StudioMainWindow(
                facade=BrowseOnlyFacade(),
                uniform_catalog=Nfl2k5UniformCatalog((), (), folder / "catalog.json"),
                extended_visual_catalog=Nfl2k5ExtendedVisualCatalog((), VisualReportPaths()),
                offer_recovery=False,
            )

    def test_a_dirty_workspace_is_asked_once_and_then_closes(self) -> None:
        from PyQt5.QtCore import QSettings
        from PyQt5.QtGui import QCloseEvent
        with tempfile.TemporaryDirectory(prefix="b741-studio-") as tmp:
            QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
            window = self._window(Path(tmp).resolve())
            try:
                window._workspace_dirty = True
                asked: list[str] = []

                def answer(context: str) -> str:
                    asked.append(context)
                    return "discard"

                window._prompt_unsaved_decision = answer  # type: ignore[assignment]
                went: list[bool] = []
                window.prepare_for_update_quit(lambda: went.append(True))
                # Asked once, before the update starts, and answering it is
                # what lets the update start at all.
                self.assertEqual(len(asked), 1)
                self.assertEqual(went, [True])
                self.assertTrue(window._allow_close)

                def never(context: str) -> str:
                    raise AssertionError(f"asked a second time: {context}")

                window._prompt_unsaved_decision = never  # type: ignore[assignment]
                # The close that follows the hand-off asks nothing: not about
                # unsaved work, not about a blocking operation. In beta 74 this
                # is where the save prompt appeared, underneath a banner that
                # had already said the studio was closing.
                window._workspace_dirty = True
                window._blocking = True
                event = QCloseEvent()
                window.closeEvent(event)
                self.assertTrue(event.isAccepted())
            finally:
                window._allow_close = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_the_banner_finds_the_hook_on_the_studio_it_lives_in(self) -> None:
        # The banner asks self.window(), so a reparenting that put it outside
        # the main window would silently go back to spawning first and asking
        # afterwards. Nothing else would fail.
        with tempfile.TemporaryDirectory(prefix="b741-wiring-") as tmp:
            from PyQt5.QtCore import QSettings
            QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
            window = self._window(Path(tmp).resolve())
            try:
                banner = window._update_banner
                self.assertIs(banner.window(), window)
                self.assertTrue(callable(getattr(banner.window(), "prepare_for_update_quit", None)))
            finally:
                window._allow_close = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_a_busy_studio_refuses_the_update_instead_of_starting_one(self) -> None:
        # The drain fences that defer a close are left alone; an update that
        # would meet one is never started, so the installer never waits on a
        # studio that cannot close.
        with tempfile.TemporaryDirectory(prefix="b741-busy-") as tmp:
            from PyQt5.QtCore import QSettings
            QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)
            window = self._window(Path(tmp).resolve())
            try:
                window._blocking = True
                went: list[bool] = []
                with unittest.mock.patch(
                    "mod_editor.gui.studio_qt.QMessageBox.information"
                ) as told:
                    window.prepare_for_update_quit(lambda: went.append(True))
                self.assertEqual(went, [])
                self.assertFalse(window._allow_close)
                told.assert_called_once()
            finally:
                window._allow_close = True
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
