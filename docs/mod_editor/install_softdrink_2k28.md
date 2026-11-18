# Install SOFTDRINK 2K28 in 5 steps

1. Download **2K5 Mod Studio beta 81** and choose the game patch for your memory setting. v0.10 is the 128 MiB release. For 64 MiB use **SOFTDRINK-2K28-v0.9-64MB.2k5patch**. Keep the patch in its original format. [Studio downloads](https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-81) · [128 MiB game](https://github.com/cruuz/softdrink-2k28/releases/tag/v0.10) · [64 MiB game](https://github.com/cruuz/softdrink-2k28/releases/tag/v0.9)
2. Open Studio. On **Getting Started**, press **Install SOFTDRINK 2K28…** (the same button is on **Build & Share → Install & Share**).
3. Choose your **unmodified ESPN NFL 2K5 USA Xbox disc image**, then the **`.2k5patch` file itself**. Use the original image for each update.
4. Choose where to save the **new image**, such as `SOFTDRINK 2K28.xiso.iso`. Wait for **Disc ready**.
5. In xemu, choose **Machine → Load Disc** and select that **new image**, or click **Play latest disc in xemu** in Studio. In the game, **load the disc roster and start a fresh franchise**. Existing franchises keep their saved rosters.

For the **standard pack**, choose **128 MiB** in xemu and use the tested **COMPLEX 4627** Flash ROM. For the **v0.9 experimental 64 MB pack**, choose **64 MiB**. A franchise saved on the standard edition shows as **Damaged** in the 64 MB game. Do not delete it; it still loads on the standard edition. After a memory or BIOS change, close xemu completely and reopen it. A startup message on the standard pack gives the detected kernel number when it needs a different BIOS. [Recommended xemu settings](recommended_xemu_settings.md) · [Startup message guide](2k5_mod_studio_faq.md)

To report a freeze, open **Help → Check my SOFTDRINK disc…** and select your finished game. Include its result, the pack version and memory variant, your platform and renderer, the in-game screen or play, and whether it happens in a fresh franchise or only after loading a save. For a custom build, include the Studio build receipt. On Steam Deck, the same xemu settings apply. PC and Android ports and XBased use different runtimes. Identify the runtime when reporting an issue.
