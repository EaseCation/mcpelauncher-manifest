0.5.0 adds an AArch64 Linux runtime next to the Apple Silicon macOS one. Use a
mcpywrap version with the `linux-arm64` backend; it selects
`catalog-linux-arm64.json` from this release for fresh Linux installations.

The developer APK runs natively on AArch64 Linux, whose calling convention
matches Android: the x18 rewrite, variadic compat libc, jitless V8 and ANGLE
that macOS needs are not used, and graphics go through the host EGL/GLES via
GLFW on Wayland or X11. The runtime needs glibc 2.35 or newer (Ubuntu 22.04,
Debian 12 or later), a GLES 3 driver and a 4 KiB or 16 KiB page kernel.
OpenSSL, curl, libstdc++ and libgcc are linked statically; the launcher needs
only libc, libm and libz. It is not signed; integrity comes from the SHA-256
manifest.

Linux has no seatbelt that keeps mcpy's per-process port checks intact, so the
launcher guards the network calls of game code in process: offline worlds may
reach only loopback, and unauthenticated sessions additionally the resolved
server endpoint. This is not a kernel sandbox. The engine's Tracy stays local
on 127.0.0.1:8086 and its perf-based system sampling is off by default.

Fixes found while porting, shared with macOS where relevant: libc-shim maps
every Bionic scheduling policy instead of aborting on SCHED_FIFO; the
SIZE_MAX vsprintf rewrite is limited to macOS (on glibc it wrote nothing and
broke every Python bridge request); GLFW initialization errors include the
platform reason.

Validated on a Raspberry Pi 5 (Debian 13, 16 KiB pages, V3D 7.1, Mesa 26.2,
headless Wayland) with developer APK 3.10.100.301421: installation from the
official APK channel, offline worlds with addon systems on both sides, Python
hot reload, JSON UI reload requests, screenshots, save-before-exit, Tracy
capture, and an unauthenticated join to a Nemisys/Nukkit test server with
server-delivered `.mcp` and plain-source packs. The glibc 2.35 build from CI
was run on the same device.

The runtime contains no Minecraft APK, game library/assets, worlds or account
credentials. The corresponding recursive source archive, licenses and
SHA256SUMS accompany each platform's runtime. Existing macOS worlds remain
bound to their original runtime.
