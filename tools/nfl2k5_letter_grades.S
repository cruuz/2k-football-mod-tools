# Letter grades in Franchise (b77 job F4): the owned RX code and RO table, GNU as --32, Intel syntax.
#
# Reproduce mod_editor/core/nfl2k5_letter_grades_code.py with tools/nfl2k5_letter_grades_assemble.py.
# EXPERIMENTAL / UNWITNESSED. Pure functions plus one static table: no runtime state, no new RW.
#
# External symbols (resolved by the owner module against the retail executable):
#   fn_overall   0x000E6660  player overall (ecx = player record) -> eax = the integer the game displays
#   fn_swprintf  0x0004A400  swprintf(ecx = destination, edx = format, [esp+4] = argument list pointer)
#   nan_default  0x001732CA  the spreadsheet cell formatter's unknown-kind exit ("**NAN**")
# Calling conventions are the game's own: caller-saved eax/ecx/edx, callee-saved ebx/esi/edi/ebp.

        .intel_syntax noprefix
        .text

# ---------------------------------------------------------------------------------------------------
# grade_text: eax = rating (signed) -> eax = pointer to the grade's UTF-16 label (up to 3 characters).
# Walks the band table (highest minimum first, last minimum = INT_MIN so the walk always ends).
# Preserves every register except eax.
grade_text:
        push    esi
        mov     esi, offset bands
1:      cmp     eax, dword ptr [esi]
        jge     2f
        add     esi, 12
        jmp     1b
2:      lea     eax, [esi + 4]
        pop     esi
        ret

# ---------------------------------------------------------------------------------------------------
# convert_R: the game's swprintf conversion handler for "%R" (it replaces the unused "%n" row of the
# registration list). ABI of the stock handlers (0x49CD0 "%s" is the model):
#   ecx = output cursor, edx = remaining characters + 1, [esp+4] -> state (state+4 = argument cursor),
#   [esp+8] -> flags (ignored: a grade has no width, precision or padding), ret 8, eax = characters written.
convert_R:
        push    ebx
        push    esi
        push    edi
        mov     ebx, dword ptr [esp + 0x10]
        mov     esi, dword ptr [ebx + 4]
        add     esi, 3
        and     esi, -4
        mov     eax, dword ptr [esi]
        add     esi, 4
        mov     dword ptr [ebx + 4], esi
        dec     edx
        call    grade_text
        mov     esi, eax
        xor     ebx, ebx
1:      test    edx, edx
        jle     2f
        movzx   eax, word ptr [esi + ebx*2]
        test    eax, eax
        jz      2f
        mov     word ptr [ecx + ebx*2], ax
        inc     ebx
        dec     edx
        jmp     1b
2:      mov     eax, ebx
        pop     edi
        pop     esi
        pop     ebx
        ret     8

# ---------------------------------------------------------------------------------------------------
# cell_kind9: the spreadsheet cell formatter FUN_00173120 (eax = cell kind, ecx = output buffer,
# [esp+0xC] = the cell's float value once its "sub esp, 8" has run) takes its 'ja' here for every kind above
# 8. Kind 9 writes the grade of the value; any other kind leaves for the retail "**NAN**" exit unchanged.
# The wrappers read only the buffer afterwards, so eax/ecx/edx are free; the function's own epilogue follows.
cell_kind9:
        cmp     eax, 9
        jne     nan_default
        cvtss2si eax, dword ptr [esp + 0xC]
        call    grade_text
        mov     edx, eax
1:      movzx   eax, word ptr [edx]
        mov     word ptr [ecx], ax
        add     edx, 2
        add     ecx, 2
        test    eax, eax
        jnz     1b
        add     esp, 8
        ret     4

# ---------------------------------------------------------------------------------------------------
# matchup_overall: the OVERALL case of the 0x2B0940 text callback. Retail runs "call 0xE6660; jmp 0x2B0A74",
# a tail it shares with the third rating attribute, so a format-literal swap cannot reach it alone. This is that
# tail, byte for byte, with the "%R" literal. (Entered by a jmp from 0x2B0A29; esp is the callback's own frame.)
matchup_overall:
        call    fn_overall
        lea     ecx, [esp + 4]
        push    ecx
        mov     ecx, dword ptr [esp + 0x10]
        mov     edx, offset fmt_grade
        mov     dword ptr [esp + 8], eax
        call    fn_swprintf
        pop     esi
        pop     ecx
        ret     0xC

        .section .rodata
        .balign 4
# The band table: { signed minimum rating, UTF-16 label (3 characters + NUL) } x 11, descending.
# Noah's scale (2K Player Grade System, 2026-10-07): 95+ A+, 90-94 A, 85-89 B+, 80-84 B, 75-79 C+, 70-74 C,
# 65-69 D+, 60-64 D, 55-59 F+, 50-54 F, 0-49 F-. The module rewrites this table from its settings; this is the default.
bands:
        .long   95
        .hword  'A', '+', 0, 0
        .long   90
        .hword  'A', 0, 0, 0
        .long   85
        .hword  'B', '+', 0, 0
        .long   80
        .hword  'B', 0, 0, 0
        .long   75
        .hword  'C', '+', 0, 0
        .long   70
        .hword  'C', 0, 0, 0
        .long   65
        .hword  'D', '+', 0, 0
        .long   60
        .hword  'D', 0, 0, 0
        .long   55
        .hword  'F', '+', 0, 0
        .long   50
        .hword  'F', 0, 0, 0
        .long   0x80000000
        .hword  'F', '-', 0, 0

# Format literals (UTF-16, NUL terminated, 4-byte aligned).
        .balign 4
fmt_grade:
        .hword  '%', 'R', 0, 0
fmt_overall:
        .hword  'O', 'v', 'e', 'r', 'a', 'l', 'l', ':', '%', 'R', 0, 0
        .balign 4
fmt_rating_sentence:
        .hword  'A', ' ', '%', 's', ' ', 'w', 'i', 't', 'h', ' ', 'r', 'a', 't', 'i', 'n', 'g', ' ', '%', 'R', ' '
        .hword  'o', 'r', ' ', 'b', 'e', 't', 't', 'e', 'r', '.', 0, 0
ro_end:
