"""Exercise the actual protected-file code blocks in WIRING.md in memory.

Never edits GUI sources. Once integration lands, run the suites without this
helper as well. Source lines in diagnostic stacks point back to the handoff.
"""
import functools
import linecache
from pathlib import Path
import re
import textwrap

ROOT = Path(__file__).resolve().parents[2]


def sources(shell):
    handoff = (ROOT / "WIRING.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
    result = {}
    for name, block in re.findall(r'### `(_\w+)`\n\n```python\n(.*?)\n```', handoff, re.S):
        assert hasattr(shell.StudioMainWindow, name), name
        result[name] = textwrap.dedent(block) + "\n"
    assert {"_show_workspace", "_prefill_panels_from_source", "_refresh_entered_page"} <= result.keys()
    return result


def install(shell):
    if getattr(shell.StudioMainWindow, "_b661_wiring_installed", False):
        return
    for name, source in sources(shell).items():
        namespace = {}
        filename = f"<WIRING.md:{name}>"
        linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
        exec(compile(source, filename, "exec"), vars(shell), namespace)
        setattr(shell.StudioMainWindow, name, namespace[name])
    original = shell.StudioMainWindow.__init__
    @functools.wraps(original)
    def initialize(self, *args, **kwargs):
        original(self, *args, **kwargs)
        # The source hook runs just after _build_ui. Both execute before Open
        # Disc or any asynchronous page entry; do not install twice if wired.
        if not hasattr(self, "_stall_watchdog"):
            from mod_editor.gui.workspace_runtime import install
            self._stall_watchdog = install(self)
    shell.StudioMainWindow.__init__ = initialize
    shell.StudioMainWindow._b661_wiring_installed = True
