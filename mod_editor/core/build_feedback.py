"""Measured build outcomes, independent of optimistic step names."""
import hashlib
from pathlib import Path

BLOCK = 1024 * 1024


def _digest(path):
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(BLOCK), b""):
            digest.update(block)
            size += len(block)
    return {"sha256": digest.hexdigest(), "size": size}


def measure(source, target):
    """Compare final files after all writers, before publishing a success notice."""
    before, after = _digest(source), _digest(target)
    changed = before != after
    return {"status": "changed" if changed else "unchanged", "source": before, "output": after,
            "message": ("The output differs from the source. Review the build receipt for the selected changes."
                        if changed else "No changes were written. The output is an unchanged copy of the source. "
                        "The selected patches may already be installed; review the source and your selections.")}


def kept_retail_notes(receipt):
    """Slots a build step kept at retail because their art could not fit.

    The shared texture project reports these as ``kept_retail`` rows on its
    step (``BuildResult.kept_retail``).  They are warnings on a finished disc,
    not failures, and the completion notice must carry them so a modder does
    not go looking in-game for a digit the builder never wrote.
    """
    notes = []
    for step in receipt.get("steps", []) or ():
        if not isinstance(step, dict):
            continue
        for row in step.get("kept_retail", ()) or ():
            if isinstance(row, dict):
                notes.append(str(row.get("message") or row.get("selector") or "unknown slot"))
    return notes


def completion(receipt):
    """A missing measurement never becomes a claim that patches were written."""
    outcome = receipt.get("outcome", {})
    if outcome.get("status") == "unchanged":
        title, message = "No changes written", outcome["message"]
    elif outcome.get("status") == "changed":
        title, message = "Disc ready", outcome["message"]
    else:
        title, message = "Copy ready; changes not measured", "This receipt does not establish whether the output differs from the source."
    notes = kept_retail_notes(receipt)
    if notes:
        message += (
            f"\n\nKept retail for {len(notes)} uniform slot{'s' if len(notes) != 1 else ''} "
            "whose art could not fit its fixed texture slot:\n"
            + "\n".join(f"- {note}" for note in notes)
        )
    return title, message
