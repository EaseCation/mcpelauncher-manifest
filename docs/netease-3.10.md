# Developer APK 3.10 compatibility

The optional profile `tools/macos_runtime_profile_3.10.json` selects
`com.netease.mctest` version `3.10.100.299889`. The default build profile remains
3.9; this file changes the default download profile. The same runtime binary and
structural rules can serve both profiles; a separate native adaptation is not required.

```sh
python3 tools/build_macos_runtime.py \
  --profile tools/macos_runtime_profile_3.10.json \
  --output build-macos-arm64/Runtime310.app
python3 tools/package_macos_release.py \
  --runtime build-macos-arm64/Runtime310.app \
  --version 0.4.0-preview.310.1 \
  --output build-macos-arm64/release-310
mcpy --local --non-interactive engine install \
  --catalog build-macos-arm64/release-310/catalog.json --json
```

The installer retrieves the matching official APK when it is not already in
its verified cache. `--apk` remains available for local import. Set
`MCPY_ENGINE_HOME` to isolate the installation from other runtime selections.
Existing worlds retain their pinned runtime; use a new instance for 3.10.
No public download source is implied by this example.

The dispatcher and optional JSON UI/CPython bindings are resolved from the target
ELF by [structural rules](automatic-binary-compatibility.md), without a per-version
address table. Unknown core structures are rejected before selecting an installation;
optional UI recognition failures disable that capability.

The supported development scope is offline Addon worlds, automatic source Mod
initialization, client/server Python, native UI controls, player actions, and
JSON UI definition reload. JSON UI reload requires registering/recreating the
screen and rebinding callbacks. Material and Metal Shader reload remain disabled
in mcpy until independently verified. Online login is not part of this profile.

Use the optional `tests/manual/runtime_controls/run.py` suite in mcpy for game
regression. Test reports and downloaded APK/game data belong in ignored local
build directories, not the repository. Deployment target and signing limits are
unchanged; see [runtime packaging](mcpy-runtime-release.md).
