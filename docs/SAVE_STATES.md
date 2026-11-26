# Save states on the ModRetro M64

This page explains why this toolkit cannot add save states (snapshot / restore,
sometimes called "memories" on other handhelds) to a ModRetro M64, what ModRetro
has and has not open-sourced as of late November 2026, and which third-party
projects are worth watching if you want to track this feature.

If you just want in-game saves to your cartridge or Controller Pak, see
[Controller Pak saves vs. save states](#controller-pak-saves-vs-save-states) below
— that part already works on stock firmware and has nothing to do with this
repository.

## Why stock-M64 save states are not possible from this toolkit

The M64 plays N64 games on an **FPGA core** (a Xilinx/AMD Artix UltraScale+ part),
not a software emulator. The live machine state while a game is running — CPU
registers, RSP/RDP state, RDRAM contents — lives entirely inside the FPGA
fabric, loaded from a bitstream that ModRetro has not published.

This repository only reverse-engineers and DFU-flashes the **STM32H7 menu / OS /
UI firmware** — the Cortex-M7 microcontroller that draws menus, reads the SD
card, and loads the FPGA bitstream at boot. See
[`docs/GUIDE.md`](GUIDE.md) for the hardware details. That MCU firmware has no
path into the FPGA's live register and memory state once a game is running, so
no amount of menu-firmware patching from this toolkit can produce a snapshot or
resume-from-anywhere feature.

A real save state requires the FPGA core itself to expose a way to freeze and
read back its internal registers and RAM, and a way to reload them later. That
has to be built into the N64 core design, not the menu firmware around it.

### Controller Pak saves vs. save states

Don't confuse the two:

- **Cartridge / Controller Pak saves** are the game's own in-game save data
  (cartridge SRAM/EEPROM/Flash, or a virtual Controller Pak). This is normal
  save-game functionality and is unrelated to snapshotting the running machine.
- **Save states** snapshot the entire running machine — CPU, RSP, RDP, RDRAM —
  so you can resume from the exact point you stopped, including mid-action,
  without using the game's own save system.

Official firmware **1.26.4** (announced 27 October 2026) added a built-in
virtual Controller Pak, i.e. normal in-game saves, not snapshots
([Reddit announcement](https://www.reddit.com/r/ModRetro/comments/1xgy95r/firmware_1264_is_finally_here/)).
No later 1.27/1.28 changelog adding save states was found as of late November
2026.

## Current official status (as of late November 2026)

ModRetro has released mechanical CAD and electrical schematics for the M64, but
has **not** published the FPGA core or firmware source.

- [`ModRetro/oss-m64-console`](https://github.com/ModRetro/oss-m64-console) is
  still a placeholder: the README says hardware designs are linked and
  "Software: Coming soon!" The tree contains only `LICENSE` and `README.md`.
  Last content push was 13 August 2026.
- [`ModRetro/oss-m64-controller`](https://github.com/ModRetro/oss-m64-controller)
  is likewise "Coming soon!"
- Official support article for the published hardware files:
  [support.modretro.com: M64 open source files](https://support.modretro.com/en_us/articles/m64-open-source-files-ByrpukdUGg)

Timeline of statements about opening the FPGA core:

| Date | Source | What it says |
|---|---|---|
| 23 Apr 2026 | [Ship-timeline blog post](https://modretro.com/blogs/blog/m64-update-and-ship-timelines) | FPGA core would be open-sourced upon launch |
| 2 Jun 2026 | [FPGA deep dive (Robert Peip / FPGAzumSpass)](https://modretro.com/blogs/blog/fpga-development-deep-dive) | A different MiSTer core was ported to M64 as a proof of concept; opening the design is needed for other cores to run. M64's N64 timing issues are described as inherited from the MiSTer core. |
| 24 Jul 2026 | [Official Reddit roadmap post](https://www.reddit.com/r/ModRetro/comments/1v5ji65/launch_update_software_roadmap/) | Open source would roll out after public-facing documentation; shipping was prioritized first |

The [M64 product page](https://modretro.com/products/m64) still markets the
FPGA core and firmware as "open-source." As of late November 2026 that claim is
ahead of what is actually published on GitHub.

Note that ModRetro's Chromatic repos —
[`oss-chromatic-console-fpga`](https://github.com/ModRetro/oss-chromatic-console-fpga)
and
[`oss-chromatic-console-mcu`](https://github.com/ModRetro/oss-chromatic-console-mcu)
— are real, published source, but they're for a **different product** (the
Chromatic, which uses a Gowin FPGA). They are not M64 source and don't run on
the M64's Artix UltraScale+.

Independent reviews agree save states are not out yet:

- A 17 October 2026 comparison on note.com lists save states as supported on
  the Analogue 3D but "Not implemented as of this writing" on the M64
  ([note.com](https://note.com/kao_futa_note/n/n56fcc4742b53?hl=en)).
- Retro Dodo's review (updated 21 July 2026) says the M64 has no save states
  and describes them as "coming after launch"
  ([retrododo.com](https://retrododo.com/modretro-m64-review/)).
- An earlier Retro Dodo post (1 June 2026) mentioned save states among
  features ModRetro had discussed pre-launch, but the actual post-launch
  feature list published in that article does not include them
  ([retrododo.com](https://retrododo.com/official-modretro-m64-launch-after-launch-features-revealed/)).
  Treat "coming after launch" as a widely repeated expectation, not a dated
  official commitment.

## Related open-source / community projects

None of these currently ship working N64 save states on the M64. The table
below is a snapshot as of late November 2026 — check each link for the current
state before assuming anything here still holds.

| Project | Link | Touches M64 save states? |
|---|---|---|
| ModRetro/oss-m64-console | [GitHub](https://github.com/ModRetro/oss-m64-console) | No — placeholder, no core/firmware source published yet |
| OM64 (unofficial firmware) | [Reddit announcement](https://www.reddit.com/r/M64/comments/1wmcc4j/om64_open_m64_custom_firmware/) · [update](https://www.reddit.com/r/M64/comments/1x7eirf/om64_update/) · [Ko-fi](https://ko-fi.com/post/OM64--Open-M64-custom-firmware-D2R127EMXY) | Planned, not shipped; no public repo |
| markus-zzz/m64-misc | [GitHub](https://github.com/markus-zzz/m64-misc) | No — hardware bring-up only, no N64 core |
| MiSTer-devel/N64_MiSTer | [GitHub](https://github.com/MiSTer-devel/N64_MiSTer) | No shipped feature; incomplete scaffolding in source (see below) |
| tortugaveloz/MIRLO64 | [GitHub](https://github.com/tortugaveloz/MIRLO64) | Working save states, but for the **Analogue Pocket**, not the M64 |

Notes on each:

**ModRetro/oss-m64-console.** The repository to watch for when official
core/firmware source actually lands. Until it has real content beyond the
README, there is nothing here to build an M64 save-state feature on.

**OM64.** An unofficial, full replacement firmware for the M64, built from
ModRetro's published schematics rather than from any leaked or official
source. As announced, it has working Game Boy and SNES cores (MiSTer ports,
retargeted to the M64's hardware), and later demos added Neo Geo, CPS 1.5/2,
and PSX. An N64 core was described as "in development" at announcement.
Source and public binaries were still unreleased as of late November 2026; an
open-source beta has been promised once the project's framework (referred to
as WAVE in the October 2026 update) is stable. A 22 September 2026 write-up
([retro-gamer.jp](https://retro-gamer.jp/?p=47679)) reports that saves were
SRAM-only at that time and that save states were planned by the developer —
that specific comment was not independently retrieved from the Reddit thread
itself. Later OM64 update posts checked for this page do not claim working
save states. There is no public GitHub repository for OM64 as of late
November 2026.

**markus-zzz/m64-misc.** An actively developed, Zephyr-based custom firmware
with an example UltraScale+ bitstream built from the published schematics.
As of the version checked, the sample bitstream only does hardware bring-up
(toggling controller-port pins) — there is no N64 core and no save-state
work. Its README warns that flashing it erases the stock firmware.

**MiSTer-devel/N64_MiSTer.** The open FPGA N64 core that ModRetro's own FPGA
deep-dive post credits as the origin of the M64's N64 core (and of its
inherited timing issues). Licensed GPL-3.0. Its README documents cartridge
EEPROM/SRAM/Flash and Controller Pak backup saves, plus 64DD disk saves — it
does not list save states as a feature. There is incomplete save-state RTL in
the source tree (`rtl/savestates.vhd` and `rtl/statemanager.vhd`): in the
version checked in late November 2026, the `saving_savestate` signal is
hard-wired to `'0'`, the `save = '1'` transition is commented out, and the
`SAVEMEMORY_*` save path is commented out, while a load path still exists.
This reads as unfinished scaffolding, not a shipped feature — there is no
dedicated pull request implementing it. For context on how MiSTer save
states normally work, see the
[MiSTer savestate developer API docs](https://mister-devel.github.io/MkDocs_MiSTer/developer/savestates/).
Last commit on the tree checked: 28 September 2026 (UTC).

**tortugaveloz/MIRLO64.** An open FPGA N64 core, but written for the
**Analogue Pocket**, not the M64. Licensed Apache-2.0. Its README states that
"Save states (Sleep/Wake, Memories) are supported" — this is the best
existing *working* open FPGA N64 save-state implementation found during this
research, and a useful reference design. It is not a drop-in for the M64:
porting it would mean a full core port across a different FPGA family,
different memory subsystem, and different video output stack, and it would
replace the official M64 core rather than patch it. No M64 port of MIRLO64
was found. See also a v0.7 write-up at
[retro-gamer.jp](https://retro-gamer.jp/?p=51057).

Two adjacent mentions, included only to avoid confusion:

- The Analogue 3D's "Memories" feature is closed-source. A YouTube comparison
  video calls it "memories, essentially save states" as a point in the 3D's
  favor ([video, ~18:13](https://www.youtube.com/watch?v=oNn0hTl9Bd8)). It is
  not a repository anyone can build on.
- [SummerCart64 save states on original N64 hardware](https://www.reddit.com/r/M64/comments/1wmtz2z/save_states_on_original_n64_hardware_with_the/)
  are implemented flashcart-side on real N64 consoles — they say nothing about
  the M64's FPGA core.

This toolkit itself — a menu/UI firmware patcher — cannot add FPGA save states
under any of the paths above.

## Bottom line

Save states on the M64 are blocked until one of these happens:

1. ModRetro open-sources the FPGA N64 core (and/or ships an official
   save-state update itself), or
2. a third-party N64 core with a finished, working snapshot path is ported to
   the M64's FPGA and shipped as a replacement firmware — for example, if a
   project like OM64 eventually gets there once source exists to build from.

Either way, that is a **different project** from this menu-firmware toolkit.
Do not expect [`docs/GUIDE.md`](GUIDE.md) or the DFU scripts in this repository
to grow a save-state feature — they operate entirely outside the FPGA and have
no access to the running game's machine state.
