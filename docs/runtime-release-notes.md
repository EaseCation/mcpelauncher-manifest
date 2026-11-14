0.4.9 lets two macOS clients join the same development server. Use mcpywrap
0.7.5, which selects this runtime by default for fresh installations; `mcpy
connect <host> --port <port> --clients 2` then starts both players with distinct
anonymous developer identities.

mcpy already assigns each dual-client role its own identity and writes it to the
session cppconfig as `player_info`, but the launcher joined every network session
as `LocalDev` with user id 0. Two clients therefore shared a name and UUID, and
the server disconnected the first one as logged in elsewhere. The launcher now
passes `player_info` to `InitOfflinePlayer` and `join_world`. The identity must be
an integer user id between 1 and 2^31-1 and a 1–16 character name of letters,
digits or underscores; anything else is rejected before launch instead of being
embedded in the game-side expression. Without `player_info` a session still
joins as `LocalDev`, so single-client behavior is unchanged. The capability is
declared as `developer_identity_protocol=1`.

Validated on Apple Silicon / macOS 26.6.2 / developer APK 3.10.100.301421 against
a local Nemisys + SynapseAPI + Nukkit server: two clients from one `--clients 2`
group joined with different names and UUIDs, stayed connected through repeated
group restarts and exchanged real melee hits for a recorded comparison. Unit
tests cover the default identity, a distinct identity from cppconfig and invalid
or injected identities.

This release keeps every capability of 0.4.8 (plain-source network packs,
background window, screenshots, input clock, cppconfig, unauthenticated
connections and the host interfaces used by the built-in Tracy profiler).
Existing worlds remain bound to their original runtime; upgrading the CLI does
not silently migrate them.

The runtime contains no Minecraft APK, game library/assets, worlds or account
credentials. The corresponding recursive source archive, licenses and SHA256SUMS
accompany this runtime. It is ad-hoc signed, without a Developer ID certificate
or notarization. Its deployment target is macOS 13; live validation was on
macOS 26.6.2.
