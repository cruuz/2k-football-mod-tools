# Franchise record fixes, revision 2 of nfl2k5_coach_career_fix (b780 hunt6). GNU as, Intel syntax; the test links
# each section at its retail address and compares the bytes with the module's patched spans:
#   ld -m elf_i386 --section-start=.result=0x135260 --section-start=.owner_text=0x148a40
# Revision 1's site (0x247CD6, inc word [eax+0x32] -> nop dword [eax+0]) is a single instruction and lives in the module.
.intel_syntax noprefix
# b780 hunt6 (Q87): FUN_00135260, the per-game coach record update (esi = coach record, edi/ebx = the two scores,
# edi < ebx a win). Retail adds playoff games to the career W-L (+0x20/+0x22) and this season's W-L (+0x26/+0x28);
# the rollover counts a winning season when this season's W > L, so a 9-8 club that loses its first playoff game
# (9-9) got no winning season and the roster's regular-season career records start mixing in playoff games. In
# stage 9 (postseason) the win and loss paths now skip those four words; streaks, playoff W-L (+0x34/+0x36) and
# Super Bowl W-L (+0x38/+0x3A) are kept exactly as retail. Same span and callees; like retail it changes only eax
# (the stage on every way out, or the Super Bowl test in the postseason) and the record words.
.section .result,"ax"
.global result
result:
 call 0xc4bb0                  # eax = league stage (7 preseason, 8 regular season, 9 postseason)
 cmp eax, 7
 je done
 cmp edi, ebx
 jg loss
 jl win
 inc word ptr [esi+0x24]       # tie: career and season ties, streak length 0 (retail)
 inc word ptr [esi+0x2a]
 mov word ptr [esi+0x2e], 0
 ret
win:
 cmp eax, 9
 je win_streak                 # a playoff win stays out of the career and season W
 inc word ptr [esi+0x20]
 inc word ptr [esi+0x26]
win_streak:
 cmp word ptr [esi+0x2c], 0
 jne win_more
 mov dword ptr [esi+0x2c], 0x00010001    # streak kind 1 (wins), length 1
 jmp win_long
win_more:
 inc word ptr [esi+0x2e]
win_long:
 mov ax, word ptr [esi+0x2e]
 cmp ax, word ptr [esi+0x3c]
 jle win_post
 mov word ptr [esi+0x3c], ax   # longest winning streak
win_post:
 call 0xc4bb0                  # as retail: eax is the stage again on the way out
 cmp eax, 9
 jne done
 call 0x133a30                 # the Super Bowl week?
 test eax, eax
 je win_playoff
 inc word ptr [esi+0x38]
 ret
win_playoff:
 inc word ptr [esi+0x34]
 ret
loss:
 cmp eax, 9
 je loss_streak                # a playoff loss stays out of the career and season L
 inc word ptr [esi+0x22]
 inc word ptr [esi+0x28]
loss_streak:
 cmp word ptr [esi+0x2c], 0
 je loss_more
 mov dword ptr [esi+0x2c], 0x00010000    # streak kind 0 (losses), length 1
 jmp loss_post
loss_more:
 inc word ptr [esi+0x2e]
loss_post:
 cmp eax, 9                    # eax is still the stage (retail read it again here: same value)
 jne done
 call 0x133a30
 test eax, eax
 je loss_playoff
 inc word ptr [esi+0x3a]
 ret
loss_playoff:
 inc word ptr [esi+0x36]
done:
 ret

# b780 hunt6 (Q68): the Owner Firing row's retail text callback indexes the Off/On table with the raw value; a
# franchise saved on a carousel build with All Teams (2) reads table[2] = NULL on any build without the carousel.
# (value + 1) >> 1 maps 0, 1, 2 to Off, On, On (retail treats any nonzero value as On).
.section .owner_text,"ax"
.global owner_text
owner_text:
 mov eax, dword ptr [0xe60144]
 inc eax
 shr eax, 1
 mov eax, dword ptr [eax*4+0x4ed994]
 ret
