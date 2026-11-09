#!/usr/bin/env python3
"""Build a relocatable, game-free AArch64 Linux runtime (clang/CMake/Ninja required).

The runtime links OpenSSL, curl, libstdc++ and libgcc statically. Graphics, audio and
windowing libraries (EGL/GLES, Wayland/X11, ALSA/PulseAudio) are loaded from the host at
run time, so the only hard requirements are glibc and a GLES 3 capable driver.

Build on the oldest supported glibc (the release workflow uses ubuntu-22.04-arm); the audit
rejects binaries that need newer GLIBC symbol versions than --minimum-glibc.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from build_macos_runtime import SOURCES as MACOS_SOURCES, digest, download, extract, run  # noqa: E402

SOURCES = {name: MACOS_SOURCES[name] for name in ('openssl-3.6.3.tar.gz', 'curl-8.21.0.tar.gz')}
# 只允许依赖 glibc 自身与几乎所有发行版都具备的基础库；图形/音频/窗口库由 GLFW/SDL 运行时 dlopen。
ALLOWED_NEEDED = {'libc.so.6', 'libm.so.6', 'libdl.so.2', 'libpthread.so.0', 'librt.so.1',
                  'ld-linux-aarch64.so.1', 'libz.so.1', 'libatomic.so.1'}
ADAPTER_FILES = ('run_netease_dev.py', 'netease_source_loader.py', 'netease_network_sources.py',
                 'analyze_developer_binary.py', 'inspect_android_elf.py', 'developer_binary_rules.json',
                 'netease_cppconfig.py')
LICENSE_DIRECTORIES = ('libjnivm', 'libc-shim', 'mcpelauncher-linker', 'game-window', 'file-picker', 'file-util',
                       'logger', 'base64', 'properties-parser', 'arg-parser', 'sdl3', 'imgui', 'simple-ipc',
                       'daemon-utils', 'msa-daemon-client', 'cll-telemetry', 'axml-parser', 'mcpelauncher-apkinfo')


def version_tuple(value):
    return tuple(int(x) for x in value.split('.'))


def elf_audit(stage, minimum_glibc):
    """检查 ELF 架构、动态依赖白名单和 GLIBC 符号版本上限；只读取文件，不执行。"""
    records = []
    limit = version_tuple(minimum_glibc)
    for path in sorted(stage.rglob('*')):
        if not path.is_file() or path.read_bytes()[:4] != b'\x7fELF':
            continue
        relative = str(path.relative_to(stage))
        if relative.startswith('share/mcpelauncher/lib/'):
            continue  # Android ABI 的兼容库由运行包内 linker 加载，不受宿主 glibc 约束
        header = subprocess.check_output(['readelf', '-h', str(path)], text=True, env=dict(os.environ, LC_ALL='C'))
        if 'AArch64' not in header or 'ELF64' not in header:
            raise ValueError('Unexpected runtime architecture: ' + relative)
        dynamic = subprocess.check_output(['readelf', '-d', str(path)], text=True, env=dict(os.environ, LC_ALL='C'))
        needed = sorted(re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]', dynamic))
        unexpected = [name for name in needed if name not in ALLOWED_NEEDED]
        if unexpected:
            raise ValueError('Nonportable shared library dependency in %s: %s' % (relative, ', '.join(unexpected)))
        if re.search(r'\((RPATH|RUNPATH)\)', dynamic):
            raise ValueError('Runtime binaries must not embed RPATH/RUNPATH: ' + relative)
        versions = subprocess.check_output(['readelf', '--version-info', '-W', str(path)], text=True,
                                           env=dict(os.environ, LC_ALL='C'))
        glibc = sorted({version_tuple(v) for v in re.findall(r'GLIBC_([0-9]+(?:\.[0-9]+)+)', versions)})
        if glibc and glibc[-1] > limit:
            raise ValueError('%s requires GLIBC_%s, newer than the %s baseline'
                             % (relative, '.'.join(map(str, glibc[-1])), minimum_glibc))
        records.append({'file': relative, 'arch': 'aarch64', 'needed': needed,
                        'max_glibc': '.'.join(map(str, glibc[-1])) if glibc else None, 'sha256': digest(path)})
    if not any(record['file'] == 'bin/mcpelauncher-client' for record in records):
        raise ValueError('Runtime client binary missing from audit')
    return records


def build_openssl(deps, work, jobs, env):
    ssl = deps/'openssl'
    stamp = ssl/'mcpy-build.json'
    recipe = {'source_sha256': SOURCES['openssl-3.6.3.tar.gz'][1], 'arch': 'aarch64', 'target': 'linux-aarch64'}
    if stamp.is_file() and json.loads(stamp.read_text()) == recipe:
        return ssl
    source = deps/'openssl-3.6.3'
    with (work/'openssl-build.log').open('w') as log:
        run(['perl', 'Configure', 'linux-aarch64', 'no-shared', 'no-tests', 'no-docs', '--prefix=' + str(ssl),
             '--libdir=lib'], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        run(['make', '-j' + str(jobs)], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        run(['make', 'install_sw'], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    stamp.write_text(json.dumps(recipe, indent=2) + '\n')
    return ssl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT/'build-linux-arm64/portable')
    parser.add_argument('--output', type=Path, default=ROOT/'build-linux-arm64/McpyRuntime')
    parser.add_argument('--build-dir', type=Path, help='Reuse an existing CMake build directory')
    parser.add_argument('--minimum-glibc', default='2.35', help='Oldest glibc the audit accepts (default: Ubuntu 22.04)')
    parser.add_argument('--profile', type=Path, default=ROOT/'tools/linux_runtime_profile.json',
                        help='Verified APK compatibility profile embedded into this runtime')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    args = parser.parse_args()
    if not sys.platform.startswith('linux') or platform.machine() != 'aarch64':
        parser.error('Build on an AArch64 Linux host; cross builds are not supported')
    work, output = args.work_dir.resolve(), args.output.resolve()
    if output.exists() or output.name != 'McpyRuntime':
        parser.error('--output must be a new directory named McpyRuntime; active runtimes are never overwritten')
    # 允许 CI 指定较新的 clang（例如 Ubuntu 22.04 的 clang-15）。
    cc, cxx = os.environ.get('CC', 'clang'), os.environ.get('CXX', 'clang++')
    for tool in (cc, cxx, 'cmake', 'ninja', 'perl', 'make', 'readelf', 'strip'):
        if not shutil.which(tool):
            parser.error('Missing build tool: ' + tool)
    deps = work/'deps'
    deps.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CC=cc, CXX=cxx)
    for name in SOURCES:
        source = download(name, deps)
        if not (deps/name.removesuffix('.tar.gz')).exists():
            extract(source, deps)
    ssl = build_openssl(deps, work, args.jobs, env)
    # FindOpenSSL 的静态链接参数来自 pkg-config；优先使用自建 OpenSSL 的 .pc，避免拾取宿主
    # libssl-dev 的依赖（如 -lzstd）。其他库（Wayland 等）仍从系统 pkg-config 路径查找。
    env['PKG_CONFIG_PATH'] = os.pathsep.join(filter(None, [str(ssl/'lib/pkgconfig'), env.get('PKG_CONFIG_PATH')]))
    # Advertise these protocols only when every native implementation is present.
    for source, marker in (('game-window/src/window_glfw.cpp', 'MCPY_GAME_BACKGROUND'),
                           ('mcpelauncher-client/src/window_callbacks.cpp', 'MCPY_GAME_BACKGROUND'),
                           ('mcpelauncher-client/src/developer_network_guard.h', 'DeveloperNetworkGuard'),
                           ('mcpelauncher-client/CMakeLists.txt', 'developer_screenshot.cpp')):
        if marker not in (ROOT/source).read_text():
            raise RuntimeError('Missing Linux runtime source patch: ' + source)
    build = args.build_dir.resolve() if args.build_dir else work/'client'
    link_flags = '-static-libstdc++ -static-libgcc -Wl,--as-needed'
    config = ['cmake', '-S', ROOT, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
              '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', '-DGAMEWINDOW_SYSTEM=GLFW',
              '-DENABLE_DEV_PATHS=OFF', '-DBUILD_UI=OFF', '-DBUILD_WEBVIEW=OFF', '-DENABLE_ERROR_WINDOW=OFF',
              '-DXAL_WEBVIEW_USE_QT=OFF', '-DBUILD_COMPAT_TESTS=ON', '-DUSE_OWN_CURL=ON', '-DNO_OPENSSL=OFF',
              '-DCMAKE_EXE_LINKER_FLAGS=' + link_flags,
              '-DOPENSSL_USE_STATIC_LIBS=TRUE', '-DOPENSSL_ROOT_DIR=' + str(ssl),
              '-DOPENSSL_INCLUDE_DIR=' + str(ssl/'include'), '-DOPENSSL_CRYPTO_LIBRARY=' + str(ssl/'lib/libcrypto.a'),
              '-DOPENSSL_SSL_LIBRARY=' + str(ssl/'lib/libssl.a'), '-DOWN_CURL_SOURCE_DIR=' + str(deps/'curl-8.21.0'),
              '-DCURL_EXT_EXTRA_OPTIONS=-DOPENSSL_USE_STATIC_LIBS=TRUE;-DCURL_USE_OPENSSL=ON']
    with (work/'client-build.log').open('w') as log:
        run(config, env=env, stdout=log, stderr=subprocess.STDOUT)
        run(['cmake', '--build', build, '--target', 'mcpelauncher-client', 'libc-compat-smoke', 'libc-host-info-test',
             'netease-auth-bridge-test', 'ipc-large-write', 'developer-screenshot-test',
             'developer-network-guard-test', '--parallel', str(args.jobs)], env=env, stdout=log, stderr=subprocess.STDOUT)
    run(['ctest', '--test-dir', build, '--output-on-failure'])
    stage = output.with_name(output.name + '.staging')
    if stage.exists():
        parser.error('Remove or inspect stale staging directory first: ' + str(stage))
    (stage/'bin').mkdir(parents=True)
    client = stage/'bin/mcpelauncher-client'
    shutil.copy2(build/'mcpelauncher-client/mcpelauncher-client', client)
    # 保留符号表供崩溃回溯，去掉调试段以缩小下载体积。
    run(['strip', '--strip-debug', client])
    client.chmod(0o755)
    # Only the support ELF needed by this backend; never copy native FMOD, game libraries,
    # APKs, worlds or assets into the runtime.
    support = stage/'share/mcpelauncher/lib/arm64-v8a'
    support.mkdir(parents=True)
    shutil.copy2(ROOT/'mcpelauncher-linux-bin/lib/arm64-v8a/libsqliteX.so', support/'libsqliteX.so')
    mappings = build/'gamecontrollerdb/gamecontrollerdb.txt'
    if mappings.is_file():
        shutil.copy2(mappings, stage/'share/mcpelauncher/gamecontrollerdb.txt')
    resources = stage/'resources'
    adapter = resources/'launcher'
    adapter.mkdir(parents=True)
    for name in ADAPTER_FILES:
        shutil.copy2(ROOT/'tools'/name, adapter/name)
    licenses = resources/'licenses'
    licenses.mkdir()
    shutil.copy2(ROOT/'mcpelauncher-linux-bin/README.md', licenses/'mcpelauncher-linux-bin-README.md')
    for directory in (ROOT, *(ROOT/x for x in LICENSE_DIRECTORIES), deps/'openssl-3.6.3', deps/'curl-8.21.0',
                      build/'_deps/glfw3_ext-src', build/'_deps/nlohmann_json_ext-src'):
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                shutil.copy2(path, licenses/(directory.name + '-' + path.name))
    for path in stage.rglob('*'):
        if path.is_symlink():
            raise ValueError('Runtime links are not supported: ' + str(path))
        if path.is_file() and path != client:
            path.chmod(0o644)
    binaries = elf_audit(stage, args.minimum_glibc)
    metadata = {'schema': 1, 'platform': 'linux-arm64', 'minimum_glibc': args.minimum_glibc,
                'client_python_protocol': 1, 'json_ui_reload_protocol': 1, 'input_monotonic_clock_protocol': 1,
                'screenshot_protocol': 1, 'background_window_protocol': 1,
                'launch_protocol': 1, 'addon_link_protocol': 1, 'cppconfig_protocol': 1, 'network_connect_protocol': 1,
                'network_plain_source_protocol': 1, 'network_guard_protocol': 1,
                'graphics': {'api': 'GLES 3', 'window_system': 'GLFW (Wayland, X11)'},
                'game_compatibility': {'elf_rules_schema': 1, 'package_name': 'com.netease.mctest', 'abi': 'arm64-v8a',
                                       'rules_sha256': digest(ROOT/'tools/developer_binary_rules.json')},
                'game_profile': json.loads(args.profile.read_text()),
                'minimum_os_runtime_tested': False, 'signing': 'none; verified by SHA-256 integrity manifest',
                'sources': SOURCES,
                'manifest_commit': (json.loads((ROOT/'SOURCE_STATE.json').read_text())['root_commit']
                                    if (ROOT/'SOURCE_STATE.json').is_file()
                                    else subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()),
                'working_tree_modified': bool(subprocess.run(['git', 'diff', '--quiet', 'HEAD'], cwd=ROOT).returncode),
                'binaries': [{k: v for k, v in record.items() if k != 'sha256'} for record in binaries]}
    (resources/'runtime.json').write_text(json.dumps(metadata, indent=2) + '\n')
    stage.rename(output)
    integrity = {'runtime': output.name, 'binaries': binaries,
                 'files': {path.relative_to(output).as_posix(): digest(path)
                           for path in sorted(output.rglob('*')) if path.is_file()}}
    output.with_name('McpyRuntime.integrity.json').write_text(json.dumps(integrity, indent=2) + '\n')
    print('Runtime:', output)


if __name__ == '__main__':
    main()
