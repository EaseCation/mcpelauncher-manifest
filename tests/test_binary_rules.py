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


if __name__=='__main__':unittest.main()
