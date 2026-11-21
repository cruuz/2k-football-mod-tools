/* Beta 81 scoring slice: simulated field-goal chance (in place at 0x109B5A, 148 bytes; two nops pad the end). Bytes: mod_editor/core/nfl2k5_sim_scoring.py */
.intel_syntax noprefix
.code32
.text
.global start
start:                              /* 0x109B5A: EAX = credited yards (rounded) */
    mov edi, dword ptr [esi+0xc]
    shl eax, 0xe
    xor eax, edi
    and eax, 0x3fc000
    xor dword ptr [esi+0xc], eax    /* credited distance into the kick record, as before */
    mov eax, dword ptr [esp+0x10]   /* kick yards (float bits, always positive) */
    mov ecx, 0x3f733333             /* 0.95 under 30 */
    cmp eax, 0x41f00000
    jb 1f
    mov ecx, 0x3f666666             /* 0.90 for 30-39 */
    cmp eax, 0x42200000
    jb 1f
    mov ecx, 0x3f59999a             /* 0.85 from 40 on (stock: 0.75 from 50) */
1:  mov dword ptr [esp+0x14], ecx
    fld dword ptr [esp+0x28]        /* adjusted distance */
    fmul dword ptr [0x4f6bdc]       /* 0.015 */
    fsub dword ptr [0x4f6bb0]       /* 0.375 */
    fsubr dword ptr [esp+0x14]      /* base + 0.375 - 0.015 x adjusted, the stock arithmetic */
    cmp dword ptr [0xa971c0], 0     /* extra point: keep the stock chance */
    jne 3f
    fld dword ptr [esp+0x10]
    cmp eax, 0x425c0000             /* past 55 yards */
    jbe 2f
    fmul dword ptr [tailk]
    fadd dword ptr [tailb]
    jmp 4f
tailk: .float -0.01775
tailb: .float 1.2375
gain:  .float 0.00475
2:  fmul dword ptr [gain]
4:  faddp st(1), st
3:  fstp dword ptr [esp+0x14]
    mov ecx, 0x3f7ae148             /* 0.98 cap */
    cmp dword ptr [esp+0x14], ecx
    jle 5f
    mov dword ptr [esp+0x14], ecx
5:  nop
    nop
end:
