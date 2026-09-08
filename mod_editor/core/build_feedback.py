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


def completion(receipt):
    """A missing measurement never becomes a claim that patches were written."""
    outcome = receipt.get("outcome", {})
    if outcome.get("status") == "unchanged":
        return "No changes written", outcome["message"]
    if outcome.get("status") == "changed":
        return "Disc ready", outcome["message"]
    return "Copy ready; changes not measured", "This receipt does not establish whether the output differs from the source."
