"""Skip, rather than error, when a test's game data is not on this machine.

Most of this suite reads things that are deliberately not in the repository: the
user's own disc images, the folders they extract to, and the large generated
reports under ``reports/``. All of them are gitignored, so somebody who clones
this repo and runs pytest has none of them.

Only missing-data errors qualify. Assertion verdicts (including unittest's
custom failureException and pytest.fail) always remain failures, even when
their message or exception chain names absent data. Tests that require private
data but assert its presence must explicitly skip before making assertions.

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
        "docs/research",
        "tools/vendor",
        "tools/generated",
        "artifacts",
        "assets",
        "mod_editor/assets",
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

def _is_game_data(path: Path) -> bool:
    """True when this path is game data that is not on this machine at all.

    The containing tree has to be missing, not just the one file. A file absent
    from a directory that *does* exist is a different thing entirely: usually a
    step that was supposed to produce it and did not, which is a real failure
    and has to stay one. Requiring the whole tree to be gone means this can only
    fire on a machine that never had the data, which is the case it is for.
    """

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

    A path mention alone is not evidence of missing input. Require an explicit
    file-absence statement next to the path, and match the actual tree, not a
    suffix such as ``research`` inside a present ``docs/research`` tree.
    """

    text = str(error)
    for candidate in GITIGNORED_TREES + GITIGNORED_FILES:
        if candidate.exists():
            continue
        relative = candidate.relative_to(ROOT).as_posix()
        if str(candidate) not in text and not _names_a_path(text, relative):
            continue
        for name in (str(candidate), relative):
            path = rf"(?<![\w./-]){re.escape(name)}(?:/[^\s'\"\n:,;]*)?(?![\w./-])"
            absent = r"(?:missing(?: or symlinked)?|absent|not found|does not exist)"
            label = r"(?:(?:required|local|retail|source|input|file|directory|path|report|tree|game|data|XISO)\s+)*"
            before = rf"(?:\b{label}(?:is\s+)?{absent}\s*:?\s*|\bmissing\s+{label}|\bNo such file or directory:\s*)['\"]?{path}"
            after = rf"{path}['\"]?\s+(?:is\s+)?{absent}\b"
            if re.search(before, text, re.IGNORECASE) or re.search(after, text, re.IGNORECASE):
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

    This is only a preliminary path-shaped candidate check. The caller also
    requires explicit absence next to the configured path itself, so a match
    for ``research`` inside a present ``docs/research`` tree cannot skip it.
    """

    name = re.escape(relative)
    if "/" in relative:
        pattern = rf"(?<![\w.-]){name}(?![\w-])"
    else:
        pattern = rf"(?:(?<=/){name}(?![\w-])|(?<![\w.-]){name}/)"
    return re.search(pattern, text) is not None


def _missing_game_data(
    error: BaseException, failure_exception: type[BaseException] = AssertionError,
) -> Path | None:
    """The absent game-data path behind this error, if that is what it is."""

    verdicts = (AssertionError, failure_exception)
    if hasattr(pytest, "fail"):
        verdicts += (pytest.fail.Exception,)
    chain: list[BaseException] = []
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        # Inspect the entire chain before accepting missing data. A wrapper
        # must not turn an assertion verdict into a missing-input error.
        if isinstance(error, verdicts):
            return None
        chain.append(error)
        cause = error.__cause__
        error = cause if cause is not None else error.__context__
    for error in chain:
        if isinstance(error, OSError):
            for name in (getattr(error, "filename", None),
                         getattr(error, "filename2", None)):
                if not name:
                    continue
                try:
                    path = Path(os.fsdecode(name)).resolve()
                except (OSError, TypeError, ValueError):
                    continue
                if _is_game_data(path):
                    return path
        elif isinstance(error, Exception):
            named = _named_in_message(error)
            if named is not None:
                return named
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.outcome != "failed" or call.excinfo is None:
        return
    testcase = getattr(item, "_testcase", None)
    failure_exception = getattr(testcase, "failureException", AssertionError)
    missing = _missing_game_data(call.excinfo.value, failure_exception)
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


def pytest_collection_modifyitems(items) -> None:
    """Guard the frozen v1 proof fixture without rewriting its pinned bytes.

    The v2 proof pins the entire v1 test module, so its private-report
    prerequisite lives here. Present input still runs every original assertion.
    """
    frozen_test = ROOT / "tests/test_nfl_group36_xemu_runtime_result.py"
    report = ROOT / "reports/assets/nfl2k5_group36_s42_xemu_runtime_partial.v1.json"
    if report.is_file():
        return
    marker = pytest.mark.skip(reason=f"private frozen v1 xemu diagnostic result absent: {report}")
    for item in items:
        if Path(item.path) == frozen_test:
            item.add_marker(marker)
