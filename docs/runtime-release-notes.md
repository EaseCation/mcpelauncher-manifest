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
