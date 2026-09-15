"""Check the delivery diff, protected paths and public attribution rule."""
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[2]
git = ["git", "--git-dir=.scratch/git", "--work-tree=."]
base = "e2f5c6e61a0aa5772b0b7d858cb3fb3d35896174"
def capture(*args):
    return subprocess.check_output([*git, *args], cwd=root, text=True)

changed = capture("diff", "--name-only", base).splitlines()
protected = [p for p in changed if p.startswith(("mod_editor/gui/", "mod_editor/capabilities/registry", "packaging/check_"))
             or p in ("mod_editor/core/mod_build.py", "packaging/release-allowlist.txt", "mod_editor/core/update_check.py",
                      "data/nfl2k5_cave_reservations.json")
             or (p.startswith("tests/") and ("installer" in p or "release" in p))]
assert not protected, protected
history = capture("show", base + ":docs/mod_editor/apf2k8_mod_studio_changelog.md")
attributions = set(re.findall(r'^- (\w+): [“"]', history, re.MULTILINE))
added = "\n".join(line[1:] for line in capture("diff", "--unified=0", base).splitlines()
                  if line.startswith("+") and not line.startswith("+++"))
texts = [added]
texts.extend(p.read_text(encoding="utf-8") for p in (root / "reports/b71_apf2").iterdir()
             if p.suffix in (".md", ".json", ".jsonl", ".py", ".log"))
assert not any(re.search(r'\b' + re.escape(name) + r'\b', text, re.IGNORECASE)
               for name in attributions for text in texts), "A new artifact repeats an old tester attribution"
helper = root / "tools/apf_h7a_optimal"
assert helper.stat().st_mode & 0o777 == 0o755
scratch = sum(p.stat().st_size for p in (root / ".scratch").rglob("*") if p.is_file() and not p.is_symlink())
assert scratch < 200 * 1024 * 1024, scratch
result = {"changed_paths": changed, "protected_paths_changed": protected,
          "public_attribution_check": "pass", "h7a_helper_mode": "0755", "scratch_bytes": scratch,
          "base": base, "head": capture("rev-parse", "HEAD").strip(), "gameplay": "UNWITNESSED"}
print(json.dumps(result, indent=2))
