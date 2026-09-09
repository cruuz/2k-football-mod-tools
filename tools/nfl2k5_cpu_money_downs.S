/* EXPERIMENTAL / UNWITNESSED. GNU as --32. No runtime-owned data.
 * Fourth: 20B180 entry, ordinary CPU scrimmage only; native fallback.
 * Play: 20980D, ESI candidate, EBP native frame, formation [EBP+8].
 * Target: 1987B5, EBX projection-score pointer, ST0 native ranking score.
 * All hooks preserve GPRs/flags except their displaced native outputs.
 * Temporary floating-point operations balance the x87 stack; XMM untouched.
 */
.intel_syntax noprefix
.code32
.text
.global fourth, play, target, level, code_end, policy, primary_depth
.extern fourth_tail, play_tail, target_tail, native_category, half_time

fourth:
    pushfd
    pushad
    call policy
    test eax, eax
    jz fourth_original
    popad
    popfd
    jmp native_category
fourth_original:
    popad
    popfd
    mov eax, [0xe60280]
    jmp fourth_tail

/* EAX=1 means use native offensive category 0..10; 0 retains retail.
 * No random draws, no special-team choice, no mutable global scratch. */
policy:
    call eligible
    test eax, eax
    jz no
    cmp dword ptr [eax+4], 4
    jne no
    cmp dword ptr [0xe602c4], 4
    ja no                            /* overtime keeps its native policy */
    cmp dword ptr [0xe602c4], 1
    jb no
    push ebx
    push esi
    push edi
    sub esp, 20
    mov esi, eax
    mov edi, ecx
    mov edx, [edi+8]
    test edx, edx
    jz policy_no
    mov ebx, [edi]
    test ebx, ebx
    jz policy_no
    mov ebx, [ebx+8]
    test ebx, ebx
    jz policy_no
    mov ebx, [ebx]
    neg ebx
    add ebx, [edx]                  /* offense score minus opponent score */
    mov edx, [edx+12]
    test edx, edx
    jz policy_no
    mov eax, [edx+4]
    and eax, 0x7fffffff
    cmp eax, 0x3f800000
    jne policy_no                  /* native direction must be +/-1 */
    test dword ptr [edx+4], 0x80000000
    jnz policy_negative
    fld dword ptr [esi+0x18]
    jmp policy_position
policy_negative:
    fld dword ptr [esi+0x18]
    fchs
policy_position:
    fdiv dword ptr yard
    fadd dword ptr fifty
    fstp dword ptr [esp]            /* own-goal yard line, 0..100 */
    mov eax, [esp]
    cmp eax, 0x42c80000
    ja policy_no                   /* negative, nonfinite, >100 */
    fld dword ptr [esi+0x28]
    fsub dword ptr [esi+0x18]
    fabs
    fdiv dword ptr yard
    fstp dword ptr [esp+4]
    mov eax, [esp+4]
    test eax, eax
    jz policy_no
    cmp eax, 0x41a00000
    ja policy_no                   /* no more than twenty yards */
    call half_time
    fstp dword ptr [esp+8]
    cmp dword ptr [esp+8], 0x461c4000
    ja policy_no                   /* invalid clock or >10,000 sec */
    cmp dword ptr [0xe602c4], 2
    jne policy_fourth_quarter
    cmp dword ptr [esp+8], 0x41f00000
    jbe policy_no                  /* final thirty seconds of first half */
policy_fourth_quarter:
    cmp dword ptr [0xe602c4], 4
    jne policy_table
    cmp dword ptr [esp+8], 0x42f00000
    ja policy_table
    cmp ebx, -3
    jge policy_no                  /* late tying/winning FG or protecting lead */
policy_table:
    fld dword ptr [esp]
    fadd dword ptr yard_epsilon
    fstp dword ptr [esp]
    xor ecx, ecx
    mov eax, [esp]
    cmp eax, 0x419fffff             /* float just below own20 */
    jbe policy_no
    inc ecx
    cmp eax, 0x42200000
    jb policy_band
    inc ecx
    cmp eax, 0x42700000
    jb policy_band
    inc ecx
    cmp eax, 0x42a00000
    jb policy_band
    inc ecx
    cmp eax, 0x42be0000
    jb policy_band
    inc ecx
policy_band:
    cmp dword ptr level, 2
    je policy_aggressive
    movzx eax, byte ptr modern_table[ecx]
    jmp policy_late
policy_aggressive:
    movzx eax, byte ptr aggressive_table[ecx]
policy_late:
    cmp dword ptr [0xe602c4], 4
    jne policy_compare
    cmp dword ptr [esp+8], 0x43960000
    ja policy_compare              /* >300 seconds */
    cmp ebx, 9
    jl policy_trailing
    dec eax
    jmp policy_compare
policy_trailing:
    cmp ebx, -4
    jg policy_compare
    cmp dword ptr [esp+8], 0x42f00000
    ja policy_two_scores
    add eax, 4
    jmp policy_compare
policy_two_scores:
    cmp ebx, -9
    jg policy_compare
    add eax, 2
policy_compare:
    mov [esp+12], eax
    fild dword ptr [esp+12]
    fadd dword ptr yard_epsilon
    fcomp dword ptr [esp+4]
    fnstsw ax
    test ah, 5
    jnz policy_no
    mov eax, 1
    jmp policy_exit
policy_no:
    xor eax, eax
policy_exit:
    add esp, 20
    pop edi
    pop esi
    pop ebx
    ret

play:
    pushfd
    pushad
    call eligible
    test eax, eax
    jz play_original
    mov ecx, [ebp-0x20]
    cmp ecx, [0xe60280]
    jne play_original
    call primary_depth             /* EAX integer cm, -32768 if unsupported */
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
    jnz play_original              /* marker > endpoint or nonfinite */
    cmp dword ptr level, 2
    je play_aggressive
    fmul dword ptr play_modern
    jmp play_original
play_aggressive:
    fmul dword ptr play_agg
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
    cmp dword ptr level, 2
    je target_aggressive
    fadd dword ptr target_modern
    jmp target_original
target_aggressive:
    fadd dword ptr target_agg
target_original:
    popad
    popfd
    fstp dword ptr [ebp-4]
    fld dword ptr [ebp-4]
    jmp target_tail

eligible:
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
    sub edx, 3
    cmp edx, 1
    ja no
    ret
no:
    xor eax, eax
    ret
.balign 4, 0xcc
level: .long 1
yard: .float 91.44
yard_epsilon: .float 0.0001
fifty: .float 50
play_modern: .float 1.5
play_agg: .float 2
target_modern: .float 0.15
target_agg: .float 0.30
modern_table: .byte 0,1,2,3,2,2
aggressive_table: .byte 0,2,3,5,3,3
code_end:
