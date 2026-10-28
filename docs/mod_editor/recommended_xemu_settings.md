# Recommended xemu settings for SOFTDRINK 2K28

- **Memory:** in xemu's system settings, set **System Memory → 128 MiB**, then restart xemu. SOFTDRINK's modern artwork needs this setting.
- **Picture:** try **View → Int. Resolution Scale → 2×** if the game looks grainy. Try 3× if performance stays smooth; lower the scale if it slows down. Enlarging the window alone does not increase rendering resolution. See [xemu's resolution FAQ](https://xemu.app/docs/faq/).
- **Disc:** load the **new SOFTDRINK image** through **Machine → Load Disc**. In the game, load the disc roster, then start a fresh franchise.
- **BIOS:** use your own compatible MCPX and BIOS files. xemu needs a debug or modified BIOS that can boot unsigned software; an unmodified retail BIOS cannot do that. Studio supplies neither. SOFTDRINK's 128 MB startup patch needs the modified retail **COMPLEX 4627** Flash ROM; choose it under **Machine → Settings → System → Flash ROM (BIOS)**. Any other BIOS leaves the patch asleep, and the game stops with the 4627 BIOS message. See [xemu's required-files guide](https://xemu.app/docs/required-files/).

These settings apply to **xemu**. A separate PC port uses its own resolution controls.

Start with [Install SOFTDRINK 2K28 in 5 steps](install_softdrink_2k28.md).
