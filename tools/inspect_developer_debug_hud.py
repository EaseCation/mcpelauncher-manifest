#!/usr/bin/env python3
"""Read-only debug-HUD evidence for ARM64 developer APKs; never enables features.

Presence of bindings or strings is not proof that a renderer works. Unknown or
ambiguous layouts remain unknown; the result must not be used as a patch plan.
"""
import argparse
import hashlib
import json
from pathlib import Path
from analyze_developer_binary import Resolver

NAMES = ('ShowHudInfo', 'SetDebugImGuiShow', '$pre_release',
         'button.cycle_next_debug_overlay_page', 'button.cycle_previous_debug_overlay_page',
         'button.render_debug', 'button.render_debug_reverse',
         'options.dev_enableDebugHudOverlay.imgui', 'Debug/ImGui')
MENU_LABELS = ('Block Debug', 'Mob Debug', 'Player Debug', 'Level Debug', 'Debug Control',
               '##MainMenuBar', 'Debug##Default', '##Tooltip', '[F3]: next, [F4]: prev')


def inspect(path):
    resolver = Resolver(path, {})
    addresses = {name: resolver.string_addresses(name) for name in NAMES}
    all_addresses = {a for values in addresses.values() for a in values}
    refs = resolver.xrefs(all_addresses)
    by_value = {}
    for pc in refs:
        value = resolver.address(pc)
        if value: by_value.setdefault(value[0], []).append(pc)
    evidence = {}
    for name, values in addresses.items():
        sites = sorted({pc for value in values for pc in by_value.get(value, [])})
        evidence[name] = {'strings': values, 'code_references': sites}
        if name in ('ShowHudInfo', 'SetDebugImGuiShow'):
            callbacks = set()
            for pc in sites:
                if resolver.address(pc)[1] != 1: continue
                for at in range(pc+4, pc+24, 4):
                    value = resolver.address(at)
                    if value and value[1] == 2 and resolver.elf.executable(value[0]):
                        callbacks.add(value[0])
            evidence[name]['binding_candidates'] = sorted(callbacks)
    prerelease = []
    for pc in evidence['$pre_release']['code_references']:
        # Audited 3.9/3.10: address, ldrb w1, [address], conversion call,
        # then the $pre_release key. Read-only recognition, no version table.
        try:
            value = resolver.address(pc-20)
            word = resolver.word(pc-12)
            if not value or word & 0xffc0001f != 0x39400001: continue
            if (word >> 10) & 0xfff or (word >> 5) & 31 != value[1]: continue
            resolver.call(pc-4)
            address = value[0]
            segment = next(s for s in resolver.elf.loads if s[3] <= address < s[3]+s[5])
            prerelease.append({'address': address, 'file_value': resolver.elf.data[resolver.elf.offset(address)],
                               'read_only': not bool(segment[1] & 2), 'anchor': pc})
        except (ValueError, StopIteration): continue
    return {'schema': 1, 'elf_sha256': hashlib.sha256(resolver.elf.data).hexdigest(),
            'bindings_and_actions': evidence,
            'prerelease_flag': prerelease[0] if len(prerelease) == 1 else None,
            'prerelease_candidates': len(prerelease),
            'menu_label_counts': {name: resolver.elf.data.count(name.encode()) for name in MENU_LABELS},
            'runtime_rendering': 'not_verified',
            'note': 'Bindings, enum labels and shaders do not prove that the native menu renderer is present or active.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = inspect(args.elf)
    output = json.dumps(result, indent=2) + '\n'
    if args.output: args.output.write_text(output, encoding='utf-8')
    else: print(output, end='')


if __name__ == '__main__': main()
