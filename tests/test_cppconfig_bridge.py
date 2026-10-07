"""Check native startup recipes without importing or running the game."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from netease_cppconfig import creation_arguments, server_target
from run_netease_dev import world_commands, network_commands, network_policy


class BridgeTests(unittest.TestCase):
    def config(self):
        return {'world_info': {'level_id': 'test', 'name': 'survival', 'world_type': 1,
            'seed': '31415', 'game_type': 0, 'difficulty': 3, 'permission_level': 1,
            'start_with_map': True, 'bonus_items': True, 'cheat': True,
            'cheat_info': {'keep_inventory': False, 'show_coordinates': True, 'random_tick_speed': 4},
            'resource_packs': ['resource'], 'behavior_packs': ['behavior']}}

    def test_create_passes_generator_seed_rules_and_pack_order(self):
        config = self.config()
        args, settings = creation_arguments(config)
        self.assertEqual(args, ['test', 1, True, True, '31415'])
        self.assertEqual(settings['option_info'], {'show_coordinates': True})
        self.assertEqual(settings['cheat_info'], {'enable': True, 'keep_inventory': False, 'random_tick_speed': 4})
        with tempfile.TemporaryDirectory() as root:
            recipe = world_commands(Path(root), config)
        world = Mock(); world.create_world.return_value = True; world.set_world_info.return_value = True
        with patch.dict(sys.modules, world=world, application=Mock(), engine_notify_handler=Mock()):
            eval(recipe[1]['args'][0])
        world.create_world.assert_called_once_with(*args)
        world.set_world_info.assert_called_once_with('test', settings)
        self.assertEqual(world.play_world.call_args.args[:4], ('test', 'survival', ['resource'], ['behavior']))

    def test_existing_save_never_reapplies_creation_settings(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'minecraftWorlds/test/level.dat'
            path.parent.mkdir(parents=True);path.touch()
            recipe = world_commands(Path(root), self.config())
        world = Mock()
        with patch.dict(sys.modules, world=world, application=Mock(), engine_notify_handler=Mock()):
            eval(recipe[1]['args'][0])
        world.create_world.assert_not_called()
        world.set_world_info.assert_not_called()
        world.play_world.assert_called_once()

    def test_network_calls_existing_engine_entry_without_world_creation(self):
        config = {'world_info': None, 'room_info': {'ip': 'localhost', 'port': 29132}}
        commands = network_commands(config)
        world = Mock()
        with patch.dict(sys.modules, world=world, application=Mock(), engine_notify_handler=Mock()):
            eval(commands[1]['args'][0])
        world.create_world.assert_not_called()
        world.play_world.assert_not_called()
        self.assertEqual(world.join_world.call_args.args[:2], ('localhost', 29132))
        self.assertEqual(world.join_world.call_args.args[-1], {'multiplayer_game_type': 100})
        self.assertIn('get_level_id', commands[-1]['wait_for'])

    def test_server_config_rejects_world_and_invalid_endpoints(self):
        for host, port in [('bad/host', 19132), ('a..b', 19132), ('localhost', True), ('localhost', 65536)]:
            with self.assertRaises(ValueError):
                server_target({'room_info': {'ip': host, 'port': port}})
        with self.assertRaises(ValueError):
            server_target({'world_info': {}, 'room_info': {'ip': 'localhost', 'port': 19132}})
        self.assertEqual(server_target({'room_info': {'ip': '::1', 'port': 19132}}), ('::1', 19132))

    def test_network_sandbox_retains_deny_default_and_scopes_udp(self):
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('127.0.0.1', 29132))]):
            policy = network_policy('localhost', 29132)
        self.assertIn('(deny network*)', policy)
        self.assertIn('remote udp "localhost:29132"', policy)
        with patch('socket.getaddrinfo', return_value=[(None, None, None, None, ('192.0.2.1', 19132))]):
            policy = network_policy('example.test', 19132)
        self.assertIn('remote udp "*:19132"', policy)

    def test_unknown_or_unverified_options_are_not_silently_ignored(self):
        for key, value in [('experimental_holiday', True), ('fancy_bubbles', True), ('unknown', False)]:
            config = self.config(); config['world_info']['cheat_info'][key] = value
            with self.assertRaises(ValueError):creation_arguments(config)
        config = self.config(); config['world_info']['level_id'] = '../outside'
        with self.assertRaises(ValueError):creation_arguments(config)


if __name__ == '__main__':unittest.main()
