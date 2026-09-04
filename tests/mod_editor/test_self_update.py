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
    "mod_editor/__init__.py": b"",
    "mod_editor/__main__.py": b"print('new')\n",
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
            "2K5-Mod-Studio-1.0.0rc99-Setup.exe": b"exe",
            "2K5-Mod-Studio-1.0.0rc99-Setup.exe.sha256": b"x",
            "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz": b"tgz",
            "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz.sha256": b"x",
            "APF-2K8-Mod-Studio-0.9.0-Setup.exe": b"apf",
            "apf2k8-mod-studio-0.9.0.tar.gz": b"apf",
            "SOFTDRINK-patch-notes.md": b"...",
        }

    def test_each_install_kind_picks_its_own_file_and_sidecar(self) -> None:
        document = _document(self._assets())
        tar = U.plan_update(document, self.tarball)
        self.assertEqual(tar.asset.name, "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz")
        self.assertEqual(tar.sidecar.name, tar.asset.name + ".sha256")
        win = U.plan_update(document, self.windows)
        self.assertEqual(win.asset.name, "2K5-Mod-Studio-1.0.0rc99-Setup.exe")
        self.assertEqual(win.sidecar.name, win.asset.name + ".sha256")
        self.assertEqual(win.tag, "beta-99")

    def test_the_apf_product_never_takes_a_2k5_file(self) -> None:
        document = _document(self._assets())
        apf_root = Path(self.tmp.name).resolve() / "apf"
        (apf_root / "tools").mkdir(parents=True)
        (apf_root / "tools" / "launch_apf2k8_mod_studio.sh").write_text("")
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
                {"name": "2K5-Mod-Studio-v1.0-RC99-x.tar.gz", "browser_download_url": "https://evil.invalid/a.tar.gz", "size": 3},
                {"name": "2K5-Mod-Studio-v1.0-RC99-y.tar.gz", "browser_download_url": HOST + "y.tar.gz", "size": 3},
            ],
        }
        rows = update_check._assets(document)
        self.assertEqual([row["name"] for row in rows], ["2K5-Mod-Studio-v1.0-RC99-y.tar.gz"])
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
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC99-2026-09-09", RELEASE_FILES)
        name = "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz"
        files = {name: payload, name + ".sha256": _sidecar(name, payload)}
        started = []
        with tempfile.TemporaryDirectory() as tmp:
            root = _tarball_install(Path(tmp).resolve())
            install = U.detect_install(root, platform="linux", executable="python3")
            plan = U.run_update(_document(files), install=install, work=Path(tmp).resolve() / "dl",
                                opener=_opener(files), spawn_tarball=lambda cmd, cwd: started.append((cmd, cwd)))
            self.assertEqual((root / "mod_editor" / "__main__.py").read_text(), "print('new')\n")
            previous = root.with_name(root.name + ".previous")
            self.assertEqual((previous / "mod_editor" / "__main__.py").read_text(), "print('old')\n")
            self.assertTrue(os.access(root / "tools" / "launch_2k5_mod_studio.sh", os.X_OK))
            self.assertFalse((Path(tmp).resolve() / (root.name + ".new")).exists())
        self.assertEqual(started, [(["python3", "-m", "mod_editor", "--studio"], root)])
        self.assertTrue(any("previous" in note for note in plan.notes))

    def test_a_second_update_replaces_the_previous_copy(self) -> None:
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
            self.assertFalse((previous / "stale").exists())
            self.assertTrue((previous / "2K5-Mod-Studio.bat").exists())

    def test_a_folder_that_cannot_be_renamed_falls_back_to_a_sibling(self) -> None:
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC99-2026-09-09", RELEASE_FILES)
        started = []
        with tempfile.TemporaryDirectory() as tmp:
            root = _tarball_install(Path(tmp).resolve())
            plan = U.UpdatePlan("2k5", "beta-99", U.detect_install(root, platform="linux"), U.ReleaseAsset("t", HOST + "t", 1), None)
            tarball = Path(tmp).resolve() / "t.tar.gz"
            tarball.write_bytes(payload)
            real_rename = os.rename

            def refuse(src, dst):
                if Path(src) == root:
                    raise PermissionError("in use")
                return real_rename(src, dst)

            with unittest.mock.patch.object(U.os, "rename", refuse):
                new_root, _cmd = U.apply_tarball(plan, tarball, spawn=lambda cmd, cwd: started.append(cwd))
            self.assertEqual(new_root, Path(tmp).resolve() / "2K5-Mod-Studio-v1.0-RC99-2026-09-09")
            self.assertEqual((new_root / "mod_editor" / "__main__.py").read_text(), "print('new')\n")
            self.assertEqual((root / "mod_editor" / "__main__.py").read_text(), "print('old')\n")
            self.assertEqual(started, [new_root])
        self.assertTrue(any("could not be replaced" in note for note in plan.notes))

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
            installer = Path(tmp).resolve() / "dl" / "2K5-Mod-Studio-1.0.0rc99-Setup.exe"
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
            script = B.render_nsis(B.PRODUCTS["2k5"], "1.0.0rc99", Path(tmp).resolve(), None, Path(tmp).resolve())
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
        self.install = U.detect_install(self.root, platform="linux", executable="python3")

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
        name = "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz"
        banner.show_status(self._status({name: b"x", name + ".sha256": b"y"}))
        self.assertTrue(banner.update_button.isVisibleTo(banner))
        checkout = self.update_ui.UpdateBanner()
        self.assertEqual(checkout.install.kind, "checkout")
        self.assertFalse(checkout.can_self_update(self._status({name: b"x", name + ".sha256": b"y"})))
        banner.deleteLater()
        checkout.deleteLater()

    def test_the_whole_flow_runs_off_the_gui_thread_and_asks_to_quit(self) -> None:
        payload = _make_tarball("2K5-Mod-Studio-v1.0-RC99-2026-09-09", RELEASE_FILES)
        name = "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz"
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
        self.assertEqual(started, [(["python3", "-m", "mod_editor", "--studio"], self.root)])
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
        name = "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz"
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

    def test_declining_the_confirmation_does_nothing(self) -> None:
        name = "2K5-Mod-Studio-v1.0-RC99-2026-09-09.tar.gz"
        banner = self._banner()
        banner.confirm = lambda plan: False
        banner.show_status(self._status({name: b"x", name + ".sha256": b"y"}))
        with unittest.mock.patch.object(self.update_ui.self_update, "run_update") as run:
            self.assertFalse(banner.start_update())
        run.assert_not_called()
        self.assertTrue(banner.update_button.isEnabled())
        banner.deleteLater()


import unittest.mock  # noqa: E402  (used by the apply tests)

if __name__ == "__main__":
    unittest.main()
