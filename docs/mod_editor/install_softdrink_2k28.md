# Install SOFTDRINK 2K28 in 5 steps

1. Download **2K5 Mod Studio** and the **SOFTDRINK 2K28 `.2k5patch` file** from their release pages. These are two downloads. Keep the patch file as downloaded; do not extract it.
2. Open Studio. On **Getting Started**, press **Install SOFTDRINK 2K28…** (the same button is on **Build & Share → Install & Share**).
3. Choose your **unmodified ESPN NFL 2K5 USA Xbox disc image**, then the **`.2k5patch` file itself**. Use the original image for each update.
4. Choose where to save the **new image**, such as `SOFTDRINK 2K28.xiso.iso`. Wait for **Disc ready**.
5. In xemu, choose **Machine → Load Disc** and select that **new image**, or click **Play latest disc in xemu** in Studio. In the game, **load the disc roster and start a fresh franchise**. Existing franchises keep their saved rosters.

For the **standard pack**, choose **128 MiB** in xemu and use the tested **COMPLEX 4627** Flash ROM. For the **experimental 64 MB pack**, choose **64 MiB**. After a memory or BIOS change, close xemu completely and reopen it. A startup message on the standard pack gives the detected kernel number when it needs a different BIOS. [Recommended xemu settings](recommended_xemu_settings.md) · [Startup message guide](2k5_mod_studio_faq.md)

To report a freeze, open **Check my SOFTDRINK disc** first. Include its result, the pack version and memory variant, your platform and renderer, the in-game screen or play, and whether it happens in a fresh franchise or only after loading a save. For a custom build, include the Studio build receipt. On Steam Deck, the same xemu settings apply. PC and Android ports and XBased use different runtimes. Identify the runtime when reporting an issue.

Studio: [downloads](https://github.com/cruuz/2k-football-mod-tools/releases).
SOFTDRINK: [patch downloads](https://github.com/cruuz/softdrink-2k28/releases).
