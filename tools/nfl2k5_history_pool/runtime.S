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
     site G 0x14F239  the writer's capacity call -> reserve_cap (b81 playoff reserve)
     site H 0x14EDA8  the end of 0x14ED90 (delete a man's words of the current class) -> rollover_tail (b81)
     site I 0x14F170  the retail fold's dead tail (site D ends the fold before it): age_ok, folded_age2, rollover_tail
   gc_chunk folds whole season levels, oldest first, until 6,000 words are free, never at depth < 3 (the current
   and the last season are never folded), so a full pool collects once per ~6,000 writes, not on every write.

   b81 history-pool (Noah 11/23: "fix the history storage for franchise now"): when that leaves the pool still full
   (every word in the current, the last or the folded career season, the case that dropped Trey Smack's 52-yard
   attempt in seed 68003's 2029), gc_chunk folds the last season into the career row for the men on the game's
   free-agent list only (fa_fold, fold with depth -2, fold_base) before the write is dropped. Club men (active list,
   injured reserve, practice squad) keep their last season. Nothing changes while depth 3+ leaves the write room: the
   extra test reads the pool and the capacity only, so a franchise that never reaches this point is byte-identical.
   A write that still finds no room is dropped at history_drop (0x14F256), as before.

   b81 playoff reserve (coordinator's ruling on the history-pool report, 11/24: permanent honors outrank playoff stat
   words, which the offseason rollover wipes anyway): a new playoff word (postseason class, [CLASS] 1, while the
   franchise stage [0xE576A4] is 9, the playoffs) may not take one of the last RESERVE (512) words. The writer's
   capacity test (site G) uses reserve_cap, so such a word reaches gc_chunk 512 words before the pool is full; gc_chunk
   runs the same depth 3+ collection v0.9 runs at the full pool, and keeps the word only if RESERVE words stay free.
   Preseason games write the postseason class too (stage 7, about 20,000 words a season, wiped when the regular season
   starts); they see the whole capacity, as in v0.9, because they are not playoff words and filling the pool with them
   is what triggers v0.9's yearly collection (a first panel that held them to the reserve left the franchise on another
   path from the 2027 preseason on). No postseason-class word, in any stage, runs the free-agent resort. Regular-class
   writes (every season stat, the season honors, the next season's words) see the whole capacity, exactly as before.

   b81 playoff fold (coordinator's second ruling, 11/24: keep the playoff stats too). A playoff word that still finds
   no room outside the reserve after the depth 3+ collection runs fold(PLAYOFF_FOLD): every man's career row (2 seasons
   back) merges into his last season, which is the merge v0.9's own first collection of the next preseason makes (then
   at depth 3), only earlier, and it frees a playoffs' worth of words (11,547 on the stored full 68001/2032 pool). It
   leaves alone the fields the Studio's season close reads per season (nfl2k5_history read_career: games 0, club 87 and
   the ten leader fields 2, 3, 8, 9, 12, 13, 14, 18, 19, 20), so the close, which runs after the playoffs and before
   the rollover, counts each man's last season, club and seasons exactly as with v0.9's bytes. At the rollover's
   postseason wipe (0x247B40 calls 0x14ED90 with class 1 for every player, the first record first, years pro already
   advanced; rollover_tail knows it by its return address) finishes the merge for every man folded early (a FOLDED
   word two seasons back):
   fold(COMPLETE_FOLD) merges what is older into it, as v0.9's next preseason collection would. It does nothing when no
   man was folded early, so a franchise whose playoffs never fill the pool is byte-identical. The free-agent resort
   runs only in stages 8-9 (never in the preseason, after the rollover, where the star career reads the season just
   played).

   Round 4 (coordinator's third ruling, 11/24): the playoff fold folds only as much as the playoffs need, free agents
   first (fa_fold), then every man in record order until PLAYOFF_ROOM words are free besides the reserve
   (playoff_fold in site F's tail, playoff_staged in site A's, playoff_target in site J); a second playoff word that
   finds the pool short again folds on. Every early fold leaves the honors fields 96-105 alone, and the free-agent resort
   and the playoff fold leave the close's fields. */
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
        .set FA_DEPTH2, -2             /* fold(-2): depth 2, men on the free-agent list only (fold_base) */
        .set PLAYOFF_FOLD, -3          /* fold(-3): depth 2, every man, but the season close's fields (age_ok) */
        .set PLAYOFF_ROOM, 4096        /* round 4: the playoff fold stops once this much is free besides the reserve */
        .set HONORS_FIRST, 96          /* round 4: the honors fields 96-105 stay out of every early fold */
        .set HONORS_COUNT, 10
        .set COMPLETE_FOLD, -4         /* fold(-4): depth 3 for a man folded early this season (folded_age2) */
        .set NO_FOLD_BASE, -0x40       /* fold_base for a man a negative depth does not touch: no word passes age_ok */
        .set CLOSE_FIELDS, 0x001C730D  /* fields 0, 2, 3, 8, 9, 12, 13, 14, 18, 19, 20 (and FIELD_TEAM): read per season */
        .set FIELD_TEAM, 87
        .set ROLLOVER_WIPE, 0x00247C82 /* 0x247B40's postseason wipe: the instruction after its call of 0x14ED90 */
        .set FA_PLAYERS, 4096          /* the free-agent bitmap's bits: the capacity arena's 4,096 primary records */
        .set RESERVE, 512              /* words a playoff (postseason-class) word may not take: kept for permanent words */
        .set STAGE,    0x00E576A4      /* franchise stage: 7 preseason, 8 regular season, 9 playoffs */
        .set PLAYOFFS, 9

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

/* reserve_cap (b81 history-pool, playoff reserve; in site A's tail): eax = the words a new word of the current class
   may fill: the capacity, less RESERVE for a playoff word (postseason class [CLASS] 1 in stage 9). The writer's
   capacity test (site G, 0x14F239) and gc_chunk's room test call it in place of CAPACITY; like CAPACITY it clobbers
   ecx and edx. */
        .globl reserve_cap
reserve_cap:
        call    CAPACITY
        cmp     dword ptr [CLASS], 0
        je      1f
        cmp     dword ptr [STAGE], PLAYOFFS
        jne     1f                      /* preseason words see the whole pool, as in v0.9 */
        sub     eax, RESERVE
1:      ret

/* playoff_staged (round 4; reached from playoff_fold in site F after the free agents): fold(PLAYOFF_FOLD) down to
   PLAYOFF_ROOM words free besides the reserve. fold_base asks playoff_target before each man; the target (the used
   count to reach) sits right above fold's argument. A second playoff word that finds the pool short again folds on from
   where this stopped (the men already folded have nothing left to merge). */
        .globl playoff_staged
playoff_staged:
        call    CAPACITY
        sub     eax, RESERVE + PLAYOFF_ROOM
        push    eax
        push    PLAYOFF_FOLD
        call    fold
        pop     eax
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
2:      call    CAPACITY
        mov     ecx, [ROSTER]
        mov     edx, [STAGE]
        sub     edx, 8
        cmp     dword ptr [esp], 0
        je      3f
        sub     eax, RESERVE            /* a postseason-class word: room means RESERVE words left free */
        cmp     [ecx+0x40], eax
        jl      4f
        dec     edx
        jnz     4f                      /* a playoff word (stage 9) only; preseason words are dropped as in v0.9 */
        call    playoff_fold            /* round 4: free agents first, then the rest, only as far as the playoffs need */
        nop
        nop
        jmp     4f
3:      cmp     [ecx+0x40], eax
        jl      4f                      /* the write has room: as before */
        cmp     edx, 1
        ja      4f                      /* stages 8 and 9 only: never in the preseason or the offseason */
        call    fa_fold                 /* last resort: the free agents' last season into their career row */
4:      pop     dword ptr [CLASS]
        call    reserve_cap             /* room for this class: a playoff word must leave RESERVE words free */
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
   edi, ebp. b81: under the free-agent resort and the playoff fold a full pool answers 0 without a compaction (measured on the stored 68001/2032 image:
   a write into a pool that stays full compacted 109 times, against 3 in v0.9, retrying the same unmovable words). */
        .globl room
room:
        call    CAPACITY
        mov     ecx, [ROSTER]
        cmp     [ecx+0x40], eax
        jl      1f
        cmp     dword ptr [esp+44], COMPLETE_FOLD   /* b81: fold's depth (only fold calls room). The rollover's */
        je      4f                      /* completion compacts for a move like any fold; the free-agent resort and */
        cmp     dword ptr [esp+44], 0   /* the playoff fold (negative) compact nothing for a move, which frees */
        jl      3f                      /* nothing: the word stays, as here */
4:
        push    eax
        push    0
        call    compact
        pop     ecx
        mov     edx, [ROSTER]
        cmp     [edx+0x40], ecx
        jl      2f
3:      xor     eax, eax
        ret
1:      mov     eax, 1
        ret
2:      mov     eax, 2
        ret

/* fold_base (b81 history-pool): ecx = player record, called by fold for each player; stores the base fold's age test
   (age_ok) compares with each word's slot into fold's [esp+12] ([esp+16] here; fold's player index is [esp+4] here,
   its depth argument [esp+44]): a word merges when base - slot >= 0. Depth >= 0: years pro - depth (the hist1 rule).
   FA_DEPTH2 (fa_fold): years pro - 2 for a man on the game's free-agent list (one bit of the bitmap fa_fold keeps right
   above fold's argument, [esp+48] here, by player index), nobody else. PLAYOFF_FOLD: years pro - 2 for every man
   (age_ok keeps the season close's fields). COMPLETE_FOLD (rollover_tail): years pro - 3 for a man with a FOLDED word
   two seasons back (folded early this season), nobody else. A man not folded gets NO_FOLD_BASE and eax 0, on which
   fold goes straight to the next man. Returns eax 1 to walk the man. Keeps ebx, ecx, esi, edi, ebp. */
        .globl fold_base
fold_base:
        mov     edx, [ecx+0x24]
        shr     edx, 8
        and     edx, 31                 /* years pro */
        mov     eax, [esp+44]
        test    eax, eax
        jns     5f
        add     eax, 2
        jnz     3f
        mov     eax, [esp+4]            /* FA_DEPTH2 */
        cmp     eax, FA_PLAYERS
        jae     1f
        bt      dword ptr [esp+48], eax
        jnc     1f
4:      dec     edx
        dec     edx                     /* depth 2 */
        jmp     6f
3:      inc     eax
        jnz     7f
        call    playoff_target          /* PLAYOFF_FOLD: every man until the room is there */
        jc      1f
        jmp     4b
7:      call    folded_age2             /* COMPLETE_FOLD */
        test    eax, eax
        jz      1f
        sub     edx, 3                  /* depth 3: the rest of his career row into the row folded early */
        jmp     6f
5:      sub     edx, eax
6:      mov     [esp+16], edx
        xor     eax, eax
        inc     eax
        ret
1:      mov     dword ptr [esp+16], NO_FOLD_BASE
        xor     eax, eax
        ret

/* ---- site D: fold(depth), stdcall ret 4: every live word of the current class at least `depth` seasons old merges
   one slot up (sum, or max where the rule table says so), the retail order (restart from the stream head after each
   merge). A sum the 16-bit cell cannot hold is not merged: that word stays, so the career total stays whole.
   Returns 1 when the pool shrank. Locals: [esp] player index, [esp+4] used at entry, [esp+8] player,
   [esp+12] fold_base's base (a word merges when base - slot >= 0), [esp+16] new value; the depth is [esp+40]. */
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
        call    fold_base               /* [esp+12]: years pro (b81: or the free-agent rule of a negative depth) */
        test    eax, eax                /* 0: a man a negative depth does not fold (8 bytes with the jump: the rest of */
        jz      .Lf_nextplayer          /* the fold keeps its addresses) */
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
        shr     ecx, 16
        and     ecx, 127
        mov     esi, ecx                /* field */
        call    age_ok                  /* b81: the age test against fold_base's base, and the playoff fold's fields */
        test    eax, eax
        js      .Lf_advance
        .byte   0x0F, 0x1F, 0x00        /* nop: every later instruction keeps its address */
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

/* ---- site G (b81 playoff reserve): the writer's capacity test, 0x14F239 (retail `call 0x14E7E0`): the limit a new
   word of the current class may fill, so a playoff word that would take one of the last RESERVE words goes to the
   full-pool path (gc_chunk refuses it there) ----------------------------------------------------------------------- */
        .section .site_g, "ax"
        call    reserve_cap

/* ---- site H (b81 playoff fold): 0x14EDA8, the end of 0x14ED90 (delete every word of a man in the current class;
   retail `mov eax, 1`): rollover_tail, which returns 1 ------------------------------------------------------------ */
        .section .site_h, "ax"
        call    rollover_tail

/* ---- site I (b81 playoff fold): 0x14F170, the retail fold's dead tail (site D ends the fold at 0x14F166 and site E
   returns before this) ------------------------------------------------------------------------------------------- */
        .section .site_i, "ax"
/* age_ok: fold's age test (called from its word loop: esi = field, edi = slot; fold's base is [esp+16] here, its
   depth [esp+44]) -> eax >= 0 merge the word, < 0 leave it. Every negative depth (the free-agent resort, the playoff
   fold, the rollover's completion) leaves the honors fields 96-105 (round 4: the honors card's year list stays right;
   the next preseason collection, fold(3), merges them as in v0.9). The free-agent resort and the playoff fold also
   leave the fields the season close reads per season (CLOSE_FIELDS, FIELD_TEAM): a free agent a club signs before the
   close is read by it too. Keeps every register but eax and edx. */
        .globl age_ok
age_ok:
        mov     eax, [esp+16]
        sub     eax, edi
        js      2f                      /* younger than the depth */
        cmp     dword ptr [esp+44], 0
        jge     2f                      /* a collection (depth 3+): every field */
        lea     edx, [esi-HONORS_FIRST]
        cmp     edx, HONORS_COUNT - 1
        jbe     1f                      /* the honors */
        cmp     dword ptr [esp+44], COMPLETE_FOLD
        je      2f                      /* the completion merges the close's fields (after the close) */
        cmp     esi, FIELD_TEAM
        je      1f
        cmp     esi, 31
        ja      2f
        mov     eax, CLOSE_FIELDS
        bt      eax, esi
        sbb     eax, eax                /* -1 for a close field, 0 to merge */
        ret
1:      or      eax, -1
2:      ret

/* folded_age2: ecx = player -> eax nonzero when a live regular-class word of his two seasons back is FOLDED (a man
   folded early this season, after the rollover advanced his years pro; v0.9 folds only into three seasons back by
   then). Keeps every register but eax. */
        .globl folded_age2
folded_age2:
        push    esi
        push    ebx
        mov     ebx, [ecx+0x24]
        shr     ebx, 8
        and     ebx, 31
        sub     ebx, 2
        shl     ebx, 23
        bts     ebx, 30                 /* the pattern: FOLDED, live, regular class, that slot (none for a rookie) */
        mov     esi, [ecx+0x2C]
        xor     eax, eax
        test    esi, esi
        jz      3f
1:      mov     eax, [esi]
        add     esi, 4
        push    eax
        and     eax, 0x7F800000
        cmp     eax, ebx
        pop     eax
        je      3f
        test    eax, eax
        jns     1b                      /* until the end word */
        xor     eax, eax
3:      pop     ebx
        pop     esi
        ret

/* rollover_tail (site H): at the rollover's postseason wipe (0x14ED90 called from 0x247C7D, so its return address
   [esp+8] here is ROLLOVER_WIPE; class 1, stage still 9, the first record: 0x247B40 walks every record from index 0
   after advancing years pro, and the season close has run), when any man was folded early this season,
   fold(COMPLETE_FOLD) in the regular class. The call site, not the class, tells the rollover from the retirement pass's
   record resets (0x2BDB00 -> 0x2BDA90 -> 0xE64D0 -> 0x14ED90 with class 1, also in stage 9 but before the close).
   Returns eax 1 (0x14ED90's result). */
        .globl rollover_tail
rollover_tail:
        cmp     dword ptr [esp+8], ROLLOVER_WIPE
        jne     9f                      /* (0x247B40 runs only when the franchise leaves stage 9) */
        mov     eax, [ROSTER]
        cmp     esi, [eax+4]
        jne     9f
        pushad
        mov     ebp, [eax]
        mov     ecx, esi
1:      dec     ebp
        js      8f                      /* nobody folded early: nothing to do */
        call    folded_age2
        add     ecx, 0x54
        test    eax, eax
        jz      1b
        dec     dword ptr [CLASS]       /* 1 -> 0: the wipe set class 1 (0x247C41) */
        push    COMPLETE_FOLD
        call    fold
        inc     dword ptr [CLASS]       /* back to 1: the wipe set it (0x247C41) */
8:      popad
9:      mov     eax, 1
        ret

/* ---- site J (round 4): 0x14EFB0..0x14EFDF, the second half of a retail routine nothing calls (0x14EF90, a club's sum
   over a past period, the twin of 0x14EF50: no call, jump or pointer to it in the retail or any built executable). Its
   first 32 bytes stay retail: nfl2k5_star_career pins 0x14EF20..0x14EFAF. --------------------------------------------- */
        .section .site_j, "ax"
/* playoff_target: fold_base's question for the playoff fold (fold's player index is [esp+8] here, the target
   [esp+52]) -> CF 1 stop (fold no more men), 0 fold this one. Every 64th man it compacts (the merges so far only marked
   words deleted) and stops once the used count is at the target; then it zeroes the target, so every later man of this
   walk stops at once. Keeps every register but eax and the flags. */
        .globl playoff_target
playoff_target:
        cmp     dword ptr [esp+52], 0
        je      8f
        test    byte ptr [esp+8], 63
        jnz     9f
        push    ecx
        push    edx
        push    0
        call    compact
        pop     edx
        pop     ecx
        mov     eax, [ROSTER]
        mov     eax, [eax+0x40]
        cmp     eax, [esp+52]
        ja      9f
        and     dword ptr [esp+52], 0
8:      stc
        ret
9:      clc
        ret

/* ---- site F: inside 0x14F220, where retail starts its full-pool path (push 1 / call 0x14E9D0) ---------------- */
        .section .site_f, "ax"
        call    gc_chunk
        test    eax, eax
        jne     0x0014F2BB              /* retail's write path */
        .globl history_drop
history_drop:                           /* 0x14F256: the full pool has no room even after the last resort */
        pop     edi
        pop     esi
        pop     ebp
        pop     ecx
        ret

/* fa_fold (b81 history-pool, in the dead tail of retail's full-pool path, 0x14F25B..0x14F2B6): called by gc_chunk
   (inside its pushad, class 0) when depth 3+ left the pool full. Marks the game's free-agent list (root+0x38 count,
   root+0x3C list of player pointers) in a FA_PLAYERS-bit bitmap on the stack, by player index (a pointer that is not a
   primary record start below FA_PLAYERS is left out), then runs fold(-2), whose fold_base reads the bitmap: one bit
   test per player instead of a walk of the list. Clobbers every register but esp (gc_chunk restores them). */
        .globl fa_fold
fa_fold:
        sub     esp, FA_PLAYERS / 8
        mov     edi, esp
        xor     eax, eax
        mov     ecx, FA_PLAYERS / 32
        rep stosd
        mov     esi, [ROSTER]
        mov     ecx, [esi+0x38]
        mov     ebx, [esi+0x3C]
        mov     esi, [esi+4]
        mov     ebp, 0x54
1:      dec     ecx
        js      2f
        mov     eax, [ebx+ecx*4]
        sub     eax, esi
        jb      1b
        xor     edx, edx
        div     ebp
        test    edx, edx
        jnz     1b
        cmp     eax, FA_PLAYERS
        jae     1b
        bts     dword ptr [esp], eax
        jmp     1b
2:      push    FA_DEPTH2
        call    fold
        add     esp, FA_PLAYERS / 8
        ret

/* playoff_fold (round 4): gc_chunk (class 0) for a playoff word that has no room outside the reserve: the free agents
   first (fa_fold: their last season into their career row, but the close's fields and the honors), then the rest only
   as far as the playoffs need (playoff_staged, site A). */
        .globl playoff_fold
playoff_fold:
        call    fa_fold
        jmp     playoff_staged
