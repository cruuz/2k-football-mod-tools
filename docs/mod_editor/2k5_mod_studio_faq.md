# 2K5 Mod Studio FAQ, beta 79

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

No, it is not supported. SOFTDRINK 2K28 is built and tested only for xemu on a Windows, Linux or macOS computer, with 128 MiB
of memory and the COMPLEX 4627 BIOS. hakuX is a separate Android emulator, not xemu, and by its own requirements it runs without
an Xbox BIOS, so the disc's 4627 BIOS check is not expected to pass there. A black screen in hakuX is what to expect. We do not
test hakuX and cannot fix it. xemu itself has no Android version (see xemu's [FAQ](https://xemu.app/docs/faq/)).

## Can I keep the whole Crib, with its shops?

Yes, when you build your own disc. All three Studio presets, and the SOFTDRINK 2K28 pack, cut the Crib down to the Trophy Room.
In **Build & Share**, open the **Build** tab and untick **The Crib: keep only the Trophy Room (removes the shops)** under
**Gameplay**, then **Make my disc**. If you start from **Share**, then **Customize SOFTDRINK 2K28**, the box is ticked there
too: untick it before you build. Nothing in your save changes either way, and a disc built without the cut shows everything a
profile bought again. The name is a separate option, **The Crib is now the Trophy Room**, under **Franchise**: untick it too
if you want the old name back. The ready-made disc from **Install SOFTDRINK 2K28** cannot be changed afterwards.

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
files from the same release (about 65 MB). It needs 64-bit Python 3.11 or 3.12 from
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

## Which slider helps dropped interceptions?

CER asked what to increase for dropped picks. Use the game's **Interceptions** slider.
**Gameplay > Saves & Sliders** writes that slider into a copy of your Xbox save; it does not
change the disc. The SOFTDRINK **BASIC** pack includes **Fix Catching & Interception sliders**,
which repairs the game's response to those sliders. That repair makes the slider adjustment
affect the intended catch/interception behaviour; it does not guarantee every defender catches
every ball. Build the repair into the disc, adjust the save, and compare the same situation.
Community slider sets are separate content and are not automatically installed by the studio.

## Why does a build take time, and what does Disc ready mean?

The studio prepares your edits, copies the disc and verifies the output. Unchanged artwork
can reuse the private compile cache, and the final check uses the build receipt instead of
compiling that artwork again. Shared texture spans can require several related edits to be
prepared together. Copying and comparing a whole disc still take time.

Coach Edwards and maumau78 reported builds of about five minutes after earlier long waits.
That is their experience, not a timing promise for your project or computer. If a build fails,
post **Copy Build summary** and the first error, including the named edit and file.
**Disc ready** describes the selection and result. **No changes written** means the output
matched the source; the changes may already have been installed. Neither message is a played
verification of every feature. The original game disc is not changed.

## Can I find out what will stop a long build before I start it?

Yes. On the Build tab press **Check my project**. It runs in minutes, writes nothing, and lists
exactly what to untick or change (an option that cannot be combined with another, stadium
edits that conflict with the Modern stadium boards, a disc problem the build would find at the
start) and, separately, what Build will do with your work. The same list can be made from a
saved project without opening Studio:
`python -m mod_editor.core.nfl2k5_project_check MyProject.2k5mod --source "ESPN NFL 2K5 (USA).xiso.iso"`.

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

## xemu is choppy or grainy. Which studio option fixes it?

lt9608's performance question concerns **emulator settings**. Compare your original game in
xemu, then use xemu's settings and emulator community support. The studio does not set emulator
resolution or guarantee performance. Include emulator version and settings when reporting a
played issue; keep that separate from a build failure.
