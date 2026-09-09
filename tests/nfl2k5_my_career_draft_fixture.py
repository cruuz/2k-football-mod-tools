"""Native CAP and draft fixture with explicit prior-year input preconditions.

Fast tests begin from the pinned f0 franchise, supplying year-1 untouched
Combine scalars and a declared prior-season ordering of clubs 0 through 31.
They do not prove the prior-year bootstrap. The separate
probe executes that route from the retail ROST. No pick, signing, cleanup,
serializer, identity or purchase routine is substituted.
"""
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_played_fixture import Machine as PlayedMachine
from tests.nfl2k5_supersim_draft_fixture import signed_save


class Machine(PlayedMachine):
    def prepare_draft(self, roster, *, position=0, seed=2, ratings=None, preseason=True, one_pool=False, complete=True):
        self.frontend(roster)
        self.native_load(signed_save(), requested=False)
        # End the load-preview service seam before any native league work.
        # Preseason simulation needs both real match-to-primary mapping tables.
        for va in (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77470, 0x77B00):
            self.replace_stub(va, None)
        self.replace_stub(0x16C880, None)
        self.child_services()
        self.replace_stub(0x48BC0, None)
        self.replace_stub(0x177990, lambda: self.ret(pop=4))  # progress presentation
        # f0 has no completed prior year: its schedule-rank bytes are FF.
        # Supply this explicit input along with the year/stage scalars. It is
        # not a simulated standings result. The separate bootstrap computes
        # its own actual prior-season order through native league processing.
        self.uc.mem_write(0xE41BB8, bytes(range(32)))
        for rng in (0xB12680, 0xE5FCA0):
            self.call(0x48BE0, ecx=rng, edx=seed)
        self.call(0x6E390, ecx=self.manager, edx=0x5015CC)
        self.select(1)
        for address, value in ((0xE576A4, 4), (0xE576B0, 1), (0xE576B4, 0),
                               (0xE576B8, 1), (0xE6011C, 0), (0xE60120, int(preseason)), (mode.EXTRA_VA, 2)):
            self.put(address, value)
        if one_pool:
            # Explicit roster-policy input, matching the existing position-pool
            # owner: the whole current OLB class becomes the combined LB pool.
            for i in range(self.get(self.root)):
                q = self.get(self.root + 4) + 84*i
                if self.uc.mem_read(q+53, 1)[0] == 10:
                    self.uc.mem_write(q+53, b'\x0b')
        self.creation_before = bytes(self.uc.mem_read(self.root, 0x91000))
        self.call('mode_create', ecx=self.manager, budget=10000000)
        p = self.get(0xCB8B14)
        self.uc.mem_write(p + 53, bytes((position,)))
        self.call(0x343460)
        self.cap_record = bytes(self.uc.mem_read(p, 84))
        self.cap_index = (p - self.get(self.root + 4)) // 84
        def placement_input(*_):
            # CAP revisits the template while advancing its native pages.
            # Apply an optional rating experiment only after that final page,
            # immediately before placement; the default keeps every template.
            if ratings is not None:
                from mod_editor.core.nfl2k5_my_career_progression import FIELDS
                for field, _, _ in FIELDS:
                    self.uc.mem_write(p + field, bytes((ratings,)))
            self.placement_before = bytes(self.uc.mem_read(self.root, 0x91000))
            self.cap_record = bytes(self.uc.mem_read(p, 84))
        self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE, placement_input,
            begin=self.labels['m3_place'], end=self.labels['m3_place']))
        if not complete:
            return p
        for _ in range(4):
            self.frame(0x10)
        if self.top() != self.labels['m3_prep_menu'] or self.get(self.state + 24) != 2:
            raise AssertionError(f'native CAP did not enter Senior Bowl preparation: {self.top():#x}')
        p = self.call('primary')
        self.native_signings = []
        def native_signing(*_):
            if self.reg('ECX') == p:
                self.native_signings.append(dict(stage=self.get(0xE576A4),
                    round=self.get(0xE3C0A8), pick=self.get(0xE3C0A4), team=self.reg('EDX')))
        self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE, native_signing,
            begin=0x325B50, end=0x325B50))
        return p

    def draft(self):
        self.select(0, budget=200000000)
        for _ in range(224):
            if self.get(0xE576A4) != 5:
                break
            # Preseason off executes all five native weeks and season cuts in
            # the last transition. The instruction limit remains explicit.
            try:
                self.frame(budget=6000000000)
            except self.u.UcError as exc:
                raise AssertionError(
                    f'native draft transition fault at {self.reg("EIP"):#x}; '
                    f'stage={self.get(0xE576A4)}, week={self.get(0xE576B4)}, '
                    f'round={self.get(0xE3C0A8)}, pick={self.get(0xE3C0A4)}') from exc
        if self.get(0xE576A4) == 5:
            raise AssertionError('native draft did not finish in 224 picks')
        return self.get(self.state + 56)
