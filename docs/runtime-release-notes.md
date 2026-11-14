0.4.11 lets developers choose the offline player name, including Chinese
nicknames, for local worlds and server connections. Use mcpywrap 0.7.7, which
selects this runtime by default for fresh installations and adds
`--player-name` to `run`, `connect` and `--clients 2`.

Local worlds always started as `LocalDev` with user id 0. The launcher now
accepts `--player-name` and `--player-id` for offline worlds. These pass the
identity to `InitOfflinePlayer` and `play_world`, and it is not written to the
instance cppconfig. Without them a world still starts as `LocalDev`. Network
sessions keep taking the identity from cppconfig `player_info`. Combining
`--player-name` with a network session or a custom command list is rejected.

Names may now contain Chinese characters as well as letters, digits and
underscores, up to 16 characters. Quotes, whitespace and control characters are
still rejected before a name is embedded in a game-side expression. The runtime
declares `offline_identity_protocol=1`.

Validated on Apple Silicon / macOS 26.6.2 / developer APK 3.10.100.301421 with a
fresh local world started as `测试玩家`:
- The client and the server-side player list both reported that name.
- After reopening the same world as `Steve_1`, the server reported the new
  name and the host inventory was preserved.

Unit tests cover the default identity, English and Chinese identities for local
worlds and network sessions, and the rejected names.

This release keeps every capability of 0.4.10 (copy-on-write first-launch
assets, per-client developer identity, plain-source network packs, background
window, screenshots, input clock, cppconfig, unauthenticated connections and the
host interfaces used by the built-in Tracy profiler). Existing worlds remain
bound to their original runtime; upgrading the CLI does not silently migrate
them.

The runtime contains no Minecraft APK, game library/assets, worlds or account
credentials. The corresponding recursive source archive, licenses and SHA256SUMS
accompany this runtime. It is ad-hoc signed, without a Developer ID certificate
or notarization. Its deployment target is macOS 13; live validation was on
macOS 26.6.2.
