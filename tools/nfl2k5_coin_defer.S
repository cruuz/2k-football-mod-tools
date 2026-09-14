/* CPU-only deferral: the two-row retail menu cannot hold a third/fourth row.
 * Actual toss winner B72684 is preserved. C39188 is the menu's choice parity;
 * winner_result restores its original interpretation for the result consumer.
 */
.intel_syntax noprefix
.code32
.text
.global choose, menu, halftime, winner_result
.extern state, notice, choose_tail, native_menu, native_possession
.extern human_query, random_word, home_name, away_name
choose:
    pushfd
    push ecx
    push edx
    push eax
    mov dword ptr [state], 0
    cmp dword ptr [0xe602c4], 1
    jne original
    cmp dword ptr [0xe602b4], 0
    jne original
    call human_query                 /* EDI is native side 1/2; EAX != 0 human */
    test eax, eax
    jnz original
draw:
    mov ecx, 0xe5fca0
    call random_word
    cmp eax, -1                      /* 2^32 - 1 is divisible by 17 */
    je draw
    xor edx, edx
    mov ecx, 17
    div ecx
    cmp edx, 15                      /* 240/272 = 15/17; cited 2023 season */
    jae original
    mov [state], esi                 /* original CPU winner, not opening kicker */
    mov esi, [esi]
    mov [0xb72688], esi              /* loser now chooses kick/receive */
    xor dword ptr [0xc39188], 1       /* existing choice/side callbacks follow loser */
    neg edi
    add edi, 3
    cmp edi, 1
    jne away
    call home_name
    jmp name_ready
away:
    call away_name
name_ready:
    mov [esp], eax
original:
    pop eax
    pop edx
    pop ecx
    popfd
    mov ebx, eax
    mov eax, [0xc3918c]
    jmp choose_tail
menu:
    pushfd
    cmp dword ptr [state], 0
    je menu_original
    mov dword ptr [esp+16], offset notice
menu_original:
    popfd
    jmp native_menu
halftime:
    push eax
    cmp dword ptr [0xe602c4], 3
    jne half_original
    mov eax, [state]
    cmp eax, 0xe5fc20
    je half_deferred
    cmp eax, 0xe5fc60
    jne half_original
half_deferred:
    mov ecx, [eax]                   /* CPU chooses receive even if loser kicked H1 */
half_original:
    pop eax
    jmp native_possession
winner_result:
    mov ecx, [0xc3918c]
    mov edx, [0xc39188]
    cmp dword ptr [state], 0
    je result_original
    xor edx, 1
result_original:
    xor eax, eax
    cmp ecx, edx
    sete al
    ret
