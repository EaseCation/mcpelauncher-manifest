# EaseCation macOS developer runtime fork

This public fork adds an Apple Silicon macOS runtime for the supported NetEase
Minecraft developer APK. The original launcher and third-party license notices
are retained. Game APKs, libraries, assets, accounts and worlds are not included.

```sh
git clone --recurse-submodules https://github.com/EaseCation/mcpelauncher-manifest.git
cd mcpelauncher-manifest
python3 tools/build_macos_runtime.py --output build-macos-arm64/McpyRuntime.app
```

The adaptation branch is `netease-macos-arm64` (the fork's default branch).
Submodules are pinned by commit: modified components use the public EaseCation
forks; unchanged components continue to use their original upstream repositories.
See [fork layout](docs/fork-layout.md), [runtime packaging](docs/mcpy-runtime-release.md)
and [offline developer worlds](docs/netease-dev-offline.md).

The build requires Apple Silicon, Xcode command-line tools, Python, CMake and
Ninja. The built runtime does not require Homebrew or another installed Launcher.
Online authentication experiments under `tools/netease_auth` are optional and
not part of the offline build; their Dart dependency is a separately supplied
sibling checkout. Do not use these experiments as a supported login flow.

The inherited launcher documentation follows.

---

# mcpelauncher

An unstable unofficial launcher for the Android version of Minecraft: Bedrock Edition on linux and macOS.

# UI

The User Interface to login, download and manage Versions can be found [here](https://github.com/minecraft-linux/mcpelauncher-ui-manifest)

# System Requirements

> [!WARNING]
> Once the new OpenGL ES 3.1 system requirement for "Vibrant Visuals" aka "Deferred Technical Preview" of 31. March 2025 no longer allow the game to start using classic "Fancy" Graphics on OpenGL ES 3.0 the **macOS port Minecraft updates are going to be on hold**

Operating System|Architecture|Requirements|Minecraft Versions
---|---|---|---
linux glibc|x86|Intel or Amd CPU with SSSE3 Instruction Set and OpenGL ES 2.0 or newer.|1.13.0 - 1.20.20
linux glibc|x86|Intel or Amd CPU with SSSE3 Instruction Set and OpenGL ES 3.0 or newer.|1.13.0 - 1.21.73
macOS 10.10 - 10.14|x86|Intel or Amd CPU with SSSE3 Instruction Set.|1.13.0 - 1.16.1X
linux glibc|x86_64|Intel or Amd CPU with SSSE3, SSE4.1, SSE4.2,  POPCNT Instruction Sets and OpenGL ES 2.0 or newer.|1.13.0 - 1.20.20
linux glibc|x86_64|Intel or Amd CPU with SSSE3, SSE4.1, SSE4.2, POPCNT Instruction Sets and OpenGL ES 3.0 or newer.|1.13.0 - 1.21.73
macOS 10.10 - latest|x86_64|Intel or Amd CPU with SSSE3, SSE4.1, SSE4.2 and POPCNT Instruction Sets. Rosetta 2 worked in macOS 11 and 12, but no longer in macOS 13|1.13.0 - 1.21.73
linux glibc|arm32|armv7 CPU, pulseaudio and OpenGL ES 2.0 or newer|1.13.0 - 1.18.10
linux glibc|arm64|armv7 CPU, pulseaudio and OpenGL ES 3.0 or newer|1.13.0 - 1.21.73
linux glibc|arm64|armv8 CPU, pulseaudio and OpenGL ES 2.0 or newer|1.13.0 - 1.20.20
linux glibc|arm64|armv8 CPU, pulseaudio and OpenGL ES 3.0 or newer|1.13.0 - 1.21.73
macOS 11.0 - latest|arm64|apple m series CPU (Experimental, modding limitations)|1.19.70 - 1.21.73

## Versions 1.20.30+ will not have hardware rendering on older hardware (GLES 3.0 is now required)

Read Issue https://github.com/minecraft-linux/mcpelauncher-manifest/issues/933 to force software rendering to be able to run them anyway

For mesa3d this would be defining `LIBGL_ALWAYS_SOFTWARE` to `1` of the launcher process. Alternatively you can replace your libEGl drivers with <https://github.com/google/angle/> and tell it to use the swiftshader backend.

# Important Minecraft Version specific Bugs

Minecraft Version|Bug Description
---|---
1.13.0 - 1.16.1X|Xbox login doesn't work. It is working in previous Versions of this Launcher.
1.16.20 - latest|No sound for macOS x86 launcher without compiling yourself with pulseaudio
1.16.210 - 1.17.4X|Crafting is broken on x86 and x86_64 based devices
1.16.210 - 1.17.4X|Textures are off by one on x86 and x86_64 based devices, enable texture patch in profile settings to mitigate this Bug
1.16.210 - 1.17.4X|World Corruption while next to water
1.18.30 - latest|The armv7 port might not work correctly
1.19.50 - latest|You cannot sprint while diagonal strafing on Intel cpu (see [MCPE-170810](https://bugs.mojang.com/browse/MCPE-170810))
all|You are unable to receive Xbox live game invites
all|You may be unable to join worlds hosted by this launcher using Xbox live friends joining

# Wiki

Please check our wiki https://minecraft-linux.github.io for information about compiling or installing this launcher.
The old wiki of readthedocs is obsolete.

# Nightly Prebuilds

[AppImage (Deprecated) and DMG Files](https://github.com/minecraft-linux/mcpelauncher-manifest/releases/tag/nightly)
[Debian, Ubuntu and Fedora Packages (ca. 1-24h delay)](https://github.com/minecraft-linux/pkg?tab=readme-ov-file#nightly)
[flatpak install flathub-beta io.mrarm.mcpelauncher (ca. 1-24h delay)](https://discourse.flathub.org/t/how-to-use-flathub-beta/2111)
