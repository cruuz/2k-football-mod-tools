/* EXPERIMENTAL / UNWITNESSED. GNU as --32. No runtime-owned data. CPU decisions "Modern 2" (b77 p9).
 * Same owner and 2048-byte allocation as nfl2k5_cpu_money_downs.S (levels Modern and Aggressive stay on that template);
 * this template replaces the fourth-down policy and adds a sourced two-point chart, an overtime branch and a field goal guard.
 *
 * Fourth:    20B180 entry. policy() returns 0 retail, 1 go (native category 209FE0), 2 kick the field goal (category 0x13).
 *            A go skips the native Hail Mary / kneel / fake-kick steps, so policy() answers retail while the native Hail Mary
 *            test 206DD0 fires (kneel never applies on 4th down).
 * Play:      20980D, ESI candidate, EBP native frame, formation [EBP+8] (x1.5 for a supported primary route, as Modern).
 * Target:    1987B5, EBX projection-score pointer, ST0 native ranking score (+0.15, as Modern).
 * TwoPoint:  206E70 entry (the whole retail chart is replaced; ECX = team); EAX 1 = go for two.
 * FgGuard:   the two calls of the field goal test 20AF80 at 20B1A4 (dispatcher) and 20B6DD (commit: fake check). A kick the
 *            policy forces must also pass the commit-time test, or the CPU lines up a fake. On overtime first-possession
 *            downs 1 to 3 the guard answers "no field goal".
 * All hooks preserve GPRs/flags except their displaced native outputs. Temporary x87 operations balance the stack; XMM untouched.
 * Tables (limit_x, shift, thr) come from docs/mod_editor/nfl2k5_cpu_decisions_modern2_sources.json through the .inc.
 */
.intel_syntax noprefix
.code32
.text
.global fourth, play, target, two_point, fg_guard, code_end, policy, primary_depth, limit_x, shift, thr
.extern fourth_tail, play_tail, target_tail, native_category, half_time, native_fg, kicker_range, margin_fn, hail_mary

fourth:
    pushfd
    pushad
    call policy
    cmp eax, 1
    je fourth_go
    cmp eax, 2
    je fourth_kick
    popad
    popfd
    mov eax, [0xe60280]
    jmp fourth_tail
fourth_go:
    popad
    popfd
    jmp native_category
fourth_kick:
    popad
    popfd
    mov eax, 0x13
    ret

/* EAX = 0 retail, 1 go, 2 kick. No random draws, no special-team choice, no mutable global scratch (native stack only).
 * Locals: [esp] yards to goal, +4 yards to go, +8 seconds (then game seconds), +12 yard index, +16 period,
 * +20 limit, +24 region (0 own side of the 40, 1 middle, 2 opponent 40 and in). */
policy:
    call eligible
    test eax, eax
    jz no
    cmp dword ptr [eax+4], 4
    jne no
    push ebx
    push esi
    push edi
    sub esp, 28
    mov esi, eax
    mov edi, ecx
    mov edx, [edi+8]
    test edx, edx
    jz p_exit_no
    mov ebx, [edi]
    test ebx, ebx
    jz p_exit_no
    mov ebx, [ebx+8]
    test ebx, ebx
    jz p_exit_no
    mov ebx, [ebx]
    neg ebx
    add ebx, [edx]                  /* offense score minus opponent score */
    mov edx, [edx+12]
    test edx, edx
    jz p_exit_no
    mov eax, [edx+4]
    and eax, 0x7fffffff
    cmp eax, 0x3f800000
    jne p_exit_no                   /* native direction must be +/-1 */
    fld dword ptr [esi+0x18]
    fdiv dword ptr yard
    test dword ptr [edx+4], 0x80000000
    jnz p_dir_negative
    fchs
p_dir_negative:
    fadd dword ptr fifty            /* yards to the opponent goal line */
    fstp dword ptr [esp]
    mov eax, [esp]
    cmp eax, 0x42c80000
    ja p_exit_no                    /* negative, nonfinite, >100 */
    fld dword ptr [esi+0x28]
    fsub dword ptr [esi+0x18]
    fabs
    fdiv dword ptr yard
    fstp dword ptr [esp+4]
    mov eax, [esp+4]
    test eax, eax
    jz p_exit_no
    cmp eax, 0x41c80000
    ja p_exit_no                    /* no more than 25 yards */
    call half_time
    fstp dword ptr [esp+8]
    cmp dword ptr [esp+8], 0x461c4000
    ja p_exit_no                    /* invalid clock or >10,000 sec */
    mov ecx, [0xe602c4]
    mov [esp+16], ecx
    fld dword ptr [esp]
    fadd dword ptr eps
    fstp dword ptr [esp+12]
    mov eax, [esp+12]
    call floor_pos
    mov [esp+12], eax               /* whole yards to goal */
    xor edx, edx
    cmp eax, 60
    ja p_region
    inc edx
    cmp eax, 40
    ja p_region
    inc edx
p_region:
    mov [esp+24], edx
    xor ecx, ecx
    cmp eax, 80
    ja p_base
    movzx ecx, byte ptr [eax+limit_x]
p_base:
    mov [esp+20], ecx               /* typical limit; zero inside the own 20 */
    mov ecx, [esp+16]
    cmp ecx, 5
    jae p_overtime
    dec ecx
    cmp ecx, 3
    ja p_exit_no                    /* period outside 1..4 */
    cmp dword ptr [esp+16], 2
    jne p_regulation
    cmp dword ptr [esp+8], 0x42f00000
    jbe p_exit_no                   /* last two minutes of the first half: retail clock logic */
p_regulation:
    cmp dword ptr [esp+16], 2
    ja p_clock_ready
    fld dword ptr [esp+8]
    fadd dword ptr [0xe602b0]
    fadd dword ptr [0xe602b0]
    fstp dword ptr [esp+8]          /* first half: add the two second-half quarters */
p_clock_ready:
    mov eax, [esp+8]
    xor ecx, ecx
    cmp eax, 0x44e10000
    ja p_clock_class
    inc ecx
    cmp eax, 0x44610000
    ja p_clock_class
    inc ecx
    cmp eax, 0x44160000
    ja p_clock_class
    inc ecx
    cmp eax, 0x43960000
    ja p_clock_class
    inc ecx
    cmp eax, 0x42f00000
    ja p_clock_class
    inc ecx
p_clock_class:
    xor edx, edx
    cmp ebx, -9
    jle p_margin_class
    inc edx
    cmp ebx, -4
    jle p_margin_class
    inc edx
    cmp ebx, -1
    jle p_margin_class
    inc edx
    test ebx, ebx
    jz p_margin_class
    inc edx
    cmp ebx, 3
    jle p_margin_class
    inc edx
    cmp ebx, 8
    jle p_margin_class
    inc edx
p_margin_class:
    imul ecx, ecx, 7
    add ecx, edx
    lea ecx, [ecx+ecx*2]
    add ecx, [esp+24]
    movsx eax, byte ptr [ecx+shift]
    add eax, [esp+20]
p_compare:
    mov [esp+20], eax
    fild dword ptr [esp+20]
    fadd dword ptr eps
    fcomp dword ptr [esp+4]
    fnstsw ax
    test ah, 5
    jnz p_not_go                    /* limit below the distance (or nonfinite) */
p_go:
    call hail_mary                  /* native 206DD0: the end-of-half Hail Mary call stays in charge */
    test eax, eax
    jnz p_exit_no
    mov eax, 1
    jmp p_exit
p_not_go:
    cmp dword ptr [esp+16], 4
    jne p_exit_no
    cmp dword ptr [esp+8], 0x42f00000
    ja p_exit_no                    /* only the last two minutes */
    lea eax, [ebx-1]
    cmp eax, 2
    ja p_exit_no                    /* only when leading by 1 to 3 */
    cmp dword ptr [esp+4], 0x40dfff2e
    jb p_exit_no                    /* 7 or more yards to go */
    mov ecx, edi
    call kicker_range
    fdiv dword ptr yard
    fsub dword ptr five
    fadd dword ptr eps              /* inclusive, with the 0.0001 yard tolerance every other threshold has (no dependence on FPU rounding at the edge) */
    fcomp dword ptr [esp]
    fnstsw ax
    test ah, 5
    jnz p_exit_no                   /* outside the kicker's range minus 5 yards */
    mov eax, 2
    jmp p_exit
p_overtime:
    movzx ecx, byte ptr [0xe602a8]
    and ecx, 3
    jz p_exit_no                    /* no possession tracking: retail */
    mov edx, 1
    cmp edi, 0xe5fc20
    je p_ot_own
    mov edx, 2
p_ot_own:
    test ecx, edx
    jz p_exit_no                    /* own possession not recorded: retail */
    cmp ecx, 3
    jne p_ot_first
    test ebx, ebx
    jns p_exit_no                   /* sudden death or leading: retail */
    cmp ebx, -4
    jle p_go                        /* last possession, behind by a touchdown or more: always go */
    call native_fg
    test eax, eax
    jnz p_exit_no                   /* a tying field goal stays native */
    jmp p_go                        /* never punt on the last possession */
p_ot_first:
    mov eax, [esp+20]               /* typical table, no clock or score terms */
    jmp p_compare
p_exit_no:
    xor eax, eax
p_exit:
    add esp, 28
    pop edi
    pop esi
    pop ebx
    ret

/* EAX = float bits of a value in [0,128); returns floor in EAX, clobbers ECX. Rounding-mode independent. */
floor_pos:
    cmp eax, 0x3f800000
    jb floor_zero
    mov ecx, eax
    shr ecx, 23
    sub ecx, 127
    and eax, 0x7fffff
    or eax, 0x800000
    neg ecx
    add ecx, 23
    shr eax, cl
    ret
floor_zero:
    xor eax, eax
    ret

/* Replaces the whole retail chart 206E70 (ECX = team). EAX = 1 go for two. Preserves every register but EAX/EDX. */
two_point:
    push ebx
    push esi
    sub esp, 8
    mov esi, ecx
    call margin_fn                  /* native 205F40: offense score minus opponent score */
    mov ebx, eax
    mov eax, [0xe602c4]
    cmp eax, 5
    jae tp_overtime
    test eax, eax
    jz tp_no
    call half_time
    cmp dword ptr [0xe602c4], 2
    ja tp_clock
    fadd dword ptr [0xe602b0]
    fadd dword ptr [0xe602b0]
tp_clock:
    fstp dword ptr [esp]            /* game seconds left */
    lea eax, [ebx+16]
    cmp eax, 32
    ja tp_no
    movzx eax, byte ptr [eax+thr]
    test eax, eax
    jz tp_no
    cmp eax, 255
    je tp_yes
    imul eax, eax, 10
    mov [esp+4], eax
    fild dword ptr [esp+4]
    fcomp dword ptr [esp]
    fnstsw ax
    test ah, 5
    jnz tp_no
    jmp tp_yes
tp_overtime:
    cmp ebx, -2
    je tp_yes
    cmp ebx, -1
    jne tp_no
    movzx eax, byte ptr [0xe602a8]
    and eax, 3
    cmp eax, 3
    jne tp_no
tp_yes:
    mov eax, 1
    jmp tp_exit
tp_no:
    xor eax, eax
tp_exit:
    add esp, 8
    pop esi
    pop ebx
    ret

/* Both call sites of the field goal test 20AF80 jump through here; the displaced call's return address is kept. */
fg_guard:
    pushfd
    pushad
    call eligible_any
    test eax, eax
    jz fg_native
    cmp dword ptr [eax+4], 4
    jne fg_early
    call policy
    cmp eax, 2
    jne fg_native
    popad
    popfd
    mov eax, 1
    ret                             /* the policy forced this kick: the commit-time test agrees, so no fake */
fg_early:
    cmp dword ptr [0xe602c4], 5
    jb fg_native
    movzx eax, byte ptr [0xe602a8]
    and eax, 3
    mov edx, 1
    cmp ecx, 0xe5fc20
    je fg_own
    mov edx, 2
fg_own:
    cmp eax, edx
    jne fg_native                   /* only the first possession of overtime */
    popad
    popfd
    xor eax, eax
    ret                             /* no field goal on downs 1 to 3 of the first possession */
fg_native:
    popad
    popfd
    jmp native_fg

play:
    pushfd
    pushad
    call eligible
    test eax, eax
    jz play_original
    mov ecx, [ebp-0x20]
    cmp ecx, [0xe60280]
    jne play_original
    call primary_depth              /* EAX integer cm, -32768 if unsupported */
    cmp eax, -32768
    je play_original
    push eax
    fild dword ptr [esp]
    mov ecx, [0xe602ec]
    fld dword ptr [ecx+0x28]
    fsub dword ptr [ecx+0x18]
    fabs
    fxch st(1)
    fcompp
    fnstsw ax
    add esp, 4
    test ah, 5
    jnz play_original               /* marker > endpoint or nonfinite */
    fmul dword ptr play_modern
play_original:
    popad
    popfd
    fstp dword ptr [ebp-0x18]
    mov eax, [ebp-0x18]
    jmp play_tail

/* Strict grammar: explicit QB primary, Start(mode1,role3,zero offset),
 * straight leg, optionally one terminal lateral break. Full loaded spans
 * bounded to their own native book. Integer cm depth rounds DOWN, so it
 * never awards a bonus because of fractional-centimetre rounding up.
 * ESI play, [EBP+8] formation, [EBP-0x28] native mirror choice. */
primary_depth:
    mov ebx, 0xb75a40
    mov eax, esi
    sub eax, ebx
    cmp eax, 0x13390
    jb primary_book
    add ebx, 0x13390
    sub eax, 0x13390
primary_book:
    sub eax, 0x33fc
    cmp eax, 270*96
    jae primary_no
    xor edx, edx
    mov ecx, 96
    div ecx
    test edx, edx
    jnz primary_no
    mov edi, [ebp+8]
    mov eax, edi
    sub eax, ebx
    sub eax, 0x134
    cmp eax, 50*180
    jae primary_no
    xor edx, edx
    mov ecx, 180
    div ecx
    test edx, edx
    jnz primary_no
    test dword ptr [esi+4], 0x1c0
    jnz primary_no                 /* offense family only */
    lea edx, [esi+8]
    call chain
    test eax, eax
    jz primary_no
    lea eax, [eax+ecx*8-8]
    movzx edx, word ptr [eax]
    and edx, 0xfbff
    cmp edx, 0x0206
    jne primary_no
    movzx edx, byte ptr [eax+4]
    shr edx, 4
    dec edx
    cmp edx, 4
    ja primary_no
    add edx, 6
    push edx
    lea edx, [esi+edx*8+8]
    call chain
    pop edx
    test eax, eax
    jz primary_no
    cmp ecx, 2
    jb primary_no
    cmp ecx, 3
    ja primary_no
    cmp dword ptr [eax+4], 0x80400301
    jne primary_no                 /* mode1 receiver, no offset or timer */
    mov esi, [eax+8]
    and esi, 0xfbff
    cmp ecx, 2
    jne primary_lateral
    cmp esi, 0x0212
    jne primary_no
    jmp primary_straight
primary_lateral:
    cmp esi, 0x0012
    jne primary_no
    movzx esi, word ptr [eax+16]
    and esi, 0xfbff
    cmp esi, 0x0212
    jne primary_no
    movzx esi, byte ptr [eax+20]
    and esi, 31
    sub esi, 4
    cmp esi, 1
    ja primary_no
primary_straight:
    test byte ptr [eax+12], 31      /* type0, no alternate flag */
    jnz primary_no
    movzx esi, byte ptr [eax+15]
    sub esi, 64                    /* native route distance in feet */
    js primary_no
    cmp dword ptr [ebp-0x28], 0
    je primary_slot
    test dword ptr [edi+4], 0x100000
    jz primary_slot
    imul eax, edx, 14
    movzx eax, byte ptr [edi+eax+0x1b]
    shr eax, 4
    cmp eax, 11
    je primary_slot
    cmp eax, 10
    ja primary_no
    mov edx, eax
primary_slot:
    imul edx, edx, 14
    movsx ecx, word ptr [edi+edx+0x22]
    imul eax, esi, 3048
    xor edx, edx
    mov esi, 100
    div esi
    add eax, ecx
    ret
primary_no:
    mov eax, -32768
    ret

/* EDX descriptor, EBX buffer. EAX chain, ECX declared count, or zero. */
chain:
    mov ecx, [edx]
    and ecx, 15
    cmp ecx, 2
    jb no
    mov eax, [edx+4]
    sub eax, ebx
    sub eax, 0x9adc
    cmp eax, 3500*8
    jae no
    test al, 7
    jnz no
    lea edx, [eax+ecx*8]
    cmp edx, 3500*8
    ja no
    lea eax, [ebx+eax+0x9adc]
    cmp word ptr [eax], 1
    jne no
    ret

target:
    pushfd
    pushad
    call eligible
    test eax, eax
    jz target_original
    mov ecx, [0xbe4f8c]             /* live passer */
    test ecx, ecx
    jz target_original
    mov ecx, [ecx+0xc]
    test ecx, ecx
    jz target_original
    cmp dword ptr [ecx], -1
    jne target_original            /* human passer retains retail ranking */
    mov ecx, [0xe60280]
    mov ecx, [ecx+8]
    mov ecx, [ecx+12]
    fld dword ptr [ebx-12]
    fsub dword ptr [eax+0x28]       /* projection relative to marker */
    fmul dword ptr [ecx+4]          /* native direction is +/-1 */
    ftst
    fnstsw ax
    fstp st(0)
    test ah, 5
    jnz target_original
    fadd dword ptr target_modern
target_original:
    popad
    popfd
    fstp dword ptr [ebp-4]
    fld dword ptr [ebp-4]
    jmp target_tail

/* ECX team, EAX game state (CPU offense, scrimmage phase, down 3 or 4) or zero. */
eligible:
    call eligible_any
    test eax, eax
    jz no
    cmp dword ptr [eax+4], 3
    jb no
    ret
eligible_any:
    cmp dword ptr [0xe602b4], 4
    jne no
    mov ecx, [0xe60280]
    test ecx, ecx
    jz no
    cmp dword ptr [ecx+0x30], 0
    jne no
    mov eax, [0xe602ec]
    test eax, eax
    jz no
    mov edx, [eax+4]
    dec edx
    cmp edx, 3
    ja no                           /* down 1 to 4 */
    ret
no:
    xor eax, eax
    ret
.balign 4, 0xcc
yard: .float 91.44
eps: .float 0.0001
fifty: .float 50
five: .float 5
play_modern: .float 1.5
target_modern: .float 0.15
.include "nfl2k5_cpu_money_downs_m2_tables.inc"
code_end:
