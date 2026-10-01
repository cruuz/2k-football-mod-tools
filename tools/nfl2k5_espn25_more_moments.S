/* EXPERIMENTAL / UNWITNESSED. ESPN 25th Anniversary: 25 more moments (rows 26 to 50).
 *
 * The moment select handler 20CB30 finds each side's historic team with 20BD80 (name on the stack, season in
 * EBX; it scans the roster's historic list, count at root+0x58, 16-byte entries at root+0x5C) and loads it with
 * 2D17B0 (ECX = the entry index). New moments name team-seasons that are not in the roster's list. They live in a
 * moment-only table in this allocation (same 16-byte entry format: u16 season, u8 file number, u16 code text at
 * +4, name pointer at +0xC), so the roster block does not grow.
 *   search:    20BD80 checks the moment table first; a hit returns 0x10000 + k. Otherwise the retail search runs.
 *   load_team: the two calls of 2D17B0 in 20CB30 (20CBAA, 20CBD5). A moment-table index points the roster's
 *              historic list (root+0x58, root+0x5C) at the moment table for the duration of the retail loader
 *              call and restores it; any other index calls 2D17B0 unchanged. 2D17B0 itself is not modified.
 *   mark_set:  a won moment's mark (20C695). Rows 1 to 32 keep the saved dword [BF18CC] (bits 25 to 31 were
 *              never used by retail); rows 33 to 50 go to a session dword that is never saved.
 *   venue_name: the details screen's venue line (the call of 77460 at 2C5A71 inside the text callback 2C5A70,
 *              which formats the first dword of what 77460 returns). A new row with a venue text gets a cell
 *              holding that text; every other row gets 77460's stadium record, as retail. Display only: the
 *              selected stadium [E5FE64] and its record are not touched.
 * The count (20C340), the completion test (20C390) and the announcer guard (20C4A1) are in-place edits.
 */
.intel_syntax noprefix
.code32
.text
.global search, load_team, mark_set, venue_name
.extern table, team_count, name_equal, search_resume, historic_load, after_set, session
.extern venue_table, venue_count, stadium_get

.set ROOT, 0xb72918              /* roster root pointer */
.set HCOUNT, 0x58                /* root: historic entry count */
.set HTABLE, 0x5c                /* root: historic entries, 16 bytes each */
.set MOMENT_INDEX, 0xbf1858      /* the selected moment */
.set MASK, 0xbf18cc              /* completed moments, saved in the profile */
.set MOMENT_BASE, 0x10000        /* first moment-table index */

/* ---- 20BD80: find (name, season); [esp+4] = name, EBX = season, returns the entry index or -1 (ret 4) ----
 * Only the select handler 20CB30 calls 20BD80 (20CB9C, 20CBC7), after it stores the moment index. Rows 1 to 25
 * keep the retail search, so a retail moment whose team-season is also a new one (A YARD TOO SHORT's Titans '99,
 * VINATIERI STRIKES AGAIN's Patriots '01) still loads its retail file. */
search:
    cmp dword ptr [MOMENT_INDEX], 25
    jb search_plain
    push esi
    push edi
    push ebp
    mov ebp, [esp + 16]          /* the name */
    xor edi, edi
search_next:
    cmp edi, OFFSET team_count
    jae search_retail
    mov esi, edi
    shl esi, 4
    add esi, OFFSET table
    movzx eax, word ptr [esi]
    cmp ebx, eax
    jne search_skip
    mov edx, [esi + 12]
    mov ecx, ebp
    call name_equal              /* 30CF0: nonzero when the texts match, as the retail loop uses it */
    test eax, eax
    jne search_hit
search_skip:
    inc edi
    jmp search_next
search_hit:
    lea eax, [edi + MOMENT_BASE]
    pop ebp
    pop edi
    pop esi
    ret 4
search_retail:
    pop ebp
    pop edi
    pop esi
search_plain:
    mov ecx, [ROOT]              /* the replaced first instruction of 20BD80 */
    jmp search_resume            /* 20BD86 */

/* ---- 20CBAA and 20CBD5: ECX = the entry index, EDX = the other side's team (the 2D17B0 arguments) ---- */
load_team:
    cmp ecx, MOMENT_BASE
    jb load_retail
    push esi
    mov esi, [ROOT]
    push dword ptr [esi + HCOUNT]
    push dword ptr [esi + HTABLE]
    mov dword ptr [esi + HCOUNT], OFFSET team_count
    mov dword ptr [esi + HTABLE], OFFSET table
    sub ecx, MOMENT_BASE
    call historic_load           /* 2D17B0, retail: loads entry ECX of the list into a spare slot */
    mov esi, [ROOT]
    pop dword ptr [esi + HTABLE]
    pop dword ptr [esi + HCOUNT]
    pop esi
    ret
load_retail:
    jmp historic_load

/* ---- 20C695: mark the won moment ---- */
mark_set:
    mov ecx, [MOMENT_INDEX]
    mov eax, 1
    shl eax, cl                  /* 1 << (index & 31) */
    cmp ecx, 32
    jae mark_high
    or [MASK], eax
    jmp after_set                /* 20C6A8 */
mark_high:
    or [session], eax
    jmp after_set

/* ---- 2C5A71: the details screen's venue text; returns EAX = a cell whose first dword is the text ---- */
venue_name:
    mov eax, [MOMENT_INDEX]
    sub eax, 25                  /* rows 26 to 50 are indexes 25 to 49 */
    jb venue_retail
    cmp eax, OFFSET venue_count
    jae venue_retail
    lea eax, [eax * 4 + venue_table]
    cmp dword ptr [eax], 0
    je venue_retail
    ret
venue_retail:
    jmp stadium_get              /* 77460: the selected stadium record, whose first dword is its name */
