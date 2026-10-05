#!/usr/bin/env python3
"""Inspect ELF64 AArch64 via PT_DYNAMIC even when section names are obfuscated.
No third-party dependencies. Writes metadata, never executes the input library.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


class ELF:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if self.data[:6] != b'\x7fELF\x02\x01':
            raise ValueError('expected little-endian ELF64')
        h = self.unpack('<16sHHIQQQIHHHHHH', 0)
        if h[2] != 183:
            raise ValueError('expected AArch64')
        self.entry = h[4]
        self.segments = [self.unpack('<IIQQQQQQ', h[5] + i * h[9]) for i in range(h[10])]
        self.loads = [s for s in self.segments if s[0] == 1]
        dynamic = next(s for s in self.segments if s[0] == 2)
        self.tags = {}
        for offset in range(dynamic[2], dynamic[2] + dynamic[5], 16):
            tag, value = self.unpack('<QQ', offset)
            if tag == 0:
                break
            self.tags.setdefault(tag, []).append(value)
        self.strtab = self.offset(self.tag(5))
        self.strsize = self.tag(10)
        count = self.symbol_count()
        syms = self.offset(self.tag(6))
        self.symbols = []
        for i in range(count):
            name, info, other, section, value, size = self.unpack('<IBBHQQ', syms + i * self.tag(11))
            if name >= self.strsize:
                raise ValueError('symbol name outside DT_STRSZ')
            self.symbols.append(dict(name=self.string(self.strtab + name, self.strsize-name),
                                     binding=info >> 4, type=info & 15, defined=section != 0,
                                     value=value, size=size, visibility=other & 3))
        self.relocations = {}
        for address_tag, size_tag in [(7, 8), (23, 2)]:
            if address_tag not in self.tags:
                continue
            offset = self.offset(self.tag(address_tag))
            for i in range(0, self.tag(size_tag), 24):
                address, info, addend = self.unpack('<QQq', offset + i)
                kind, index = info & 0xffffffff, info >> 32
                if kind == 1027:  # R_AARCH64_RELATIVE
                    self.relocations[address] = addend
                elif kind == 257 and index < len(self.symbols) and self.symbols[index]['defined']:
                    self.relocations[address] = self.symbols[index]['value'] + addend

    def unpack(self, fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(self.data):
            raise ValueError('ELF structure outside file')
        return struct.unpack_from(fmt, self.data, offset)

    def offset(self, address):
        for s in self.loads:
            if s[3] <= address < s[3] + s[5]:
                return s[2] + address - s[3]
        raise ValueError('virtual address not file-backed: ' + hex(address))

    def string(self, offset, limit=1024):
        end = self.data.find(b'\0', offset, min(offset + limit, len(self.data)))
        if end < 0:
            return ''
        return self.data[offset:end].decode('utf-8', 'replace')

    def tag(self, tag):
        return self.tags[tag][0]

    def symbol_count(self):
        if 4 in self.tags:
            return self.unpack('<II', self.offset(self.tag(4)))[1]
        gh = self.offset(self.tag(0x6ffffef5))
        buckets, start, bloom, _ = self.unpack('<IIII', gh)
        base = gh + 16 + 8*bloom
        values = self.unpack('<' + 'I'*buckets, base)
        index = max(values, default=0)
        if index < start:
            return start
        chains = base + 4*buckets
        while not self.unpack('<I', chains + 4*(index-start))[0] & 1:
            index += 1
        return index + 1

    def pointer(self, address):
        if address in self.relocations:
            return self.relocations[address]
        try:
            return self.unpack('<Q', self.offset(address))[0]
        except ValueError:
            return 0

    def executable(self, address):
        return any(s[1] & 1 and s[3] <= address < s[3]+s[5] for s in self.loads)

    def report(self):
        names = ['JNI_OnLoad', 'ANativeActivity_onCreate', 'GameActivity_register',
                 'Java_com_google_androidgamesdk_GameActivity_initializeNativeCode',
                 'Java_com_mojang_minecraftpe_MainActivity_nativeRegisterThis',
                 'Java_com_mojang_minecraftpe_MainActivity_000246_run__']
        methods = []
        # JNINativeMethod is {name*, signature*, function*}. Check the two strings
        # and a relocated executable address before treating a tuple as a candidate.
        for address, value in self.relocations.items():
            try:
                name = self.string(self.offset(value), 160)
                if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{2,120}', name):
                    continue
                if not any(word in name.lower() for word in ['native', 'init', 'create', 'start', 'run']):
                    continue
                sig = self.string(self.offset(self.pointer(address + 8)), 500)
                func = self.pointer(address + 16)
                if re.fullmatch(r'\([^ ]*\)[VZBCSIJFDL\[].*', sig) and self.executable(func):
                    methods.append(dict(name=name, signature=sig, table_va=hex(address), function_va=hex(func)))
            except ValueError:
                continue
        return dict(path=str(self.path.resolve()), size=len(self.data),
                    sha256=hashlib.sha256(self.data).hexdigest(), entry_va=hex(self.entry),
                    needed=[self.string(self.strtab+n) for n in self.tags.get(1, [])],
                    load_segments=[dict(va=hex(s[3]), offset=hex(s[2]), file_size=s[5], memory_size=s[6], flags=s[1]) for s in self.loads],
                    dynamic_symbols=len(self.symbols),
                    entry_exports={n:[dict(va=hex(s['value']), type=s['type']) for s in self.symbols if s['defined'] and s['name']==n] for n in names},
                    init_array_va=hex(self.tag(25)) if 25 in self.tags else None,
                    init_array_count=self.tag(27)//8 if 27 in self.tags else 0,
                    first_constructors=[hex(self.pointer(self.tag(25)+8*i)) for i in range(min(8,self.tag(27)//8))] if 27 in self.tags else [],
                    jni_table_candidates=methods,
                    imports=[s['name'] for s in self.symbols if not s['defined'] and s['name']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('libraries', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps([ELF(p).report() for p in args.libraries], ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(result + '\n')
    else:
        print(result)


if __name__ == '__main__':
    main()
