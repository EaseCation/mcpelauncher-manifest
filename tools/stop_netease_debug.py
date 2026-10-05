#!/usr/bin/env python3
"""Save and close one identity-checked mcpy attached test session.

Run with mcpy's Python interpreter. Current launchers save through the same
native lifecycle used by window close and SIGTERM; legacy launchers save via Python.
"""
import argparse
import json
import time
from pathlib import Path


def main():
    from mcpywrap.mcstudio import sessions
    from mcpywrap.mcstudio.processes import checked_process
    from mcpywrap.mcstudio.runtime_debug import control_request
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--session', required=True)
    args = parser.parse_args()
    data = sessions.read(args.project, args.session)
    game = checked_process(data['game']) if data.get('game') else None
    directory = sessions.session_path(args.project, args.session)
    engine_log = Path(data.get('engine_log_path') or directory/'engine.log')
    native_stop = engine_log.is_file() and 'Save-before-exit enabled (v1)' in engine_log.read_text(errors='replace')
    if game and not native_stop:
        result = control_request(args.project, args.session, 'execute', side='client',
                                 code="__import__('minecraft').instance.quit_local_game()")
        if result.get('state') != 'completed':
            raise RuntimeError('World exit was not acknowledged; game retained')
        for _ in range(100):
            game = checked_process(data['game'])
            if not game or not any('/minecraftWorlds/' in f.path and '/db/' in f.path for f in game.open_files()):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('World database remains open; game retained')
    # Existing mcpy process identity checks and worker cleanup remain authoritative.
    # A timeout reports failure and retains the process; never force-kill a world.
    sessions.stop(args.project, args.session)
    print(json.dumps({'state': 'closed', 'session': args.session, 'game_pid': data.get('game', {}).get('pid')}))


if __name__ == '__main__':
    main()
