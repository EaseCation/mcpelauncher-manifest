#!/usr/bin/env python3
"""Build a relocatable, game-free macOS arm64 runtime (Xcode/CMake/Ninja required).

OpenSSL/curl are built from pinned sources. ANGLE is taken from a verified
upstream release, not an application installed on the build machine.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'openssl-3.6.3.tar.gz': (
        'https://github.com/openssl/openssl/releases/download/openssl-3.6.3/openssl-3.6.3.tar.gz',
        '243a86649cf6f23eeb6a2ff2456e09e5d77dd9018a54d3d96b0c6bdd6ba6c7f1'),
    'curl-8.21.0.tar.gz': (
        'https://github.com/curl/curl/releases/download/curl-8_21_0/curl-8.21.0.tar.gz',
        'd9b327997999045a24cda50f3983e69e51c516bd8be6ef9842fc7f99135e33bb'),
    'upstream-launcher-v1.8.5.dmg': (
        'https://github.com/minecraft-linux/macos-builder/releases/download/v1.8.5/Minecraft.Bedrock.Launcher.dmg',
        '1faa08ed77f998a4c049b597300525761c5543209de5e51199ab32aa611197f4'),
    'angle-LICENSE': (
        'https://raw.githubusercontent.com/minecraft-linux/angle/c7068f790980/LICENSE',
        'bf4da21bd20bcfb5b60b7ecc67fa864a79be049e21d6178076887f178dd6c71a'),
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def download(name, directory):
    url, expected = SOURCES[name]
    target = directory / name
    if target.is_file() and digest(target) == expected:
        return target
    part = target.with_suffix(target.suffix + '.part')
    print('Downloading', name, flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, part.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    if digest(part) != expected:
        raise ValueError('Download checksum mismatch: ' + name)
    part.replace(target)
    return target


def extract(source, directory):
    # filter=data rejects archive links/path traversal outside the destination.
    with tarfile.open(source) as archive:
        archive.extractall(directory, filter='data')


def audit(app, minimum):
    records = []
    for path in sorted(app.rglob('*')):
        if not path.is_file():
            continue
        kind = subprocess.check_output(['file', '-b', str(path)], text=True)
        if 'Mach-O' not in kind:
            continue
        architectures = subprocess.check_output(['lipo', '-archs', str(path)], text=True).strip()
        if architectures != 'arm64':
            raise ValueError('Unexpected runtime architecture: ' + str(path))
        dependencies = subprocess.check_output(['otool', '-L', str(path)], text=True)
        for line in dependencies.splitlines()[1:]:
            dependency = line.strip().split(' (', 1)[0]
            if not dependency.startswith(('/usr/lib/', '/System/Library/', '@rpath/', '@loader_path/', '@executable_path/')):
                raise ValueError('Nonportable dylib dependency: ' + dependency)
        commands = subprocess.check_output(['otool', '-l', str(path)], text=True).splitlines()
        versions = [line.split()[1] for line in commands if line.strip().startswith('minos ')]
        if not versions or any(tuple(map(int, v.split('.'))) > tuple(map(int, minimum.split('.'))) for v in versions):
            raise ValueError('Unexpected deployment target: ' + str(path) + ': ' + str(versions))
        records.append({'file': str(path.relative_to(app)), 'arch': architectures, 'minos': versions, 'sha256': digest(path)})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'build-macos-arm64/portable')
    parser.add_argument('--output', type=Path, default=ROOT / 'build-macos-arm64/McpyRuntime.app')
    parser.add_argument('--build-dir', type=Path, help='Reuse an existing CMake build directory')
    parser.add_argument('--minimum-macos', default='11.0', choices=['11.0', '12.0', '13.0', '14.0', '15.0'])
    parser.add_argument('--profile', type=Path, default=ROOT/'tools/macos_runtime_profile.json',
                        help='Verified APK compatibility profile embedded into this runtime')
    parser.add_argument('--jobs', type=int, default=6)
    args = parser.parse_args()
    work, output = args.work_dir.resolve(), args.output.resolve()
    if output.exists():
        parser.error('--output must not already exist; active runtimes are never overwritten')
    deps = work / 'deps'
    deps.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET=args.minimum_macos)
    for name in ('openssl-3.6.3.tar.gz', 'curl-8.21.0.tar.gz'):
        source = download(name, deps)
        if not (deps / name.removesuffix('.tar.gz')).exists():
            extract(source, deps)
    ssl = deps / 'openssl'
    stamp = ssl / 'mcpy-build.json'
    recipe = {'source_sha256': SOURCES['openssl-3.6.3.tar.gz'][1], 'arch': 'arm64', 'minos': args.minimum_macos}
    if not stamp.is_file() or json.loads(stamp.read_text()) != recipe:
        with (work / 'openssl-build.log').open('w') as log:
            source = deps / 'openssl-3.6.3'
            run(['perl', 'Configure', 'darwin64-arm64-cc', 'no-shared', 'no-tests', '--prefix=' + str(ssl),
                 '-mmacosx-version-min=' + args.minimum_macos], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
            run(['make', '-j' + str(args.jobs)], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
            run(['make', 'install_sw'], cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
        stamp.write_text(json.dumps(recipe, indent=2) + '\n')
    build = args.build_dir.resolve() if args.build_dir else work / 'client'
    config = ['cmake', '-S', ROOT, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        '-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=' + args.minimum_macos,
        '-DENABLE_DEV_PATHS=OFF', '-DBUILD_UI=OFF', '-DBUILD_WEBVIEW=OFF', '-DENABLE_ERROR_WINDOW=OFF',
        '-DXAL_WEBVIEW_USE_QT=OFF', '-DBUILD_COMPAT_TESTS=ON', '-DUSE_OWN_CURL=ON', '-DNO_OPENSSL=OFF',
        '-DOPENSSL_USE_STATIC_LIBS=TRUE', '-DOPENSSL_ROOT_DIR=' + str(ssl),
        '-DOPENSSL_INCLUDE_DIR=' + str(ssl / 'include'), '-DOPENSSL_CRYPTO_LIBRARY=' + str(ssl / 'lib/libcrypto.a'),
        '-DOPENSSL_SSL_LIBRARY=' + str(ssl / 'lib/libssl.a'), '-DOWN_CURL_SOURCE_DIR=' + str(deps / 'curl-8.21.0'),
        '-DCURL_EXT_EXTRA_OPTIONS=-DCMAKE_OSX_DEPLOYMENT_TARGET=' + args.minimum_macos +
        ';-DCMAKE_OSX_ARCHITECTURES=arm64;-DOPENSSL_USE_STATIC_LIBS=TRUE']
    with (work / 'client-build.log').open('w') as log:
        run(config, env=env, stdout=log, stderr=subprocess.STDOUT)
        run(['cmake', '--build', build, '--target', 'mcpelauncher-client', 'libc-compat-smoke',
             'netease-auth-bridge-test', 'ipc-large-write', '--parallel', str(args.jobs)], env=env, stdout=log, stderr=subprocess.STDOUT)
    run(['ctest', '--test-dir', build, '--output-on-failure'])
    dmg = download('upstream-launcher-v1.8.5.dmg', work)
    stage = output.with_name(output.name + '.staging')
    if stage.exists():
        parser.error('Remove or inspect stale staging directory first: ' + str(stage))
    contents = stage / 'Contents'
    mac, frameworks = contents / 'MacOS', contents / 'Frameworks'
    mac.mkdir(parents=True)
    frameworks.mkdir()
    shutil.copy2(build / 'mcpelauncher-client/mcpelauncher-client', mac / 'mcpelauncher-client')
    mount = work / 'upstream-mount'
    mount.mkdir(exist_ok=True)
    run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, dmg], stdout=subprocess.DEVNULL)
    try:
        source = mount / 'Minecraft Bedrock Launcher.app/Contents/Frameworks'
        for name in ('libEGL.dylib', 'libGLESv2.dylib'):
            target = frameworks / name
            run(['lipo', source / name, '-thin', 'arm64', '-output', target])
            run(['install_name_tool', '-id', '@rpath/' + name, target])
            run(['codesign', '--force', '--sign', '-', target])
    finally:
        run(['hdiutil', 'detach', mount], stdout=subprocess.DEVNULL)
    # Only the support ELF files needed by this backend; never copy native FMOD,
    # another app, game libraries, APKs, worlds or assets into the runtime.
    support = contents / 'share/mcpelauncher/lib/arm64-v8a'
    support.mkdir(parents=True)
    for name in ('libc.so', 'liblog.so', 'libjnivmsupport.so', 'libsqliteX.so', 'README.md'):
        shutil.copy2(ROOT / 'mcpelauncher-mac-bin/lib/arm64-v8a' / name, support / name)
    mappings = build / 'gamecontrollerdb/gamecontrollerdb.txt'
    if mappings.is_file():
        shutil.copy2(mappings, support.parents[1] / 'gamecontrollerdb.txt')
    licenses = contents / 'Resources/licenses'
    licenses.mkdir(parents=True)
    adapter = contents/'Resources/launcher'
    adapter.mkdir()
    for name in ('run_netease_dev.py', 'netease_source_loader.py', 'analyze_developer_binary.py',
                 'inspect_android_elf.py', 'developer_binary_rules.json'):
        shutil.copy2(ROOT/'tools'/name, adapter/name)
    shutil.copy2(download('angle-LICENSE', work), licenses/'ANGLE-LICENSE')
    for directory in (ROOT, *(ROOT / x for x in ('libjnivm', 'libc-shim', 'mcpelauncher-linker', 'game-window',
                      'file-picker', 'file-util', 'logger', 'base64', 'properties-parser', 'arg-parser', 'sdl3', 'imgui',
                      'simple-ipc', 'daemon-utils', 'msa-daemon-client', 'cll-telemetry', 'epoll-shim', 'axml-parser',
                      'mcpelauncher-apkinfo')), deps / 'openssl-3.6.3', deps / 'curl-8.21.0',
                      build / '_deps/glfw3_ext-src', build / '_deps/nlohmann_json_ext-src'):
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                shutil.copy2(path, licenses / (directory.name + '-' + path.name))
    (contents / 'Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'org.mcpy.runtime.netease', 'CFBundleName': 'mcpy runtime',
        'CFBundleExecutable': 'mcpelauncher-client', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
        'LSMinimumSystemVersion': args.minimum_macos, 'NSHighResolutionCapable': True}))
    metadata = {'schema': 1, 'platform': 'darwin-arm64', 'minimum_macos': args.minimum_macos,
        'client_python_protocol': 1, 'json_ui_reload_protocol': 1,
        'launch_protocol': 1, 'addon_link_protocol': 1,
        'game_compatibility': {'elf_rules_schema': 1, 'package_name': 'com.netease.mctest', 'abi': 'arm64-v8a',
                               'rules_sha256': digest(ROOT/'tools/developer_binary_rules.json')}, 'game_profile': json.loads(args.profile.read_text()),
        'minimum_os_runtime_tested': False, 'signing': 'ad-hoc; not notarized', 'sources': SOURCES,
        'manifest_commit': (json.loads((ROOT/'SOURCE_STATE.json').read_text())['root_commit'] if (ROOT/'SOURCE_STATE.json').is_file()
                            else subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()),
        'working_tree_modified': True,
        # Bundle signing changes the main executable. Its final hash cannot be
        # embedded in a resource sealed by that same signature (a hash cycle).
        'binaries': [{k: v for k, v in record.items() if k != 'sha256'}
                     for record in audit(stage, args.minimum_macos)]}
    (contents / 'Resources/runtime.json').write_text(json.dumps(metadata, indent=2) + '\n')
    run(['codesign', '--force', '--sign', '-', stage])
    run(['codesign', '--verify', '--deep', '--strict', stage])
    stage.rename(output)
    integrity = {'runtime': output.name, 'binaries': audit(output, args.minimum_macos),
                 'files': {str(path.relative_to(output)): digest(path)
                           for path in sorted(output.rglob('*')) if path.is_file()}}
    output.with_suffix('.integrity.json').write_text(json.dumps(integrity, indent=2) + '\n')
    print('Runtime:', output)


if __name__ == '__main__':
    main()
