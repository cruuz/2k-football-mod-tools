/* nfl2k5_history_pool (b780 hist1): the franchise career-history pool's garbage collection, rewritten in place.

   Retail (USA default.xbe): every history write goes through FUN_0014F220. When the 50,000-word pool is full it runs
   the compaction 0x14E9D0 and then the fold 0x14EFE0 at the oldest season level, on EVERY write, and the fold
   compacts the whole pool once per merged word (O(pool) each) and sums old seasons into one signed 16-bit cell with
   no overflow check (a long-career QB's 66,267 career passing yards read 1,065 after one offseason).

   This file replaces, inside the engine's own bytes (no cave, no new section):
     site A 0x14E8B0  insert one word: dword move instead of the byte-wise memmove (same semantics, same fixups)
     site B 0x14E930  (the old remove, only the old compaction called it) -> gc_chunk: the full-pool path of 0x14F220
     site C 0x14E9D0  compaction: one pass, pointer fixups from a 256-word block table on the stack; plus helpers
     site D 0x14EFE0  fold(depth): skips a merge whose 16-bit sum would wrap; deletes are compacted once at the end
     site E 0x14F16F  `ret` after the 7-byte rule-table load at 0x14F168 (retail bytes, or the honors owner's call)
     site F 0x14F249  the full-pool path of 0x14F220 calls gc_chunk; a zero result drops the write as retail does
   gc_chunk folds whole season levels, oldest first, until 6,000 words are free, never at depth < 3 (the current
   and the last season are never folded), so a full pool collects once per ~6,000 writes, not on every write. */
        .intel_syntax noprefix

        .set ROSTER,   0x00B72918      /* the roster object: [0] players, [4] first player, [0x40] used, [0x44] pool */
        .set CLASS,    0x00BD7F98      /* history class: 0 regular season, 1 postseason (the searches filter by it) */
        .set CAPACITY, 0x0014E7E0      /* -> eax: 50,000 words (35+ teams) or 20,000 */
        .set FIRST,    0x0014E8A0      /* eax=player, esi=field|0xFF, edx=slot|0xFF -> eax word* (live, this class) */
        .set NEXT,     0x0014E880      /* eax=word*, esi, edx -> next match or 0 */
        .set MAXAGE,   0x0014EBC0      /* -> eax: max(years pro - slot) over every live word of this class */
        .set FIND,     0x0014EE20      /* ecx=player, edx=field, [esp+4]=slot -> eax word*; ret 4 */
        .set RULE,     0x0014F168      /* esi=field -> eax: nonzero sums, zero keeps the max (+ site E's ret) */
        .set APPEND,   0x0014F220      /* ecx=player, edx=word -> eax */
        .set DELETED,  0x10000000
        .set FOLDED,   0x40000000
        .set CHUNK,    6000            /* words a full-pool collection frees */
        .set MIN_DEPTH, 3              /* fold(3) merges seasons 3+ years old into the one 2 years old */

/* ---- site A: insert one word at edi (called by 0x14F220 only) ------------------------------------------------ */
        .section .site_a, "ax"
        .globl insert_word
insert_word:
        push    esi
        push    edi
        mov     ecx, [ROSTER]
        mov     eax, [ecx+0x40]
        mov     esi, edi
        sub     esi, [ecx+0x44]
        sar     esi, 2
        mov     ecx, eax
        sub     ecx, esi                /* dwords from edi to the end of the used pool */
        jle     1f
        lea     esi, [edi+ecx*4-4]
        lea     edi, [edi+ecx*4]
        std
        rep movsd
        cld
1:      pop     edi
        mov     esi, [ROSTER]
        mov     ecx, [esi]
        mov     edx, [esi+4]
2:      test    ecx, ecx
        jle     4f
        cmp     [edx+0x2C], edi
        jbe     3f
        add     dword ptr [edx+0x2C], 4
3:      add     edx, 0x54
        dec     ecx
        jmp     2b
4:      inc     dword ptr [esi+0x40]
        mov     eax, 1
        pop     esi
        ret

/* ---- site B: the full-pool path of 0x14F220 (pool used >= capacity) -> eax 1 room for the write, 0 none ------- */
        .section .site_b, "ax"
        .globl gc_chunk
gc_chunk:
        pushad
        push    dword ptr [CLASS]
        mov     dword ptr [CLASS], 0
        push    1
        call    compact                 /* deleted words first (the offseason's postseason wipe, retirements) */
        call    MAXAGE
        mov     ebx, eax
1:      call    CAPACITY
        mov     ecx, [ROSTER]
        sub     eax, CHUNK
        cmp     [ecx+0x40], eax
        jle     2f                      /* 6,000 words free: done */
        cmp     ebx, MIN_DEPTH
        jl      2f                      /* never into the last or the current season */
        push    ebx
        call    fold
        dec     ebx
        jmp     1b
2:      pop     dword ptr [CLASS]
        call    CAPACITY
        mov     ecx, [ROSTER]
        xor     edx, edx
        cmp     [ecx+0x40], eax
        setl    dl
        mov     [esp+28], edx           /* pushad's eax */
        popad
        ret

/* ---- site C: compaction (stdcall, 1 ignored argument, ret 4; eax 1 when it removed a word) and helpers -------- */
        .section .site_c, "ax"
        .globl compact
compact:
        push    ebp
        push    ebx
        push    esi
        push    edi
        sub     esp, 520                /* [esp] u16 deleted-before table per 256-word block, [esp+512] used */
        mov     eax, [ROSTER]
        mov     ecx, [eax+0x40]
        mov     esi, [eax+0x44]
        test    ecx, ecx
        jle     .Lc_none
        cmp     ecx, 0x10000
        ja      .Lc_none
        mov     [esp+512], ecx
        xor     edx, edx                /* deleted so far */
        xor     ebx, ebx                /* word index */
.Lc_p1: test    bl, bl
        jnz     1f
        mov     edi, ebx
        shr     edi, 8
        mov     [esp+edi*2], dx
1:      test    dword ptr [esi+ebx*4], DELETED
        jz      2f
        inc     edx
2:      inc     ebx
        cmp     ebx, ecx
        jb      .Lc_p1
        test    edx, edx
        jz      .Lc_none
        mov     ebp, edx                /* total deleted */
        mov     eax, [ROSTER]
        mov     ecx, [eax]
        mov     ebx, [eax+4]
.Lc_p2: test    ecx, ecx
        jle     .Lc_p3
        mov     eax, [ebx+0x2C]
        sub     eax, esi
        jb      .Lc_nx                  /* null or below the pool */
        shr     eax, 2
        cmp     eax, [esp+512]
        jae     .Lc_nx                  /* not in the used pool */
        mov     edx, eax                /* a stream that starts on a deleted word must still hold a live one */
3:      mov     edi, [esi+edx*4]
        test    edi, DELETED
        jz      4f
        test    edi, edi
        js      .Lc_empty               /* deleted to its end word: no live word left */
        inc     edx
        cmp     edx, [esp+512]
        jb      3b
.Lc_empty:
        mov     dword ptr [ebx+0x2C], 0
        jmp     .Lc_nx
4:      mov     edx, eax
        shr     edx, 8
        movzx   edi, word ptr [esp+edx*2]
        shl     edx, 8
5:      cmp     edx, eax
        jae     6f
        test    dword ptr [esi+edx*4], DELETED
        jz      7f
        inc     edi
7:      inc     edx
        jmp     5b
6:      shl     edi, 2
        sub     [ebx+0x2C], edi
.Lc_nx: add     ebx, 0x54
        dec     ecx
        jmp     .Lc_p2
.Lc_p3: mov     ecx, [esp+512]           /* slide the live words down */
        xor     edx, edx
        mov     edi, esi
        xor     ebx, ebx                /* 1 while the last word kept is a live word without the end bit */
8:      mov     eax, [esi+edx*4]
        test    eax, DELETED
        jnz     10f
        mov     [edi], eax
        add     edi, 4
        xor     ebx, ebx
        test    eax, eax
        js      9f
        inc     ebx
        jmp     9f
10:     test    eax, eax                /* a deleted end word after live words of its stream: the last of them */
        jns     9f                      /* ends the stream now (the game's delete keeps this so; a stream that */
        test    ebx, ebx                /* missed it would otherwise run on into the next one) */
        jz      9f
        or      dword ptr [edi-4], 0x80000000
        xor     ebx, ebx
9:      inc     edx
        cmp     edx, ecx
        jb      8b
        mov     eax, [ROSTER]
        sub     [eax+0x40], ebp
        mov     eax, 1
        jmp     .Lc_out
.Lc_none:
        xor     eax, eax
.Lc_out:
        add     esp, 520
        pop     edi
        pop     esi
        pop     ebx
        pop     ebp
        ret     4

/* delete_at: ecx = player, eax = live word* in his stream. Marks it deleted; when it ended the stream the last live
   word before it ends it now, or the stream is empty (pointer 0). Keeps every register but eax and ecx. */
        .globl delete_at
delete_at:
        push    edx
        mov     edx, [eax]
        or      edx, DELETED
        mov     [eax], edx
        test    edx, edx
        jns     3f
        mov     edx, [ecx+0x2C]
1:      cmp     eax, edx
        jbe     2f
        sub     eax, 4
        test    dword ptr [eax], DELETED
        jnz     1b
        or      dword ptr [eax], 0x80000000
        jmp     3f
2:      mov     dword ptr [ecx+0x2C], 0
3:      pop     edx
        ret

/* room: -> eax 1 the pool has room, 2 it has room after a compaction (words moved), 0 it is full. Keeps ebx, esi,
   edi, ebp. */
        .globl room
room:
        call    CAPACITY
        mov     ecx, [ROSTER]
        cmp     [ecx+0x40], eax
        jl      1f
        push    eax
        push    0
        call    compact
        pop     ecx
        mov     edx, [ROSTER]
        cmp     [edx+0x40], ecx
        jl      2f
        xor     eax, eax
        ret
1:      mov     eax, 1
        ret
2:      mov     eax, 2
        ret

/* ---- site D: fold(depth), stdcall ret 4: every live word of the current class at least `depth` seasons old merges
   one slot up (sum, or max where the rule table says so), the retail order (restart from the stream head after each
   merge). A sum the 16-bit cell cannot hold is not merged: that word stays, so the career total stays whole.
   Returns 1 when the pool shrank. Locals: [esp] player index, [esp+4] used at entry, [esp+8] player,
   [esp+12] years pro, [esp+16] new value; the depth is [esp+40]. */
        .section .site_d, "ax"
        .globl fold
fold:
        push    ebp
        push    ebx
        push    esi
        push    edi
        sub     esp, 20
        mov     eax, [ROSTER]
        mov     ecx, [eax+0x40]
        mov     [esp+4], ecx
        mov     dword ptr [esp], 0
.Lf_player:
        mov     eax, [ROSTER]
        mov     ecx, [esp]
        cmp     ecx, [eax]
        jge     .Lf_done
        imul    ecx, ecx, 0x54
        add     ecx, [eax+4]
        mov     [esp+8], ecx
        mov     edx, [ecx+0x24]
        shr     edx, 8
        and     edx, 31
        mov     [esp+12], edx
.Lf_restart:
        mov     eax, [esp+8]
        mov     esi, 0xFF
        mov     edx, esi
        call    FIRST
.Lf_word:
        test    eax, eax
        jz      .Lf_nextplayer
        mov     ebx, eax                /* ebx = this word */
        mov     ecx, [ebx]
        mov     edi, ecx
        shr     edi, 23
        and     edi, 31                 /* slot */
        mov     edx, [esp+12]
        sub     edx, edi                /* age in seasons */
        cmp     edx, [esp+40]
        jl      .Lf_advance
        shr     ecx, 16
        and     ecx, 127
        mov     esi, ecx                /* field */
        inc     edi                     /* the slot it merges into */
        push    edi
        mov     ecx, [esp+12]
        mov     edx, esi
        call    FIND
        mov     ebp, eax                /* ebp = the receiving word or 0 */
        xor     ecx, ecx
        test    eax, eax
        jz      1f
        movsx   ecx, word ptr [eax]
1:      movsx   edx, word ptr [ebx]
        cmp     esi, 87
        jae     .Lf_sum                 /* TEAM and the added fields (honors, pressure counters) sum */
        push    ecx
        push    edx
        call    RULE
        pop     edx
        pop     ecx
        test    eax, eax
        jnz     .Lf_sum
        cmp     ecx, edx
        jge     .Lf_have_value
        mov     ecx, edx
        jmp     .Lf_have_value
.Lf_sum:
        add     ecx, edx
        lea     eax, [ecx+0x8000]
        cmp     eax, 0xFFFF
        ja      .Lf_advance             /* would wrap: keep this word as it is */
.Lf_have_value:
        mov     [esp+16], ecx
        test    ebp, ebp
        jnz     .Lf_existing
        test    ecx, ecx
        jz      .Lf_drop_source
        call    room
        test    eax, eax
        jz      .Lf_advance             /* no room for the new word: leave this one */
        cmp     eax, 2
        je      .Lf_restart             /* the compaction moved the words: find it again */
        mov     ecx, [esp+8]
        mov     eax, ebx
        call    delete_at
        mov     edx, edi
        shl     edx, 7
        or      edx, esi
        shl     edx, 16
        movzx   eax, word ptr [esp+16]
        or      edx, eax
        or      edx, FOLDED
        mov     ecx, [esp+8]
        call    APPEND
        jmp     .Lf_restart
.Lf_existing:
        test    ecx, ecx
        jnz     2f
        mov     ecx, [esp+8]
        mov     eax, ebp
        call    delete_at
        jmp     .Lf_drop_source
2:      mov     eax, [ebp]
        and     eax, 0xFFFF0000
        movzx   ecx, cx
        or      eax, ecx
        or      eax, FOLDED
        mov     [ebp], eax
.Lf_drop_source:
        mov     ecx, [esp+8]
        mov     eax, ebx
        call    delete_at
        jmp     .Lf_restart
.Lf_advance:
        mov     eax, ebx
        mov     esi, 0xFF
        mov     edx, esi
        call    NEXT
        jmp     .Lf_word
.Lf_nextplayer:
        inc     dword ptr [esp]
        jmp     .Lf_player
.Lf_done:
        push    0
        call    compact
        mov     eax, [ROSTER]
        mov     ecx, [eax+0x40]
        xor     eax, eax
        cmp     [esp+4], ecx
        seta    al
        add     esp, 20
        pop     edi
        pop     esi
        pop     ebx
        pop     ebp
        ret     4

/* ---- site E: the rule-table load at 0x14F168 (7 bytes, retail or the honors owner's) returns here ------------ */
        .section .site_e, "ax"
        ret

/* ---- site F: inside 0x14F220, where retail starts its full-pool path (push 1 / call 0x14E9D0) ---------------- */
        .section .site_f, "ax"
        call    gc_chunk
        test    eax, eax
        jne     0x0014F2BB              /* retail's write path */
        pop     edi
        pop     esi
        pop     ebp
        pop     ecx
        ret
