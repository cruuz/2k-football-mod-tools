"""Skip, rather than error, when a test's game data is not on this machine.

Most of this suite reads things that are deliberately not in the repository: the
user's own disc images, the folders they extract to, and the large generated
reports under ``reports/``. All of them are gitignored, so somebody who clones
this repo and runs pytest has none of them.

Without this, a clean checkout produces 136 failures and 207 errors. Every one
of them is a missing retail file, and the honest reading of that output is "this
project is broken", which is the opposite of true. A skip with a reason is the
accurate report: the test did not run because its input is absent.

The decision is made from the exception the test actually raised, not from
guessing which tests need what. A test that cannot open a path inside a
gitignored directory is missing game data by definition, because those are
precisely the paths git is told never to carry. Anything else, including a
missing file the repo does ship, still fails exactly as loudly as before.

Nothing is skipped when the data is present, so a machine that has it, including
the maintainer's and CI, runs exactly what it ran before.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Headless CI / monorepo GUI tests: offscreen Qt avoids modal dialogs and
# display-server hangs. Individual modules may still set this; setdefault keeps
# an explicit QT_QPA_PLATFORM from the invoker.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import pytest
except ModuleNotFoundError:
    # ``unittest discover`` imports this module through the focused boundary
    # tests below, even though it never invokes pytest hooks.  Keep those
    # dependency-free while still using pytest's real marker whenever pytest
    # is the runner.
    class _PytestCompat:
        @staticmethod
        def hookimpl(**_kwargs):
            def decorate(function):
                return function

            return decorate

    pytest = _PytestCompat()

ROOT = Path(__file__).resolve().parents[1]

#: Directories .gitignore excludes because they hold retail or generated data.
#: Kept in step with .gitignore by hand; a path that is not listed here is
#: treated as a real failure, which is the safe direction to be wrong in.
GITIGNORED_TREES: tuple[Path, ...] = tuple(
    ROOT / part
    for part in (
        "extracted",
        "All-Pro Football 2K8 (USA)",
        "reports/assets",
        "reports/cut_content",
        "reports/static_recomp",
        "reports/manifests",
        "reports/headers",
        "reports/asset_samples",
        "reports/cross_title",
        "research",
        "tools/vendor",
        "tools/generated",
        "artifacts",
        "assets",
        # Build outputs. Several tests read a workflow manifest an earlier
        # tooling run left here, which a fresh checkout has never produced.
        "build",
        "build-clang",
        "build-sanitize",
        "build-static-recomp-apf",
        "ghidra_projects",
        "release-staging",
        "docs/updates",
    )
)

#: Individual files excluded the same way.
GITIGNORED_FILES: tuple[Path, ...] = (ROOT / "ESPN NFL 2K5 (USA).xiso.iso",)

_SUFFIXES = (".iso", ".qcow2")


def _is_game_data(path: Path) -> bool:
    """True when this path is game data that is not on this machine at all.

    The containing tree has to be missing, not just the one file. A file absent
    from a directory that *does* exist is a different thing entirely: usually a
    step that was supposed to produce it and did not, which is a real failure
    and has to stay one. Requiring the whole tree to be gone means this can only
    fire on a machine that never had the data, which is the case it is for.
    """

    if path.suffix.lower() in _SUFFIXES:
        return not path.exists()
    if path in GITIGNORED_FILES:
        return not path.exists()
    return any(
        (path == tree or tree in path.parents) and not tree.exists()
        for tree in GITIGNORED_TREES
    )


def _named_in_message(error: BaseException) -> Path | None:
    """A gitignored tree this error names, when that tree is absent here.

    Most tools do not let an OSError escape: they check the path themselves and
    raise their own type, with the path in the message and no ``filename``
    attribute to read. Matching the message is what covers those.

    Requiring the tree to be *absent* is what keeps this honest. On a machine
    that has the data, no message can trigger a skip, so a genuine failure that
    happens to mention ``reports/assets`` still fails.
    """

    text = str(error)
    for candidate in GITIGNORED_TREES + GITIGNORED_FILES:
        if candidate.exists():
            continue
        if str(candidate) in text:
            return candidate
        if _names_a_path(text, candidate.relative_to(ROOT).as_posix()):
            return candidate
    return None


def _names_a_path(text: str, relative: str) -> bool:
    """True when ``text`` names ``relative`` as a PATH, not as an English word.

    This hook turns a FAILED test into a SKIPPED one, and six of the gitignored
    trees are bare words that appear constantly in this project's assertion
    text: ``build``, ``assets``, ``research``, ``extracted``, ``artifacts`` and
    ``docs/updates``. A plain substring test therefore silently hides real red --
    a genuine AssertionError reading "... decided at build time" was reported as
    "Skipped: game data not present: build" purely because the message contained
    the word "build". A check that agrees with the mistake is worse than no
    check.

    So a bare word only counts when it sits next to a path separator -- either
    following one (``.../ancestor_link/All-Pro Football 2K8 (USA)``) or followed
    by one (``build/manifest.json``). "decided at build time" has neither and
    stays a failure. A multi-segment name already looks like a path, so a word
    boundary is enough.

    Both directions matter. A *preceding* separator is what lets ``research/``
    match ``docs/research/``, since the gitignore pattern applies at any depth,
    and it is what keeps a directory named at the end of a path from being
    unmasked.
    """

    name = re.escape(relative)
    if "/" in relative:
        pattern = rf"(?<![\w.-]){name}(?![\w-])"
    else:
        pattern = rf"(?:(?<=/){name}(?![\w-])|(?<![\w.-]){name}/)"
    return re.search(pattern, text) is not None


def _missing_game_data(error: BaseException) -> Path | None:
    """The absent game-data path behind this error, if that is what it is."""

    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, (FileNotFoundError, NotADirectoryError)):
            for name in (getattr(error, "filename", None),
                         getattr(error, "filename2", None)):
                if not name:
                    continue
                try:
                    path = Path(name).resolve()
                except OSError:
                    continue
                if _is_game_data(path):
                    return path
        named = _named_in_message(error)
        if named is not None:
            return named
        # A refusal is often re-raised as the tool's own error type with the
        # original attached, so the cause chain has to be walked too.
        error = error.__cause__ or error.__context__
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.outcome != "failed" or call.excinfo is None:
        return
    missing = _missing_game_data(call.excinfo.value)
    if missing is None:
        return
    try:
        shown = missing.relative_to(ROOT)
    except ValueError:
        shown = missing
    # A three-part longrepr is what pytest reads as a skip reason. Setting
    # wasxfail instead would file these under "xfailed", which would claim the
    # tests are known-broken rather than simply not run here.
    report.outcome = "skipped"
    report.longrepr = (str(item.fspath), item.location[1],
                       f"Skipped: game data not present: {shown}")


def pytest_sessionfinish(session, exitstatus) -> None:
    """Best-effort cleanup so leftover ProcessPool/Qt workers do not hang the suite.

    Product writers already use ProcessPoolExecutor context managers; this is a
    belt-and-suspenders exit path for monorepo order-dependent hangs.
    """

    try:
        import multiprocessing as mp

        for child in mp.active_children():
            try:
                child.terminate()
            except Exception:
                pass
    except Exception:
        pass
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:
        pass
