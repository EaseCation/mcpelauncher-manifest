#!/usr/bin/env python3
"""Prepare and run a local developer-APK world through the existing JNI bridge.

Requires a portable arm64 runtime and this user's own extracted developer APK.
Offline by default. --online explicitly enables developer account experiments.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import zipfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'build-macos-arm64/netease-dev'
BUNDLED_RUNTIME = Path(__file__).resolve().parents[3] if (Path(__file__).resolve().parents[2]/'MacOS/mcpelauncher-client').is_file() else None
POLICY = '(version 1) (allow default) (deny network*) (allow network* (local unix-socket) (remote unix-socket))'
DEBUG_POLICY = POLICY + ' (allow network-bind (local ip "localhost:*")) (allow network-inbound (local ip "localhost:*")) (allow network-outbound (remote ip "localhost:*"))'


def rpc(module, function, args, instance=False):
    return dict(module_name=module, func_name=function, args=args, use_instance=instance)


def world_commands(data, world_id, resource_packs=None, behavior_packs=None, world_name='本地开发测试'):
    # A normal client-Python request with an explicit, side-effect-free readiness
    # predicate. Other requests can execute while the startup recipe is waiting.
    scene = "getattr(__import__('sys').modules.get('launcher.launcher'), 'base_scene', None)"
    hide_login = rpc('__builtin__', 'eval', [scene + '.setVisible(False)'])
    hide_login['readiness'] = 'python'
    hide_login['wait_for'] = "(lambda scene: bool(scene) and scene.getName() == 'launcher_scene')(" + scene + ")"
    commands = [hide_login]
    create = None
    if not (data/'minecraftWorlds'/world_id/'level.dat').is_file():
        info = {'basic_info': {'game_type': 1, 'difficulty': 0, 'level_name': world_name},
                'cheat_info': {'enable': True}}
        create = "(__import__('world').create_world(*" + repr([world_id, 2, False, False, '20261004']) + ") and " \
                 "__import__('world').set_world_info(*" + repr([world_id, info]) + "))"
    play_args = [world_id, world_name, resource_packs or [], behavior_packs or [],
                 {'user_name': 'LocalDev', 'user_id': '0'}, None, {'multiplayer_game_type': 0}, None]
    # Set the complete offline state in a single game-thread dispatch. Spreading
    # these transitions over ticks races the Cocos startup failure callbacks.
    start = "(__import__('application').instance.InitOfflinePlayer(0, 'LocalDev'), " \
            "__import__('engine_notify_handler').instance.set_offline_start('1'), " \
            "__import__('world').play_world(*" + repr(play_args) + "))[-1]"
    if create:
        start = create + ' and ' + start
    ready = rpc('clientlevel', 'get_level_id', [])
    ready['wait_for'] = "__import__('clientlevel').get_level_id() not in (None, -1, '-1')"
    commands += [rpc('__builtin__', 'eval', [start]), ready]
    return commands


def install_source_addons(addons, installed, link=False):
    """Install mcpy build directories; preserve source projects and stable UUIDs."""
    resources, behaviors, roots = [], [], []
    seen = set()
    for addon in addons:
        addon = addon.resolve()
        found = False
        for kind, names in [('behavior', behaviors), ('resource', resources)]:
            source = addon / (kind + '_pack')
            if not source.is_dir():
                continue
            manifest = json.loads((source/'manifest.json').read_text())
            identity = str(uuid.UUID(manifest['header']['uuid']))
            if (kind, identity) in seen:
                raise ValueError('Duplicate addon pack UUID: ' + identity)
            seen.add((kind, identity))
            name = 'dev_' + identity
            target = installed / (kind + '_packs') / name
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = target.with_name(name + '.staging')
            if stage.is_symlink(): stage.unlink()
            elif stage.exists(): shutil.rmtree(stage)
            if link:
                stage.symlink_to(source.resolve(), target_is_directory=True)
            else:
                shutil.copytree(source, stage, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
            if kind == 'behavior':
                (stage/'entities').mkdir(exist_ok=True)
            if target.is_symlink(): target.unlink()
            elif target.exists(): shutil.rmtree(target)
            stage.rename(target)
            names.append(name)
            if kind == 'behavior':
                roots.append(str(target))
            found = True
        if not found:
            raise ValueError('--source-addon requires an assembled addon with behavior_pack/resource_pack: ' + str(addon))
    return resources, behaviors, roots


def extract_apk(apk, game):
    if game.exists() and any(game.iterdir()):
        raise ValueError('--apk extraction requires an empty --game-dir; reuse an extracted directory without --apk')
    game.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        for entry in archive.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe APK member path')
            if entry.filename == 'AndroidManifest.xml' or entry.filename.startswith(('assets/', 'lib/arm64-v8a/')):
                archive.extract(entry, game)
    (game/'source-apk.json').write_text(json.dumps({'path': str(apk.resolve()), 'size': apk.stat().st_size}, indent=2)+'\n')


def prepare(args):
    game, data, cache, client, angle = (p.resolve() for p in (args.game_dir, args.data_dir, args.cache_dir, args.client, args.angle_dir))
    if args.apk:
        extract_apk(args.apk, game)
    for p in [client, angle/'libEGL.dylib', angle/'libGLESv2.dylib', game/'AndroidManifest.xml',
              game/'lib/arm64-v8a/libminecraftpe.so', game/'assets/assets/vanilla.mcp']:
        if not p.is_file():
            raise ValueError('missing required file: ' + str(p))
    data.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    installed = data/'games/com.netease'
    installed.mkdir(parents=True, exist_ok=True)
    # Android normally installs these before the Python runtime starts.
    # Preserve existing settings and script packs, including user edits.
    for name in ['vanilla.mcp', 'netease_resource_packs.json', 'client_cfg.json', 'rnconfig.json']:
        if not (installed/name).exists():
            shutil.copy2(game/'assets/assets'/name, installed/name)
    resources, behaviors, source_roots = install_source_addons(args.source_addon, installed, args.link_source_addons)
    commands = [] if args.online else world_commands(data, args.world_id, resources, behaviors, args.world_name)
    if source_roots:
        loader = installed/'developer_source_loader.py'
        shutil.copy2(Path(__file__).with_name('netease_source_loader.py'), loader)
        commands.insert(1, rpc('__builtin__', 'execfile', [str(loader), {'SOURCE_ROOTS': source_roots}]))
    if args.commands_json:
        commands = json.loads(args.commands_json.read_text())
        if not isinstance(commands, list) or any(not isinstance(c, dict) for c in commands):
            raise ValueError('--commands-json must contain an array of bridge-call objects')
    return game, data, cache, client, angle, commands


def launch_command(game, data, cache, client, angle, commands, session=None, debug_loopback=False, angle_backend=None):
    command = ([] if session else ['/usr/bin/sandbox-exec', '-p', DEBUG_POLICY if debug_loopback else POLICY]) + ['/usr/bin/env', 'DYLD_LIBRARY_PATH='+str(angle)]
    if angle_backend:
        command += ['ANGLE_DEFAULT_PLATFORM='+angle_backend]
    command += [str(client), '--netease-dev', '--force-opengles', '--game-dir', str(game),
               '--data-dir', str(data), '--cache-dir', str(cache)]
    if session:
        command += ['--netease-session', str(session)]
    for call in commands:
        command += ['--netease-command', json.dumps(call, ensure_ascii=False)]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, help='Extract developer APK into an empty game directory')
    parser.add_argument('--game-dir', type=Path, default=RUNTIME/'game')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--online', action='store_true', help='Enable network and host MPay bridge, using separate data and no offline-world commands')
    parser.add_argument('--debug-loopback', action='store_true', help='Offline world with localhost-only Safaia debugging')
    parser.add_argument('--session-file', type=Path, default=ROOT/'build-macos-arm64/netease-online/private/session.json')
    parser.add_argument('--world-name', default='本地开发测试')
    parser.add_argument('--link-source-addons', action='store_true', help='Link assembled development packs instead of copying them')
    parser.add_argument('--runtime', type=Path, default=BUNDLED_RUNTIME or ROOT/'build-macos-arm64/McpyRuntime.app',
                        help='Portable runtime produced by build_macos_runtime.py')
    parser.add_argument('--client', type=Path, help='Explicit development binary override')
    parser.add_argument('--angle-dir', type=Path, help='Explicit development ANGLE override')
    parser.add_argument('--angle-backend', choices=['metal', 'opengl'], help='Select the ANGLE backend explicitly; Metal uses separate default data/cache')
    parser.add_argument('--world-id', default='codex-arm64-smoke')
    parser.add_argument('--commands-json', type=Path, help='Optional replacement sequence of developer JSON bridge calls')
    parser.add_argument('--source-addon', type=Path, action='append', default=[], help='Explicit developer source addon (mcpy build directory); repeat for multiple addons')
    parser.add_argument('--make-app', action='store_true', help='Create a local test .app under the build directory')
    parser.add_argument('--app-name', help='Optional distinct name for the generated test .app')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run-seconds', type=int, help='Bounded smoke run; stops after this time, not a save/quit test')
    parser.add_argument('--log', type=Path)
    parser.add_argument('--exec-client', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.client = args.client or args.runtime/'Contents/MacOS/mcpelauncher-client'
    args.angle_dir = args.angle_dir or args.runtime/'Contents/Frameworks'
    if args.online and args.debug_loopback:
        parser.error('--online and --debug-loopback are mutually exclusive')
    if args.source_addon and (args.online or args.commands_json):
        parser.error('--source-addon is offline-only and cannot be combined with --commands-json')
    runtime = ROOT/'build-macos-arm64/netease-online' if args.online else ROOT/'build-macos-arm64/netease-metal' if args.angle_backend == 'metal' else ROOT/'build-macos-arm64/netease-debug' if args.debug_loopback else RUNTIME
    args.data_dir = args.data_dir or runtime/'data'
    args.cache_dir = args.cache_dir or runtime/'cache'
    args.log = args.log or runtime/'run.log'
    if args.online:
        os.umask(0o077)
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        runtime.chmod(0o700)
    if sys.platform != 'darwin' or not shutil.which('sandbox-exec'):
        parser.error('macOS sandbox-exec is required')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.world_id):
        parser.error('--world-id must be a simple directory name')
    if args.app_name and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{0,59}', args.app_name):
        parser.error('--app-name must contain only letters, digits, spaces or hyphens')
    if args.run_seconds is not None and args.run_seconds < 1:
        parser.error('--run-seconds must be positive')
    try:
        # Keep the lock across exec into the game to protect live worlds/packs.
        import fcntl
        args.data_dir.mkdir(parents=True, exist_ok=True)
        data_lock = (args.data_dir/'launcher.lock').open('a')
        fcntl.flock(data_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.set_inheritable(data_lock.fileno(), True)
        game, data, cache, client, angle, commands = prepare(args)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    log = args.log.resolve()
    log.parent.mkdir(parents=True, exist_ok=True)
    command = launch_command(game, data, cache, client, angle, commands, args.session_file.resolve() if args.online else None, args.debug_loopback, args.angle_backend)
    (log.parent/'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2)+'\n')
    if args.make_app:
        app_name = 'NetEase Online Test' if args.online else 'NetEase Metal Test' if args.angle_backend == 'metal' else 'NetEase Debug Test' if args.debug_loopback else 'NetEase Developer Test'
        app_name = args.app_name or app_name
        app = ROOT/'build-macos-arm64'/(app_name+'.app')
        mac = app/'Contents/MacOS'
        mac.mkdir(parents=True, exist_ok=True)
        shutil.copy2(client, mac/'mcpelauncher-client')
        frameworks = app/'Contents/Frameworks'
        frameworks.mkdir(parents=True, exist_ok=True)
        for name in ['libEGL.dylib', 'libGLESv2.dylib']:
            shutil.copy2(angle/name, frameworks/name)
        runtime_info = client.parent.parent/'Resources/runtime.json'
        if runtime_info.is_file():
            (app/'Contents/Resources').mkdir(exist_ok=True)
            shutil.copy2(runtime_info, app/'Contents/Resources/runtime.json')
        support = client.parent.parent/'share'
        if support.is_dir():
            shutil.copytree(support, app/'Contents/share', dirs_exist_ok=True)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'local.mcpelauncher.netease-test' if app_name == 'NetEase Developer Test' else 'local.mcpelauncher.'+app_name.lower().replace(' ', '-'), 'CFBundleName': app_name,
            'CFBundleDisplayName': app_name,
            'CFBundleExecutable': 'Launch', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
            'NSHighResolutionCapable': True}))
        # Regenerate commands on every launch so existing worlds are reopened,
        # never recreated. exec then preserves the app's LaunchServices identity.
        script = mac/'Launch'
        wrapper = [sys.executable, str(Path(__file__).resolve()), '--game-dir', str(game), '--data-dir', str(data),
                   '--cache-dir', str(cache), '--client', str(mac/'mcpelauncher-client'), '--angle-dir', str(app/'Contents/Frameworks'),
                   '--world-id', args.world_id, '--world-name', args.world_name, '--log', str(log), '--exec-client']
        if args.commands_json:
            wrapper += ['--commands-json', str(args.commands_json.resolve())]
        if args.online:
            wrapper += ['--online', '--session-file', str(args.session_file.resolve())]
        if args.debug_loopback:
            wrapper += ['--debug-loopback']
        if args.angle_backend:
            wrapper += ['--angle-backend', args.angle_backend]
        if args.link_source_addons:
            wrapper += ['--link-source-addons']
        for addon in args.source_addon:
            wrapper += ['--source-addon', str(addon.resolve())]
        script.write_text('#!/bin/sh\nexec '+shlex.join(wrapper)+'\n')
        script.chmod(0o755)
        print('App:', app)
    print('Data:', data, '\nLog:', log, flush=True)
    if args.prepare_only:
        return 0
    if args.exec_client:
        with log.open('w') as out:
            os.dup2(out.fileno(), 1)
            os.dup2(out.fileno(), 2)
        os.chdir(data)
        os.execv(command[0], command)
    # Use a distinct process group for bounded diagnostics and reliable cleanup.
    with log.open('w') as out:
        process = subprocess.Popen(command, cwd=data, stdout=out, stderr=subprocess.STDOUT,
                                   start_new_session=True, pass_fds=(data_lock.fileno(),))
        try:
            code = process.wait(timeout=args.run_seconds)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            # The native developer lifecycle saves the world before exiting.
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                print('Save/exit did not finish; retained PID', process.pid, 'and world lock. Inspect', log)
                return 125
            print('Save/exit completed; inspect log for world status.')
            return 124
    print('Exit:', code)
    return code if code >= 0 else 128-code


if __name__ == '__main__':
    sys.exit(main())
