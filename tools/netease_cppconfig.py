"""Translate the existing MC Studio world_info contract to Android's world API.

No game imports on the host. Creation-only settings are never replayed for a save.
"""
import copy
import re

OPTION_RULES = {'pvp', 'show_coordinates', 'fire_spreads', 'tnt_explodes',
                'mob_loot', 'natural_regeneration', 'tile_drops'}
CHEAT_RULES = {'always_day', 'mob_griefing', 'keep_inventory', 'weather_cycle',
               'mob_spawn', 'entities_drop_loot', 'daylight_cycle',
               'command_blocks_enabled', 'random_tick_speed'}


def world_info(config):
    info = config.get('world_info')
    if not isinstance(info, dict):
        raise ValueError('cppconfig.world_info must be an object')
    if not isinstance(info.get('level_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', info['level_id']):
        raise ValueError('Invalid cppconfig world ID')
    for key, values in [('world_type', (1, 2)), ('game_type', (0, 1, 2)),
                        ('difficulty', (0, 1, 2, 3)), ('permission_level', (0, 1, 2))]:
        if type(info.get(key)) is not int or info[key] not in values:
            raise ValueError('Unsupported cppconfig field: ' + key)
    for key in ('start_with_map', 'bonus_items', 'cheat'):
        if type(info.get(key)) is not bool:
            raise ValueError('Expected boolean cppconfig field: ' + key)
    for key in ('name', 'seed'):
        if not isinstance(info.get(key), str) or '\0' in info[key]:
            raise ValueError('Expected string cppconfig field: ' + key)
    for key in ('resource_packs', 'behavior_packs'):
        if not isinstance(info.get(key), list) or any(not isinstance(p, str) for p in info[key]):
            raise ValueError('Expected cppconfig pack path list: ' + key)
    rules = info.get('cheat_info', {})
    if not isinstance(rules, dict):
        raise ValueError('cppconfig.cheat_info must be an object')
    for key, value in rules.items():
        if key not in OPTION_RULES | CHEAT_RULES:
            # Legacy cppconfig emits these disabled flags. Enabled experiments
            # require version-specific verification; do not silently discard them.
            if key not in ('experimental_holiday', 'experimental_biomes', 'fancy_bubbles') or value is not False:
                raise ValueError('Unsupported Android world option: ' + key)
        elif key == 'random_tick_speed':
            if type(value) is not int or not 0 <= value <= 2147483647:
                raise ValueError('Invalid random_tick_speed')
        elif type(value) is not bool:
            raise ValueError('Expected boolean rule: ' + key)
    return info


def creation_arguments(config):
    info = world_info(config)
    # Official studio_message_handler uses these same generator enum values.
    args = [info['level_id'], info['world_type'], info['start_with_map'], info['bonus_items'], info['seed']]
    rules = info.get('cheat_info', {})
    settings = {
        'basic_info': {'game_type': info['game_type'], 'difficulty': info['difficulty'],
                       'level_name': info['name'], 'player_permission_level': info['permission_level']},
        'option_info': {key: value for key, value in rules.items() if key in OPTION_RULES},
        'cheat_info': dict({'enable': info['cheat']}, **{key: value for key, value in rules.items() if key in CHEAT_RULES})}
    return args, settings


def with_installed_packs(config, resources, behaviors):
    result = copy.deepcopy(config)
    result['world_info'].update(resource_packs=resources, behavior_packs=behaviors)
    return result
