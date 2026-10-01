/* EXPERIMENTAL / UNWITNESSED. Historic teams in Quick Game Team Select.
 *
 * Quick Game, Practice and FPF (Team Select flows 1, 3, 7 at [0xACF614]) step past the last resident team into the
 * roster's historic list (count at root+0x58, 16-byte entries at root+0x5C) and wraps back to the first
 * NFL team after the last entry, in both directions. Stepping onto entry k imports it into the side's
 * spare slot (home: the first created/historic slot in table order, USER1; away: the second, USER2)
 * with the game's own loader core, the same calls 2D17B0 makes ("Load Historic Team"), without its
 * slot choice and without 2D13B0 (the Create a Team refresh):
 *   name "h-%s-%d-%s-%d.iff", queue 43F50 in context "historic", wait 432D0, lookup 449E0 (ROST),
 *   clear C2300 (the slot's players go back to the spare pool first), import C1030, category 4,
 *   label copied from the team with the same asset code, pop 432F0.
 * The slot is loaded only when it is empty (category 2, no players) or holds a historic team
 * (category 4), and never while the other side is showing it. A user-created team is never touched:
 * that side just skips the historic list. The resident list skips both spare slots while they hold
 * historic teams, so neither side can pick the team in the other side's slot. The Random Team spin
 * stays on the resident list. Every other Team Select flow calls the retail step functions.
 * Loading waits in the menu; nothing stays queued, and no memory is added: the two slots and the
 * 155-record spare pool exist in retail. A network session (128C70 nonzero: Xbox Live or system link) keeps
 * the retail steps, so both consoles always name the same resident team. State: 16 zero-initialised RW bytes, per side
 * {u32 slot, u16 entry+1, u16 identity number}.
 */
.intel_syntax noprefix
.code32
.text
.global home_next, away_next, home_prev, away_prev, home_random, away_random
.extern retail_home_next, retail_home_prev, retail_away_next, retail_away_prev
.extern team_mask, iter_next, iter_prev, set_home, set_away, network_session
.extern text_format, loader_heap, loader_queue, loader_wait, loader_lookup, loader_pop
.extern team_release, team_import, text_equal
.extern state

.set ROOT, 0xb72918              /* roster root pointer */
.set TS_MODE, 0xacf614           /* Team Select flow; 1 Quick Game, 3 Practice, 7 FPF */
.set TS_HOME, 0xacf63c           /* the home side's team; the away side's is at +4 */
.set TS_AWAY, 0xacf640
.set QUICK_GAME, 1
.set TEAMS, 0x18                 /* root: team count */
.set TABLE, 0x1c                 /* root: team table, 500-byte records */
.set HCOUNT, 0x58                /* root: historic entry count */
.set HTABLE, 0x5c                /* root: historic entries, 16 bytes each */
.set CODE, 0x10c                 /* team: asset code text */
.set LABEL, 0x110                /* team: label (names the playbook) */
.set IDENT, 0x118                /* team: identity number */
.set ACTIVE, 0x11c               /* team: player count */
.set CAT, 0x128                  /* team: category (2 created, 4 historic) */
.set FMT_FILE, 0xe9f984          /* "h-%s-%d-%s-%d.iff" */
.set FMT_CODE, 0xe9f9bc          /* "%s" */
.set CTX, 0xe9f9a8               /* "historic" */
.set ROST, 0x54534f52

/* ---- the six replaced calls ------------------------------------------------------------------ */
home_next:                       /* 2C22D0 in the next handler 2C2240; EDX = the flow's team mask */
    push edx
    push 1
    push 0
    call step
    add esp, 12
    ret
away_next:                       /* 2C2280 */
    push edx
    push 1
    push 1
    call step
    add esp, 12
    ret
home_prev:                       /* 2C2392 in the previous handler 2C2310; retail computes its mask */
    call team_mask
    push eax
    push -1
    push 0
    call step
    add esp, 12
    ret
away_prev:                       /* 2C2349 */
    call team_mask
    push eax
    push -1
    push 1
    call step
    add esp, 12
    ret
home_random:                     /* 2C1B02 in the Random Team spin 2C1AC0; EDX = mask */
    push edx
    push 0
    call random_step
    add esp, 8
    ret
away_random:                     /* 2C1B52 in 2C1B10 */
    push edx
    push 1
    call random_step
    add esp, 8
    ret

/* step(side, dir, mask): one Team Select step. Preserves EBX, ESI, EDI, EBP like the retail steps. */
step:
    push ebp
    push ebx
    push esi
    push edi
    mov esi, dword ptr [esp+20]          /* side: 0 home, 1 away */
    mov eax, dword ptr [TS_MODE]
    cmp eax, 3                         /* Practice: the same two spare-team loaders */
    je step_local
    cmp eax, 7                         /* First Person Football uses game mode 4 */
    je step_local
    cmp eax, QUICK_GAME
    jne step_retail
step_local:
    call network_session                 /* 128C70: a Live or system-link session keeps the retail list */
    test eax, eax
    jnz step_retail
    mov ebx, dword ptr [TS_HOME+esi*4]   /* this side's team */
    test ebx, ebx
    jz step_retail
    mov ecx, esi
    call spare_slot
    mov edi, eax                         /* this side's spare slot, or 0 */
    mov ecx, esi
    mov edx, edi
    call slot_usable
    mov ebp, eax                         /* 1: the historic list is open to this side */
    test ebp, ebp
    jz step_resident
    cmp ebx, edi
    jne step_resident
    cmp dword ptr [edi+CAT], 4
    jne step_resident
    /* In the historic list: the next or previous entry, or back out to the resident list. */
    mov ecx, esi
    mov edx, edi
    call current_entry                   /* EAX = entry, or -1 when unknown */
    cmp eax, -1
    jne step_have_entry
    cmp dword ptr [esp+24], 0
    jg step_have_entry                   /* unknown, forward: -1 + 1 = entry 0 */
    mov eax, dword ptr [ROOT]
    mov eax, dword ptr [eax+HCOUNT]      /* unknown, back: N - 1 */
step_have_entry:
    add eax, dword ptr [esp+24]
    js step_leave
    mov ecx, dword ptr [ROOT]
    cmp eax, dword ptr [ecx+HCOUNT]
    jge step_leave
    mov ebp, eax                         /* the entry to show */
    push esi
    push ebp
    push edi
    call load_entry
    add esp, 12
    test eax, eax
    jz step_leave
    mov ecx, esi
    mov edx, edi
    mov eax, ebp
    call remember
    mov edx, edi
    jmp step_publish
step_leave:
    /* Past either end of the historic list (or a failed load): the slot goes back to an empty
     * created-team slot, and the side moves to the first (forward) or last (back) resident team. */
    mov ecx, esi
    mov edx, edi
    call release_slot
    mov word ptr [state+esi*8+4], 0
    xor ecx, ecx                         /* forward: the first resident team after "none" */
    cmp dword ptr [esp+24], 0
    jg step_leave_target
    mov ecx, dword ptr [ROOT]
    mov ecx, dword ptr [ecx+TABLE]       /* back: the resident team before the first team */
step_leave_target:
    mov edx, dword ptr [esp+28]
    push edx
    mov edx, dword ptr [esp+28]          /* dir (the push moved it by 4) */
    push edx
    push ecx
    call resident_step
    add esp, 12
    mov edx, eax
    jmp step_publish
step_resident:
    mov edx, dword ptr [esp+28]          /* mask */
    push edx
    mov edx, dword ptr [esp+28]          /* dir */
    push edx
    push ebx
    call resident_step
    add esp, 12
    mov edx, eax                         /* the next resident team */
    test ebp, ebp
    jz step_publish
    cmp dword ptr [esp+24], 0
    jl step_resident_back
    cmp edx, ebx
    ja step_publish                      /* forward without passing the end of the table */
    xor eax, eax                         /* wrapped forward: historic entry 0 */
    jmp step_enter
step_resident_back:
    cmp edx, ebx
    jb step_publish                      /* back without passing the start of the table */
    mov eax, dword ptr [ROOT]
    mov eax, dword ptr [eax+HCOUNT]
    dec eax                              /* wrapped back: the last historic entry */
step_enter:
    mov ebp, eax
    push edx                             /* keep the resident fallback */
    push esi
    push ebp
    push edi
    call load_entry
    add esp, 12
    pop edx
    test eax, eax
    jz step_publish                      /* not loaded: take the resident team as retail would */
    mov ecx, esi
    mov edx, edi
    mov eax, ebp
    call remember
    mov edx, edi
step_publish:
    mov ecx, esi
    call publish
    jmp step_out
step_retail:
    mov edx, dword ptr [esp+28]
    mov eax, dword ptr [esp+24]
    test esi, esi
    jnz step_retail_away
    test eax, eax
    jl step_retail_home_prev
    call retail_home_next
    jmp step_out
step_retail_home_prev:
    call retail_home_prev
    jmp step_out
step_retail_away:
    test eax, eax
    jl step_retail_away_prev
    call retail_away_next
    jmp step_out
step_retail_away_prev:
    call retail_away_prev
step_out:
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret

/* random_step(side, mask): one Random Team spin step on the resident list (Quick Game) or retail. */
random_step:
    push ebp
    push ebx
    push esi
    push edi
    mov esi, dword ptr [esp+20]
    mov eax, dword ptr [TS_MODE]
    cmp eax, 3
    je random_local
    cmp eax, 7
    je random_local
    cmp eax, QUICK_GAME
    jne random_retail
random_local:
    call network_session
    test eax, eax
    jnz random_retail
    mov ebx, dword ptr [TS_HOME+esi*4]
    test ebx, ebx
    jz random_retail
    mov edx, dword ptr [esp+24]          /* mask */
    push edx
    push 1
    push ebx
    call resident_step
    add esp, 12
    mov edx, eax
    mov ecx, esi
    call publish
    jmp random_out
random_retail:
    mov edx, dword ptr [esp+24]          /* the mask for the retail step */
    test esi, esi
    jnz random_retail_away
    call retail_home_next
    jmp random_out
random_retail_away:
    call retail_away_next
random_out:
    pop edi
    pop esi
    pop ebx
    pop ebp
    ret

/* resident_step(team, dir, mask): the retail iterator, skipping any team in the historic category. */
resident_step:
    push ebx
    push esi
    push edi
    mov esi, dword ptr [esp+16]
    mov ebx, dword ptr [ROOT]
    mov ebx, dword ptr [ebx+TEAMS]
    inc ebx                              /* at most one lap */
resident_loop:
    mov ecx, esi
    mov edx, dword ptr [esp+24]
    cmp dword ptr [esp+20], 0
    jl resident_prev
    call iter_next
    jmp resident_got
resident_prev:
    call iter_prev
resident_got:
    mov esi, eax
    test eax, eax
    jz resident_done
    cmp dword ptr [eax+CAT], 4
    jne resident_done
    dec ebx
    jnz resident_loop
resident_done:
    mov eax, esi
    pop edi
    pop esi
    pop ebx
    ret

/* spare_slot: ECX = n -> EAX = the n-th team (table order) in category 2 or 4, or 0. */
spare_slot:
    push ebx
    mov eax, dword ptr [ROOT]
    mov edx, dword ptr [eax+TEAMS]
    mov eax, dword ptr [eax+TABLE]
spare_loop:
    test edx, edx
    jle spare_none
    mov ebx, dword ptr [eax+CAT]
    cmp ebx, 2
    je spare_match
    cmp ebx, 4
    jne spare_next
spare_match:
    test ecx, ecx
    jz spare_done
    dec ecx
spare_next:
    add eax, 500
    dec edx
    jmp spare_loop
spare_none:
    xor eax, eax
spare_done:
    pop ebx
    ret

/* slot_usable: ECX = side, EDX = slot -> EAX = 1 when the slot may be cleared and loaded. */
slot_usable:
    xor eax, eax
    test edx, edx
    jz usable_done
    neg ecx
    cmp edx, dword ptr [TS_AWAY+ecx*4]   /* the other side's team: never taken from under it */
    je usable_done
    mov ecx, dword ptr [edx+CAT]
    cmp ecx, 4
    je usable_list
    cmp ecx, 2
    jne usable_done
    cmp byte ptr [edx+ACTIVE], 0
    jne usable_done                      /* a user-created team: never overwritten */
usable_list:
    mov ecx, dword ptr [ROOT]
    cmp dword ptr [ecx+HCOUNT], 0
    jle usable_done
    inc eax
usable_done:
    ret

/* current_entry: ECX = side, EDX = slot -> EAX = the entry this side loaded there, or -1. */
current_entry:
    push ebx
    lea ecx, [state+ecx*8]
    cmp dword ptr [ecx], edx
    jne entry_unknown
    movzx eax, word ptr [ecx+4]
    test eax, eax
    jz entry_unknown
    mov bx, word ptr [ecx+6]
    cmp bx, word ptr [edx+IDENT]
    jne entry_unknown
    dec eax
    mov ecx, dword ptr [ROOT]
    cmp eax, dword ptr [ecx+HCOUNT]
    jb entry_out
entry_unknown:
    or eax, -1
entry_out:
    pop ebx
    ret

/* remember: ECX = side, EDX = slot, EAX = entry. */
remember:
    lea ecx, [state+ecx*8]
    mov dword ptr [ecx], edx
    inc eax
    mov word ptr [ecx+4], ax
    mov ax, word ptr [edx+IDENT]
    mov word ptr [ecx+6], ax
    ret

/* publish: ECX = side, EDX = team, through the retail setters 2C1780 / 2C17C0. */
publish:
    test ecx, ecx
    mov ecx, edx
    jnz publish_away
    jmp set_home
publish_away:
    jmp set_away

/* release_slot: ECX = side, EDX = slot. C2300 returns its players to the pool; then an empty
 * created-team slot (category 2, identity 90 or 91), as the moment exit event 20C3C0 leaves it. */
release_slot:
    test edx, edx
    jz release_done
    push ebx
    push esi
    mov ebx, edx
    mov esi, ecx
    mov ecx, ebx
    call team_release
    mov byte ptr [ebx+ACTIVE], 0
    mov dword ptr [ebx+CAT], 2
    lea eax, [esi+0x5a]
    mov word ptr [ebx+IDENT], ax
    pop esi
    pop ebx
release_done:
    ret

/* load_entry(slot, entry, side) -> EAX = 1 loaded, 0 not. The frame and calls follow 2D17B0. */
load_entry:
    sub esp, 0xb4
    push ebx
    push ebp
    push esi
    push edi
    mov ebx, dword ptr [esp+0xc8]        /* slot */
    mov eax, dword ptr [esp+0xcc]        /* entry */
    mov ecx, dword ptr [ROOT]
    shl eax, 4
    add eax, dword ptr [ecx+HTABLE]
    movzx ecx, byte ptr [eax+2]
    mov dword ptr [esp+0x1c], ecx        /* throwback */
    mov edx, dword ptr [eax+12]
    mov dword ptr [esp+0x18], edx        /* franchise name */
    movzx ecx, word ptr [eax]
    mov dword ptr [esp+0x14], ecx        /* year */
    lea esi, [eax+4]                     /* asset code */
    lea edx, [esp+0x10]
    push edx
    mov edx, FMT_FILE
    lea ecx, [esp+0x24]                  /* file name buffer, frame +0x20 */
    mov dword ptr [esp+0x14], esi
    call text_format
    push 0
    push 0
    call loader_heap
    push eax
    lea eax, [esp+0xac]
    push eax
    lea edx, [esp+0x30]
    mov ecx, CTX
    call loader_queue
    call loader_wait
    push CTX
    mov edx, ROST
    mov ecx, CTX
    call loader_lookup
    test eax, eax
    jz load_failed                       /* the file never arrived: the slot is untouched */
    mov ebp, eax
    mov ecx, ebx
    call team_release                    /* clear first: its players go back to the spare pool */
    mov edx, ebx
    mov ecx, ebp
    call team_import
    test eax, eax
    jz import_failed
    mov dword ptr [ebx+CAT], 4
    lea ecx, [esp+0x10]                  /* the label of the team with the same asset code */
    push ecx
    mov edx, FMT_CODE
    lea ecx, [esp+0x24]
    mov dword ptr [esp+0x14], esi
    call text_format
    xor edi, edi
label_loop:
    mov ecx, dword ptr [ROOT]
    cmp edi, dword ptr [ecx+TEAMS]
    jge label_done
    mov esi, dword ptr [ecx+TABLE]
    imul eax, edi, 500
    add esi, eax
    mov ecx, dword ptr [esi+CODE]
    lea edx, [esp+0x20]
    call text_equal
    test eax, eax
    jz label_next
    mov eax, dword ptr [esi+LABEL]
    mov dword ptr [ebx+LABEL], eax
label_next:
    inc edi
    jmp label_loop
label_done:
    mov ecx, CTX
    call loader_pop
    mov eax, 1
    jmp load_out
import_failed:
    mov byte ptr [ebx+ACTIVE], 0         /* an empty created-team slot, hidden from every list */
    mov dword ptr [ebx+CAT], 2
    mov eax, dword ptr [esp+0xd0]
    add eax, 0x5a
    mov word ptr [ebx+IDENT], ax
load_failed:
    mov ecx, CTX
    call loader_pop
    xor eax, eax
load_out:
    pop edi
    pop esi
    pop ebp
    pop ebx
    add esp, 0xb4
    ret
