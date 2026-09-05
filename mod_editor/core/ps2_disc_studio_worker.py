"""One PS2 Disc Studio build step, run as a child process.

``python -m mod_editor.core.ps2_disc_studio_worker <job.json>`` reads a job
the service wrote -- lane, source image, destination image, recipe,
catalogue path, work directory -- and does the three things a step is:

1. **plan** the recipe against the step's actual input with the lane's own
   dry run (in a chained queue that input is the previous step's output, not
   the original disc);
2. **write** the new image through the lane's own patcher;
3. **verify** input against output with the lane's independent verifier.

Progress is streamed to stdout as one JSON object per line
(``{"event": "stage", "text": "..."}``) and the outcome is written to the
job's ``result_path``.  Exit status 0 means the result says ``ok``; anything
else means the destination this step created has been removed and the result
carries the stage and the lane's own sentence.

Why a child process rather than a thread: the ISO writer has no cancel hook,
a step stages a 1 GiB pack in memory, and a stadium refit can run for tens of
minutes.  The service kills this process to cancel and frees the memory by
letting it exit.  :func:`run_step` is also importable, so the same code is
unit-tested in-process.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.ps2_disc_studio_lanes import (  # noqa: E402
    LaneRefusal,
    Ps2DiscStudioError,
    lane as lane_by_id,
)

JOB_SCHEMA = "nfl2k5_ps2_disc_studio_job/v1"
RESULT_SCHEMA = "nfl2k5_ps2_disc_studio_step_result/v1"


def _emit(event: str, **fields: Any) -> None:
    sys.stdout.write(json.dumps(dict(event=event, **fields), sort_keys=True) + "\n")
    sys.stdout.flush()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def run_step(job: Dict[str, Any], progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Plan, write and verify one step.  Raises the lane's own refusal on failure."""
    announce = progress if progress is not None else (lambda _text: None)
    if job.get("schema") != JOB_SCHEMA:
        raise Ps2DiscStudioError(f"the job is not a {JOB_SCHEMA} document")
    lane = lane_by_id(str(job["lane"]))
    source = Path(job["source"])
    destination = Path(job["destination"])
    catalogue_path = Path(job["catalogue_path"])
    work_dir = Path(job["work_dir"])
    recipe = job["recipe"]
    if not source.is_file():
        raise Ps2DiscStudioError(f"the step's input image is missing: {source}")
    if os.path.lexists(destination):
        raise Ps2DiscStudioError(f"the destination already exists: {destination}")
    if not catalogue_path.is_file():
        raise Ps2DiscStudioError(f"the {lane.title} catalogue is missing: {catalogue_path}")
    work_dir.mkdir(parents=True, exist_ok=True)
    seconds: Dict[str, float] = {}

    def timed(stage: str, text: str, call: Callable[[], Any]) -> Any:
        announce(text)
        started = time.monotonic()
        try:
            return call()
        except LaneRefusal:
            raise
        except Ps2DiscStudioError as exc:
            raise LaneRefusal(lane.id, str(exc), stage) from exc
        finally:
            seconds[stage] = round(time.monotonic() - started, 2)

    input_sha256 = None
    if job.get("hash_input"):
        input_sha256 = timed("hash_input", "hashing the source image", lambda: _sha256_file(source))
    plan = timed("plan", "checking the recipe against this step's input image",
                 lambda: lane.plan(source, recipe, catalogue_path, work_dir))
    receipt = timed("write", "writing the new image (a full copy plus one rewritten pack)",
                    lambda: lane.apply(source, destination, recipe, catalogue_path, work_dir))
    verdict = timed("verify", "running the independent verifier over both images",
                    lambda: lane.verify(source, destination, receipt, recipe, catalogue_path, work_dir))
    output_sha256 = timed("hash_output", "hashing the new image", lambda: _sha256_file(destination))
    return {
        "schema": RESULT_SCHEMA,
        "ok": True,
        "lane": lane.id,
        "plan_summary": plan.summary,
        "plan_detail": plan.detail,
        "receipt": receipt,
        "receipt_summary": lane.receipt_summary(receipt),
        "verdict": {"passed": verdict.passed, "summary": verdict.summary, "report": verdict.report},
        "seconds": seconds,
        "input_sha256": input_sha256,
        "output_size": destination.stat().st_size,
        "output_sha256": output_sha256,
    }


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        sys.stderr.write("usage: python -m mod_editor.core.ps2_disc_studio_worker <job.json>\n")
        return 2
    job_path = Path(args[0])
    try:
        job = json.loads(job_path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"could not read the job: {exc}\n")
        return 2
    result_path = Path(job.get("result_path") or job_path.with_name("result.json"))
    destination = Path(str(job.get("destination", "")))
    existed = bool(destination) and os.path.lexists(destination)
    try:
        result = run_step(job, lambda text: _emit("stage", text=text))
    except BaseException as exc:  # noqa: BLE001 - the whole point is to report it
        if destination and not existed and os.path.lexists(destination):
            destination.unlink(missing_ok=True)
        stage = getattr(exc, "stage", "") or ""
        message = str(exc).strip() or exc.__class__.__name__
        result_path.write_bytes(_json_bytes({
            "schema": RESULT_SCHEMA, "ok": False, "lane": job.get("lane"),
            "stage": stage, "error": message,
        }))
        _emit("failed", stage=stage, error=message)
        return 3 if isinstance(exc, KeyboardInterrupt) else 2
    result_path.write_bytes(_json_bytes(result))
    _emit("done", verified=result["verdict"]["passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
