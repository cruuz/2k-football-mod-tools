# 2K5 Mod Studio FAQ, beta 80

Start with the [Getting Started guide](2k5_mod_studio_getting_started.md).
These answers combine the previous release FAQ and the community reports for beta 71.1.
A successful offline check does not establish how every change plays in a game.

## Which studio and emulator do I need?

**ESPN NFL 2K5** is the original Xbox game: use **2K5 Mod Studio** and **xemu**.
**All-Pro Football 2K8** is the Xbox 360 game: use its separate studio and **Xenia**.
Both studios need your own game dump. Neither includes a game or emulator.

## Should my game file end in .iso or .xiso?

Both are the same kind of file: an Xbox disc image of your own ESPN NFL 2K5 (USA) disc. The ending is only a label, but
end the name in **.iso** for xemu, because xemu's Load Disc window looks for `.iso` files. A name like
`SOFTDRINK 2K28.xiso.iso` is on purpose: the `.xiso` part says it is an xiso (the layout xemu needs) and the `.iso` at the end
is what xemu looks for. The Studio opens `.iso`, `.xiso` and `.img` files and reads what is inside, not the ending. If xemu does
not show a file that ends only in `.xiso`, rename it to end in `.iso`. Renaming changes nothing inside the file.

These are not disc images, so they will not work: a folder of game files (Install SOFTDRINK 2K28 needs one image file, see
[Start here](../START_HERE.md)), a zip or 7z file, a `.cue` and `.bin` pair, a shortcut or symbolic link, and compressed
formats such as `.chd` (xemu cannot load them). A full dump of the whole disc (about 7 GB, with a video part in front of the
game part, often called a redump image) installs SOFTDRINK 2K28 fine, but xemu cannot load that raw form itself. Always
load the new disc the Studio saves in xemu, not your raw dump.

## I have no disc drive. How do I get the game file?

You need a way to read your own disc. Nobody in this project can send you a game file or a link to one, and neither the
Studio nor xemu includes a game. A normal computer DVD drive usually cannot make a usable Xbox dump by itself. xemu's own
guide, [Disc Images](https://xemu.app/docs/disc-images/), names two ways to back up a disc you own: copy the game files
over your network from a real Xbox that runs a custom dashboard, or use a special reflashed DVD drive and the Redump dumping
guide. If you have neither a drive nor a modified Xbox, you cannot make the file yourself. Once you have the files, the same
guide shows how to turn them into one image file.

## How do I make the picture sharper?

That is an xemu setting, not a Studio option. In xemu choose **View**, then **Int. Resolution Scale**, then **2x**. Try
**3x** if the game stays smooth, and go back down if it slows. Making the xemu window bigger does not make the game sharper:
the window only stretches the same picture, while the scale makes xemu draw more pixels, so a higher scale needs a stronger
graphics card. See [recommended xemu settings](recommended_xemu_settings.md) and xemu's own
[FAQ](https://xemu.app/docs/faq/).

## The game will not start. What should I check?

Go through this list in order. Most start-up problems are an xemu setup problem, not the disc.

1. **Does the original game start?** Load your untouched retail disc image in the same xemu. If that does not start either,
   the problem is xemu's own setup, and nothing in the Studio will fix it. xemu needs its own boot ROM, BIOS and hard disk
   image: see xemu's [required files](https://xemu.app/docs/required-files/).
2. **Memory.** Set xemu's **System Memory** to **128 MiB** (Machine, then Settings, then the System tab). Quit xemu completely
   and open it again, because xemu applies this only after a restart. The current SOFTDRINK 2K28 disc does not run at 64 MiB.
   (A disc you built yourself with **Console memory** set to 64 MB is the one exception; see the next question.)
3. **BIOS.** xemu needs a debug BIOS or a modified retail BIOS that can start unsigned games, and SOFTDRINK 2K28's start-up
   patch needs the modified retail **COMPLEX 4627** one. Choose it under Machine, then Settings, then System, then Flash ROM
   (BIOS). With any other BIOS the patch stays asleep and the game stops with a BIOS message. The Studio and this project do
   not supply BIOS files.
4. **The right disc.** In xemu choose **Machine**, then **Load Disc**, and pick the new disc the Studio saved, not your
   original and not an older SOFTDRINK disc. It must be the whole image file, not a shortcut, a zip or a folder.
5. **Paths and folders.** Keep the disc image and xemu's files (BIOS, boot ROM, hard disk image) in plain folders you can read
   and write, such as `C:\2K5` on Windows, not in a folder that OneDrive or another service syncs. xemu remembers where each
   file was when you chose it: if you moved or renamed one, choose it again. Keep at least 8 GB free where the new disc is
   saved.
6. **Stuck on the Xbox logo?** Quit xemu completely, not just the game, open it again and load the disc again.
7. **Still stuck?** Ask in the Discord and say your Studio version, the SOFTDRINK pack version, your xemu version, the
   memory setting, the BIOS name and exactly where it stops (Xbox logo, black screen, a message), with a screenshot. For a disc
   you built yourself, also post **Copy Build summary**.

## Can I play SOFTDRINK 2K28 on Android, in hakuX?

Not the ready-made pack, but you can try a **64 MB build** (experimental, estimated, not yet tested on a real Xbox or
hakuX). The SOFTDRINK 2K28 pack that **Install SOFTDRINK 2K28** puts on your disc is the full build for xemu on a Windows,
Linux or macOS computer (and the Steam Deck), with 128 MiB of memory and the COMPLEX 4627 BIOS. hakuX is a separate Android emulator, not xemu: by its own requirements it runs without
an Xbox BIOS, because it reimplements the Xbox kernel instead of running the real one. The pack's start-up check needs the
real 4627 kernel and 128 MiB, so the pack is not expected to start there, and a black screen without the message is what to
expect.

The Studio can make a disc for 64 MB machines, such as an original Xbox console and hakuX:

1. In **Build & Share**, open the **Share** tab. Set **Build for** to **64 MB, original Xbox and Android hakuX
   (experimental, estimated, not yet tested on a real Xbox or hakuX)**, then click **Customize SOFTDRINK 2K28…**. The **Build**
   tab opens with the pack's art and options and the recommended 64 MB set already applied. (To start from your own
   selection instead, open the **Build** tab and set **Console memory** there.)
2. On the **Build** tab, **Console memory** now reads 64 MB. Every option that needs 128 MB or the real Xbox kernel is off
   and greyed out, with the reason beside it, for example the three 128 MB memory options, Guardian caps, 16 reserves, the
   two extra created teams and the Hi-res pack. The start-up checks for 128 MB and the 4627 BIOS are left out too.
3. Each remaining option shows what it costs in memory at 64 MB. The line under **Console memory** says whether your
   selection is predicted to fit at the hardest stadium, or how much to remove and what to turn off. Untick what you can
   do without, or click **Use the recommended 64 MB set**. **Make my disc** refuses a selection that is predicted not to fit
   and names what to turn off. When the line says the selection fits with the default uniforms but a player-picked
   alternate kit at the heaviest stadium may not fit, the disc is made with that warning: if a game loops on the stadium
   shots, use the default uniforms.
4. The pack's 2026 rosters stay. At 128 MB they make the roster file bigger; at 64 MB the build fits them to the original
   game's roster size instead. What is dropped: the free agents beyond the original game's count, and franchise draft-pick
   ownership and the backfield labels fall back to the 2004 game's (the Player Card champions page also starts empty).
   The build summary lists how many free agents were kept. This route keeps the pack's art, the 2026 rosters and the
   options that fit.

The 64 MB build is experimental, estimated, not yet tested on a real Xbox or hakuX: its memory numbers come from a model,
not a measurement on a console. We cannot fix hakuX itself. For the full SOFTDRINK experience, use xemu at 128 MiB.
To try a 64 MB disc in xemu the way a console runs it, set xemu's **System Memory** to **64 MiB**. xemu itself has no
Android version (see xemu's [FAQ](https://xemu.app/docs/faq/)).

## Can I keep the whole Crib, with its shops?

Yes, when you build your own disc. All three Studio presets, and the SOFTDRINK 2K28 pack, cut the Crib down to the Trophy Room.
In **Build & Share**, open the **Build** tab and untick **The Crib: keep only the Trophy Room (removes the shops)** under
**Gameplay**, then **Make my disc**. If you start from **Share**, then **Customize SOFTDRINK 2K28**, the box is ticked there
too: untick it before you build. Nothing in your save changes either way, and a disc built without the cut shows everything a
profile bought again. The name is a separate option, **The Crib is now the Trophy Room**, under **Franchise**: untick it too
if you want the old name back. The ready-made disc from **Install SOFTDRINK 2K28** cannot be changed afterwards. The
sidebar page **The Crib** repeats this note at the top.

## My studio will not open or update. How do I reinstall?

GoldenTiger reported an installation arranged by an assistant that stopped opening after
an update. On Windows, uninstall that studio installation, download the latest **Setup.exe**
from the [release page](https://github.com/cruuz/2k-football-mod-tools/releases), and run it.
Keep your projects and original game dump. You do not need to install Python for Setup.exe.
**Help > Check for Updates…** checks the release; **Get the update** opens the download page.
Git checkouts use their source-code update workflow.

If you used the green **Code > Download ZIP** button instead of the release asset, that is
the source code, not the Studio. Double-click `2K5-Mod-Studio.bat` in the extracted folder.
The first run creates a private `.venv` beside it and installs the Studio packages
automatically (about 110 MB, internet needed). It also downloads the reviewed data
files from the same release (about 65 MB). It needs 64-bit Python 3.11, 3.12 or 3.13 from
[python.org](https://www.python.org/downloads/windows/); the launcher prints that address
when Python is missing. No administrator rights are needed. Run
`2K5-Mod-Studio.bat --setup` to repair the private runtime, or download the latest
**Setup.exe** for the supported install.

## My modded disc freezes at the Xbox logo. What should I post?

MacDog850 reported a freeze after an assistant changed his studio so it could build an ISO.
**A copy of the studio edited by an assistant is unsupported.** Reinstall from the release
**Setup.exe**, rebuild from your untouched disc, then post **Copy Build summary** from
**★ Build & Share > Build**, plus the **first error** you hit. Explain what prevented the
original installation from building. A final progress line alone does not identify the cause.

Quit xemu completely, reopen the new disc, and compare your original disc with the same
emulator settings. A stop at the Xbox logo does not by itself identify a gameplay patch.
Keep the original disc and the failing output separate.

## It freezes at Berman, or the new kickoff does not appear

andrethealchemist reported that turning **Scorebug effects (reported Berman freeze)** off
cleared his freeze. Leave that option off for normal play; it is experimental and off in
all presets. This is a reported workaround, not a general freeze fix.

For lt9608's missing-kickoff report, include the Build summary and whether **Dynamic kickoff**
was selected. It must be included in the build to change the kickoff. Compare the same build
with Scorebug effects off. Passing offline checks do not reproduce every boot or save.

## The game froze and the commentators keep repeating. What should I post?

That sound means the game has stopped while the sound card replays its last audio. First check your disc copy:
`python -m mod_editor.core.nfl2k5_disc_check "SOFTDRINK 2K28 v0.8.xiso.iso"` says whether it matches the released
disc or names the damaged file (a cut-short or damaged copy stops the game at the first failed read). If it
matches, turn on freeze capture and post the capture file from the next freeze. Both steps, for Linux, Steam Deck,
macOS and Windows, are in [When the game freezes](freeze_capture_and_disc_check.md).

## Which slider helps dropped interceptions?

CER asked what to increase for dropped picks. Use the game's **Interceptions** slider.
**Gameplay > Saves & Sliders** writes that slider into a copy of your Xbox save; it does not
change the disc. The SOFTDRINK **BASIC** pack includes **Fix Catching & Interception sliders**,
which repairs the game's response to those sliders. That repair makes the slider adjustment
affect the intended catch/interception behaviour; it does not guarantee every defender catches
every ball. Build the repair into the disc, adjust the save, and compare the same situation.
Community slider sets are separate content and are not automatically installed by the studio.

## Why does a build take time, and what does Disc ready mean?

The studio prepares your edits, copies the disc and verifies the output. Preparing is the long
part for a big project: a project with thousands of textures needs hours the first time. What a
build compiles is kept in a private cache beside the game files the studio read from your disc,
and it is keyed by your artwork and by the studio's own encoder code, never by where a file or a
project happens to be. So the next build reuses every texture whose artwork did not change: after
a failed build, after closing and reopening the studio or the project, and after a studio update
that does not touch the encoders. Only new or changed artwork is compiled again. When that step
ends, the progress line says how many textures were reused and, for any compiled again, why. The
final check uses the build receipt instead of compiling that artwork again. Shared texture spans
can require several related edits to be prepared together. Copying and comparing a whole disc
still take time.

Coach Edwards and maumau78 reported builds of about five minutes after earlier long waits.
That is their experience, not a timing promise for your project or computer. If a build fails,
post **Copy Build summary** and the first error, including the named edit and file.
**Disc ready** describes the selection and result. **No changes written** means the output
matched the source; the changes may already have been installed. Neither message is a played
verification of every feature. The original game disc is not changed.

## My build failed. Should I clear the cache, delete the sessions folder or reinstall?

No. A failed build leaves your project and your artwork alone, and everything it had already
compiled stays in the cache. The cache is what makes the next try fast: those textures are reused,
so a retry skips the compile work, which is most of the time of a big project. Clearing it only
makes the next build slow again. Reinstalling does not help either; it is for a studio that will
not open or update (the first question above). Post **Copy Build summary** and the first error
instead, so the cause can be found.

What the cache is and what deleting it costs: the compiled textures sit in a folder called
`project-stage`, next to the private game cache (Windows `%LOCALAPPDATA%\2k5-mod-studio\cache\project-stage`,
Linux and macOS `~/.cache/2k5-mod-studio/project-stage`). They are made from your own disc, so keep
the folder private like the game cache and never share it. It is limited to about 3 GiB and the
oldest results go first; a build never removes what it is using. Updating or reinstalling the studio
does not delete it, and your reused textures survive an update that does not change how textures are
encoded. Deleting the folder yourself is safe, but it costs one slow build, because every texture is
compiled again (hours for thousands of textures).
Your projects, your artwork and your original disc are not stored there. The working sessions
under `sessions` hold copies of the artwork you opened and clean themselves up after two weeks;
the build no longer keeps its compiled textures in them.

## Can I find out what will stop a long build before I start it?

Yes. On the Build tab press **Check my project**. It writes nothing to your project or your
disc, and lists exactly what to untick or change (an option that cannot be combined with
another, stadium edits that conflict with a stadium option, a disc problem the build would find
at the start, a new Anniversary kit a classic team needs that cannot be made from your kits)
and, separately, what Build will do with your work. Since beta 80 it also tries the long
build's risky steps on your own options and art (a few minutes for most projects, up to about half an hour
with every stadium option on): every
stadium field, bump map and divot layer that Modern colour, the modern stadiums, the practice
facility, Modern surfaces and Broadcast greens refit, with your own Modern colour values; the
new kits on your own kits; the options and settings no release build ever tried; and your
project against every size limit. Press **Save report** to keep the whole report (a text file,
a JSON file and a short summary) and send it with a help request. The same report can be made
from a saved project without opening Studio:
`python -m mod_editor.core.nfl2k5_project_check MyProject.2k5mod --source "ESPN NFL 2K5 (USA).xiso.iso" --report MyReport`
(add `--quick` for the checks that take seconds).

After every build of a project, the Build summary also says whether every kit and stadium piece
you edited is on the finished disc exactly as the texture stage wrote it, and names any that is
not.

The built-in Anniversary and classic kits are composed from kits already on the disc, which
may be kits you edited. If one of your edited sock, glove or shoe chunks cannot be used in
a new kit (it needs more video memory than any game kit, or a sock whose clean and mud copies
no longer share their image), the build uses the retail version of that one chunk in that new
kit only, names it in the build log, and keeps your artwork in your own kit. In the message
"composed kit allocation 10752/2867776" the two numbers are bytes (system and video memory of
the kit), not counts; the largest kit in the game uses 2,840,256 video bytes.

## Can I use uniforms from another year?

X_Ray and maumau78 asked about older uniforms. You can author another era's artwork for the
supported physical sets on the disc. Follow each texture's size, channel, palette and fit
requirements. Which eras a community conversion includes is a decision for that conversion's author.

## Why are designer socks or shoes blurry, or shared by both teams?

**Give this sock, glove or shoe its own texture** preserves authored designs when they fit.
Start from a fresh exported template and keep the original game size. Choosing a smaller game
image deliberately removes detail. Dirty socks are a separate import; relief maps are separate too.
An unchanged retail export imported as own artwork at original size preserves its existing
palette and distance images when the studio recognizes it. New artwork must pass the fit check.

Global shoe rows offer **All teams** because the game shares those styles. Style 3 selects
shoes09; Style 6 selects shoes10 in each worn uniform package. Choose the style on both feet.
maumau78 reported “I assigned this shoe to both mud and normal slot and it finally show up
in-game,” while it still looked buggy. A normal shoe, glove or pad import now stages its mud
sibling wherever that sibling exists; a mud-only import stays separate. Revert on the normal
slot restores the same group in one undoable action. Import each home/away uniform you wear.
The tested field path chooses the normal/mud cache row from a runtime player-record flag,
including under dry weather inputs. The flag's gameplay lifecycle is not established. These
changes are **UNWITNESSED in game**; the earlier single-slot guidance was insufficient in
maumau78's game.

The import result, measured project rows and verified build summary identify the fitted
size and the colours actually referenced across its mip chain, for example **fitted at
64 x 64, 16 colours**. High-contrast bands keep a palette limit of at least 16 entries;
if they do not fit, **Try that** offers an explicitly checked smaller image. A design with
fewer colours may use fewer than 16 entries without losing any of those colours. Quantization
uses the authored art with no dithering. A smaller image still loses fine detail. The actual
source PNG for Coach Edwards' photographed socks was not available, so the photo's cause
has not been isolated. Larger equipment allocations remain unavailable until the full
archive relocation and disc round trip are proved.

## Why are arm digits on the sleeve instead of the shoulder pad?

The jersey mesh and its UV coordinates determine which body surface carries the artwork
and how the picture maps onto it. Importing the digit changes the artwork, not its position.
The retail model contains both sleeve and shoulder digit surface names; choosing and moving
those surfaces needs model and visibility research. See the
[arm-digit model research note](../research/nfl2k5_arm_digit_placement.md).

## Do equipment textures replace existing ones or add extras?

They replace an existing slot's artwork; they do not add another selectable shoe, sock or glove style.

## Why can a modified stadium banner still look original in a game?

Each venue has separate day, afternoon and night packages, each with dry, rain and snow
variants. An import changes only its selected SCNE occurrence and the materials linked to
that embedded texture. Choose the venue and conditions in the now-named scene list before
importing; the build receipt names the exact package and texture occurrence. Other variants
keep their own art. The generic old “stadium” labels hid this distinction.

For a daytime dry Bears home test, search **Chicago Field**, select **Day / Dry (s05dd.iff)**,
and edit **Texture 42 / banner_corp**. For Cincinnati choose **Paul Brown Stadium / Day / Dry
(s06dd.iff)** and **Texture 29 / banner_corp**. Look at the corporate sponsor boards around
the field. Different time/weather packages must be edited separately. The native material
binding and written pixels pass offline checks; appearance in game remains **UNWITNESSED**.
The stadium in andrethealchemist's report is unknown, and Texture 29 alone cannot identify it.

## What is the raised logo under my shoe artwork?

maumau78's “under layer” is separate shoe relief. **Bump Maps** edits the seven global shoe
normal maps. Style 1 uses bump_shoes1; Styles 3 and 6 share bump_shoes7. Maps 5 and 6 exist but
have no selected style in the reviewed table. Changing relief can affect both teams; it does
not make a global colour texture local. Offline binding checks do not prove every lighting result.

## Import Edited Kit says zero imported. Did it fail?

Not necessarily. It compares incoming pixels with the currently staged project and lists
identical files as skipped. Saving a PNG without changing pixels is a no-op. An untouched export
can also preserve newer project artwork. Check the named PNG and imported folder against the
current preview. A repeated import should not repeat an old imported count.
Opening **Equipment** from Uniforms creates its browser on the first visit; visiting All Textures
first is no longer required.

## Why does a skeleton import ask for both files?

Geometry and skeleton imports have different checks. For a skeleton pair, edit both LOD files
from one export and retain the Blender glTF exporter's **Include > Data > Custom Properties**.
An “unedited” geometry check does not establish that the skeleton pair is complete. Read the
missing-file explanation on **★ Models**. Check the build selection before combining models
with other changes; the [changelog](2k5_mod_studio_changelog.md) describes the model workflow
included in your installed build.

## Can the CPU go for it more often on fourth down?

**CPU fourth downs, two-point tries and overtime (experimental)** offers **Retail**,
**Modern**, **Aggressive** and **Modern 2** in Build and Gameplay > Game Fixes. Retail is the
Basic preset default; the Advanced and Experimental presets use Modern 2. Modern changes
fourth-down policy and first-down targeting. Modern 2 adds a fourth-down table taken from
published analytics (the ESPN Analytics chart and the nfl4th model) that also reads the score
and clock, the modern overtime rules (a team behind by a touchdown on its last possession
never punts or kicks), a modern two-point chart and more varied defensive coverage calls.
The sources and every threshold are in `nfl2k5_cpu_decisions_modern2_sources.json`. Offline
policy checks pass; in-game outcomes remain experimental and unwitnessed.

## Does Slow-QB acceleration make the CPU scramble more often?

It changes acceleration for a slow quarterback already carrying the ball. It preserves the
AI decision. It is not evidence of NFL-average scramble frequency. Use the installed option's
help and current changelog for any separate CPU decision control.

## What about weather, sunset, coin-toss deferral or conceding the clock?

BigTimeEmpire, maumau78 and CER requested these changes. Read the corresponding controls in
your installed build and the [beta 77 changelog](2k5_mod_studio_changelog.md) for what has landed
and its limits. Weather artwork or a stored environment field alone does not provide dynamic
weather, footprints, franchise weather selection, wind gameplay, or a clock-concession rule.
Do not infer those features from a texture browser or an unrelated accelerated-clock option.

## Can I check bad colleges or edit historic player names?

Use **★ Rosters > Checks > Check my rosters…** to scan for missing or invalid college references.
Repair needs a loaded roster and a readable college table, creates one undo entry, and still
needs to be saved. **★ Rosters > ESPN Anniversary** edits the fixed historic roster spans.
The automatic **Historic moments: real rosters** option was blocked by the Wide Right loading
freeze; use its current enabled state and explanation. Authoring names offline is not proof
that every moment loads. The 25 moments share 35 roster files, so shared teams need care.

## What changed in MyCareer Fast forward and PATs?

andrethealchemist confirmed the earlier fixes in-game: cancelling Fast forward with B retains
the preference, it resumes on later CPU snaps, the Apartment keeps the setting, and the scoring
side can choose a PAT. His newer report says the first play after returning to the field can
already be selected. See the current MyCareer changelog for that separate fix and play-calling
options. A report about one sequence does not verify every position, save or mode combination.

## Read option or RPO did not work. What identifies the problem?

Post the exact book, formation, play, human/CPU caller and controller mapping, with the Build
summary. The reported played failure remains distinct from passing offline controls checks.
For the documented recipes, no new input gives; release and press A again to keep; Black pitches;
RPO uses X or the named receiver when ready. Say which action failed and what the ball did.

## Can SportsCenter play like a menu-time radio show?

Mud's Tony Bruno Show-style request is **roadmap**. A menu-time radio show needs audio content
and a menu audio hook. The studio's music controls do not provide that feature. Crib phone
calls, front-office offers and a playable scouting combine are also roadmap/research; the
existing MyCareer preparation data does not establish a playable combine.

## Can I author every zone-coverage rule or custom AI routine?

Existing match-coverage and deep-zone experiments expose specific supported changes. They do
not establish unrestricted per-play zone logic or arbitrary custom AI. Read the selected tool's
scope. Community opinions about contact feel and conversion videos are reports about those
players' content, not proof of a new studio feature.

## The game stops on a black screen and says it needs 128 MB or the 4627 BIOS. I set both.

SOFTDRINK checks two things when it starts. xemu's **System Memory** must be 128 MiB, and the
**Flash ROM (BIOS)** must have the 4627 kernel (the **Complex 4627** image is the one it was
tested with). If either is wrong it stops on a black screen with white letters and names the one
to fix. It does this on purpose, because the game would otherwise fail later at the pregame
intro.

- **"THIS BUILD NEEDS 128 MB ... THEN CLOSE XEMU AND OPEN IT AGAIN":** xemu is running with 64 MiB
  right now, whatever its settings window says. xemu reads the memory setting only when it
  starts. Set **Machine, Settings, System, System Memory** to 128 MiB, close xemu completely,
  open it again, check that it still says 128 MiB, then load the disc again. If it keeps going
  back to 64, you are editing a different settings file from the one this xemu reads. The file
  is `xemu.toml` and needs `mem_limit = '128'` under `[sys]`. Windows: next to `xemu.exe` if
  there is an `xemu.toml` there, otherwise `%APPDATA%\xemu\xemu\xemu.toml`. Linux:
  `~/.local/share/xemu/xemu/xemu.toml`. Flatpak, EmuDeck and Steam Deck:
  `~/.var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml`. macOS:
  `~/Library/Application Support/xemu/xemu/xemu.toml`.
- **"THIS BUILD NEEDS THE 4627 XBOX BIOS" and a line `KERNEL 5849 CODE 1`:** the memory is right
  but the BIOS is not. The line prints the kernel number the game found and which check failed
  first. `4627` is the kernel the patch was made for. CODE 1 means the kernel is not 4627:
  choose the Complex 4627 image under **Machine, Settings, System, Flash ROM (BIOS)**. CODE 2,
  3 or 4 with `KERNEL 4627` means the kernel says 4627 but is laid out differently from the
  tested one (2: the memory tables are already in use, 3: a kernel routine the patch needs is
  not where it expects, 4: the memory page count is unusual). If you see that, post a photo of
  the screen and the MD5 hash that xemu shows under **Flash ROM (BIOS)** (Machine, Settings,
  System), or the SHA-256 start that Studio's note showed, in the Discord bugs channel, so we can
  tell which BIOS it is.

## Does Studio check my xemu settings and BIOS?

Only when you start xemu from Studio (**Play latest disc in xemu**). It reads `xemu.toml` and
shows a note if System Memory is not 128 MiB or the Flash ROM is not set. The check only reads:
it never changes your BIOS or your memory setting and never stops the launch (the one thing
Studio writes to `xemu.toml` is the path of your new disc, so xemu remembers it). It recognises
the tested Complex 4627 image by its contents, so the same BIOS saved as a 256 KB, 512 KB or
1 MB file counts as the same. For any other BIOS file it shows a short note with a SHA-256 fingerprint instead of an error. A
BIOS file keeps its kernel scrambled, so Studio cannot read the kernel number from the file.
The game itself checks the kernel when it starts, which is what the screen above is. If your
BIOS is not the tested one and the game starts at 128 MiB, nothing is wrong and you can ignore
the note. If you run xemu yourself (Steam Deck, another PC), Studio does not see it, and the
game's own screen is the check.

## Steam Deck: how do I set it up, and why did Free Agents freeze?

Run Studio in **Desktop Mode** (the Linux and Steam Deck steps are in [Start here](../START_HERE.md)).
EmuDeck installs xemu as a Flatpak, so its settings are in
`~/.var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml`. Set System Memory to 128 MiB and the Complex
4627 BIOS in Desktop Mode, close xemu normally, then start it again, from Desktop Mode or Game
Mode, and check the memory still says 128 MiB before you load the disc.

A freeze while scrolling Contracts or Free Agents has one known cause: players with no college
on the screen's info panel. Franchises saved on SOFTDRINK 0.6.1 can still hold such players, and
SOFTDRINK 0.7 and later make that panel show N/A for them instead of stopping. A new franchise
from the current disc has none. A freeze on a Deck with a newer disc is not that bug, and we have
not been able to reproduce one. If your Deck freezes, please post: xemu version, renderer
(**Machine, Settings, Display**), the System Memory setting, whether the franchise is new or older,
which list and position filter you were on and for how long you scrolled, and a photo of the
frozen screen.

## Linux setup says my Python version is not supported

The Studio's packages are pinned to versions that are proven to build the same disc on every system. Python 3.11, 3.12
and 3.13 are supported: on 3.13 setup installs NumPy 2 (NumPy 1.26 has no 3.13 build), and the same project builds a
byte-identical disc on Python 3.12 and 3.13, so `./2K5-Mod-Studio.sh --setup` works with a system Python 3.13 as it is.
If your system has only Python 3.14 or newer, or the package install fails, you do not need to replace your system
Python, and you do not need root, so this also works on a Steam Deck in Desktop Mode. Install uv (the one-line installer
is on [docs.astral.sh/uv](https://docs.astral.sh/uv/)), then, in the extracted Studio folder, run:

```
uv python install 3.12
MOD_STUDIO_PYTHON="$(uv python find 3.12)" ./2K5-Mod-Studio.sh --setup
```

After that, start the Studio with `./2K5-Mod-Studio.sh` as usual; it keeps using the Python 3.12 setup. uv's Python lives
in your home folder and changes nothing else on the system.

## xemu is choppy or grainy. Which studio option fixes it?

lt9608's performance question concerns **emulator settings**. Compare your original game in
xemu, then use xemu's settings and emulator community support. The studio does not set emulator
resolution or guarantee performance. Include emulator version and settings when reporting a
played issue; keep that separate from a build failure.
