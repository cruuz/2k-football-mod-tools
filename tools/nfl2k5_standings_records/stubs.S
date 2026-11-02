/* Team Standings records view (job b780 j1-standings): the retail patch sites enter here. EXPERIMENTAL / UNWITNESSED.
   Game routines are reached through absolute addresses in eax. Every entry is a "call" that replaces an instruction of
   FUN_003551A0 (input), FUN_003554B0 (draw) or FUN_00355CD0 (legend) and keeps the instructions around it as they were,
   so nothing here may touch ebx, esi, edi or ebp, and the x87 stack is empty at every site.

   Frame facts (static RE, USA retail): inside FUN_003554B0 esp is 16-byte aligned plus a fixed frame; its locals are the
   text position vector at [esp+0x20] (x, y, z), the text context at [esp+0x60] and the count buffer at [esp+0xF0]
   (the context and the vector keep their offsets when a "call" at the site pushes a return address, so add 4). */
    .intel_syntax noprefix
    .text
    .globl sr_input, sr_hdr0, sr_hdr1, sr_hdr2, sr_cell0, sr_cell1, sr_cell2, sr_leg0, sr_leg1, sr_leg2, sr_leg3, sr_enter

/* 0x35543F, FUN_003551A0 (Team Standings and realignment input): "mov eax,[esp+0x14] ; test ah,0xC0" (7 bytes: the
   pressed mask, then the L/R conference switch test) became "call sr_input ; nop ; nop". The caller's je follows, so
   the flags come from the same test. Only ESPN.com's standings reacts: [0xAE9EE8] is 1 there, 0 on the realignment screen. */
sr_input:
    mov eax, dword ptr [esp+0x18]
    cmp dword ptr [0x00AE9EE8], 1
    jne 1f
    test eax, 0x3000
    jz 1f
    mov ecx, eax
    call sr_buttons
    mov eax, dword ptr [esp+0x18]
1:  test ah, 0xC0
    ret

/* 0x355903 / 0x35592A / 0x355951, FUN_003554B0 header labels: "mov edx, W / L / T string" became "call sr_hdrN". The
   label comes back in edx for the retail text draw that follows; the position vector is [esp+0x20] of the caller
   (this stub's esp+0x24) and its text context is the caller's [esp+0x60] (this stub's esp+0x64). */
sr_hdr0:
    xor eax, eax
    jmp sr_hdr_common
sr_hdr1:
    mov eax, 1
    jmp sr_hdr_common
sr_hdr2:
    mov eax, 2
sr_hdr_common:
    lea edx, [esp+0x64]
    push edx
    lea edx, [esp+0x28]
    mov ecx, eax
    call sr_header
    mov edx, eax
    ret

/* 0x355B1E / 0x355B68 / 0x355BB2, FUN_003554B0 cells: "call 0x4A400" (the formatter: ecx = buffer, edx = format, one
   stack argument it pops) became "call sr_cellN". The club record is in edi. A handled cell leaves its text in the
   buffer and returns like the formatter; otherwise the retail formatter runs with everything as it was. */
sr_cell0:
    xor eax, eax
    jmp sr_cell_common
sr_cell1:
    mov eax, 1
    jmp sr_cell_common
sr_cell2:
    mov eax, 2
sr_cell_common:
    push edx
    push ecx
    push edi
    lea edx, [esp+0x34]
    push edx
    mov edx, ecx
    mov ecx, eax
    call sr_cell_text
    pop ecx
    pop edx
    test eax, eax
    jnz 1f
    mov eax, 0x0004A400
    jmp eax
1:  ret 4

/* 0x355D39 / 0x355D5F / 0x355D85 / 0x355DAB, FUN_00355CD0 legend: "mov edx, clinch string" became "call sr_legN". */
sr_leg0:
    xor ecx, ecx
    jmp sr_leg_common
sr_leg1:
    mov ecx, 1
    jmp sr_leg_common
sr_leg2:
    mov ecx, 2
    jmp sr_leg_common
sr_leg3:
    mov ecx, 3
sr_leg_common:
    call sr_legend
    mov edx, eax
    ret

/* 0x54CDB4: the Team Standings enter callback pointer (retail FUN_003550F0). Every visit opens on the retail columns. */
sr_enter:
    mov dword ptr [sr_state], 0
    mov eax, 0x003550F0
    jmp eax
