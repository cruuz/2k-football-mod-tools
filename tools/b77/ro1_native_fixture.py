"""Same native service boundaries, with entry hooks at basic-block granularity.

Function-entry service replacements need not inspect every native instruction.
No league, roster, contract, class-generation or draft routine is replaced.
"""
from tests.nfl2k5_my_career_played_fixture import Machine as PlayedMachine


class Machine(PlayedMachine):
    def stub(self, va, action):
        va = self.labels.get(va, va)
        self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_BLOCK,
            lambda *_: action(), begin=va, end=va))

    def replace_stub(self, va, action):
        if va in self.hooks:
            self.uc.hook_del(self.hooks.pop(va))
        if action is not None:
            self.hooks[va] = self.uc.hook_add(self.u.UC_HOOK_BLOCK,
                lambda *_: action(), begin=va, end=va)
