#!/usr/bin/env python3
"""Resolve an audited ARM64 engine family from structure, without version/address tables.

This is a bounded compatibility recognizer, not a general disassembler or ABI guesser.
Rules contain normalized code digests learned from a baseline; output addresses always
come from the input ELF. Unknown or ambiguous structures fail closed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
# Bundled scripts live inside a signed, immutable application.
sys.dont_write_bytecode = True
from inspect_android_elf import ELF


class Incompatible(ValueError):
    pass


def unique(items, label):
    items = sorted(set(items))
    if len(items) != 1:
        raise Incompatible('%s: expected one verified candidate, found %d' % (label, len(items)))
    return items[0]


def signed(n, bits):
    return n - (1 << bits) if n & (1 << (bits-1)) else n


def branch(word, address):
    if word & 0x7c000000 != 0x14000000:
        raise Incompatible('Expected direct branch')
    return address + 4*signed(word & 0x3ffffff, 26)


def normalized(data, address):
    """Ignore relocatable addresses and data offsets; retain registers, stack and CFG."""
    output = bytearray()
    for i, (word,) in enumerate(struct.iter_unpack('<I', data)):
        pc = address + i*4
        rd, rn = word & 31, (word >> 5) & 31
        if word & 0x1f000000 == 0x10000000:  # ADR/ADRP
            word &= 0x9f00001f
        elif word & 0xfc000000 == 0x94000000:  # external calls
            word &= 0xfc000000
        elif word & 0xfc000000 == 0x14000000 and not address <= branch(word, pc) < address + len(data):
            word &= 0xfc000000
        elif word & 0x3b000000 == 0x39000000 and rn not in (29, 31):
            word &= ~(0xfff << 10)  # retain load/store width, base and value registers
        elif word & 0x1f000000 == 0x11000000 and rd not in (29, 31) and rn not in (29, 31):
            word &= ~(0xfff << 10)  # non-stack address/field immediates
        output.extend(struct.pack('<I', word))
    return bytes(output)


def loaded_fnv(data):
    # Model the existing Apple ELF loader's TLS instruction rewrite.
    data = bytearray(data)
    for i in range(0, len(data), 4):
        word = struct.unpack_from('<I', data, i)[0]
        if word & 0xffffffe0 == 0xd53bd040:
            struct.pack_into('<I', data, i, 0xd53bd060 | (word & 31))
    h = 14695981039346656037
    for b in data:
        h = ((h ^ b) * 1099511628211) & 0xffffffffffffffff
    return h


class Resolver:
    def __init__(self, path, rules):
        self.elf = ELF(path)
        self.rules = rules
        self.refs = {}
        for slot, value in self.elf.relocations.items():
            self.refs.setdefault(value, []).append(slot)
        self.xref_cache = {}
        self.evidence = []

    def data(self, a, n):
        e = self.elf
        if not e.executable(a) or not e.executable(a+n-1) or n <= 0 or n % 4:
            raise Incompatible('Code range is outside an executable segment')
        off = e.offset(a)
        return e.data[off:off+n]

    def word(self, a):
        return struct.unpack('<I', self.data(a, 4))[0]

    def match(self, a, shape):
        try:
            data = self.data(a, shape['size'])
            return hashlib.sha256(normalized(data, a)).hexdigest() == shape['digest']
        except (ValueError, struct.error):
            return False

    def verify(self, a, name):
        if not self.match(a, self.rules['shapes'][name]):
            raise Incompatible('Unexpected instruction structure: ' + name)
        self.evidence.append({'rule': name, 'address': a})
        return a

    def string_addresses(self, text):
        needle = text.encode()+b'\0'; found=[]; pos=0
        while True:
            pos = self.elf.data.find(needle, pos)
            if pos < 0: return found
            seg = next((s for s in self.elf.loads if s[2] <= pos < s[2]+s[5]), None)
            if seg: found.append(seg[3]+pos-seg[2])
            pos += len(needle)

    def address(self, pc):
        word = self.word(pc)
        if word & 0x1f000000 != 0x10000000: return None
        imm = signed(((word>>29)&3) | (((word>>5)&0x7ffff)<<2), 21)
        if word & 0x80000000:
            value = (pc & ~4095)+(imm<<12)
            following = self.word(pc+4)
            if following & 0xffc00000 != 0x91000000 or ((following>>5)&31) != word&31 or following&31 != word&31:
                return None
            return value+((following>>10)&0xfff), word&31
        return pc+imm, word&31

    def xrefs(self, addresses):
        addresses=set(addresses);key=tuple(sorted(addresses))
        if key in self.xref_cache:return self.xref_cache[key]
        pages={a & ~4095 for a in addresses};result=[]
        for seg in self.elf.loads:
            if not seg[1]&1:continue
            region=self.elf.data[seg[2]:seg[2]+seg[5]]
            # Filter ADR/ADRP by their high instruction byte before decoding.
            for m in re.finditer(b'[\x10\x30\x50\x70\x90\xb0\xd0\xf0]',region):
                off=m.start()-3
                if off<0 or off%4 or off+8>len(region):continue
                word=struct.unpack_from('<I',region,off)[0]
                if word&0x1f000000!=0x10000000:continue
                pc=seg[3]+off;imm=signed(((word>>29)&3)|(((word>>5)&0x7ffff)<<2),21)
                if word&0x80000000 and (pc&~4095)+(imm<<12) not in pages:continue
                value=self.address(pc)
                if value and value[0] in addresses:result.append(pc)
        self.xref_cache[key]=result
        return result

    def call(self, a):
        if self.word(a)&0xfc000000 != 0x94000000:raise Incompatible('Expected BL')
        target=branch(self.word(a),a)
        # Linker veneers may tail-branch to the real implementation.
        for _ in range(4):
            if self.word(target)&0xfc000000 != 0x14000000:return target
            target=branch(self.word(target),target)
        raise Incompatible('Too many branch veneers')

    def anchored_function(self, text, shape):
        candidates=[]
        for pc in self.xrefs(self.string_addresses(text)):
            for start in range(max(0,pc-256),pc+1,4):
                if self.match(start,self.rules['shapes'][shape]):candidates.append(start)
        return self.verify(unique(candidates,shape),shape)

    def registered_function(self, name):
        candidates=[]
        for value in self.string_addresses(name):
            for slot in self.refs.get(value,[]):
                target=self.elf.pointer(slot+8)
                if self.elf.executable(target) and target%4==0:candidates.append(target)
        return unique(candidates,name)

    def vtable(self, name):
        tables=[]
        for value in self.string_addresses(name):
            for name_slot in self.refs.get(value,[]):
                for ti_slot in self.refs.get(name_slot-8,[]):
                    start=ti_slot+8
                    if self.elf.pointer(ti_slot-8)==0 and self.elf.executable(self.elf.pointer(start)):
                        tables.append(start)
        return unique(tables,name)

    def dispatcher(self):
        rule=self.rules['dispatcher'];needle=bytes.fromhex(rule['anchor']);candidates=[]
        for seg in self.elf.loads:
            if not seg[1]&1:continue
            region=self.elf.data[seg[2]:seg[2]+seg[5]];pos=0
            while True:
                pos=region.find(needle,pos)
                if pos<0:break
                a=seg[3]+pos
                if a%4==0 and self.match(a,rule):candidates.append(a)
                pos+=4
        begin=unique(candidates,'arm64_dispatcher');body=self.data(begin,rule['size'])
        plan={'begin':begin,'end':begin+len(body),'loaded_fnv':loaded_fnv(body),
              'enter':begin+rule['enter'],'leave':begin+rule['leave'],'direct':[],'special':[]}
        for patch in rule['patches']:
            a=begin+patch['offset'];word=self.word(a)
            if patch['kind']=='scalar':
                replacement=((word|0x04000000)&~31)|15
                plan['direct'].append([a,word,replacement])
            else:
                plan['special'].append([a,word,word^patch['register_xor'],patch['scratch']])
        self.evidence.append({'rule':'arm64_dispatcher','address':begin,'direct':len(plan['direct']),
                              'special':len(plan['special']),'structure_sha256':rule['digest']})
        return plan

    def ui(self):
        candidates=[]
        for pc in self.xrefs(self.string_addresses('check_ui_def')):
            # Registration's name x1 and callback x2 must be in the same small block.
            if self.address(pc)[1]!=1:continue
            for at in range(pc+4,pc+24,4):
                value=self.address(at)
                if value and value[1]==2 and self.match(value[0],self.rules['shapes']['check_wrapper']):
                    candidates.append(value[0])
        wrapper=self.verify(unique(candidates,'check_ui_def callback'),'check_wrapper')
        check=self.verify(self.call(wrapper+28),'check_impl')
        output={}
        for name,offset in [('thread',32),('isMainThread',36),('context',44),('game',48)]:
            output[name]=self.verify(self.call(check+offset),name)
        # The standard-library singleton's cold initialization is not part of
        # its pointer-return ABI. Verify its hot return path plus the shared
        # thread-identity call used by the actual comparison function.
        identity = self.call(output['isMainThread'] + 16)
        identity_calls = [self.call(at) for at in range(output['thread'], output['thread']+128, 4)
                          if self.word(at)&0xfc000000 == 0x94000000]
        if identity not in identity_calls:
            raise Incompatible('Thread singleton and checker disagree on identity API')
        # CPython's own built-in initialization supplies the real module constructor.
        constructors=[]
        for module in ('_json','imp'):
            entry=self.registered_function(module);calls=[]
            for at in range(entry,entry+192,4):
                if self.word(at)==0x52807ea4 and self.word(at+4)&0xfc000000==0x94000000:
                    calls.append(self.call(at+4))  # mov w4, #1013 (CPython API version)
            constructors.append(unique(calls,module+' module constructor'))
        output['initModule']=self.verify(unique(constructors,'shared CPython constructor'),'initModule')
        output['boolean']=self.verify(branch(self.word(self.registered_function('isnan')+56),self.registered_function('isnan')+56),'boolean')
        output['gilEnsure']=self.anchored_function("Couldn't create thread-state for new thread",'gilEnsure')
        output['gilRelease']=self.anchored_function('auto-releasing thread-state, but no thread-state for this thread','gilRelease')
        output['vtable']=self.vtable('13MinecraftGame')
        closure=self.vtable(self.rules['reload_closure'])
        sites=self.xrefs([closure]);entries=[]
        for index in range(256):
            target=self.elf.pointer(output['vtable']+index*8)
            if not self.elf.executable(target):break
            if self.match(target,self.rules['shapes']['reload']) and any(target<=site<target+256 for site in sites):
                entries.append((index,target))
        index,target=unique(entries,'UI reload virtual method')
        output['reload']=self.verify(target,'reload');output['reload_index']=index
        return output

    def resolve(self):
        result={'schema':1,'rule_family':self.rules['family'],'elf_sha256':hashlib.sha256(self.elf.data).hexdigest(),
                'elf_size':len(self.elf.data),'mapping_end':max(s[3]+s[6] for s in self.elf.loads),
                'dispatcher':self.dispatcher()}
        try:result['ui']=self.ui()
        except (ValueError, KeyError, IndexError, struct.error) as error:
            result['ui']=None;result['ui_error']=str(error)
        result['evidence']=self.evidence
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('library',type=Path);p.add_argument('--rules',type=Path,default=Path(__file__).with_name('developer_binary_rules.json'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        result=Resolver(a.library,json.loads(a.rules.read_text())).resolve()
        result['rules_sha256']=hashlib.sha256(a.rules.read_bytes()).hexdigest()
    except (OSError,ValueError,KeyError,IndexError,StopIteration,struct.error) as error:
        print(json.dumps({'ok':False,'code':'unsupported_binary_structure','stage':'native_compatibility',
                          'error':str(error),'hint':'Keep the previous engine and include this diagnostic when reporting compatibility.'}))
        return 1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    temporary=a.output.with_suffix(a.output.suffix+'.tmp');temporary.write_text(json.dumps(result,indent=2)+'\n');temporary.replace(a.output)
    print(json.dumps({'ok':True,'rule_family':result['rule_family'],'capabilities':{'arm64_dispatcher':True,'json_ui_reload':result['ui'] is not None},'output':str(a.output)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
