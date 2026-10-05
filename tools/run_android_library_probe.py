#!/usr/bin/env python3
"""Run the macOS ELF load probe offline in isolated data/cache directories."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', required=True, type=Path, help='Extracted APK root (contains lib/arm64-v8a)')
    parser.add_argument('--runtime', type=Path, default=root/'build-macos-arm64/McpyRuntime.app')
    parser.add_argument('--client', type=Path)
    parser.add_argument('--angle-dir', type=Path)
    parser.add_argument('--output', type=Path, default=root/'build-macos-arm64/netease-probe/latest')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--stage', choices=['load', 'jni'], default='load')
    args = parser.parse_args()
    args.client = args.client or args.runtime/'Contents/MacOS/mcpelauncher-client'
    args.angle_dir = args.angle_dir or args.runtime/'Contents/Frameworks'
    if sys.platform != 'darwin' or not shutil.which('sandbox-exec'):
        parser.error('requires macOS sandbox-exec for network isolation')
    if args.timeout < 1:
        parser.error('timeout must be positive')
    game, client, angle, output = (p.resolve() for p in (args.game_dir, args.client, args.angle_dir, args.output))
    for path in [client, game/'lib/arm64-v8a/libminecraftpe.so', angle/'libEGL.dylib', angle/'libGLESv2.dylib']:
        if not path.is_file():
            parser.error('missing file: ' + str(path))
    output.mkdir(parents=True, exist_ok=True)
    data, cache = output/'data', output/'cache'
    data.mkdir(exist_ok=True)
    cache.mkdir(exist_ok=True)
    # env is invoked inside the sandbox because macOS strips DYLD_* from
    # the environment of restricted system executables (including sandbox-exec).
    command = ['sandbox-exec', '-p', '(version 1) (allow default) (deny network*)',
               '/usr/bin/env', 'DYLD_LIBRARY_PATH=' + str(angle), 'MCPELAUNCHER_LINKER_VERBOSITY=1',
               str(client), '--probe-jni' if args.stage == 'jni' else '--probe-library', '--force-opengles', '--game-dir', str(game),
               '--data-dir', str(data), '--cache-dir', str(cache)]
    result = dict(command=command, network='denied by sandbox-exec', timeout_seconds=args.timeout, stage=args.stage)
    log = output/'probe.log'
    with log.open('w') as stream:
        try:
            result['returncode'] = subprocess.run(command, cwd=output, stdout=stream, stderr=subprocess.STDOUT,
                                                 timeout=args.timeout).returncode
            result['timed_out'] = False
        except subprocess.TimeoutExpired:
            result['returncode'] = 124
            result['timed_out'] = True
    text = log.read_text(errors='replace')
    result['load_completed'] = '[LibraryProbe] Load completed;' in text
    result['jni_completed'] = '[LibraryProbe] JNI probe completed;' in text
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Log:', log)
    print('Exit:', result['returncode'], 'ELF load completed:', result['load_completed'])
    for line in text.splitlines():
        if 'LibraryProbe' in line or 'Signal ' in line or 'cannot locate symbol' in line:
            print(line)
    # Do not report success merely because an upstream error handler returned 0.
    code = result['returncode']
    completed = result['jni_completed'] if args.stage == 'jni' else result['load_completed']
    return (128-code if code < 0 else code) or (0 if completed else 1)


if __name__ == '__main__':
    sys.exit(main())
