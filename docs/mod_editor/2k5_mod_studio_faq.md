# 2K5 Mod Studio FAQ, beta 73

Start with the [Getting Started guide](2k5_mod_studio_getting_started.md).
These answers combine the previous release FAQ and the community reports for beta 71.1.
A successful offline check does not establish how every change plays in a game.

## Which studio and emulator do I need?

**ESPN NFL 2K5** is the original Xbox game: use **2K5 Mod Studio** and **xemu**.
**All-Pro Football 2K8** is the Xbox 360 game: use its separate studio and **Xenia**.
Both studios need your own game dump. Neither includes a game or emulator.

## My studio will not open or update. How do I reinstall?

GoldenTiger reported an installation arranged by an assistant that stopped opening after
an update. On Windows, uninstall that studio installation, download the latest **Setup.exe**
from the [release page](https://github.com/cruuz/2k-football-mod-tools/releases), and run it.
Keep your projects and original game dump. You do not need to install Python for Setup.exe.
**Help > Check for Updates…** checks the release; **Get the update** opens the download page.
Git checkouts use their source-code update workflow.

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

**CPU fourth downs and first downs (experimental)** offers **Retail**, **Modern** and
**Aggressive** in Build and Gameplay > Game Fixes. Retail is the preset default. It changes
fourth-down policy and first-down targeting. Offline policy checks pass; in-game outcomes
remain experimental and unwitnessed for untested situations.

## Does Slow-QB acceleration make the CPU scramble more often?

It changes acceleration for a slow quarterback already carrying the ball. It preserves the
AI decision. It is not evidence of NFL-average scramble frequency. Use the installed option's
help and current changelog for any separate CPU decision control.

## What about weather, sunset, coin-toss deferral or conceding the clock?

BigTimeEmpire, maumau78 and CER requested these changes. Read the corresponding controls in
your installed build and the [beta 73 changelog](2k5_mod_studio_changelog.md) for what has landed
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
