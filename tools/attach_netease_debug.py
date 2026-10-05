#!/usr/bin/env python3
"""Attach mcpywrap's existing Safaia worker to a local developer-APK process.

Run using the Python interpreter from the mcpy installation. This adapter does
not launch, replace or terminate the game. All script transport is mcpywrap's.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def worker(args):
    from mcpywrap.mcstudio import sessions
    from mcpywrap.mcstudio.processes import identity, checked_process
    from mcpywrap.mcstudio.runtime_debug import SafaiaChannel, RuntimeControlServer
    directory = sessions.session_path(args.project, args.session)
    directory.mkdir(parents=True, exist_ok=False)
    game = identity(args.pid)
    if Path(game['executable']).name != 'mcpelauncher-client':
        raise ValueError('Expected the explicitly selected launcher process')
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    with (directory/'game.log').open('a', buffering=1) as log:
        channel = SafaiaChannel(log.write)
        # The package advertises the native client channel before Python boots.
        # Legacy packages continue to use the original Safaia transport.
        from mcpywrap.mcstudio.launcher_python import LauncherPythonChannel
        import psutil
        argv = psutil.Process(args.pid).cmdline()
        data_directory = None
        if '--netease-dev' in argv and '--data-dir' in argv:
            data_directory = Path(argv[argv.index('--data-dir') + 1])
        manifest = Path(game['executable']).parent.parent/'Resources/runtime.json'
        advertised = manifest.is_file() and json.loads(manifest.read_text()).get('client_python_protocol') == 1
        if data_directory and (advertised or (data_directory/'python-control.json').is_file()):
            channel = LauncherPythonChannel(channel, data_directory)
        token = secrets.token_hex(32)
        control = RuntimeControlServer(channel, token)
        record = {
            'session': args.session, 'project': str(args.project), 'state': 'running',
            'created_at': time.time(), 'worker': identity(os.getpid()), 'game': game,
            'mode': 'local', 'origin': 'macos-android-developer-attach',
            'log_path': str(directory/'game.log'), 'engine_log_path': str(args.engine_log),
            'config_path': None, 'level_id': None, 'mcs_auth': False,
            'error': None, 'safaia_connected': False,
            'client_python_transport': 'launcher-jni' if isinstance(channel, LauncherPythonChannel) else 'safaia',
        }
        if args.engine_log.exists():
            (directory/'engine.log').symlink_to(args.engine_log)
        sessions.save(directory/'control.json', {'port': control.server_address[1], 'token': token,
                                               'python_reload_sides': ['client', 'server']})
        channel.start(args.pid)
        control.start()
        sessions.save(directory/'session.json', record)
        try:
            while not stopped.wait(.5) and not (directory/'stop').exists() and checked_process(game):
                connected = channel.connected.is_set()
                if record['safaia_connected'] != connected or record['error'] != channel.last_error:
                    record.update(safaia_connected=connected, error=channel.last_error)
                    sessions.save(directory/'session.json', record)
        finally:
            control.close()
            channel.close()
            (directory/'control.json').unlink(missing_ok=True)
            record.update(state='exited', safaia_connected=False)
            sessions.save(directory/'session.json', record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--pid', type=int)
    target.add_argument('--launch', action='store_true', help='Start an offline world with localhost debugging, then attach')
    parser.add_argument('--project', type=Path, default=ROOT/'build-macos-arm64/netease-debug/mcpy-project')
    parser.add_argument('--mcpy-source', type=Path, default=ROOT.parent/'mcpywrap')
    parser.add_argument('--engine-log', type=Path, default=ROOT/'build-macos-arm64/netease-debug/run.log')
    parser.add_argument('--session', default=None, help=argparse.SUPPRESS)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.project = args.project.resolve()
    args.engine_log = args.engine_log.resolve()
    sys.path.insert(0, str(args.mcpy_source.resolve()))
    os.umask(0o077)
    if args.launch:
        from mcpywrap.mcstudio.processes import identity, checked_process
        handoff = args.engine_log.parent/'session.json'
        if handoff.exists():
            saved = json.loads(handoff.read_text())
            from mcpywrap.mcstudio import sessions
            existing = sessions.read(saved['project'], saved['session'])
            if existing['state'] == 'running':
                print(json.dumps(saved))
                return
            if existing.get('game') and checked_process(existing['game']):
                raise RuntimeError('Previous debug game is still running; attach its PID instead of opening its world twice')
        args.engine_log.parent.mkdir(parents=True, exist_ok=True)
        with (args.engine_log.parent/'wrapper.log').open('w') as out:
            game = subprocess.Popen([sys.executable, str(ROOT/'tools/run_netease_dev.py'),
                '--debug-loopback', '--angle-backend', 'metal', '--exec-client', '--log', str(args.engine_log)],
                cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        args.pid = game.pid
        for _ in range(100):
            if game.poll() is not None:
                raise RuntimeError('Game exited during startup; inspect '+str(args.engine_log))
            if Path(identity(args.pid)['executable']).name == 'mcpelauncher-client':
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Game startup handoff timed out')
    if args.worker:
        worker(args)
        return
    args.project.mkdir(parents=True, exist_ok=True)
    session = uuid.uuid4().hex
    directory = args.project/'.runtime/sessions'/session
    # The worker owns the session record; the parent only waits for its handoff.
    log_path = args.project/('attach-'+session+'.log')
    with log_path.open('w') as out:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker',
            '--pid', str(args.pid), '--project', str(args.project), '--session', session,
            '--mcpy-source', str(args.mcpy_source.resolve()), '--engine-log', str(args.engine_log)],
            stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(100):
        path = directory/'session.json'
        if path.exists():
            result = {'project': str(args.project), 'session': session, 'worker_pid': process.pid,
                      'game_pid': args.pid, 'state': 'attached', 'connected': False}
            from mcpywrap.mcstudio import sessions
            sessions.save(args.engine_log.parent/'session.json', result)
            print(json.dumps(result))
            return
        if process.poll() is not None:
            raise RuntimeError('Attach worker exited; inspect '+str(log_path))
        time.sleep(.1)
    raise RuntimeError('Attach handoff timed out; inspect '+str(log_path))


if __name__ == '__main__':
    main()
