#!/usr/bin/env python3
"""Run the bounded APF 2K8 slot-43 Xenia experiment headlessly.

The runner accepts a user's extracted game directory and one exact custom
Xenia build.  It never copies or writes game files.  Xenia is launched under
Xvfb with fresh storage, content, cache, home, and XDG roots.  The default
``observe`` mode only logs the pinned roster consumer.  ``modified`` exposes
one pinned, otherwise-unassigned player through that one consumer and requires
an exact operator confirmation token.

The raw Xenia log stays in the private run directory.  ``result.json`` contains
only hashes, counters, booleans, fixed reason codes, and relative artifact
names; guest pointers and raw log lines are deliberately omitted.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from typing import Iterable, Mapping, Sequence


SCHEMA = "apf2k8_slot43_xenia_experiment/v1"
RESULT_SCHEMA = "apf2k8_slot43_xenia_result/v1"
XENIA_SHA256 = (
    "e8d7fda95239d12c11a1d2b336bbed33b39d1da738a65dc2e757c16b8d215641"
)
DEFAULT_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
HOOK_COMMIT = "d145430737f787f522e08e7d86d3e94bdde6d6a1"
MODIFIED_CONFIRMATION = "I_ACCEPT_ONE_CONSUMER_SLOT43_OVERRIDE"
DEFAULT_TIMEOUT_SECONDS = 180
MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 900
MAX_LOG_SIZE = 256 * 1024 * 1024
MAX_APF_LINES = 20_000
SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

KNOWN_SITES = {
    "count_entry",
    "count_exit",
    "getter_entry",
    "getter_miss",
    "getter_found",
}
SITE_LR = {
    "count_entry": "84A16D34",
    "count_exit": "84A16D34",
    "getter_entry": "84A16D50",
    "getter_miss": "84A16D50",
    "getter_found": "84A16D50",
}
SITE_ACTIONS = {
    "count_entry": {"observed"},
    "count_exit": {"observed", "count_incremented"},
    "getter_entry": {"observed"},
    "getter_miss": {"observed", "candidate_returned"},
    "getter_found": {"stock_return"},
}
TOKEN_RE = re.compile(r"(?:^|\s)([a-z0-9_]+)=([^\s]+)")
HEX32_RE = re.compile(r"^[0-9A-Fa-f]{8}$")


class Slot43ExperimentError(ValueError):
    """An experiment setup or integrity error that must stop the run."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Slot43ExperimentError(message)


@dataclass(frozen=True)
class ExecutionReceipt:
    started: bool
    timed_out: bool
    returncode: int | None
    duration_ms: int
    termination: str


@dataclass(frozen=True)
class ParsedReceipts:
    target_matched: int
    validation_accepted: int
    validation_rejected: int
    target_modes: tuple[str, ...]
    accepted_modes: tuple[str, ...]
    event_actions: Mapping[str, Mapping[str, int]]
    malformed_line_count: int
    apf_line_count: int
    order_valid: bool
    complete_observe_traversals: int
    complete_modified_traversals: int

    def sanitized(self) -> dict[str, object]:
        return {
            "target_matched": self.target_matched,
            "validation_accepted": self.validation_accepted,
            "validation_rejected": self.validation_rejected,
            "event_actions": {
                site: dict(sorted(actions.items()))
                for site, actions in sorted(self.event_actions.items())
            },
            "malformed_line_count": self.malformed_line_count,
            "apf_line_count": self.apf_line_count,
            "receipt_order_valid": self.order_valid,
            "complete_observe_traversals": self.complete_observe_traversals,
            "complete_modified_traversals": self.complete_modified_traversals,
        }


def _regular_file(path: Path, label: str, *, executable: bool = False) -> Path:
    candidate = path.expanduser()
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise Slot43ExperimentError(f"{label} could not be opened: {exc}") from exc
    require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a regular, non-symlink file",
    )
    resolved = candidate.resolve(strict=True)
    if executable:
        require(os.access(resolved, os.X_OK), f"{label} is not executable")
    return resolved


def _regular_directory(path: Path, label: str) -> Path:
    candidate = path.expanduser()
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise Slot43ExperimentError(f"{label} could not be opened: {exc}") from exc
    require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"{label} must be a real, non-symlink directory",
    )
    return candidate.resolve(strict=True)


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _create_run_root(path: Path, game_root: Path, xenia: Path) -> Path:
    requested = path.expanduser()
    require(requested.name not in {"", ".", ".."}, "run root needs a file name")
    require(not requested.exists() and not requested.is_symlink(),
            "run root must be a new path")
    parent = _regular_directory(requested.parent, "run-root parent")
    target = parent / requested.name
    require(not _path_contains(game_root, target),
            "run root cannot be inside the game directory")
    require(not _path_contains(target, game_root),
            "run root cannot contain the game directory")
    require(not _path_contains(target, xenia),
            "run root cannot contain the Xenia executable")
    os.mkdir(target, mode=0o700)
    created = _regular_directory(target, "run root")
    require(created == target and not any(created.iterdir()),
            "new run root is not empty")
    return created


def _open_readonly(path: Path, label: str) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise Slot43ExperimentError(f"{label} could not be read: {exc}") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        os.close(descriptor)
        raise Slot43ExperimentError(f"{label} is not a regular file")
    return descriptor, opened


def _sha256_fd(descriptor: int) -> str:
    hasher = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        hasher.update(chunk)
    return hasher.hexdigest()


def sha256_regular_file(path: Path, label: str) -> tuple[str, int]:
    """Hash a pinned regular file without following a last-component symlink."""

    resolved = _regular_file(path, label)
    descriptor, opened = _open_readonly(resolved, label)
    try:
        digest = _sha256_fd(descriptor)
        after = os.fstat(descriptor)
        current = resolved.lstat()
        require(
            (opened.st_dev, opened.st_ino, opened.st_size)
            == (after.st_dev, after.st_ino, after.st_size)
            == (current.st_dev, current.st_ino, current.st_size),
            f"{label} changed while it was hashed",
        )
        return digest, opened.st_size
    finally:
        os.close(descriptor)


def hash_source_tree(root: Path) -> dict[str, object]:
    """Return a content/structure hash without returning any source bytes."""

    root = _regular_directory(root, "game directory")
    root_info = root.lstat()
    rows: list[tuple[str, Path, os.stat_result]] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise Slot43ExperimentError(f"game directory could not be scanned: {exc}") from exc
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            info = entry.stat(follow_symlinks=False)
            require(not stat.S_ISLNK(info.st_mode),
                    f"game directory contains a symlink: {relative}")
            if stat.S_ISDIR(info.st_mode):
                rows.append((f"D:{relative}", Path(entry.path), info))
                visit(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                rows.append((f"F:{relative}", Path(entry.path), info))
            else:
                raise Slot43ExperimentError(
                    f"game directory contains a non-file entry: {relative}"
                )

    visit(root)
    hasher = hashlib.sha256(b"APF2K8_SOURCE_TREE_V1\0")
    file_count = 0
    directory_count = 1
    total_bytes = 0
    for tagged_name, path, scanned in rows:
        tag, relative = tagged_name.split(":", 1)
        encoded = relative.encode("utf-8")
        require(len(encoded) <= 1024 * 1024, "game path is unreasonably long")
        hasher.update(tag.encode("ascii"))
        hasher.update(len(encoded).to_bytes(8, "big"))
        hasher.update(encoded)
        hasher.update(stat.S_IMODE(scanned.st_mode).to_bytes(4, "big"))
        if tag == "D":
            directory_count += 1
            current = path.lstat()
            require(
                stat.S_ISDIR(current.st_mode)
                and not stat.S_ISLNK(current.st_mode)
                and (current.st_dev, current.st_ino) == (scanned.st_dev, scanned.st_ino),
                f"game directory changed while it was hashed: {relative}",
            )
            continue
        digest, size = sha256_regular_file(path, f"game file {relative}")
        current = path.lstat()
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (scanned.st_dev, scanned.st_ino, scanned.st_size),
            f"game file changed while it was hashed: {relative}",
        )
        hasher.update(size.to_bytes(8, "big"))
        hasher.update(bytes.fromhex(digest))
        file_count += 1
        total_bytes += size
    root_after = root.lstat()
    require(
        (root_after.st_dev, root_after.st_ino) == (root_info.st_dev, root_info.st_ino),
        "game directory identity changed while it was hashed",
    )
    return {
        "sha256": hasher.hexdigest(),
        "file_count": file_count,
        "directory_count": directory_count,
        "total_bytes": total_bytes,
    }


def _create_isolated_roots(run_root: Path) -> dict[str, Path]:
    names = (
        "storage",
        "content",
        "cache",
        "home",
        "xdg-config",
        "xdg-data",
        "xdg-cache",
        "tmp",
        "logs",
    )
    roots: dict[str, Path] = {}
    for name in names:
        path = run_root / name
        os.mkdir(path, mode=0o700)
        require(path.is_dir() and not path.is_symlink() and not any(path.iterdir()),
                f"isolated {name} root is not a fresh empty directory")
        roots[name] = path
    return roots


def _find_xvfb_run() -> Path:
    found = shutil.which("xvfb-run", path=SAFE_PATH)
    require(found is not None, "xvfb-run is required for the headless experiment")
    return _regular_file(Path(found), "xvfb-run", executable=True)


def _find_env_executable() -> Path:
    found = shutil.which("env", path=SAFE_PATH)
    require(found is not None, "env is required for the headless experiment")
    return _regular_file(Path(found), "env", executable=True)


def _xenia_child_prefix(
    *, env_executable: Path, xenia: Path, roots: Mapping[str, Path]
) -> list[str]:
    """Restore the private temp root only after xvfb-run creates its auth file."""

    require("tmp" in roots, "isolated Xenia temporary root is missing")
    return [
        str(env_executable),
        f"TMPDIR={roots['tmp']}",
        str(xenia),
    ]


def build_command(
    *,
    xvfb_run: Path,
    env_executable: Path,
    xenia: Path,
    default_xex: Path,
    roots: Mapping[str, Path],
    xenia_log: Path,
    mode: str,
) -> list[str]:
    """Build the exact, isolated command; no user config flags are inherited."""

    require(mode in {"observe", "modified"}, "mode must be observe or modified")
    required_roots = {"storage", "content", "cache", "tmp"}
    require(required_roots <= roots.keys(), "isolated Xenia roots are incomplete")
    override = "true" if mode == "modified" else "false"
    command = [
        str(xvfb_run),
        "-a",
        "--server-args=-screen 0 1280x720x24",
    ]
    command.extend(_xenia_child_prefix(
        env_executable=env_executable,
        xenia=xenia,
        roots=roots,
    ))
    command.extend([
        "--gpu=null",
        "--apu=nop",
        "--hid=nop",
        "--fullscreen=false",
        "--portable=false",
        "--apply_title_update=false",
        "--apply_patches=false",
        "--allow_plugins=false",
        "--discord=false",
        "--mount_scratch=false",
        "--mount_memory_unit=false",
        "--license_mask=1",
        "--log_to_stdout=false",
        "--flush_log=true",
        "--log_level=2",
        f"--log_file={xenia_log}",
        f"--storage_root={roots['storage']}",
        f"--content_root={roots['content']}",
        f"--cache_root={roots['cache']}",
        "--apf_roster_slot43_log=true",
        f"--apf_roster_slot43_override={override}",
        str(default_xex),
    ])
    return command


def _isolated_environment(roots: Mapping[str, Path]) -> dict[str, str]:
    # Deliberately omit TMPDIR here.  Debian's xvfb-run expands its generated
    # Xauthority path without shell quoting when it invokes Xvfb.  A private
    # run path containing spaces therefore breaks the virtual display.  The
    # command restores roots["tmp"] for Xenia through /usr/bin/env after
    # xvfb-run has created its secure temporary auth directory under /tmp.
    return {
        "PATH": SAFE_PATH,
        "HOME": str(roots["home"]),
        "XDG_CONFIG_HOME": str(roots["xdg-config"]),
        "XDG_DATA_HOME": str(roots["xdg-data"]),
        "XDG_CACHE_HOME": str(roots["xdg-cache"]),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _open_exclusive_log(path: Path) -> int:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    return os.open(path, flags, 0o600)


def _launch_bounded(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    launcher_log: Path,
    timeout_seconds: int,
) -> ExecutionReceipt:
    """Launch one isolated process group and always stop it within the bound."""

    started_at = time.monotonic()
    descriptor = _open_exclusive_log(launcher_log)
    process: subprocess.Popen[bytes] | None = None
    try:
        with os.fdopen(descriptor, "wb") as stream:
            process = subprocess.Popen(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=dict(environment),
                start_new_session=True,
                close_fds=True,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
                termination = "exited"
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = "timeout_sigterm"
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    returncode = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    termination = "timeout_sigkill"
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    returncode = process.wait(timeout=5)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        return ExecutionReceipt(True, timed_out, returncode, duration_ms, termination)
    except OSError:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        return ExecutionReceipt(False, False, None, duration_ms, "launch_failed")


def _tokens(payload: str) -> dict[str, str]:
    return {name: value.rstrip(",") for name, value in TOKEN_RE.findall(payload)}


def _valid_hex32(value: str | None) -> bool:
    return value is not None and HEX32_RE.fullmatch(value) is not None


def _contains_ordered(
    events: Sequence[tuple[str, str]], required: Sequence[tuple[str, str]]
) -> bool:
    cursor = 0
    for event in events:
        if event == required[cursor]:
            cursor += 1
            if cursor == len(required):
                return True
    return False


def parse_receipt_lines(lines: Iterable[str]) -> ParsedReceipts:
    """Parse APF receipts while retaining no raw line or guest pointer value."""

    target_modes: list[str] = []
    accepted_modes: list[str] = []
    target_matched = 0
    validation_accepted = 0
    validation_rejected = 0
    malformed = 0
    apf_line_count = 0
    actions: dict[str, Counter[str]] = {
        site: Counter() for site in sorted(KNOWN_SITES)
    }
    first_target: int | None = None
    first_accepted: int | None = None
    first_event: int | None = None
    accepted_team: str | None = None
    accepted_candidate: str | None = None
    active_identity: tuple[str, str, str] | None = None
    active_events: list[tuple[str, str]] = []
    complete_observe_traversals = 0
    complete_modified_traversals = 0

    def finish_traversal() -> None:
        nonlocal complete_observe_traversals, complete_modified_traversals
        if _contains_ordered(
            active_events,
            (
                ("count_entry", "observed"),
                ("count_exit", "observed"),
                ("getter_entry", "observed"),
                ("getter_found", "stock_return"),
            ),
        ):
            complete_observe_traversals += 1
        if _contains_ordered(
            active_events,
            (
                ("count_entry", "observed"),
                ("count_exit", "count_incremented"),
                ("getter_entry", "observed"),
                ("getter_miss", "candidate_returned"),
            ),
        ):
            complete_modified_traversals += 1

    for line in lines:
        marker = line.find("APF_SLOT43")
        if marker < 0:
            continue
        apf_line_count += 1
        if apf_line_count > MAX_APF_LINES:
            malformed += 1
            break
        values = _tokens(line[marker + len("APF_SLOT43"):])
        receipt = values.get("receipt")
        if receipt is not None:
            if receipt == "target_matched":
                target_matched += 1
                first_target = apf_line_count if first_target is None else first_target
                mode = values.get("mode", "")
                site = values.get("site", "")
                lr = values.get("lr")
                target_modes.append(mode)
                if (
                    mode not in {"observe", "modified"}
                    or site not in KNOWN_SITES
                    or not _valid_hex32(lr)
                    or lr.upper() != SITE_LR[site]
                ):
                    malformed += 1
            elif receipt == "validation_accepted":
                validation_accepted += 1
                first_accepted = (
                    apf_line_count if first_accepted is None else first_accepted
                )
                mode = values.get("mode", "")
                team = values.get("team0")
                candidate = values.get("candidate")
                accepted_modes.append(mode)
                if (
                    mode not in {"observe", "modified"}
                    or not _valid_hex32(team)
                    or not _valid_hex32(candidate)
                    or values.get("stock_cb_count") != "4"
                ):
                    malformed += 1
                elif accepted_team is None:
                    accepted_team = team.upper()
                    accepted_candidate = candidate.upper()
                elif (
                    accepted_team != team.upper()
                    or accepted_candidate != candidate.upper()
                ):
                    malformed += 1
            elif receipt == "validation_rejected":
                validation_rejected += 1
                site = values.get("site", "")
                lr = values.get("lr")
                if (
                    site not in KNOWN_SITES
                    or not _valid_hex32(lr)
                    or lr.upper() != SITE_LR[site]
                ):
                    malformed += 1
            else:
                malformed += 1
            continue

        site = values.get("site", "")
        action = values.get("action", "")
        if site not in KNOWN_SITES or action not in SITE_ACTIONS.get(site, set()):
            malformed += 1
            continue
        first_event = apf_line_count if first_event is None else first_event
        lr = values.get("lr")
        thread = values.get("thread")
        team = values.get("team0")
        candidate = values.get("candidate")
        if (
            not _valid_hex32(lr)
            or lr.upper() != SITE_LR[site]
            or not _valid_hex32(thread)
            or not _valid_hex32(team)
            or not _valid_hex32(candidate)
            or values.get("stock_cb_count") != "4"
        ):
            malformed += 1
            continue
        if accepted_team is not None and (
            team.upper() != accepted_team or candidate.upper() != accepted_candidate
        ):
            malformed += 1
            continue
        if site == "getter_miss":
            ordinal = values.get("ordinal")
            if not _valid_hex32(ordinal) or int(ordinal, 16) != 4:
                malformed += 1
                continue
        identity = (thread.upper(), team.upper(), candidate.upper())
        if site == "count_entry":
            if active_identity is not None:
                finish_traversal()
            active_identity = identity
            active_events = []
        elif active_identity is None or identity != active_identity:
            malformed += 1
            continue
        active_events.append((site, action))
        actions[site][action] += 1

    if active_identity is not None:
        finish_traversal()

    order_valid = True
    if validation_accepted or any(actions[site] for site in actions):
        order_valid = (
            first_target is not None
            and first_accepted is not None
            and first_target < first_accepted
            and (first_event is None or first_accepted < first_event)
        )
    return ParsedReceipts(
        target_matched=target_matched,
        validation_accepted=validation_accepted,
        validation_rejected=validation_rejected,
        target_modes=tuple(target_modes),
        accepted_modes=tuple(accepted_modes),
        event_actions={site: dict(counter) for site, counter in actions.items()},
        malformed_line_count=malformed,
        apf_line_count=apf_line_count,
        order_valid=order_valid,
        complete_observe_traversals=complete_observe_traversals,
        complete_modified_traversals=complete_modified_traversals,
    )


def parse_receipt_log(path: Path) -> ParsedReceipts:
    log = _regular_file(path, "Xenia experiment log")
    require(log.stat().st_size <= MAX_LOG_SIZE, "Xenia experiment log is too large")
    with log.open("r", encoding="utf-8", errors="replace") as stream:
        return parse_receipt_lines(stream)


def classify_receipts(
    mode: str,
    receipts: ParsedReceipts,
    *,
    execution_acceptable: bool = True,
    source_tree_unchanged: bool = True,
    default_xex_unchanged: bool = True,
) -> tuple[str, list[str]]:
    """Classify only complete receipt sets; partial traffic never proves a path."""

    reject_reasons: list[str] = []
    if not execution_acceptable:
        reject_reasons.append("emulator_execution_failed")
    if not source_tree_unchanged:
        reject_reasons.append("source_tree_changed")
    if not default_xex_unchanged:
        reject_reasons.append("default_xex_changed")
    if receipts.validation_rejected:
        reject_reasons.append("hook_validation_rejected")
    if receipts.malformed_line_count:
        reject_reasons.append("malformed_receipt")
    if not receipts.order_valid:
        reject_reasons.append("receipt_order_invalid")
    if receipts.target_matched > 1 or receipts.validation_accepted > 1:
        reject_reasons.append("duplicate_receipt")
    if any(value != mode for value in receipts.target_modes + receipts.accepted_modes):
        reject_reasons.append("receipt_mode_mismatch")

    event = receipts.event_actions
    modifying_actions = (
        event.get("count_exit", {}).get("count_incremented", 0)
        + event.get("getter_miss", {}).get("candidate_returned", 0)
    )
    if mode == "observe" and modifying_actions:
        reject_reasons.append("observe_log_contains_override")
    if reject_reasons:
        return "validation_rejected", sorted(set(reject_reasons))

    if receipts.target_matched != 1 or receipts.validation_accepted != 1:
        return "path_not_reached", ["complete_target_receipts_not_seen"]

    if mode == "observe":
        if receipts.complete_observe_traversals > 0:
            return "observe_path_proved", []
        return "path_not_reached", ["complete_observe_path_not_seen"]

    if receipts.complete_modified_traversals > 0:
        return "modified_path_proved", []
    return "path_not_reached", ["complete_modified_path_not_seen"]


def _write_json_exclusive(path: Path, document: Mapping[str, object]) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(
                (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
            )
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        raise


def _manifest(
    *,
    mode: str,
    timeout_seconds: int,
    dry_run: bool,
    xenia: Path,
    xenia_size: int,
    game_root: Path,
    default_xex: Path,
    default_xex_size: int,
    source_before: Mapping[str, object],
    command: Sequence[str],
    roots: Mapping[str, Path],
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "mode": mode,
        "dry_run": dry_run,
        "timeout_seconds": timeout_seconds,
        "toolchain": {
            "xenia_path": str(xenia),
            "xenia_size": xenia_size,
            "xenia_sha256": XENIA_SHA256,
            "hook_commit": HOOK_COMMIT,
        },
        "source": {
            "game_directory": str(game_root),
            "default_xex": str(default_xex),
            "default_xex_size": default_xex_size,
            "default_xex_sha256": DEFAULT_XEX_SHA256,
            "tree_before": dict(source_before),
            "opened_read_only": True,
        },
        "isolation": {
            "storage_root": str(roots["storage"]),
            "content_root": str(roots["content"]),
            "cache_root": str(roots["cache"]),
            "xenia_tmp_root": str(roots["tmp"]),
            "home_root": str(roots["home"]),
            "xdg_config_root": str(roots["xdg-config"]),
            "xdg_data_root": str(roots["xdg-data"]),
            "xdg_cache_root": str(roots["xdg-cache"]),
            "fresh_empty_content_root": True,
            "xvfb_tmpdir_inherited": False,
            "xenia_tmpdir_restored_after_xvfb_setup": True,
        },
        "command": list(command),
        "safety": {
            "headless_xvfb": True,
            "apply_title_update": False,
            "apply_patches": False,
            "allow_plugins": False,
            "discord": False,
            "apu": "nop",
            "hid": "nop",
            "gpu": "null",
            "slot43_log": True,
            "slot43_override": mode == "modified",
            "game_files_copied": False,
            "game_files_written_by_runner": False,
            "retail_payload_embedded_in_tool": False,
        },
    }


def _empty_receipts() -> ParsedReceipts:
    return parse_receipt_lines(())


def run_experiment(
    *,
    xenia_path: Path,
    game_directory: Path,
    run_root_path: Path,
    mode: str = "observe",
    confirmation: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, object]:
    require(mode in {"observe", "modified"}, "mode must be observe or modified")
    require(
        MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS,
        f"timeout must be {MIN_TIMEOUT_SECONDS} to {MAX_TIMEOUT_SECONDS} seconds",
    )
    if mode == "modified":
        require(
            confirmation == MODIFIED_CONFIRMATION,
            "modified mode requires the exact --confirm-modified token",
        )
    else:
        require(confirmation in {None, ""},
                "--confirm-modified is only valid in modified mode")

    game_root = _regular_directory(game_directory, "game directory")
    default_xex = _regular_file(game_root / "default.xex", "APF default.xex")
    require(default_xex.parent == game_root,
            "default.xex must be directly inside the game directory")
    xenia = _regular_file(xenia_path, "pinned Xenia", executable=True)
    require(not _path_contains(game_root, xenia),
            "Xenia cannot be stored inside the game directory")

    xenia_sha, xenia_size = sha256_regular_file(xenia, "pinned Xenia")
    require(xenia_sha == XENIA_SHA256,
            "Xenia binary hash does not match the reviewed slot-43 build")
    default_sha, default_size = sha256_regular_file(default_xex, "APF default.xex")
    require(default_sha == DEFAULT_XEX_SHA256,
            "default.xex is not the supported APF 2K8 USA executable")

    source_before = hash_source_tree(game_root)
    run_root = _create_run_root(run_root_path, game_root, xenia)
    roots = _create_isolated_roots(run_root)
    xvfb_run = _find_xvfb_run()
    env_executable = _find_env_executable()
    xenia_log = roots["logs"] / "xenia.log"
    launcher_log = roots["logs"] / "launcher.log"
    command = build_command(
        xvfb_run=xvfb_run,
        env_executable=env_executable,
        xenia=xenia,
        default_xex=default_xex,
        roots=roots,
        xenia_log=xenia_log,
        mode=mode,
    )
    require(not any(roots["content"].iterdir()),
            "isolated content root was not empty immediately before launch")

    manifest = _manifest(
        mode=mode,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
        xenia=xenia,
        xenia_size=xenia_size,
        game_root=game_root,
        default_xex=default_xex,
        default_xex_size=default_size,
        source_before=source_before,
        command=command,
        roots=roots,
    )
    manifest_path = run_root / "manifest.json"
    if dry_run:
        source_after = hash_source_tree(game_root)
        default_after, _ = sha256_regular_file(default_xex, "APF default.xex")
        manifest["dry_run_integrity"] = {
            "tree_after": source_after,
            "tree_unchanged": source_after == source_before,
            "default_xex_unchanged": default_after == default_sha,
        }
        require(source_after == source_before and default_after == default_sha,
                "source game changed during dry-run preparation")
        _write_json_exclusive(manifest_path, manifest)
        return manifest

    _write_json_exclusive(manifest_path, manifest)
    require(not any(roots["content"].iterdir()),
            "isolated content root changed before launch")
    xenia_prelaunch, _ = sha256_regular_file(xenia, "pinned Xenia")
    require(xenia_prelaunch == xenia_sha,
            "Xenia binary changed after the manifest was written")
    execution = _launch_bounded(
        command,
        cwd=run_root,
        environment=_isolated_environment(roots),
        launcher_log=launcher_log,
        timeout_seconds=timeout_seconds,
    )

    post_hash_error = False
    try:
        source_after = hash_source_tree(game_root)
        default_after, _ = sha256_regular_file(default_xex, "APF default.xex")
    except (OSError, Slot43ExperimentError):
        post_hash_error = True
        source_after = {"sha256": None}
        default_after = None

    log_parse_error = False
    if xenia_log.is_file() and not xenia_log.is_symlink():
        try:
            receipts = parse_receipt_log(xenia_log)
        except (OSError, UnicodeError, Slot43ExperimentError):
            receipts = _empty_receipts()
            log_parse_error = True
    else:
        receipts = _empty_receipts()
        log_parse_error = True

    source_unchanged = not post_hash_error and source_after == source_before
    default_unchanged = not post_hash_error and default_after == default_sha
    execution_acceptable = execution.started and (
        execution.timed_out or execution.returncode == 0
    )
    classification, reasons = classify_receipts(
        mode,
        receipts,
        execution_acceptable=execution_acceptable,
        source_tree_unchanged=source_unchanged,
        default_xex_unchanged=default_unchanged,
    )
    if post_hash_error:
        reasons.append("source_post_hash_failed")
        classification = "validation_rejected"
    if log_parse_error:
        reasons.append("xenia_log_unavailable_or_invalid")
        classification = "validation_rejected"
    reasons = sorted(set(reasons))

    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "mode": mode,
        "classification": classification,
        "reason_codes": reasons,
        "toolchain": {
            "xenia_sha256": XENIA_SHA256,
            "hook_commit": HOOK_COMMIT,
            "default_xex_sha256": DEFAULT_XEX_SHA256,
        },
        "execution": {
            "started": execution.started,
            "timed_out": execution.timed_out,
            "returncode": execution.returncode,
            "duration_ms": execution.duration_ms,
            "termination": execution.termination,
            "timeout_seconds": timeout_seconds,
        },
        "integrity": {
            "source_tree_sha256_before": source_before["sha256"],
            "source_tree_sha256_after": source_after.get("sha256"),
            "source_tree_unchanged": source_unchanged,
            "default_xex_unchanged": default_unchanged,
            "runner_direct_write_calls_to_source": False,
        },
        "receipts": receipts.sanitized(),
        "artifacts": {
            "manifest": "manifest.json",
            "xenia_log": "logs/xenia.log",
            "launcher_log": "logs/launcher.log",
            "raw_logs_private": True,
        },
        "claims": {
            "observe_consumer_path_proved": classification == "observe_path_proved",
            "one_candidate_returned_by_exact_consumer": (
                classification == "modified_path_proved"
            ),
            "true_53_man_rosters_proved": False,
            "all_roster_consumers_extended": False,
            "gameplay_visibility_proved": False,
            "retail_game_bytes_copied_by_runner": False,
            "retail_game_bytes_embedded_in_result": False,
        },
    }
    _write_json_exclusive(run_root / "result.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xenia", required=True, type=Path,
                        help="reviewed native Xenia slot-43 binary")
    parser.add_argument("--game-dir", required=True, type=Path,
                        help="your extracted APF 2K8 game directory")
    parser.add_argument("--run-root", required=True, type=Path,
                        help="new private directory for this experiment")
    parser.add_argument("--mode", choices=("observe", "modified"),
                        default="observe")
    parser.add_argument(
        "--confirm-modified",
        help=f"modified mode requires exactly: {MODIFIED_CONFIRMATION}",
    )
    parser.add_argument("--timeout-seconds", type=int,
                        default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--dry-run", action="store_true",
                        help="write and print the manifest without launching Xenia")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        document = run_experiment(
            xenia_path=args.xenia,
            game_directory=args.game_dir,
            run_root_path=args.run_root,
            mode=args.mode,
            confirmation=args.confirm_modified,
            timeout_seconds=args.timeout_seconds,
            dry_run=args.dry_run,
        )
    except (OSError, Slot43ExperimentError, subprocess.SubprocessError) as exc:
        print(f"APF_SLOT43_EXPERIMENT_REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(document, indent=2, sort_keys=True))
    if args.dry_run:
        return 0
    return 1 if document["classification"] == "validation_rejected" else 0


if __name__ == "__main__":
    raise SystemExit(main())
