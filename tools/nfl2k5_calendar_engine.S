/* EXPERIMENTAL / UNWITNESSED. i386 calendar, no persistent or writable state.
 * Gregorian core: EAX full year, ECX -> month/day/encoded year. Day 0 = 2000-01-01.
 * Public helpers preserve EBX/ESI/EDI/EBP and ECX unless explicitly documented.
 * Invalid arithmetic returns INT_MIN, with no date writes. Table covers 1900..2255.
 * Retail weekday ABI is MONDAY=0 (the research proposal's Sunday=0 needs adaptation).
 */
.intel_syntax noprefix
.code32
.text
.global leap, ordinal, inverse, weekday, weekday_record, legacy_ordinal
.global add_days, sub_days, opening_day, redate, birth_year, projection_year
.extern year_starts, month_starts, base_year

leap:                           /* EAX full year -> EAX bool, clobber EDX */
    push ecx
    test eax, 3
    jnz leap_no
    xor edx, edx
    mov ecx, 100
    div ecx
    test edx, edx
    jnz leap_yes
    test eax, 3
    jnz leap_no
leap_yes:
    mov eax, 1
    pop ecx
    ret
leap_no:
    xor eax, eax
    pop ecx
    ret

ordinal:                        /* ECX date, EAX full year -> ordinal or INT_MIN */
    push ebx
    push esi
    push edi
    lea edx, [eax-1900]
    cmp edx, 355
    ja ordinal_bad
    mov esi, dword ptr [year_starts+edx*4]
    movzx ebx, byte ptr [ecx]
    dec ebx
    cmp ebx, 11
    ja ordinal_bad
    call leap
    imul eax, eax, 26
    lea edi, [month_starts+eax]
    movzx eax, word ptr [edi+ebx*2]
    movzx edx, word ptr [edi+ebx*2+2]
    sub edx, eax
    add esi, eax
    movzx eax, byte ptr [ecx+1]
    dec eax
    cmp eax, edx
    jae ordinal_bad
    add eax, esi
    jmp ordinal_done
ordinal_bad:
    mov eax, 0x80000000
ordinal_done:
    pop edi
    pop esi
    pop ebx
    ret

legacy_ordinal:                 /* Retail record ABI and 1999 epoch; template context */
    push ecx
    add ecx, 3
    movzx eax, byte ptr [ecx+2]
    cmp eax, 98
    jbe legacy_2000
    add eax, 1900
    jmp legacy_convert
legacy_2000:
    add eax, 2000
legacy_convert:
    call ordinal
    cmp eax, 0x80000000
    je legacy_done
    add eax, 365
legacy_done:
    pop ecx
    ret

weekday_record:                 /* Current grid record, not a historical/template record */
    push ecx
    add ecx, 3
    call weekday
    pop ecx
    ret
weekday:                        /* Current schedule date -> Monday=0 */
    push ecx
    movzx eax, byte ptr [ecx+2]
    add eax, 2000
    call ordinal
    cmp eax, 0x80000000
    je weekday_done
    add eax, 5
    cdq
    mov ecx, 7
    idiv ecx
    mov eax, edx
    test eax, eax
    jns weekday_done
    add eax, 7
weekday_done:
    pop ecx
    ret

inverse:                        /* Day number -> encoded current schedule; atomic 3-byte write */
    push ebx
    push esi
    push edi
    cmp eax, 0
    jl inverse_bad
    cmp eax, dword ptr [year_starts+356*4]
    jge inverse_bad
    mov esi, eax
    mov ebx, 100                 /* scan at most 256 years, bounded independent of input */
inverse_year:
    cmp esi, dword ptr [year_starts+ebx*4+4]
    jl inverse_months
    inc ebx
    jmp inverse_year
inverse_months:
    sub esi, dword ptr [year_starts+ebx*4]
    lea eax, [ebx+1900]
    call leap
    imul eax, eax, 26
    lea edi, [month_starts+eax]
    xor edx, edx
inverse_month:
    movzx eax, word ptr [edi+edx*2+2]
    cmp esi, eax
    jl inverse_store
    inc edx
    jmp inverse_month
inverse_store:
    movzx eax, word ptr [edi+edx*2]
    sub esi, eax
    inc esi
    mov eax, esi
    inc edx
    sub ebx, 100
    mov byte ptr [ecx], dl
    mov byte ptr [ecx+1], al
    mov byte ptr [ecx+2], bl
    mov eax, 1
    jmp inverse_done
inverse_bad:
    mov eax, 0x80000000
inverse_done:
    pop edi
    pop esi
    pop ebx
    ret

sub_days:                       /* ECX current date, EDX signed delta */
    neg edx
    jo arithmetic_bad
add_days:
    push edx
    movzx eax, byte ptr [ecx+2]
    add eax, 2000
    call ordinal
    pop edx
    cmp eax, 0x80000000
    je arithmetic_bad
    add eax, edx
    jo arithmetic_bad
    jmp inverse
arithmetic_bad:
    mov eax, 0x80000000
    ret

opening_day:                    /* Current full Y -> Thanksgiving minus 77 days ordinal */
    push ecx
    mov eax, dword ptr [0xe576b8]
    add eax, OFFSET FLAT:base_year
    push 0x010b                  /* Nov 1 on stack */
    mov ecx, esp
    call ordinal
    add esp, 4
    cmp eax, 0x80000000
    je opening_done
    push ebx
    mov ebx, eax
    add eax, 5
    cdq
    mov ecx, 7
    idiv ecx
    mov eax, 10
    sub eax, edx
    xor edx, edx
    div ecx
    lea eax, [ebx+edx-56]        /* fourth Thursday (+21), minus 77 */
    pop ebx
opening_done:
    pop ecx
    ret

redate:                         /* ECX destination date, EDX signed offset from opening day */
    push edx
    call opening_day
    pop edx
    cmp eax, 0x80000000
    je arithmetic_bad
    add eax, edx
    jo arithmetic_bad
    jmp inverse

birth_year:                     /* EAX raw 7-bit DOB -> moving century; preserves ECX, EDX */
    push ecx
    push edx
    mov ecx, 100
    xor edx, edx
    div ecx                     /* old encodings 100..127 normalize without changing saved bits */
    mov eax, dword ptr [0xe576b8]
    add eax, OFFSET FLAT:base_year
    push eax
    sub eax, edx
    xor edx, edx
    div ecx
    pop eax
    sub eax, edx
    pop edx
    pop ecx
    ret

projection_year:                /* Preserve old +4 LEAs: EAX index -> base+index-4 */
    mov eax, dword ptr [0xe576b8]
    add eax, OFFSET FLAT:base_year-4
    ret

.global regular_anchor, display_weekday, grid_weekday
.extern mode_getter, retail_weekday
regular_anchor:                 /* ECX -> existing Nov 1 scratch; checked full-year encode */
    mov eax, dword ptr [0xe576b8]
    add eax, OFFSET FLAT:base_year-2000
    cmp eax, 255
    ja arithmetic_bad
    mov byte ptr [ecx+2], al
    ret

grid_weekday:                   /* Grid getter callsites, mode 2 proves current franchise */
    push ecx
    add ecx, 3
    call display_weekday
    pop ecx
    ret
display_weekday:
    push ecx
    call mode_getter
    pop ecx
    cmp eax, 2
    je weekday
    jmp retail_weekday          /* historical/exhibition retains retail source context */
