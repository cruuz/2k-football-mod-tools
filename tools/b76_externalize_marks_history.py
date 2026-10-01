#!/usr/bin/env python3
"""Make a local publication snapshot/bundle without private marks or evidence.

Reads SOURCE only. Writes only beneath a new SCRATCH directory; creates no remotes
or tags and never pushes. Run after all Beta 76 changes are integrated.

The snapshot has BASE as its sole parent and exactly HEAD's tree. It squashes the
unpublished stack, including a stack forked before BASE, without moving BASE or
its tag. Review BASE..HEAD first: this does not merge missing BASE file changes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

BOUNDARY = "packaging/b76_private_paths.json"


def run(source: Path, scratch: Path, base_ref: str, head_ref: str) -> dict:
    def source_git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args])

    base = source_git("rev-parse", base_ref + "^{commit}").decode().strip()
    head = source_git("rev-parse", head_ref + "^{commit}").decode().strip()
    boundary = json.loads(source_git("show", head + ":" + BOUNDARY))
    if boundary.get("schema") != "b76_private_paths/v1":
        raise ValueError("unsupported private marks boundary")
    paths = boundary["paths"]
    fork = source_git("merge-base", base, head).decode().strip()
    base_only = source_git("rev-list", head + ".." + base).decode().splitlines()
    # Require the code removal to have been integrated before rewriting history.
    tip_files = source_git("ls-tree", "-r", "--name-only", head).decode().splitlines()
    if set(paths).intersection(tip_files):
        raise ValueError("Integrate the boundary first: head still tracks private marks/evidence")
    scratch = scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    repo = scratch / "history.git"
    subprocess.run(["git", "init", "--bare", str(repo)], check=True, stdout=subprocess.DEVNULL)
    objects = source_git("rev-parse", "--path-format=absolute", "--git-path", "objects").decode().strip()
    # Git treats CR as part of an alternate object-directory name. Text-mode
    # writes on Windows would turn the terminator into CRLF and hide the source
    # objects from the scratch repository.
    (repo / "objects/info/alternates").write_bytes(objects.encode("utf-8") + b"\n")
    env = {**os.environ, "GIT_INDEX_FILE": str(scratch / "rewrite.index"), "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args, data=None):
        return subprocess.check_output(["git", "--git-dir=" + str(repo), "-c", "pack.threads=1",
                                       "-c", "pack.windowMemory=32m", *args], input=data, env=env)

    # Path-limited object traversal catches EVERY historical version, not only
    # current hashes. Ban their content wherever else it occurs too, including renames.
    ids = source_git("rev-list", "--objects", "--no-object-names", base + ".." + head, "--", *paths)
    typed = git("cat-file", "--batch-check=%(objectname) %(objecttype)", data=ids).decode().splitlines()
    banned = {line.split()[0] for line in typed if line.endswith(" blob")} | set(boundary["blobs"])
    if not banned:
        raise ValueError("No historical mark blobs found in this range")
    base_objects = {line.split()[0] for line in git("rev-list", "--objects", base).decode().splitlines()}
    if banned.intersection(base_objects):
        raise ValueError("A banned blob is already in the released base; refuse to rewrite that base")
    commits = git("rev-list", "--reverse", "--topo-order", base + ".." + head).decode().splitlines()
    tree = git("rev-parse", head + "^{tree}").decode().strip()
    # Preserve the source tip's attribution/time, but explicitly identify the squash.
    raw = git("cat-file", "commit", head)
    headers = raw.split(b"\n\n", 1)[0].split(b"\n")
    identities = [line for line in headers if line.startswith((b"author ", b"committer "))]
    message = ("Beta 76: integrated publication snapshot with private marks externalized\n\n"
               f"Snapshot tree from private integration tip {head}.\n"
               f"Released parent remains {base}.\n"
               "The unpublished stack is squashed; no automatic content merge was performed.\n\n"
               "Co-Authored-By: GPT-6 Astra (Codex) <noreply@openai.com>\n")
    content = (f"tree {tree}\nparent {base}\n".encode() + b"\n".join(identities)
               + b"\n\n" + message.encode())
    clean = git("hash-object", "-t", "commit", "-w", "--stdin", data=content).decode().strip()
    git("update-ref", "refs/heads/b76-marks-clean", clean)
    git("update-ref", "refs/heads/released-base", base)
    for label, revisions in (("pushed-range", [base + ".." + clean]), ("full-ancestry", [clean])):
        objects = git("rev-list", "--objects", *revisions)
        (scratch / (label + "-objects.txt")).write_bytes(objects)
        seen = {line.split()[0] for line in objects.decode().splitlines()}
        if banned.intersection(seen):
            raise ValueError(f"Banned blob still reachable in {label}")
    git("merge-base", "--is-ancestor", base, clean)
    # At the cleaned tip every non-target file must be byte-identical to the input tip.
    if git("diff", "--name-only", head, clean).strip():
        raise ValueError("Cleaned tip differs from integrated input tip")
    bundle = scratch / "b76-marks-clean.bundle"
    git("bundle", "create", str(bundle), base + "..refs/heads/b76-marks-clean")
    verification = subprocess.run(["git", "--git-dir=" + str(repo), "bundle", "verify", str(bundle)],
                                  capture_output=True, text=True, check=True)
    (scratch / "bundle-verify.txt").write_text(verification.stdout + verification.stderr)
    (scratch / "banned-blobs.txt").write_text("\n".join(sorted(banned)) + "\n")
    (scratch / "squashed-commits.txt").write_text("\n".join(commits) + "\n")
    proof = dict(base=base, original_head=head, clean_head=clean, commits=len(commits),
                 strategy="single publication snapshot", fork=fork, base_only_commits=base_only,
                 publication_commits=1, banned_blobs=sorted(banned),
                 externalized_paths=paths, base_unchanged=True, tip_tree_identical=True,
                 banned_blobs_reachable=False, bundle=str(bundle))
    (scratch / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True, help="new, nonexistent directory")
    parser.add_argument("--base", default="beta-75")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.scratch, args.base, args.head), indent=2))


if __name__ == "__main__":
    main()
