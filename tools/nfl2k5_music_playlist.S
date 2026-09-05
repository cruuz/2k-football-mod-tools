/* EXPERIMENTAL / UNWITNESSED. i386 retail register ABI. No audio I/O here.
 * RW: init,n,cursor,last,rng_sample,context,paused,active,pending,replay,
 * current,error,generation,preview; mask[16] at 64, shadow[16] at 80,
 * u16 bag[100] at 96. RO: count at 8, initial mask at 16, records at 192.
 */
.intel_syntax noprefix
.code32
.text
.global init, next_item, enqueue, completion, advance, frame, context, mode
.global suspend, pause, resume, preview
init:
    cmp DWORD PTR [state_data], 0
    jne init_done
    pushad
    mov DWORD PTR [state_data], 1
    mov DWORD PTR [state_data+12], -1
    mov DWORD PTR [state_data+40], -1
    mov DWORD PTR [state_data+20], 1
    mov esi, OFFSET FLAT:playlist_ro+16
    mov edi, OFFSET FLAT:state_data+64
    mov ecx, 4
    cld
    rep movsd
    popad
init_done:
    ret

/* EAX = record ordinal or -1. Preserves all other registers. One refill
 * consumes N-1 calls to the memo's 0x48bc0 RNG. Unsigned modulo contract.
 */
next_item:
    push ebx
    push ecx
    push edx
    push esi
    push edi
    call init
    xor ecx, ecx
mask_check:
    mov eax, DWORD PTR [state_data+64+ecx*4]
    cmp eax, DWORD PTR [state_data+80+ecx*4]
    je mask_same
    mov DWORD PTR [state_data+80+ecx*4], eax
    mov DWORD PTR [state_data+4], 0
    mov DWORD PTR [state_data+8], 0
mask_same:
    inc ecx
    cmp ecx, 4
    jb mask_check
    mov eax, DWORD PTR [playlist_ro+8]
    cmp eax, 100
    ja no_item
    mov ecx, DWORD PTR [state_data+8]
    cmp ecx, DWORD PTR [state_data+4]
    jb take_item
    xor ebx, ebx
    xor edi, edi
fill:
    cmp edi, DWORD PTR [playlist_ro+8]
    jae filled
    bt DWORD PTR [state_data+64], edi
    jnc omitted
    mov WORD PTR [state_data+96+ebx*2], di
    inc ebx
omitted:
    inc edi
    jmp fill
filled:
    mov DWORD PTR [state_data+4], ebx
    mov DWORD PTR [state_data+8], 0
    test ebx, ebx
    jz no_item
    mov esi, ebx
shuffle:
    cmp esi, 1
    jbe boundary
    call retail_rng
    mov DWORD PTR [state_data+16], eax
    xor edx, edx
    div esi
    dec esi
    mov ax, WORD PTR [state_data+96+esi*2]
    mov cx, WORD PTR [state_data+96+edx*2]
    mov WORD PTR [state_data+96+esi*2], cx
    mov WORD PTR [state_data+96+edx*2], ax
    jmp shuffle
boundary:
    cmp ebx, 1
    jbe take_first
    movzx eax, WORD PTR [state_data+96]
    cmp eax, DWORD PTR [state_data+12]
    jne take_first
    mov cx, WORD PTR [state_data+98]
    mov WORD PTR [state_data+96], cx
    mov WORD PTR [state_data+98], ax
take_first:
    xor ecx, ecx
take_item:
    cmp ecx, 100
    jae no_item
    movzx eax, WORD PTR [state_data+96+ecx*2]
    inc ecx
    mov DWORD PTR [state_data+8], ecx
    cmp eax, DWORD PTR [playlist_ro+8]
    jae no_item
    bt DWORD PTR [state_data+64], eax
    jnc no_item
    mov DWORD PTR [state_data+12], eax
    jmp next_done
no_item:
    mov eax, -1
next_done:
    pop edi
    pop esi
    pop edx
    pop ecx
    pop ebx
    ret

/* Replaces 0x2801a0/0x280450. Validate before binding or queueing. Native
 * packet helpers retain channel, volume, completion event and loop=0 ABI.
 */
enqueue:
    call init
    cmp DWORD PTR [state_data+20], 0
    je enqueue_return
    cmp DWORD PTR [state_data+24], 0
    jne enqueue_return
    cmp DWORD PTR [state_data+28], 0
    jne enqueue_return
    cmp DWORD PTR [state_data+52], 0
    jne enqueue_return
    cmp DWORD PTR [state_data+56], 0
    jne enqueue_return
    push ebp
    mov ebp, esp
    and esp, -8
    sub esp, 0x3ec
    push esi
    cmp DWORD PTR [state_data+36], 0
    je choose_next
    mov eax, DWORD PTR [state_data+40]
    mov DWORD PTR [state_data+36], 0
    cmp eax, DWORD PTR [playlist_ro+8]
    jae choose_next
    bt DWORD PTR [state_data+64], eax
    jc selected
choose_next:
    call next_item
selected:
    mov DWORD PTR [state_data+32], 0
    cmp eax, DWORD PTR [playlist_ro+8]
    jae enqueue_empty
    cmp eax, 100
    jae enqueue_bad
    mov DWORD PTR [state_data+40], eax
    push DWORD PTR [playlist_ro+192+eax*8]
    mov edx, 0x42535541
    xor ecx, ecx
    call resource_lookup
    test eax, eax
    jz enqueue_bad
    cmp eax, -1
    je enqueue_bad
    mov esi, eax
    cmp DWORD PTR [esi+0x40], 65536
    ja enqueue_bad
    cmp DWORD PTR [esi+0x48], 0
    je enqueue_bad
    cmp DWORD PTR [esi+0x4c], 0
    je enqueue_bad
    mov eax, DWORD PTR [state_data+40]
    mov eax, DWORD PTR [playlist_ro+196+eax*8]
    cmp eax, DWORD PTR [esi+0x40]
    jae enqueue_bad
    mov edx, DWORD PTR [esi+eax*4+0x58]
    cmp edx, DWORD PTR [esi+eax*4+0x5c]
    jae enqueue_bad
    push eax
    lea edx, [esp+0x10]
    mov ecx, esi
    call range_copy
    mov edx, esi
    mov ecx, 0xc3cc10
    call bind_bank
    mov ecx, 0xc3cc10
    call stop_stream
    mov DWORD PTR [0xc5d3a4], 1
    mov edx, DWORD PTR [0xc3cc58]
    test edx, edx
    jz packet
    mov ecx, 0xc3cc10
    call bind_volume
packet:
    lea ecx, [esp+0x18]
    call packet_init
    inc DWORD PTR [state_data+48]
    push DWORD PTR [state_data+48]
    mov edx, OFFSET FLAT:completion
    lea ecx, [esp+0x1c]
    call packet_callback
    push 0
    lea edx, [esp+0x10]
    lea ecx, [esp+0x1c]
    call packet_range
    mov DWORD PTR [state_data+28], 1
    mov DWORD PTR [state_data+44], 0
    mov DWORD PTR [0xc3ac90], 1
    lea edx, [esp+0x18]
    mov ecx, 0xc3cc10
    call queue_packet
    jmp enqueue_exit
enqueue_bad:
    mov DWORD PTR [state_data+44], 1
enqueue_empty:
    mov DWORD PTR [state_data+28], 0
    mov DWORD PTR [state_data+32], 0
    mov DWORD PTR [0xc5d398], 0
    call retail_stop_direct
enqueue_exit:
    pop esi
    mov esp, ebp
    pop ebp
enqueue_return:
    ret

/* Own callbacks carry a generation cookie. A cancelled/late callback must
 * never consume another record. Event 1 is retail cancellation, not finish.
 */
completion:
    cmp edx, DWORD PTR [state_data+48]
    jne callback_done
    cmp ecx, 1
    je callback_cancelled
    cmp DWORD PTR [state_data+28], 1
    jne callback_done
    mov DWORD PTR [state_data+28], 0
    mov DWORD PTR [state_data+32], 1
    mov DWORD PTR [0xc5d398], 2
callback_done:
    mov eax, 1
    ret
callback_cancelled:
    mov DWORD PTR [state_data+28], 0
    mov DWORD PTR [state_data+44], 2
    jmp callback_done

/* 0x27ff10's retail callback still reaches this handoff for native previews.
 * The playlist's own completion above cannot be confused with those events.
 */
advance:
    cmp DWORD PTR [state_data+52], 0
    jne native_advance
    jmp callback_done
native_advance:
    mov DWORD PTR [state_data+52], 0
    pushad
    call suspend
    mov DWORD PTR [state_data+32], 1
    mov DWORD PTR [0xc5d398], 2
    popad
    jmp callback_done

/* 0x280620 retains its entire native volume update. Its final dispatch calls
 * here after clearing the retail flag. Pause keeps our pending handoff alive.
 */
frame:
    cmp DWORD PTR [state_data+52], 0
    jne native_preview_next
    jmp enqueue
native_preview_next:
    mov ecx, DWORD PTR [0xc3cbfc]
    jmp native_preview

suspend:
    call init
    cmp DWORD PTR [state_data+28], 0
    je stopped
    mov DWORD PTR [state_data+36], 1
stopped:
    mov DWORD PTR [state_data+28], 0
    mov DWORD PTR [state_data+24], 0
    inc DWORD PTR [state_data+48]
    mov DWORD PTR [0xc5d398], 0
    cmp DWORD PTR [0xc5d3a4], 2
    je stop_hdd_player
    cmp DWORD PTR [0xc5d3a4], 4
    jne stop_direct
stop_hdd_player:
    mov ecx, 0xc3cc5c
    call stop_hdd
stop_direct:
    call retail_stop_direct
    mov DWORD PTR [0xc3ac90], 0
    ret

/* Native modal pause/resume tails maintain the actual decoder position. */
pause:
    mov DWORD PTR [state_data+24], 1
    mov eax, DWORD PTR [0xc5d3a4]
    jmp retail_pause_tail
resume:
    mov DWORD PTR [state_data+24], 0
    cmp DWORD PTR [state_data+32], 0
    je resume_tail
    mov DWORD PTR [0xc5d398], 2
resume_tail:
    mov eax, DWORD PTR [0xc5d3a4]
    jmp retail_resume_tail

/* Explicit disc/HDD jukebox preview owns the shared player until a named
 * context is requested again. PA manager uses another controller, untouched.
 */
preview:
    push ecx
    call suspend
    pop ecx
    mov DWORD PTR [state_data+52], 1
native_preview:
    push ebp
    mov ebp, esp
    and esp, -8
    jmp retail_preview_tail

context:
    test ecx, ecx
    jz context_stop
    push esi
    mov esi, ecx
    mov edx, 0xe6c0c0
    call string_equal
    test eax, eax
    jnz context_start
    mov ecx, esi
    mov edx, 0xe6c0d4
    call string_equal
    test eax, eax
    jnz context_start
    pop esi
context_stop:
    call init
    mov DWORD PTR [state_data+20], 0
    jmp suspend
context_start:
    pop esi
    call init
    cmp DWORD PTR [state_data+52], 0
    je shared_start
    call suspend
    mov DWORD PTR [state_data+52], 0
shared_start:
    mov DWORD PTR [state_data+20], 1
    mov DWORD PTR [0xc3cc08], 0
    jmp enqueue

/* The five audited F6510 modes: 0 stop/show, 1 menus, 2 loading,
 * 3 Crib, 4 game. Mode 2 retains the retail loadm path. */
mode:
    cmp ecx, 4
    ja mode_return
    push esi
    mov esi, ecx
    call init
    mov DWORD PTR [0xb9e290], esi
    test esi, esi
    jz mode_stop
    cmp esi, 2
    je mode_loading
    cmp esi, 4
    jne mode_play
    xor ecx, ecx
    call game_music_switch
mode_play:
    mov ecx, 0xe6c0c0
    call context
    pop esi
    ret
mode_loading:
    mov DWORD PTR [state_data+20], 0
    call suspend
    call loading_start
    pop esi
    ret
mode_stop:
    mov DWORD PTR [state_data+20], 0
    call suspend
    pop esi
mode_return:
    ret

/* Profile setting edits must not silently disable the explicitly selected
 * background override. Other explicit context stops still suspend normally. */
.global profile_context, player_init, halftime_enter, halftime_exit
profile_context:
    cmp DWORD PTR [0xb9e290], 4
    jne profile_other
    jmp enqueue
profile_other:
    jmp context

/* Recreated front-end player: retain the bag, restart the interrupted song. */
player_init:
    pushad
    call init
    cmp DWORD PTR [state_data+28], 0
    je player_inactive
    mov DWORD PTR [state_data+36], 1
player_inactive:
    mov DWORD PTR [state_data+28], 0
    mov DWORD PTR [state_data+24], 0
    mov DWORD PTR [state_data+52], 0
    inc DWORD PTR [state_data+48]
    popad
    jmp retail_player_init

/* Only the shared background is stopped. The complete halftime player and
 * its destructor still execute unchanged after these displaced prologues. */
halftime_enter:
    pushad
    call init
    or DWORD PTR [state_data+56], 1
    call suspend
    popad
    push ebp
    mov ebp, esp
    and esp, -8
    jmp retail_halftime_tail
halftime_exit:
    mov eax, DWORD PTR [0xb73b18]
    call retail_halftime_exit_tail
    pushad
    and DWORD PTR [state_data+56], -2
    call enqueue
    popad
    ret

/* Retail manual advance must consume the shared bag, not update a now-unused
 * single-bank index. Coalesce repeated requests; preserve a modal pause. */
.global manual_next
manual_next:
    call init
    cmp DWORD PTR [state_data+52], 0
    jne native_advance
    cmp DWORD PTR [state_data+20], 0
    je manual_done
    pushad
    mov ebx, DWORD PTR [state_data+24]
    call suspend
    mov DWORD PTR [state_data+24], ebx
    mov DWORD PTR [state_data+36], 0
    mov DWORD PTR [state_data+32], 1
    mov DWORD PTR [0xc5d398], 2
    popad
manual_done:
    ret
