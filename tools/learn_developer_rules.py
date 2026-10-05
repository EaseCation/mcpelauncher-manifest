#!/usr/bin/env python3
"""Developer-only rule training against the audited 3.9 baseline.

Requires capstone for complete instruction/register accounting. The runtime
recognizer uses only the exported rules and the standard library, not these
baseline addresses, the baseline ELF or capstone.
"""
import argparse, hashlib, json, re, struct
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from inspect_android_elf import ELF
from analyze_developer_binary import normalized

BASELINE_SHA='a0f5332d443f20063cc0adce5cf935597cccf6c790ea6a9a7e79ec8a067b72f3'
FUNCTIONS={
 'check_wrapper':(0x93ca240,72), 'check_impl':(0x9381f80,64),
 'thread':(0x123e5a28,48), 'isMainThread':(0x123e5a00,40), 'boolean':(0x12143f6c,40),
 'context':(0x94c305c,108), 'game':(0x94c3768,248), 'gilEnsure':(0x12288454,152),
 'gilRelease':(0x122884ec,224), 'initModule':(0x1228461c,136), 'reload':(0x6364d14,172)}
SPECIAL=[
 (0x10de8cb4,0x52beab12,0x52beab10,16),(0x10de8cb8,0x72804512,0x72804510,16),
 (0x10debe1c,0x7a4a1a48,0x7a4a1a08,16),(0x10debea8,0x1a92b220,0x1a90b220,16),
 (0x10df4888,0x7a4a1a48,0x7a4a1a08,16),(0x10df4914,0x1a92b220,0x1a90b220,16),
 (0x10df7268,0x51000641,0x51000601,16),(0x10df726c,0x1b127c32,0x1b107c30,16),
 (0x10df7270,0x7200025f,0x7200021f,16),(0x10df7318,0x1a80b241,0x1a80b201,16),
 (0x10df9380,0x52b83452,0x52b83450,16),(0x10df938c,0x72884ef2,0x72884ef0,16),
 (0x10df9590,0xcb120210,0xcb110210,17),(0x10df98c8,0xf8717a51,0xf8717a11,16),
 (0x10dfa4b0,0xf9414232,0xf9414230,16),(0x10dfa4b4,0xf100025f,0xf100021f,16),
 (0x10dfa4c8,0xf9416640,0xf9416600,16)]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 e=ELF(a.baseline)
 if hashlib.sha256(e.data).hexdigest()!=BASELINE_SHA:raise ValueError('Training requires the audited baseline ELF')
 def shape(address,size):
  code=e.data[e.offset(address):e.offset(address)+size]
  return {'size':size,'digest':hashlib.sha256(normalized(code,address)).hexdigest()}
 begin,end=0x10de8388,0x10dfd230
 body=e.data[e.offset(begin):e.offset(end)];md=Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN)
 instructions=list(md.disasm(body,begin))
 assert len(instructions)*4==len(body)
 assert not any(re.search(r'\b[sdqv](15|30)\b',i.op_str) for i in instructions)
 used={i.address for i in instructions if re.search(r'\b[wx]18\b',i.op_str)}
 patches=[]
 for at,original,replacement,scratch in SPECIAL:
  assert e.unpack('<I',e.offset(at))[0]==original and at in used
  patches.append({'offset':at-begin,'kind':'gpr','register_xor':original^replacement,'scratch':scratch})
 for i in instructions:
  op=int.from_bytes(i.bytes,'little')
  if i.address not in used or i.address in {s[0] for s in SPECIAL}:continue
  assert (op&31)==18 and ((op>>5)&31)!=18
  kind=op&0xffe00c00
  assert kind in (0xb8400000,0xf8400000,0xb8000000,0xf8000000) or op&0xffc00000==0xb9400000
  patches.append({'offset':i.address-begin,'kind':'scalar'})
 assert len(patches)==len(used)==470
 dispatcher=dict(shape(begin,len(body)),anchor=body[:36].hex(),enter=0x20,leave=len(body)-32,patches=sorted(patches,key=lambda x:x['offset']))
 rules={'schema':1,'family':'android-python27-scalar-dispatch-v1',
        'normalization':'aarch64-address-fields-v1','dispatcher':dispatcher,
        'shapes':{name:shape(*pair) for name,pair in FUNCTIONS.items()},
        'reload_closure':'NSt6__ndk110__function6__funcIZN13MinecraftGame25handleReloadUIDefinitionsEvE3$_0NS_9allocatorIS3_EEFvRNS_6vectorI10PackReportNS4_IS7_EEEEEEE'}
 a.output.write_text(json.dumps(rules,indent=2)+'\n')
 print('Exported address-free rules with %d accounted x18 instructions'%len(patches))
if __name__=='__main__':main()
