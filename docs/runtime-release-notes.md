0.4.8 lets network sessions load plain-source behavior packs delivered by a
development server. Use mcpywrap 0.6.5, which selects this runtime by default for
fresh installations and reports `plain_source_packs` in connect results.

The developer APK's MCP importer resolves only packed `.mcs` modules, so a pack
served as plain `.py` files failed with ImportError. Before joining, the runtime
now installs a source importer that handles only packs in the session's pack
cache which contain Python sources and no `.mcp`, `.mcs` or compiled files.
Reviewed `.mcp` packs, mixed packs and every other import path stay with the
game's own importer. Loaded packs are logged as `[PlainSourcePack]`; release
clients still require a reviewed `.mcp`, so a plain pack running on a development
server does not make it publishable. No local source directory is read and no
server-delivered content is replaced. The capability is declared as
`network_plain_source_protocol=1`.

Validated on Apple Silicon / macOS 26.6.2 / developer APK 3.9.100.297020 against
a local Nemisys + SynapseAPI + Nukkit server delivering both a reviewed `.mcp`
pack and a plain-source pack: the plain pack initialized from its delivered
sources while the `.mcp` pack loaded through the game importer as before. A
Python 2 behavior test covers archives, mixed packs, paths outside the session
cache, symlink escapes, bytecode suppression and idempotent installation.

This release keeps every capability of 0.4.7 (background window, screenshots,
input clock, cppconfig, unauthenticated connections and the host interfaces used
by the built-in Tracy profiler). Existing worlds remain bound to their original
runtime; upgrading the CLI does not silently migrate them.

The runtime contains no Minecraft APK, game library/assets, worlds or account
credentials. The corresponding recursive source archive, licenses and SHA256SUMS
accompany this runtime. It is ad-hoc signed, without a Developer ID certificate
or notarization. Its deployment target is macOS 13; live validation was on
macOS 26.6.2.
