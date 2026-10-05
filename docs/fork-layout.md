# Public fork and submodule layout

The default adaptation branch in each EaseCation fork is
`codex/netease-macos-arm64`. Upstream branches and license files are retained;
this branch contains the developer-runtime changes. All submodules use committed
Git links rather than tracking a moving branch.

| Repository | Original upstream | Purpose |
|---|---|---|
| EaseCation/mcpelauncher-manifest | minecraft-linux/mcpelauncher-manifest | Build, package, test and integrate the runtime |
| EaseCation/mcpelauncher-client | minecraft-linux/mcpelauncher-client | Developer APK/JNI, arm64 compatibility, Python and UI control |
| EaseCation/libc-shim | minecraft-linux/libc-shim | Host/Android libc compatibility |
| EaseCation/mcpelauncher-linker | minecraft-linux/mcpelauncher-linker | Pin the adapted bionic submodule |
| EaseCation/android_bionic | minecraft-linux/android_bionic | Correct 16 KiB segment-end alignment |
| EaseCation/simple-ipc | MCMrARM/simple-ipc | Complete nonblocking socket writes without truncating large results |

All other direct submodules remain at their upstream URLs and original commits.
The linker's `core` submodule continues to use `minecraft-linux/android_core`.
Absolute URLs prevent a fork's relative paths from accidentally resolving to
nonexistent repositories under EaseCation.

```sh
git clone --recurse-submodules https://github.com/EaseCation/mcpelauncher-manifest.git
# In an existing checkout after pulling changes:
git submodule sync --recursive
git submodule update --init --recursive
```

For future changes, push the deepest modified submodule first, commit its new
Git link in its parent, then push the parent. Keep a local `upstream` remote for
the original repository and `origin` for the EaseCation fork when contributing.
Do not update unrelated submodule revisions as part of a runtime release.

On case-insensitive macOS filesystems, AOSP bionic contains pairs such as
`xt_CONNMARK.h` and `xt_connmark.h` that cannot coexist faithfully in one working
tree. Git may therefore report eight header changes immediately after checkout.
These are not adaptation patches and must not be staged. The bionic fork changes
only `linker/linker_phdr.cpp`. The source packager preserves both original Git
entries when exporting corresponding source.

Game APKs, game binaries/assets, worlds, private authentication inputs and local
build/test output are not part of the adaptations. Original licenses remain in
the component repositories. Distribute the corresponding source with runtime
binaries; see [runtime packaging](mcpy-runtime-release.md).
