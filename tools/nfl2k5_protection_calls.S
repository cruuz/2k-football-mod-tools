/* Protection calls (b780 p1-slide): the user's slide call at the line replaces the game's automatic slide.
 *
 * Retail: every tick of the set phase at the line (play state 0xD, entered from 0xC when the players are set; the
 * snap moves it to 0xE, 0xB6F30) and of a live pass play (state 0xE, play kind 5), 0x23DBE0 calls
 * 0x23BC40 = `mov [0xC16BAC], 0; call 0x23B5B0; jmp 0x23B6E0` (argument 0 when set, 1 live; 0x23B6E0 returns with
 * ret 4). 0x23B6E0 counts the defenders in the box on each side of the ball and stores the slide, a world-x offset of
 * up to +-274.32 cm (3 yd) that every pass-set point and the first target pick (0x2FA9C0) use.
 *
 * snap_slide (jmp from 0x23BC4F): the retail read runs first, unchanged; then, when the offense has a call for this
 * play, the slide becomes +-274.32 cm toward the called side.  The call is the offense team's and this play's (play
 * log counter 0xE53804); it holds for every tick of the snap it was made for and is dropped when the next play is
 * set at the line.
 *
 * line_button (jmp from 0x18FE65, the at-line case for events 0x37..0x3B in 0x18FBE0): L (0x3A) and R (0x3B) on the
 * offense's three-audible panel (record 0 count 3), which retail ignores (0xFEFA0 returns no play, then the panel
 * closes), set SLIDE LEFT / SLIDE RIGHT; the same button again clears the call. Nothing is selected and the panel
 * stays open. Every other press, and L/R on five-play panels (defense, No Huddle, kicks), runs the retail code.
 *
 * State (16-byte RW block, symbol state): +0 team, +4 play log counter, +8 call (0 none, 1 left, 2 right), +9 used,
 * +12 game tick at the call (0xB71D10 counts frames from 0 in every game, 0x11A540; a call left over from a game that was
 * quit before its snap is older than the new game's clock and is dropped).
 * Local +x is the offense's right; world x = s * local x with s = +1 when the offense attacks +z (0x1B8960), so
 * k_slide[0] is the slide for RIGHT when s = +1 (and LEFT when s = -1), k_slide[1] the other (code_for writes them). */
.intel_syntax noprefix
.code32
.text
.global snap_slide, line_button, k_slide, code_end
.extern slide_auto
.extern select_play
.extern case_resume
.extern case_done
.extern state

snap_slide:
    push dword ptr [esp+4]                   /* 0x23BC40's argument */
    call slide_auto                          /* the retail automatic read (ret 4) */
    pushfd
    pushad
    movzx eax, byte ptr [state+8]
    test eax, eax
    je 9f
    mov ecx, dword ptr [0xE60280]            /* the offense */
    cmp ecx, dword ptr [state]
    jne 7f
    mov edx, dword ptr [0xE53804]            /* play log counter: moves when a play ends */
    cmp edx, dword ptr [state+4]
    jne 7f
    mov edx, dword ptr [0xB71D10]            /* game tick */
    sub edx, dword ptr [state+12]
    js 7f                                    /* the call is from an earlier game */
    cmp dword ptr [esp+0x28], 0              /* the argument: 0 = set at the line, 1 = live */
    jne 2f
    cmp byte ptr [state+9], 0
    jne 7f                                   /* used on an earlier snap */
    jmp 3f
2:
    mov byte ptr [state+9], 1                /* this snap uses the call */
3:
    mov edx, dword ptr [ecx+8]
    mov edx, dword ptr [edx+0xC]
    cmp dword ptr [edx+4], 0                 /* the attacked goal z (a float) > 0: the offense attacks +z */
    setg dl
    cmp al, 2
    sete al                                  /* 1 = right */
    xor al, dl
    movzx eax, al
    mov eax, dword ptr [k_slide + eax*4]
    mov dword ptr [0xC16BAC], eax
    jmp 9f
7:
    mov byte ptr [state+8], 0                /* another team or play: back to the automatic read */
9:
    popad
    popfd
    ret 4

line_button:
    cmp ecx, 0x3A
    jb 8f
    cmp ecx, 0x3B
    ja 8f
    cmp esi, dword ptr [0xE60280]            /* this controller's team is the offense */
    jne 8f
    cmp dword ptr [0xBA3178], 0              /* its panel (record 0, 0xFEDB0) is open ... */
    je 8f
    cmp byte ptr [0xBA317E], 3               /* ... with the formation's three audibles */
    jne 8f
    push eax
    push edx
    lea eax, [ecx-0x39]                      /* 0x3A -> 1 left, 0x3B -> 2 right */
    mov edx, dword ptr [0xE53804]
    cmp al, byte ptr [state+8]
    jne 1f
    cmp esi, dword ptr [state]
    jne 1f
    cmp edx, dword ptr [state+4]
    jne 1f
    xor eax, eax                             /* the same button again: the game's own read */
1:
    mov dword ptr [state], esi
    mov dword ptr [state+4], edx
    mov byte ptr [state+8], al
    mov byte ptr [state+9], 0
    mov edx, dword ptr [0xB71D10]
    mov dword ptr [state+12], edx
    pop edx
    pop eax
    jmp case_done                            /* no audible; the panel stays open */
8:
    lea edx, [ecx-0x37]                      /* retail 0x18FE65 */
    mov ecx, esi
    call select_play
    jmp case_resume

    .p2align 2
k_slide:
    .long 0x438928F6                         /* +274.32 */
    .long 0xC38928F6                         /* -274.32 */
code_end:
