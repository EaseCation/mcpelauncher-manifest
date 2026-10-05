# Structural compatibility for developer APKs

The launcher recognizes an audited ARM64 instruction family instead of selecting
patch addresses by APK version or ELF hash. One runtime can serve several APK
profiles. Profiles still describe which official APK to download and verify;
this does not automatically discover or approve every future official release.

`tools/analyze_developer_binary.py` reads the target ELF without executing it.
It uses the bundled `developer_binary_rules.json` and Python's standard library:

* Locate the dispatcher by its prologue and normalized full-function digest.
  Address relocations and non-stack data offsets may change; register usage,
  stack layout, instruction order and internal control flow must match.
* Derive the x18 rewrites from the target instructions and audited relative
  rewrite sites. The Darwin adapter still assumes the audited frame/register ABI.
* Resolve optional JSON UI bindings from Python registration names, CPython
  built-in initialization, string references, RTTI, vtables and call relationships.
  Each function must also match its required instruction structure.
* Reject missing or ambiguous core matches. A missing optional UI binding disables
  JSON UI reload independently of core startup.

The generated report records the actual input ELF's SHA-256, file size, discovered
addresses, original instructions and a loaded-code checksum. These hashes bind a
report to its input; they are not compatibility allowlists. The native launcher
independently verifies that identity, loaded code and rewrite preconditions before
applying the plan. Reports are local derived data, not executable update scripts.

mcpy runtimes advertise `game_compatibility.elf_rules_schema = 1`, their package/ABI
and rule digest. The installer runs structural analysis before changing the selected
installation and caches the report outside the signed application and game resources.
Failure returns `unsupported_engine_structure` with a diagnostic path, retaining the
previous selection. Existing world instances keep their pinned runtime and APK.
Older runtimes without this contract still require exact profile equality.

## Reproducing and extending rules

```sh
python3 tools/analyze_developer_binary.py /path/to/libminecraftpe.so \
  --output /tmp/developer-compatibility.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

`tools/learn_developer_rules.py` is a maintainer-only trainer requiring Capstone and
an audited baseline. Its baseline addresses never ship as runtime lookup tables.
The exported rules account for all 470 x18 uses in the audited dispatcher, including
17 special adapters, and verify the spare SIMD register assumption. New compiler
or frame layouts require another audit; do not relax checks merely to make an
unrecognized APK launch.

Rules were learned from developer APK 3.9 and exercised against 3.10. The first
3.10 check matched the dispatcher but rejected the optional thread singleton's cold
initialization. The thread rule was refined to check its hot return ABI and shared
thread-identity call, then regenerated from 3.9 without adding 3.10 addresses.
Consequently this is a cross-version validation, not an untouched blind holdout.

Use mcpy's optional `tests/manual/runtime_controls/run.py` for real-game regression.
Also verify JSON UI definition changes after recreating a custom screen; a queued
reload response alone is insufficient. Keep downloaded binaries and local reports
in ignored build directories. No APK or game assets are part of the runtime release.
