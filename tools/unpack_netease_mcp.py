#!/usr/bin/env python3
"""Extract the inspected MCPK container's indexed payloads without executing them.

MCPK indices contain hashes, not filenames. Output .bin files are raw members,
not recovered Python source. Encryption/marshal/opcode decoding is a separate
step. This parser intentionally rejects layouts outside the validated format.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inspect(data):
    if len(data) < 24 or data[:4] != b'MCPK':
        raise ValueError('Expected MCPK magic and complete header')
    buckets_start, entries_start, payload_start = struct.unpack_from('<III', data, 12)
    if not 24 <= buckets_start <= entries_start <= payload_start <= len(data):
        raise ValueError('Invalid MCPK index bounds')
    if (entries_start - buckets_start) % 12 or (payload_start - entries_start) % 16:
        raise ValueError('Unsupported MCPK index record sizes')
    entries = [struct.unpack_from('<IIII', data, p) for p in range(entries_start, payload_start, 16)]
    assigned = set()
    records = []
    for bucket in range((entries_start - buckets_start) // 12):
        bucket_hash, table_offset, count = struct.unpack_from('<III', data, buckets_start + bucket * 12)
        if table_offset % 16 or table_offset // 16 + count > len(entries):
            raise ValueError('Bucket points outside the file index')
        for index in range(table_offset // 16, table_offset // 16 + count):
            if index in assigned:
                raise ValueError('File index referenced by multiple buckets')
            assigned.add(index)
            name_hash, offset, length, auxiliary = entries[index]
            start = payload_start + offset
            if start + length > len(data):
                raise ValueError('Member payload outside file')
            raw = data[start:start + length]
            name = '%04d_%08x_%08x.bin' % (index, bucket_hash, name_hash)
            records.append({'index': index, 'bucket_hash': '%08x' % bucket_hash,
                            'name_hash': '%08x' % name_hash, 'offset': start,
                            'length': length, 'auxiliary': auxiliary, 'file': name,
                            'sha256': hashlib.sha256(raw).hexdigest()})
    if len(assigned) != len(entries):
        raise ValueError('File index contains unreferenced entries')
    return {'magic': 'MCPK', 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
            'header_time_value': struct.unpack_from('<d', data, 4)[0],
            'buckets_start': buckets_start, 'entries_start': entries_start, 'payload_start': payload_start,
            'bucket_count': (entries_start - buckets_start) // 12, 'member_count': len(entries),
            'members': sorted(records, key=lambda r: r['index'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Output directory must be empty')
    data = args.input.read_bytes()
    result = inspect(data)
    args.output.mkdir(parents=True, exist_ok=True)
    for member in result['members']:
        start = member['offset']
        (args.output/member['file']).write_bytes(data[start:start + member['length']])
    (args.output/'index.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'members'}, indent=2))


if __name__ == '__main__':
    main()
