"""Pure structural-rule tests; no proprietary binary or game process is needed."""
import hashlib
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_developer_binary import Resolver, Incompatible, normalized, unique


def words(*values): return struct.pack('<'+'I'*len(values), *values)


class RuleTests(unittest.TestCase):
    def test_relocation_and_field_offsets_preserve_identity_but_register_changes_do_not(self):
        old=words(0x90000000,0x91040000,0xf9400412,0x94000001)
        relocated=words(0xb0002000,0x91200000,0xf9419412,0x94000100)
        self.assertEqual(normalized(old,0x1000),normalized(relocated,0x8000))
        altered=words(0x90000000,0x91040000,0xf9400413,0x94000001)
        self.assertNotEqual(normalized(old,0x1000),normalized(altered,0x1000))

    def test_stack_layout_and_internal_control_flow_are_not_erased(self):
        self.assertNotEqual(normalized(words(0xd10043ff),0), normalized(words(0xd10083ff),0))
        self.assertNotEqual(normalized(words(0x14000001,0xd503201f,0xd65f03c0),0),
                            normalized(words(0x14000002,0xd503201f,0xd65f03c0),0))

    def test_ambiguous_or_missing_candidate_is_an_error(self):
        for candidates in ([],[16,32]):
            with self.assertRaises(Incompatible):unique(candidates,'candidate')

    def fixture(self, copies=1, modified=False):
        body=words(0xa9bf7bfd,0xf9400412,0xd65f03c0)
        image=b'\0'*64+body*copies
        if modified:image=image[:68]+words(0xf9400413)+image[72:]
        resolver=Resolver.__new__(Resolver)
        resolver.elf=SimpleNamespace(data=image,loads=[(1,5,0,0x1000,0,len(image),len(image),0)],
            executable=lambda a:0x1000<=a<0x1000+len(image),offset=lambda a:a-0x1000)
        resolver.rules={'family':'fixture','dispatcher':{'anchor':body[:4].hex(),'size':len(body),
            'digest':hashlib.sha256(normalized(body,0x1040)).hexdigest(),'enter':0,'leave':8,
            'patches':[{'kind':'scalar','offset':4}]}}
        resolver.evidence=[]
        return resolver

    def test_dispatcher_address_is_discovered_not_taken_from_a_version_table(self):
        plan=self.fixture().dispatcher()
        self.assertEqual(plan['begin'],0x1040)
        self.assertEqual(plan['direct'],[[0x1044,0xf9400412,0xfd40040f]])
        for r in (self.fixture(copies=2),self.fixture(modified=True)):
            with self.assertRaises(Incompatible):r.dispatcher()

    def test_optional_ui_failure_does_not_hide_required_dispatcher_success(self):
        r=self.fixture();r.ui=Mock(side_effect=Incompatible('missing UI anchor'))
        result=r.resolve()
        self.assertIsNone(result['ui'])
        self.assertIn('missing UI anchor',result['ui_error'])
        self.assertEqual(result['dispatcher']['begin'],0x1040)

    def clock_fixture(self, base=0x1000):
        r=self.fixture()
        image=bytearray(words(*([0xd503201f]*192)))
        def jump(source,target):
            return 0x14000000+((target-source)//4 & 0x3ffffff)
        for wrapper in (0,32):
            struct.pack_into('<I',image,wrapper+16,jump(wrapper+16,64))
        struct.pack_into('<I',image,64+160,jump(64+160,384))
        image[384:392]=words(0xfd000800,0xd65f03c0)
        r.elf=SimpleNamespace(data=bytes(image),loads=[],
            executable=lambda a:base<=a<base+len(image),offset=lambda a:a-base)
        r.rules['shapes']={name:{'size':size,'digest':hashlib.sha256(
            normalized(image[offset:offset+size],base+offset)).hexdigest()}
            for name,offset,size in [('math_unary_wrapper',0,20),('math_unary',64,244),('floatFromDouble',384,8)]}
        r.registered_function=lambda name:base+{'fabs':0,'ceil':32}[name]
        return r

    def test_clock_constructor_is_resolved_through_both_math_registrations(self):
        for base in (0x1000,0x8000):
            self.assertEqual(self.clock_fixture(base).float_constructor(),base+384)

    def test_clock_rejects_changed_constructor_or_disagreeing_helpers(self):
        r=self.clock_fixture()
        r.elf.data=r.elf.data[:384]+words(0xfd000801)+r.elf.data[388:]
        with self.assertRaises(Incompatible):r.float_constructor()
        r=self.clock_fixture()
        image=bytearray(r.elf.data)
        image[448:692]=image[64:308]
        struct.pack_into('<I',image,48,0x14000000+(448-48)//4)
        r.elf.data=bytes(image)
        with self.assertRaisesRegex(Incompatible,'shared CPython'):
            r.float_constructor()

    def test_missing_clock_binding_preserves_ui_capability(self):
        r=self.fixture();r.ui=Mock(return_value={'reload':123})
        r.float_constructor=Mock(side_effect=Incompatible('float ABI changed'))
        result=r.resolve()
        self.assertEqual(result['ui'],{'reload':123})
        self.assertEqual(result['input_clock_error'],'float ABI changed')


if __name__=='__main__':unittest.main()
