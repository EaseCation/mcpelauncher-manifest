0.4.5 adds on-demand game screenshots through the native launcher control channel.
Use mcpywrap 0.5.1, which selects this runtime by default for fresh installations.
The existing screenshot command reads one game framebuffer, without ScreenCaptureKit,
screen-recording permission, a capture daemon, or continuous GPU readback.

Images contain game content and HUD in physical pixels, excluding the launcher
menu and tools. The host CLI encodes PNG; the render thread preserves GL state
and uses bounded anonymous memory. Requests are session-bound, cancellable and
time-limited. macOS video recording and video frame extraction remain unsupported.

Validated with the public CLI on Apple Silicon / macOS 26.6.2 / developer APK
3.9.100.297020: default and background-only captures produced 1440x939 PNGs,
record start returned capability_missing, temporary pixels were released, and
the test world saved and exited. Native tests cover idle behavior, request
isolation, cancellation, timeouts, GL state restoration and file-write failure.

Existing installations can explicitly install this release catalog, then use
run --new. Existing worlds remain bound to their original runtime; upgrading the
CLI does not silently migrate them. User instructions are maintained in the
mcpywrap built-in Skill.

The runtime includes the ARM64 Android compatibility layer, ANGLE Metal, source
Addon loading, client/server debugging, JSON UI reload and world configuration.
It contains no Minecraft APK, game library/assets, worlds or account credentials.
mcpy discovers the current developer APK via NetEase pe and validates its identity,
content digests and native compatibility before selecting it. The corresponding
recursive source archive, licenses and SHA256SUMS accompany this runtime.

The runtime is ad-hoc signed, without a Developer ID certificate or notarization.
Its deployment target is macOS 13; live validation was on macOS 26.6.2. This release
does not claim a new full game acceptance for the 3.10 developer APK or Intel Mac.
