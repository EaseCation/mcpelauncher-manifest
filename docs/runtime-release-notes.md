0.4.10 stops every world instance and network session from keeping its own
~400 MB copy of the game's built-in assets. Use mcpywrap 0.7.6, which selects
this runtime by default for fresh installations and also clones `vanilla.mcp`
into new data directories.

On the first launch of each data directory the game asks the launcher, through
`copyInnerAssetDir`, to copy the `storge/asset` tree out of the extracted APK.
The launcher did a plain recursive copy, so every instance stored an identical
copy of the shared engine's assets. Regular files are now copy-on-write clones
(`clonefile` on APFS, `FICLONE` on Linux) with the same merge and overwrite
behavior. The game can still modify its copy without affecting the shared
engine. Volumes that cannot clone, such as non-APFS or cross-volume
destinations, fall back to a normal copy. The engine log reports how many files
were cloned and copied. Nothing in the launch protocol changes, so no new
capability is declared.

Validated on Apple Silicon / macOS 26.6.2 / developer APK 3.10.100.301421: a
fresh data directory logged `cloned 132, copied 0`. Deleting the resulting 406
MB `storge` tree freed 104 KB of disk space, compared with 26 MB for a plainly
copied `vanilla.mcp`.

This release keeps every capability of 0.4.9 (per-client developer identity,
plain-source network packs, background window, screenshots, input clock,
cppconfig, unauthenticated connections and the host interfaces used by the
built-in Tracy profiler). Existing worlds remain bound to their original
runtime, and data directories that already hold copied assets are not changed;
only first launches with this runtime use clones.

The runtime contains no Minecraft APK, game library/assets, worlds or account
credentials. The corresponding recursive source archive, licenses and SHA256SUMS
accompany this runtime. It is ad-hoc signed, without a Developer ID certificate
or notarization. Its deployment target is macOS 13; live validation was on
macOS 26.6.2.
