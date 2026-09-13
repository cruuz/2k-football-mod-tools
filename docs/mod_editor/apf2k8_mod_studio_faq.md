# APF 2K8 Mod Studio FAQ, beta 69

Use the [Getting Started guide](apf2k8_mod_studio_getting_started.md) for the complete page order
and first build. This studio edits your own USA Xbox 360 **All-Pro Football 2K8** dump.

## Is this the 2K5 studio? Which emulator do I use?

APF 2K8 uses **Xenia**. ESPN NFL 2K5 uses its separate studio and **xemu**.
A built APF game is a complete extracted folder; open its **default.xex** in Xenia.
The studio does not claim to rebuild a bootable retail ISO. Keep the original game as source.

## Can I create formations and plays, as 7ET requested?

Yes. Open **Playbooks & Plays > Design Plays / Formations** for **Create formation** and
**Create play**. These are **experimental, off by default and limited to CPU books**.
They remain **UNWITNESSED in-game** on both BASE and Title Update 1.1; offline writer,
receipt and interface checks are the evidence. Existing tools and stock templates do not
establish unrestricted human/USER-book authoring or new arbitrary game AI.

## What is Play Calling, and how is it different from designing a play?

**CPU Play Calling** controls **which plays get called**. Select a team and offense or defense,
then review its book, situation weights, formation/play ratings, personnel and tendency.
Design tools change a play or formation; Play Calling changes selection among the available
ones. Schemes start from supported book data; review the proposed edits before applying them.
APF has no studio-wide Basic/Modern preset like the 2K5 studio.

A shared book can affect several teams. Read the shared-book notice or review an own-book
copy before staging. The call preview is an offline estimate with its stated assumptions,
not live-game probabilities. Weather ratios, tempo and coin-toss strategy are not established
by situation weights alone.

## Does the TE pass-fetch patch fix all CPU play selection?

No. It affects the last-resort fetch when normal selection has failed. It does not determine
successful normal calls. It remains experimental and off by default. Installation asks before
changing Xenia's patch setting, which can also activate other enabled patches. Formation
removal and personnel gaps have their own checks; a formation appearing in a book is not proof
that its weight lets it be selected in the situation you tested. Include team, book, down,
distance and the changed settings with reports about 5-2, heavy sets or missing tight ends.

## Can I import PS3 rosters and logos?

Use **Rosters & Players > Import PS3 Roster** and **Import PS3 bundle…** in the supported art
pages. Aszemple reported successfully importing logos and roster files from RPCS3. That supports
those import workflows, not every helmet view or gameplay situation. The source remains a
USA Xbox 360 game; importing PS3 content does not turn the studio into a PS3 disc builder.
Read the mapping and appearance review before applying changes to a roster or team.

## Why can a same-size crest be too large?

Canvas size and compressed size are different. Six crest masks, their smaller images and the
chosen package's capacity all matter. The import review shows whether the art fits, whether
shade reduction is needed, or the byte shortfall. Choose a package with room, permit the
supported shade reduction, or simplify the art. Keep the roster's crest index aligned with the
chosen destination. Frontend previews do not establish every in-game helmet binding.

## Is every green Editable label an in-game test result?

**Editable** describes an available authoring action. **Preview**, **Export-only** and research
or proof boundaries describe other limits. Read the capability's findings and runtime evidence.
Offline writing and reparsing establish the stated file changes; they do not establish all
rendering, gameplay or original Xbox 360 hardware behaviour. An unwitnessed label stays in
place until the relevant played result exists.

## How do I install or recover an update that failed?

On Windows, download and run the latest **Setup.exe** from the
[release page](https://github.com/cruuz/2k-football-mod-tools/releases). Keep your projects and
original game. If an assistant changed the installed studio, reinstall the official release;
that modified installation is unsupported. Use **Help > Check for Updates…** or **Get the update**.
Post the first error, studio version, selected changes and build result if it still fails.
Never post game files or a built game folder. Share the **.apf2k8mod** project instead.

## Why does my game stutter, look grainy or need a Title Update?

Performance and rendering settings belong to **Xenia**, as xemu settings do for 2K5.
Compare the original game with the same emulator setup. The studio's **Title Update 1.1…**
control accepts your Xbox 360 update package; the update is not shipped by the studio and is
not a PS3 update. Include the emulator version, BASE or Title Update 1.1, and settings with
played reports. Changing art or a CPU book is not an emulator performance fix.

## Can I make a menu radio show, a playable combine or any custom coverage AI?

The related community requests are roadmap/research unless a specific implemented control
and its scope say otherwise. Browsing audio or a practice remnant does not create a playable
mode. For 2K5-specific answers about dropped interceptions, MyCareer or Mud's menu-time radio
request, use the [2K5 FAQ](https://github.com/cruuz/2k-football-mod-tools/blob/main/docs/mod_editor/2k5_mod_studio_faq.md).
