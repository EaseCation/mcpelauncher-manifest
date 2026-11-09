"""Linux 启动命令：进程内网络守卫取代 seatbelt，不使用 macOS 专属参数。"""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import run_netease_dev as helper


class LinuxLaunchTests(unittest.TestCase):
    def command(self, **kwargs):
        with patch.object(helper, 'LINUX', True):
            return helper.launch_command(Path('/game'), Path('/data'), Path('/cache'), Path('/rt/bin/mcpelauncher-client'),
                                         Path('/rt/Contents/Frameworks'), [], **kwargs)

    def test_offline_world_uses_network_guard(self):
        command = self.command(debug_loopback=True)
        self.assertEqual(command[0], '/usr/bin/env')
        self.assertIn('--netease-network-guard', command)
        self.assertNotIn('--netease-network-allow', command)
        self.assertFalse(any('sandbox-exec' in part or part.startswith(('DYLD_', 'ANGLE_')) for part in command))

    def test_network_session_allows_only_resolved_server(self):
        resolved = [(2, 2, 17, '', ('203.0.113.7', 19132)), (10, 2, 17, '', ('2001:db8::7', 19132, 0, 0))]
        with patch('socket.getaddrinfo', return_value=resolved):
            command = self.command(server_target=('play.example', 19132))
        allowed = [command[i + 1] for i, part in enumerate(command) if part == '--netease-network-allow']
        self.assertEqual(sorted(allowed), sorted(['udp:203.0.113.7:19132', 'udp:[2001:db8::7]:19132']))

    def test_online_session_is_not_restricted(self):
        command = self.command(session=Path('/private/session.json'))
        self.assertNotIn('--netease-network-guard', command)
        self.assertIn('--netease-session', command)

    def test_background_flag_is_passed_through_the_environment(self):
        self.assertIn('MCPY_GAME_BACKGROUND=1', self.command(background=True))

    def test_bundled_layout_resolves_linux_client(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Path(root)/'McpyRuntime'
            (runtime/'bin').mkdir(parents=True)
            (runtime/'bin/mcpelauncher-client').write_bytes(b'')
            self.assertEqual(helper.runtime_client(runtime), runtime/'bin/mcpelauncher-client')


if __name__ == '__main__':
    unittest.main()
