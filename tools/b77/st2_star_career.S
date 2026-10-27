/* b778-st2: rookie stars + stars earned and lost over a career (GNU as --32, Intel syntax).
 *
 * EXPERIMENTAL / UNWITNESSED.  No mutable state outside the owner's own data allocation.
 *
 * Rookie class: FUN_002BE940(count) sets [0xE41CDC] and jumps into FUN_002BE900, whose loop
 * allocates a prospect (0x2BD390), calls the generator FUN_002BE6F0 and repeats.  Three hooks:
 *   0x2BE940  -> class_start   (reset the class list, save the count, continue retail)
 *   0x2BE923  -> generate      (remember every generated record, then return)
 *   0x2BE937  -> class_finish  (rank the class, tag 3..5 top prospects + 1..2 gems)
 *
 * Offseason: the Preseason step 0x24857F..0x2485D6 ages every allocated player and then runs
 * the form routine.  0x24857A is hooked to run the star re-evaluation before aging (season
 * stats are final there).  The pool is [0xB72918] {count, base}; the same walk as the aging
 * loop.  A player's overall is the game's own FUN_00246D80; season production is read through
 * the game's own history getter FUN_0014EF20.
 *
 * Star bit = roster record +0x53 bit 0 (nfl2k5_player_tags).  Ability tier = +0x53 bits 6..7
 * (nfl2k5_abilities_runtime.STAR_CLASSES).  Other bits of +0x53 (abilities 1..4, Guardian 5)
 * are preserved.
 */
.intel_syntax noprefix
.code32
.text

.extern retail_generator      /* 0x2BE6F0 */
.extern class_loop            /* 0x2BE900 */
.extern overall_fn            /* 0x246D80 */
.extern stat_fn               /* 0x14EF20 */
.extern rand_fn               /* 0x48B50 */
.extern allocated_fn          /* 0x2BD380 */
.extern class_counter         /* 0xE41CDC */
.extern player_pool           /* 0xB72918 */
.extern data_base             /* the owner's writable data allocation */
.extern code_base             /* this code allocation's base VA */

/* mutable data allocation offsets (pages are zero initialised; the owner writes them at runtime) */
.set PTRS,            0x000   /* 400 record pointers, class generation order */
.set SCORES,          0x640   /* 400 class scores */
.set SUM,             0xCC0   /* 17 overall sums */
.set SCOUNT,          0xD04   /* 17 records per position */
.set MEAN,            0xD48   /* 17 mean*100 values */
.set C_CLASS_COUNT,   0xD8C
.set C_SCRATCH,       0xD90
.set C_SCRATCH2,      0xD94   /* K (top prospects) */
.set C_SCRATCH3,      0xD98   /* superstar coin / gem count */
.set C_BESTIDX,       0xD9C
.set C_BESTPOT,       0xDA0
.set C_BESTSCORE,     0xDA4
.set C_CANDSCORE,     0xDA8
.set C_REC,           0xDAC
.set C_POS,           0xDB0
.set C_YEARS,         0xDB4
.set C_OV,            0xDB8
.set C_GAMES,         0xDBC
.set C_SCORE,         0xDC0
/* constant tables live after the code in the same RX allocation */
.set K_POT,           0x600   /* 17*16 potential bytes */
.set K_VALUE,         0x710   /* 17 positional value words (percent) */
.set K_FIELD,         0x740   /* 17 production stat fields (0xFF = none) */
.set K_THI,           0x760   /* 17 high thresholds */
.set K_TMID,          0x790   /* 17 mid thresholds */
.set K_TLO,           0x7C0   /* 17 low thresholds */
.set K_HUNDRED,       0x7E8   /* float 100.0 */
.set K_CONST,         0x7F0   /* dwords: gain, lose, tier X, tier superstar */
.set K_CONST2,        0x800   /* dwords: min games, gem min, gem max, gem potential */
.set K_CONST3,        0x810   /* dword: veteran QB floor */
.set K_LIMITS,        0x814   /* bytes 0,2,4,7 */

.global class_start, class_tail, class_finish, offseason

/* ------------------------------------------------------------------ class generation hooks */
class_start:                  /* 0x2BE940: ecx=count */
    mov dword ptr [data_base + C_CLASS_COUNT], 0
    mov dword ptr [class_counter], ecx
    jmp class_loop

class_tail:                   /* 0x2BE8DB: the generator epilogue, esi = the generated record */
    push eax
    push ecx
    push edx
    pushfd
    mov eax, dword ptr [data_base + C_CLASS_COUNT]
    cmp eax, 400
    jae tail_done
    mov dword ptr [data_base + PTRS + eax*4], esi
    inc eax
    mov dword ptr [data_base + C_CLASS_COUNT], eax
tail_done:
    popfd
    pop edx
    pop ecx
    pop eax
    pop edi
    pop esi
    pop ebp
    pop ebx
    add esp, 8
    ret

class_finish:                 /* 0x2BE937: the loop exit (saved ecx is on the stack) */
    pushad
    sub esp, 108
    fnsave [esp]
    mov eax, dword ptr [data_base + C_CLASS_COUNT]
    test eax, eax
    jz finish_done
    mov ebp, eax
    xor ecx, ecx
zero_loop:
    mov dword ptr [data_base + SUM + ecx*4], 0
    mov dword ptr [data_base + SCOUNT + ecx*4], 0
    inc ecx
    cmp ecx, 17
    jl zero_loop
    /* pass 1: position means over the whole class */
    xor esi, esi
pass1:
    cmp esi, ebp
    jge pass1_done
    mov ecx, dword ptr [data_base + PTRS + esi*4]
    test ecx, ecx
    jz pass1_next
    and byte ptr [ecx + 0x53], 0x3E   /* a generated prospect starts with no star and no tier */
    call overall100
    movzx edx, byte ptr [ecx + 0x35]
    cmp edx, 17
    jae pass1_next
    add dword ptr [data_base + SUM + edx*4], eax
    inc dword ptr [data_base + SCOUNT + edx*4]
pass1_next:
    inc esi
    jmp pass1
pass1_done:
    xor ecx, ecx
mean_loop:
    mov eax, dword ptr [data_base + SCOUNT + ecx*4]
    test eax, eax
    jz mean_zero
    mov ebx, dword ptr [data_base + SUM + ecx*4]
    imul ebx, ebx, 100
    mov eax, ebx
    xor edx, edx
    div dword ptr [data_base + SCOUNT + ecx*4]
    jmp mean_store
mean_zero:
    xor eax, eax
mean_store:
    mov dword ptr [data_base + MEAN + ecx*4], eax
    inc ecx
    cmp ecx, 17
    jl mean_loop
    /* pass 2: positional value score */
    xor esi, esi
pass2:
    cmp esi, ebp
    jge pass2_done
    mov ecx, dword ptr [data_base + PTRS + esi*4]
    test ecx, ecx
    jz pass2_zero
    call overall100
    movzx edx, byte ptr [ecx + 0x35]
    cmp edx, 17
    jae pass2_zero
    imul eax, eax, 100
    sub eax, dword ptr [data_base + MEAN + edx*4]
    movzx ebx, word ptr [code_base + K_VALUE + edx*2]
    imul eax, ebx
    cdq
    mov ebx, 10000
    idiv ebx
    jmp pass2_store
pass2_zero:
    xor eax, eax
pass2_store:
    mov dword ptr [data_base + SCORES + esi*4], eax
    inc esi
    jmp pass2
pass2_done:
    /* K = 3..5; one class in eight may make its best prospect a Superstar */
    mov ecx, 0xE5FCA0
    call rand_fn
    xor edx, edx
    mov ecx, 3
    div ecx
    add edx, 3
    mov dword ptr [data_base + C_SCRATCH2], edx
    mov ecx, 0xE5FCA0
    call rand_fn
    and eax, 7
    mov dword ptr [data_base + C_SCRATCH3], eax
    xor edi, edi
select_loop:
    cmp edi, dword ptr [data_base + C_SCRATCH2]
    jge select_done
    mov ebx, 0x80000000
    mov edx, -1
    xor esi, esi
max_loop:
    cmp esi, ebp
    jge max_done
    mov eax, dword ptr [data_base + SCORES + esi*4]
    cmp eax, ebx
    jle max_next
    mov ebx, eax
    mov edx, esi
max_next:
    inc esi
    jmp max_loop
max_done:
    cmp edx, -1
    je select_done
    mov dword ptr [data_base + SCORES + edx*4], 0x80000000
    mov ecx, dword ptr [data_base + PTRS + edx*4]
    mov eax, 1
    test edi, edi
    jnz select_tier
    cmp dword ptr [data_base + C_SCRATCH3], 0
    jne select_tier
    mov eax, 2
select_tier:
    call fit_tier
    call set_star_tier
    inc edi
    jmp select_loop
select_done:
    /* 1..2 later-round gems: rank 33..160, potential >= 70, highest potential first */
    mov ecx, 0xE5FCA0
    call rand_fn
    and eax, 1
    inc eax
    mov dword ptr [data_base + C_SCRATCH3], eax
gem_loop:
    cmp dword ptr [data_base + C_SCRATCH3], 0
    jle finish_done
    mov dword ptr [data_base + C_BESTIDX], -1
    mov dword ptr [data_base + C_BESTPOT], -1
    mov dword ptr [data_base + C_BESTSCORE], 0x80000000
    xor esi, esi
gem_scan:
    cmp esi, ebp
    jge gem_scan_done
    mov eax, dword ptr [data_base + SCORES + esi*4]
    cmp eax, 0x80000000
    je gem_next
    mov dword ptr [data_base + C_CANDSCORE], eax
    xor ecx, ecx
    xor edi, edi
gem_rank:
    cmp edi, ebp
    jge gem_rank_done
    mov eax, dword ptr [data_base + SCORES + edi*4]
    cmp eax, dword ptr [data_base + C_CANDSCORE]
    jle gem_rank_next
    inc ecx
gem_rank_next:
    inc edi
    jmp gem_rank
gem_rank_done:
    inc ecx
    add ecx, dword ptr [data_base + C_SCRATCH2]
    cmp ecx, dword ptr [code_base + K_CONST2 + 4]
    jl gem_next
    cmp ecx, dword ptr [code_base + K_CONST2 + 8]
    jg gem_next
    mov ecx, dword ptr [data_base + PTRS + esi*4]
    movzx eax, byte ptr [ecx + 0x24]
    shr eax, 4
    and eax, 0x0F
    movzx edx, byte ptr [ecx + 0x35]
    shl edx, 4
    add eax, edx
    movzx eax, byte ptr [code_base + K_POT + eax]
    cmp eax, dword ptr [code_base + K_CONST2 + 12]
    jl gem_next
    cmp eax, dword ptr [data_base + C_BESTPOT]
    jl gem_next
    jg gem_take
    mov edx, dword ptr [data_base + C_CANDSCORE]
    cmp edx, dword ptr [data_base + C_BESTSCORE]
    jle gem_next
gem_take:
    mov dword ptr [data_base + C_BESTPOT], eax
    mov dword ptr [data_base + C_BESTIDX], esi
    mov eax, dword ptr [data_base + C_CANDSCORE]
    mov dword ptr [data_base + C_BESTSCORE], eax
gem_next:
    inc esi
    jmp gem_scan
gem_scan_done:
    cmp dword ptr [data_base + C_BESTIDX], -1
    je finish_done
    mov edx, dword ptr [data_base + C_BESTIDX]
    mov dword ptr [data_base + SCORES + edx*4], 0x80000000
    mov ecx, dword ptr [data_base + PTRS + edx*4]
    mov eax, 1
    call fit_tier
    call set_star_tier
    dec dword ptr [data_base + C_SCRATCH3]
    jmp gem_loop
finish_done:
    mov dword ptr [data_base + C_CLASS_COUNT], 0
    frstor [esp]
    add esp, 108
    popad
    pop ecx
    ret

/* ------------------------------------------------------------------ offseason hooks */
offseason:                    /* 0x24857A: before the aging loop */
    pushad
    sub esp, 108
    fnsave [esp]
    mov eax, dword ptr [player_pool]
    mov ebp, dword ptr [eax]
    mov esi, dword ptr [eax + 4]
    xor edi, edi
os_loop:
    cmp edi, ebp
    jge os_done
    mov eax, edi
    imul eax, eax, 0x54
    add eax, esi
    mov dword ptr [data_base + C_REC], eax
    mov ecx, eax
    call allocated_fn
    test eax, eax
    jz os_next
    mov eax, dword ptr [data_base + C_REC]
    test byte ptr [eax + 8], 0x10
    jnz os_next
    movzx ecx, byte ptr [eax + 0x35]
    cmp ecx, 17
    jae os_next
    movzx edx, byte ptr [eax + 0x25]
    and edx, 0x1F
    cmp edx, 1
    jbe os_next
    mov dword ptr [data_base + C_POS], ecx
    mov dword ptr [data_base + C_YEARS], edx
    mov ecx, dword ptr [data_base + C_REC]
    call overall100
    mov ebx, eax
    mov dword ptr [data_base + C_OV], eax
    mov ecx, dword ptr [data_base + C_REC]
    xor edx, edx
    call stat1
    mov dword ptr [data_base + C_GAMES], eax
    cmp eax, 8
    jl os_score
    mov ecx, dword ptr [data_base + C_REC]
    mov edx, dword ptr [data_base + C_POS]
    call production
    add ebx, eax
os_score:
    mov dword ptr [data_base + C_SCORE], ebx
    mov eax, dword ptr [data_base + C_REC]
    test byte ptr [eax + 0x53], 1
    jz os_gain
    cmp ebx, dword ptr [code_base + K_CONST + 4]
    jge os_keep
    mov ecx, dword ptr [data_base + C_POS]
    test ecx, ecx
    jnz os_lose_check
    cmp dword ptr [data_base + C_YEARS], 4
    jbe os_lose_check
    cmp ebx, dword ptr [code_base + K_CONST3]
    jge os_keep
os_lose_check:
    mov eax, dword ptr [code_base + K_CONST2]
    cmp dword ptr [data_base + C_GAMES], eax
    jl os_keep
    mov eax, dword ptr [data_base + C_REC]
    and byte ptr [eax + 0x53], 0xFE
    jmp os_next
os_keep:
    /* an existing star keeps his authored tier; only gains assign a tier */
    jmp os_next
os_gain:
    cmp ebx, dword ptr [code_base + K_CONST]
    jl os_next
    mov eax, 1
    cmp ebx, dword ptr [code_base + K_CONST + 8]
    jl os_gain_ss
    mov eax, 3
    jmp os_gain_band
os_gain_ss:
    cmp ebx, dword ptr [code_base + K_CONST + 12]
    jl os_gain_band
    mov eax, 2
os_gain_band:
    mov ecx, dword ptr [data_base + C_REC]
    call fit_tier
    call set_star_tier
os_next:
    inc edi
    jmp os_loop
os_done:
    frstor [esp]
    add esp, 108
    popad
    mov eax, dword ptr [player_pool]
    ret

/* ------------------------------------------------------------------ helpers */
overall100:                   /* ecx=record -> eax=overall 0..100, ecx preserved */
    push ecx
    call overall_fn
    fmul dword ptr [code_base + K_HUNDRED]
    fistp dword ptr [data_base + C_SCRATCH]
    pop ecx
    mov eax, dword ptr [data_base + C_SCRATCH]
    ret

stat1:                        /* ecx=record, edx=field -> eax=last season value */
    push 1
    call stat_fn
    ret

production:                   /* ecx=record, edx=position -> eax rating bonus */
    push ebx
    push esi
    mov esi, ecx
    mov ebx, edx
    test ebx, ebx
    jnz prod_table
    /* QB: passing yards + 20*TD - 45*INT */
    mov ecx, esi
    mov edx, 8
    call stat1
    mov dword ptr [data_base + C_SCRATCH], eax
    mov ecx, esi
    mov edx, 9
    call stat1
    imul eax, eax, 20
    add eax, dword ptr [data_base + C_SCRATCH]
    mov dword ptr [data_base + C_SCRATCH], eax
    mov ecx, esi
    mov edx, 10
    call stat1
    imul eax, eax, 45
    mov edx, dword ptr [data_base + C_SCRATCH]
    sub edx, eax
    mov eax, edx
    cmp eax, 4500
    jge prod_hi
    cmp eax, 3200
    jge prod_mid
    cmp eax, 2500
    jl prod_lo
    jmp prod_zero
prod_table:
    movzx eax, byte ptr [code_base + K_FIELD + ebx]
    cmp eax, 0xFF
    je prod_zero
    mov ecx, esi
    mov edx, eax
    call stat1
    movzx edx, word ptr [code_base + K_THI + ebx*2]
    cmp eax, edx
    jge prod_hi
    movzx edx, word ptr [code_base + K_TMID + ebx*2]
    cmp eax, edx
    jge prod_mid
    movzx edx, word ptr [code_base + K_TLO + ebx*2]
    cmp eax, edx
    jl prod_lo
    jmp prod_zero
prod_hi:
    mov eax, 5
    jmp prod_done
prod_mid:
    mov eax, 2
    jmp prod_done
prod_lo:
    mov eax, -3
    jmp prod_done
prod_zero:
    xor eax, eax
prod_done:
    pop esi
    pop ebx
    ret

fit_tier:                     /* ecx=record, eax=tier -> eax=tier whose flag limit fits */
    push ebx
    push edx
    push esi
    movzx edx, byte ptr [ecx + 0x53]
    and edx, 0x0F
    movzx ebx, word ptr [ecx + 0x52]
    and ebx, 0x1EE0
    xor esi, esi
pc_a:
    test ebx, ebx
    jz pc_a_done
    shr ebx, 1
    adc esi, 0
    jmp pc_a
pc_a_done:
    test edx, edx
    jz pc_b_done
pc_b:
    shr edx, 1
    adc esi, 0
    test edx, edx
    jnz pc_b
pc_b_done:
fit_loop:
    cmp eax, 3
    jge fit_done
    movzx edx, byte ptr [code_base + K_LIMITS + eax]
    cmp edx, esi
    jge fit_done
    inc eax
    jmp fit_loop
fit_done:
    pop esi
    pop edx
    pop ebx
    ret

set_star_tier:                /* ecx=record, eax=tier */
    or byte ptr [ecx + 0x53], 1
set_tier:
    mov dl, byte ptr [ecx + 0x53]
    and dl, 0x3F
    shl al, 6
    or dl, al
    mov byte ptr [ecx + 0x53], dl
    ret

stats_end:
