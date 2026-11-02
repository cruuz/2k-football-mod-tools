"""The build log, the errors.log entry and the diagnostic zip of one Studio build (b791-h3).

Coach Edwards sent his 3 MB errors.log twice and it held 46 copies of an old GUI crash and one line per failed build.
From beta 79.1 every build leaves:

* ``<disc>.build-log.txt`` beside the output disc, and a copy in the Studio's log folder (``builds/``): the Studio
  version, the computer, the source disc (size, SHA-256 when the build measured it, what kind of image it is), the
  project's fingerprint (edit counts and a hash of its recipe, never texture data), the options, the Modern colour
  values, every step with its time, every progress line, the notes, the steps that were left out, and, when it stopped,
  the step, the resource, the reason and the full traceback.
* on a failure, one errors.log entry with the same facts, the traceback and the last 200 progress lines;
* on a failure, ``<disc>.diagnostic-<time>.zip`` beside the output: the build log, that errors.log entry, the build
  options as JSON and the project doctor's report (``nfl2k5_project_check.doctor``). Text only, by construction: no
  game data and no textures can be put in it.

All files are UTF-8 with "\\n" line ends. Nothing here may stop a build or hide its error: every write is guarded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import re
import sys
import traceback
from typing import Any, Callable, Iterable
import zipfile

from . import build_steps

APP_NAME = "2K5 Mod Studio"
LOG_SUFFIX = ".build-log.txt"
ZIP_INFIX = ".diagnostic-"
DISCORD = "the SOFTDRINK Discord"
#: Steps whose errors are refusals made before any long work: the message is the fix, so no doctor run.
NO_DOCTOR_STEPS = frozenset({"preflight", "artwork_recipe", "project_check", "hash", "publish"})
#: Build logs kept in the log folder's builds/ (oldest removed first).
KEEP_LOG_COPIES = 30
ERRORS_LOG_LINES = 200
MAX_MEMBER_BYTES = 64 * 1024 * 1024
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._ ()+-]")


# ------------------------------------------------------------------------------------------------------------------
# Facts
# ------------------------------------------------------------------------------------------------------------------

def studio_version() -> str:
    try:
        from mod_editor import __version__ as version
    except Exception:  # noqa: BLE001
        version = "unknown"
    try:
        from mod_editor.core.update_check import BUILD_RELEASE_TAG as tag
    except Exception:  # noqa: BLE001
        tag = ""
    return f"{version} ({tag})" if tag and tag not in str(version) else str(version)


def computer_line() -> str:
    try:
        system = platform.platform()
    except Exception:  # noqa: BLE001
        system = sys.platform
    return f"{system} ({platform.machine() or 'unknown machine'}); Python {sys.version.split()[0]}"


def _plan_recipe(plan) -> dict[str, Any]:
    try:
        recipe = plan.to_recipe()
    except Exception:  # noqa: BLE001
        recipe = {}
    return recipe if isinstance(recipe, dict) else {}


def option_lines(plan, labels: Iterable[str] | None = None) -> list[str]:
    """The options of this build: the Build tab's own captions when given, else every option off its default."""
    if labels:
        return [str(label) for label in labels]
    if plan is None:
        return []
    try:
        from .mod_build import BuildPlan
        default = BuildPlan(str(getattr(plan, "source", "")), str(getattr(plan, "target", ""))).to_recipe()
    except Exception:  # noqa: BLE001
        default = {}
    recipe = _plan_recipe(plan)
    out = []
    for key in sorted(recipe):
        if key == "modern_color_settings":
            continue
        if default.get(key) != recipe[key]:
            out.append(f"{key} = {json.dumps(recipe[key], default=str, sort_keys=True)[:300]}")
    return out


def colour_values(plan) -> list[str]:
    """Every Modern colour and lighting value of the plan, each marked with its default when it differs."""
    if plan is None or not getattr(plan, "modern_color", False):
        return ["off"]
    try:
        from . import nfl2k5_modern_color as colour
        settings = colour.normalize_settings(getattr(plan, "modern_color_settings", None))
        defaults = colour.default_settings().get("values", {})
    except Exception as exc:  # noqa: BLE001
        return [f"(could not read the colour values: {exc})"]
    values = settings.get("values", {}) if isinstance(settings, dict) else {}
    out = []
    for key in sorted(values):
        value = values[key]
        mark = "" if defaults.get(key) == value else f" (default {defaults.get(key)})"
        out.append(f"{key}={value}{mark}")
    return out or ["(the default values)"]


def source_identity(path: Any, sha256: str | None = None) -> str:
    """One line about the source disc: path, size, SHA-256 (or its first 16 hex digits), the kind of image."""
    if not path:
        return "(none)"
    text = str(path)
    try:
        size = f"{Path(text).stat().st_size:,} bytes"
    except OSError as exc:
        size = f"not readable now ({exc.strerror or exc})"
    digest = f", sha256 {sha256}" if sha256 else ", sha256 not measured (the build stopped before the copy)"
    kind = ""
    try:
        from .mod_build import disc_identity
        identity = disc_identity(text)
        if identity is not None:
            kind = f". This image is: {identity.line()}"
    except Exception:  # noqa: BLE001
        pass
    return f"{text}, {size}{digest}{kind}"


def project_line(fingerprint: dict | None) -> str:
    if not fingerprint:
        return "no project artwork in this build"
    kinds = ", ".join(f"{kind} {count:,}" for kind, count in (fingerprint.get("kinds") or {}).items())
    digest = fingerprint.get("manifest_sha256") or "?"
    return f"{fingerprint.get('edits', 0):,} edits ({kinds or 'no kinds'}); recipe sha256 {digest}"


# ------------------------------------------------------------------------------------------------------------------
# Texts
# ------------------------------------------------------------------------------------------------------------------

def _duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _stopped_line(tracker) -> str:
    failure = tracker.failure or {}
    where = failure.get("label") or "?"
    if failure.get("resource"):
        where += f" ({failure['resource']})"
    return where


def header_lines(tracker, *, plan=None, labels=None, result: str | None = None) -> list[str]:
    facts = tracker.facts
    plan = plan if plan is not None else facts.get("plan")
    result = result or tracker.result
    if result == "failed":
        state = f"FAILED during {_stopped_line(tracker)}"
    elif result == "cancelled":
        current = tracker.current()
        state = f"CANCELLED during {current['label'] if current else 'the build'}"
    elif result == "ok":
        state = "OK (the disc was made)" + (f"; {len(tracker.left_out)} step(s) left out" if tracker.left_out else "")
    else:
        state = result.upper()
    started = datetime.fromtimestamp(tracker.started_wall).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"{APP_NAME} {studio_version()} build log",
        f"Result: {state}",
        f"Started: {started} (local time); ran for {_duration(tracker.elapsed())}",
        f"Computer: {computer_line()}",
        f"Source disc: {source_identity(facts.get('source') or getattr(plan, 'source', ''), facts.get('source_sha256'))}",
        f"Output disc: {facts.get('target') or getattr(plan, 'target', '') or '(none)'}",
        f"Project: {project_line(facts.get('project'))}",
    ]
    options = option_lines(plan, labels)
    lines.append("Options: " + ("; ".join(options) if options else "(the defaults)"))
    lines.append("Modern colour values: " + ", ".join(colour_values(plan)))
    return lines


def failure_lines(tracker, exc: BaseException | None) -> list[str]:
    failure = tracker.failure or {}
    if not failure and exc is None:
        return []
    message = failure.get("message") or (str(exc) if exc is not None else "")
    lines = ["", "What stopped the build:", f"  {message}"]
    if failure.get("last_progress"):
        lines.append(f"  Last progress line in that step: {failure['last_progress']}")
    if failure.get("undo"):
        lines.append(f"  This step could not be left out: {failure['undo']}")
    return lines


def step_lines(tracker) -> list[str]:
    stopped = (tracker.failure or {}).get("step")
    out = ["", "Steps (when each started, how long it took):"]
    for entry in tracker.steps:
        took = (entry["end"] if entry["end"] is not None else tracker.elapsed()) - entry["start"]
        outcome = entry.get("outcome")
        mark = ""
        if outcome == "left_out":
            mark = "  <- left out"
        elif entry.get("failed") or (stopped and entry["id"] == stopped and entry is _last_with(tracker, stopped)):
            mark = "  <- stopped here" if tracker.result == "failed" else ""
        out.append(f"  {build_steps._clock(entry['start'])}  {entry['label']} ({_duration(took)}){mark}")
    return out


def _last_with(tracker, step_id):
    return next((entry for entry in reversed(tracker.steps) if entry["id"] == step_id), None)


def build_log_text(tracker, *, plan=None, labels=None, exc: BaseException | None = None,
                   receipt: dict | None = None, paths: dict | None = None) -> str:
    """The whole build log (every progress line)."""
    lines = header_lines(tracker, plan=plan, labels=labels)
    lines += failure_lines(tracker, exc)
    if tracker.left_out:
        lines += ["", "Left out (the disc was finished without these; each was restored exactly):"]
        lines += [f"  - {row['user_notes'][0]}" for row in tracker.left_out]
    notes = [note for note in tracker.notes if not any(note == row["user_notes"][0] for row in tracker.left_out)]
    receipt_notes = list((receipt or {}).get("user_notes") or ())
    for note in receipt_notes:
        if note not in notes and not any(note == row["user_notes"][0] for row in tracker.left_out):
            notes.append(note)
    if notes:
        lines += ["", "Notes:"] + [f"  - {note}" for note in notes]
    if paths:
        lines += ["", "Files:"] + [f"  {name}: {value}" for name, value in paths.items() if value]
    lines += step_lines(tracker)
    traceback_text = (tracker.failure or {}).get("traceback") or (build_steps.failure_traceback(exc) if exc else "")
    if traceback_text:
        lines += ["", "Full error (traceback):"] + ["  " + line for line in traceback_text.rstrip().splitlines()]
    for row in tracker.left_out:
        if row.get("traceback"):
            lines += ["", f"Error of the left-out step {row['label']}:"]
            lines += ["  " + line for line in row["traceback"].rstrip().splitlines()]
    lines += ["", f"Progress ({tracker.calls:,} updates; repeats of one counter are folded into one line):"]
    lines += ["  " + line for line in tracker.lines()]
    return "\n".join(lines) + "\n"


def errors_entry_text(tracker, exc: BaseException | None, *, operation: str = "make the disc", plan=None,
                      labels=None, paths: dict | None = None, when: str | None = None) -> str:
    """One errors.log entry: version, computer, step, resource, facts, traceback, the last 200 progress lines."""
    stamp = when or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    failure = tracker.failure or {}
    lines = [
        f"{APP_NAME} {studio_version()}",
        f"time: {stamp}",
        f"python: {sys.version.split()[0]} on {sys.platform}",
        f"operation: {operation}",
        f"computer: {computer_line()}",
        f"step: {failure.get('label', '?')} ({failure.get('step', '?')})",
        f"resource: {failure.get('resource') or '(not named)'}",
        f"last progress line in that step: {failure.get('last_progress') or '(none)'}",
        "",
        failure.get("message") or (str(exc) if exc is not None else "(no message)"),
        "",
    ]
    lines += header_lines(tracker, plan=plan, labels=labels, result="failed")[4:]   # source, output, project, options, colour
    if tracker.left_out:
        lines += ["left out earlier in this build:"] + [f"  - {row['user_notes'][0]}" for row in tracker.left_out]
    if paths:
        lines += [f"{name}: {value}" for name, value in paths.items() if value]
    traceback_text = failure.get("traceback") or (build_steps.failure_traceback(exc) if exc else "")
    lines += ["", traceback_text.rstrip()]
    lines += ["", f"last {ERRORS_LOG_LINES} progress lines:"] + ["  " + line for line in tracker.lines(ERRORS_LOG_LINES)]
    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------------------------------------------------------------
# Files
# ------------------------------------------------------------------------------------------------------------------

def safe_name(name: str) -> str:
    """A file name every platform accepts (no colons, slashes or control characters)."""
    cleaned = _UNSAFE_NAME.sub("_", name).strip(" .")
    return cleaned[:150] or "build"


def write_text(path: Path, text: str) -> Path | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        return path
    except OSError:
        return None


def _output_folder(target: Any, *, require_file: bool = False) -> Path | None:
    """The folder of the output disc, when it is a real place to write beside (an absolute path whose folder exists;
    with ``require_file``, the disc itself must exist: a finished build). Never the current directory by accident."""
    if not target:
        return None
    path = Path(str(target))
    if not path.is_absolute() or (require_file and not path.is_file()):
        return None
    folder = path.parent
    return folder if folder.is_dir() else None


def write_build_log(text: str, target: Any, *, log_directory: Path | None = None,
                    stamp: str | None = None, finished: bool = False) -> dict[str, str]:
    """``<disc>.build-log.txt`` beside the output and a copy in ``<log folder>/builds/``. {"build_log", "log_copy"}.

    ``finished``: the build published its disc, so the log goes beside it only if that disc is really there."""
    out: dict[str, str] = {}
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = _output_folder(target, require_file=finished)
    if folder is not None:
        beside = write_text(folder / safe_name(Path(str(target)).name + LOG_SUFFIX), text)
        if beside is not None:
            out["build_log"] = str(beside)
    if log_directory is not None:
        builds = Path(log_directory) / "builds"
        name = safe_name(f"{stamp} {Path(str(target)).name if target else 'build'}{LOG_SUFFIX}")
        copy = write_text(builds / name, text)
        if copy is not None:
            out["log_copy"] = str(copy)
            try:
                logs = sorted(builds.glob("*" + LOG_SUFFIX), key=lambda p: p.stat().st_mtime)
                for old in logs[:-KEEP_LOG_COPIES]:
                    old.unlink()
            except OSError:
                pass
        if "build_log" not in out and copy is not None:
            out["build_log"] = str(copy)
    return out


def write_zip(path: Path, members: dict[str, str]) -> Path:
    """A zip of text members only (UTF-8). Anything that is not text is refused, so no game data can get in."""
    for name, value in members.items():
        if not isinstance(value, str):
            raise TypeError(f"diagnostic member {name!r} is not text")
        if "\x00" in value:
            raise ValueError(f"diagnostic member {name!r} holds binary data")
        if "/" in name or "\\" in name or ":" in name or name != safe_name(name):
            raise ValueError(f"diagnostic member name {name!r} is not a plain file name")
        if len(value.encode("utf-8")) > MAX_MEMBER_BYTES:
            raise ValueError(f"diagnostic member {name!r} is too large")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            info = zipfile.ZipInfo(name, date_time=datetime.now().timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value.encode("utf-8"))
    os.replace(partial, path)
    return path


# ------------------------------------------------------------------------------------------------------------------
# The project doctor (job h4's nfl2k5_project_check.doctor)
# ------------------------------------------------------------------------------------------------------------------

def run_doctor(project, source, settings, *, progress=None, workers=None) -> tuple[str, str, Any]:
    """(status, text, json-able data) of the project doctor; never raises. status: ok, unavailable, failed, cancelled.

    The call agreed with h4: ``doctor(project, source, settings, progress=..., workers=...)`` returning a Report with
    ``text()`` and ``as_dict()``. ``project`` is the saved .2k5mod path, the open session, or None for a build with
    no project; ``settings`` is the BuildPlan.
    """
    try:
        from . import nfl2k5_project_check as project_check
    except Exception as exc:  # noqa: BLE001
        return "unavailable", f"The project check could not be loaded: {exc}", None
    doctor = getattr(project_check, "doctor", None)
    if not callable(doctor):
        return "unavailable", "This Studio has no project doctor (nfl2k5_project_check.doctor).", None
    try:
        report = doctor(project, source, settings, progress=progress, workers=workers)
    except Exception as exc:  # noqa: BLE001 - the doctor's own failure goes in the zip, never over the build's
        if build_steps.is_cancel(exc):
            return "cancelled", "The project doctor was cancelled (Cancel was pressed).", None
        return "failed", f"The project doctor stopped: {exc}\n\n{build_steps.failure_traceback(exc)}", None
    try:
        text = report.text() if callable(getattr(report, "text", None)) else str(report)
    except Exception as exc:  # noqa: BLE001
        text = f"(the doctor's report could not be written as text: {exc})"
    data = None
    try:
        data = report.as_dict() if callable(getattr(report, "as_dict", None)) else None
        json.dumps(data, default=str)
    except Exception:  # noqa: BLE001
        data = None
    return "ok", str(text), data


def default_workers() -> int:
    try:
        count = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        count = os.cpu_count() or 2
    return max(1, count // 2)


# ------------------------------------------------------------------------------------------------------------------
# The whole record of a finished build
# ------------------------------------------------------------------------------------------------------------------

@dataclass
class BuildRecord:
    """Where one build's files went and what the failure dialog and the Copy summary need."""
    result: str
    step: str = ""
    label: str = ""
    resource: str | None = None
    message: str = ""
    reason: str = ""
    last_progress: str = ""
    undo: str = ""
    build_log: str = ""
    log_copy: str = ""
    errors_log: str = ""
    zip: str = ""
    doctor: str = ""
    left_out: list = field(default_factory=list)
    colour: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


README = """This is the diagnostic report of a {app} build that stopped.

If you need help, send this .zip to {discord}. It holds text only:
  build-log.txt          every step and progress line of the build, the options and the full error
  errors-log-entry.txt   the entry the Studio added to its errors.log for this build
  build-options.json     your Build options and Modern colour values (no textures)
  project-doctor.txt     the project doctor's deep check of your project and options (when it could run)
It never holds your textures, your project's images or any game data.
"""


def _settings_json(plan, labels, tracker) -> str:
    recipe = _plan_recipe(plan)
    doc = {"schema": "studio_build_options/v1", "studio": studio_version(), "labels": list(labels or ()),
           "source": str(getattr(plan, "source", "")), "target": str(getattr(plan, "target", "")),
           "options": recipe, "project": tracker.facts.get("project")}
    return json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n"


def record_failure(tracker, exc: BaseException, *, plan=None, labels=None, log_directory: Path | None = None,
                   append_errors_log: Callable[[str], Any] | None = None,
                   doctor: Callable[[], tuple[str, str, Any]] | None = None,
                   progress: Callable[..., Any] | None = None, operation: str = "make the disc") -> BuildRecord:
    """Write the build log, the errors.log entry and the diagnostic zip for a failed build; return where they are."""
    plan = plan if plan is not None else tracker.facts.get("plan")
    failure = tracker.failure or {}
    if not failure:
        build_steps.contextualize(exc, tracker)
        failure = tracker.failure or {}
    record = BuildRecord(result="failed", step=failure.get("step", ""), label=failure.get("label", ""),
                         resource=failure.get("resource"), message=failure.get("message") or str(exc),
                         reason=failure.get("reason") or build_steps.plain_reason(exc),
                         last_progress=failure.get("last_progress", ""), undo=failure.get("undo", ""),
                         left_out=[row["user_notes"][0] for row in tracker.left_out],
                         colour=", ".join(colour_values(plan)))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = tracker.facts.get("target") or getattr(plan, "target", "")
    folder = _output_folder(target)
    zip_path = None
    if folder is not None:
        zip_path = folder / safe_name(f"{Path(str(target)).name}{ZIP_INFIX}{stamp}.zip")
    elif log_directory is not None:
        zip_path = Path(log_directory) / "builds" / safe_name(f"{stamp}{ZIP_INFIX}report.zip")
    say = progress or (lambda *_args: None)
    # 1. the build log and the errors.log entry first: they must exist even if the doctor never returns
    planned = {"diagnostic report": str(zip_path) if zip_path else ""}
    try:
        paths = write_build_log(build_log_text(tracker, plan=plan, labels=labels, exc=exc, paths=planned), target,
                                log_directory=log_directory, stamp=stamp)
        record.build_log, record.log_copy = paths.get("build_log", ""), paths.get("log_copy", "")
    except Exception:  # noqa: BLE001
        pass
    entry = ""
    try:
        entry = errors_entry_text(tracker, exc, operation=operation, plan=plan, labels=labels,
                                  paths={"build log": record.build_log, "diagnostic report": planned["diagnostic report"]})
        if append_errors_log is not None:
            saved = append_errors_log(entry)
            record.errors_log = str(saved) if saved else ""
    except Exception:  # noqa: BLE001
        pass
    # 2. the doctor (skipped for refusals made before any long work)
    doctor_status, doctor_text, doctor_data = "not run", "", None
    if record.step in NO_DOCTOR_STEPS:
        doctor_text = ("The project doctor was not run: the build stopped at "
                       f"{record.label}, before any long work, and the message above says what to change.")
    elif doctor is not None:
        try:
            say("Writing the diagnostic report: the project doctor checks your project (Cancel skips this part)", 0, 0)
        except Exception:  # noqa: BLE001
            pass
        try:
            doctor_status, doctor_text, doctor_data = doctor()
        except Exception as doctor_exc:  # noqa: BLE001
            doctor_status = "cancelled" if build_steps.is_cancel(doctor_exc) else "failed"
            doctor_text = f"The project doctor stopped: {doctor_exc}"
    else:
        doctor_text = "The project doctor was not run for this build."
    record.doctor = doctor_status
    # 3. the zip
    if zip_path is not None:
        members = {"README.txt": README.format(app=APP_NAME, discord=DISCORD),
                   "build-log.txt": build_log_text(tracker, plan=plan, labels=labels, exc=exc,
                                                   paths={"build log": record.build_log,
                                                          "diagnostic report": str(zip_path)}),
                   "errors-log-entry.txt": entry or "(the errors.log entry could not be written)\n",
                   "build-options.json": _settings_json(plan, labels, tracker)}
        name = "project-doctor.txt" if doctor_status == "ok" else "project-doctor-not-run.txt"
        members[name] = (doctor_text or "(no report)").rstrip() + "\n"
        if doctor_data is not None:
            members["project-doctor.json"] = json.dumps(doctor_data, indent=1, sort_keys=True, default=str) + "\n"
        try:
            record.zip = str(write_zip(zip_path, members))
        except Exception:  # noqa: BLE001
            record.zip = ""
    return record


def record_end(tracker, *, plan=None, labels=None, receipt: dict | None = None,
               log_directory: Path | None = None) -> BuildRecord:
    """Write the build log of a build that finished (or was cancelled); return where it is."""
    plan = plan if plan is not None else tracker.facts.get("plan")
    target = (receipt or {}).get("target") or tracker.facts.get("target") or getattr(plan, "target", "")
    record = BuildRecord(result=tracker.result, left_out=[row["user_notes"][0] for row in tracker.left_out],
                         colour=", ".join(colour_values(plan)))
    try:
        paths = write_build_log(build_log_text(tracker, plan=plan, labels=labels, receipt=receipt), target,
                                log_directory=log_directory, finished=tracker.result == "ok")
        record.build_log, record.log_copy = paths.get("build_log", ""), paths.get("log_copy", "")
    except Exception:  # noqa: BLE001
        pass
    return record


def run_logged(build: Callable[[Callable[..., Any]], dict], plan, progress=None, *, labels=None,
               log_directory: Path | None = None, project=None, doctor: bool = False):
    """A command-line build with the Build tab's logs: ``run_logged(lambda p: mod_build.build(plan, p), plan, say)``.

    Writes the build log beside the output (and in ``log_directory``/builds when given); on a failure also the
    diagnostic zip (with the project doctor when ``doctor`` is true) and re-raises the "During ..." error, whose
    ``studio_build_record`` attribute says where the files are. Returns the receipt (with ``build_log``)."""
    session = build_steps.track(progress)
    try:
        with session:
            receipt = build(session.progress)
    except BaseException as exc:
        try:
            if isinstance(exc, Exception) and not build_steps.is_cancel(exc):
                runner = (lambda: run_doctor(project, getattr(plan, "source", ""), plan, progress=progress,
                                             workers=default_workers())) if doctor else None
                record = record_failure(session.tracker, exc, plan=plan, labels=labels, log_directory=log_directory,
                                        doctor=runner, operation="make the disc (command line)")
            else:
                record = record_end(session.tracker, plan=plan, labels=labels, log_directory=log_directory)
            exc.studio_build_record = record.as_dict()
        except Exception:  # noqa: BLE001 - the build's own error always wins
            pass
        raise
    try:
        record = record_end(session.tracker, plan=plan, labels=labels, receipt=receipt, log_directory=log_directory)
        if record.build_log and isinstance(receipt, dict):
            receipt["build_log"] = record.build_log
    except Exception:  # noqa: BLE001
        pass
    return receipt


__all__ = ["BuildRecord", "build_log_text", "errors_entry_text", "record_failure", "record_end", "run_doctor",
           "run_logged", "write_build_log", "write_zip", "safe_name", "colour_values", "option_lines",
           "source_identity", "default_workers", "NO_DOCTOR_STEPS"]
