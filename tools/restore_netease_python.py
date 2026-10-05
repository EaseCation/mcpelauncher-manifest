#!/usr/bin/env python3
"""Restore selected exported Python 2 code objects for offline disassembly.

Input is a JSON export from the inspected game's code objects plus an explicitly
verified opcode map. No input code is executed. Unknown opcodes/constant types
are errors; runtime-compiled and MCP-packaged code use different opcode maps.
"""
import argparse
import base64
import json
from pathlib import Path
import struct


def number(value):
    return struct.pack('<i', value)


def string(value):
    if isinstance(value, str):
        value = value.encode('utf8')
    return b's' + number(len(value)) + value


def sequence(values):
    return b'(' + number(len(values)) + b''.join(values)


def restore_bytes(code, mapping):
    data = bytearray(base64.b64decode(code['code']))
    offset = 0
    while offset < len(data):
        encoded = data[offset]
        if encoded not in mapping:
            raise ValueError('Unknown opcode %d in %s at %d' % (encoded, code['name'], offset))
        opcode = mapping[encoded]
        data[offset] = opcode
        width = 3 if opcode >= 90 else 1
        if offset + width > len(data):
            raise ValueError('Truncated instruction in ' + code['name'])
        offset += width
    return bytes(data)


def constant(value, mapping):
    kind = value['type']
    item = value.get('value')
    if kind == 'code':
        return marshal_code(item, mapping)
    if kind == 'bytes':
        return string(base64.b64decode(item))
    if kind == 'unicode':
        data = item.encode('utf8')
        return b'u' + number(len(data)) + data
    if kind == 'NoneType':
        return b'N'
    if kind == 'bool':
        return b'T' if item else b'F'
    if kind in ('int', 'long'):
        if kind == 'int' and -(1 << 31) <= item < (1 << 31):
            return b'i' + number(item)
        remaining, digits = abs(item), []
        while remaining:
            digits.append(struct.pack('<H', remaining & 0x7fff))
            remaining >>= 15
        return b'l' + number(len(digits) * (-1 if item < 0 else 1)) + b''.join(digits)
    if kind == 'float':
        return b'g' + struct.pack('<d', item)
    if kind == 'tuple':
        return sequence([constant(v, mapping) for v in item])
    raise ValueError('Unsupported constant type: ' + kind)


def marshal_code(code, mapping):
    return (b'c' + b''.join(number(code[k]) for k in ('argcount', 'nlocals', 'stacksize', 'flags')) +
            string(restore_bytes(code, mapping)) + sequence([constant(v, mapping) for v in code['consts']]) +
            b''.join(sequence([string(v) for v in code[k]]) for k in ('names', 'varnames', 'freevars', 'cellvars')) +
            string(code['filename']) + string(code['name']) + number(code['firstlineno']) +
            string(base64.b64decode(code['lnotab'])))


def walk(code):
    yield code
    for value in code['consts']:
        if value['type'] == 'code':
            yield from walk(value['value'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--opcode-map', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--function', action='append', required=True)
    args = parser.parse_args()
    payload = json.loads(args.export.read_text())
    root = payload.get('value', payload)['code_object']
    mapping = {int(k): v for k, v in json.loads(args.opcode_map.read_text())['game_to_standard'].items()}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Opcode map must be one-to-one')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in args.function:
        candidates = [c for c in walk(root) if c['name'] == name]
        if len(candidates) != 1:
            raise ValueError('Function must identify exactly one code object: ' + name)
        if not name.isidentifier():
            raise ValueError('Function filename must be an identifier')
        output = args.output_dir / (name + '.pyc')
        output.write_bytes(b'\x03\xf3\r\n' + number(0) + marshal_code(candidates[0], mapping))
        print(output)


if __name__ == '__main__':
    main()
