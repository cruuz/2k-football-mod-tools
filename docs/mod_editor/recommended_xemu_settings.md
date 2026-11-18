# Recommended xemu settings for SOFTDRINK 2K28

- **Standard pack.** Set **Machine → Settings → System → System Memory** to **128 MiB** and select your **Complex 4627** BIOS. Quit xemu completely and reopen it.
- **64 MB pack.** Choose the download whose filename contains `-64MB`. Use **64 MiB** to play with the original console's memory budget. This build omits the standard pack's 128 MiB and kernel 4627 startup checks. It is experimental on a physical Xbox and emulators that implement their own kernel. A franchise saved on the standard edition shows as **Damaged** in the 64 MB game. Do not delete it; it still loads on the standard edition.
- **Picture:** try **View → Int. Resolution Scale → 2×** if the game looks grainy. Try 3× if performance stays smooth; lower the scale if it slows down. Enlarging the window alone does not increase rendering resolution. See [xemu's resolution FAQ](https://xemu.app/docs/faq/).
- **Disc:** load the **new SOFTDRINK image** through **Machine → Load Disc**. In the game, load the disc roster, then start a fresh franchise.
- **BIOS:** use your own compatible MCPX and BIOS files. xemu needs a debug or modified BIOS that can boot unsigned software; an unmodified retail BIOS cannot do that. Studio supplies neither. SOFTDRINK's 128 MB startup patch needs a BIOS whose kernel is **4627**; the one it was tested with is the modified retail **COMPLEX 4627** Flash ROM, which you choose under **Machine → Settings → System → Flash ROM (BIOS)**. The game checks the kernel when it starts. With another kernel the patch stays asleep and the game stops on a screen that says **THIS BUILD NEEDS THE 4627 XBOX BIOS** and prints the kernel number it found and a code (see the FAQ). A BIOS file keeps its kernel scrambled, so Studio cannot read it from the file. See [xemu's required-files guide](https://xemu.app/docs/required-files/).

These settings apply to **xemu**. A separate PC port uses its own resolution controls.

Start with [Install SOFTDRINK 2K28 in 5 steps](install_softdrink_2k28.md).
