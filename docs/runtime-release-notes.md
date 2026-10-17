0.4.4 fixes `missing_monotonic_clock` for mcpy unified game input on macOS.
The native launcher now exposes a steady clock to the game's Python 2 interpreter.
The game-owned float constructor is resolved through verified CPython structural
rules; missing or ambiguous bindings keep the clock disabled without disabling UI reload.

Use with mcpywrap 0.4.6, which selects this runtime for new installations. Existing
installations must explicitly install this release catalog and create a new instance
with `run --new`; upgrading the CLI does not change existing world bindings.

Validated on Apple Silicon / macOS 26.6.2 / developer APK 3.9.100.297020: eight live
cases passed, covering idle/pause timing, three overlapping movement/jump cases,
modifier-key cancellation, attacks while moving, chat navigation and UI clicking.
Server-side attack damage was confirmed (health 100 -> 95). Structural compatibility
also passed for 3.10.100.299889; its full input suite was not run for this release.
All test sessions were saved and stopped. No system clock changes were made.

Native Apple Silicon runtime for mcpy's local Minecraft China developer worlds.
Includes the Android compatibility layer, ANGLE Metal, source Addon loading,
client/server debugging, JSON UI reload, instance cppconfig and keyboard input fixes.

The runtime archive contains no Minecraft APK, game library, game assets, worlds,
or account credentials. mcpy downloads the current developer APK discovered via NetEase pe. It validates the APK identity,
records content digests and checks native structure compatibility before selecting
the installation. Existing local worlds retain their installed version. The corresponding recursive
source archive, licenses and SHA256SUMS accompany this runtime.

This runtime is ad-hoc signed, not Developer ID notarized. Deployment target is
macOS 13; actual game validation was performed on macOS 26.6.2. Windows continues
to use a manually installed MC Studio environment.
