"""Development pack links retain source ownership across repeated preparations."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('run_netease_dev', Path(__file__).resolve().parents[1]/'tools/run_netease_dev.py')
launcher = importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


class SourceLinkTests(unittest.TestCase):
    def test_links_update_live_without_copy_and_can_be_reprepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);addon=root/'assembled';pack=addon/'behavior_pack';pack.mkdir(parents=True)
            (pack/'manifest.json').write_text(json.dumps({'header':{'uuid':'11111111-1111-1111-1111-111111111111'}}))
            source=pack/'logic.py';source.write_text('VALUE=1')
            for _ in range(2):
                with patch.object(launcher.shutil,'copytree',side_effect=AssertionError('link mode must not copy')):
                    _, names, _=launcher.install_source_addons([addon],root/'installed',link=True)
                target=root/'installed/behavior_packs'/names[0]
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(),pack.resolve())
            source.write_text('VALUE=2')
            self.assertEqual((target/'logic.py').read_text(),'VALUE=2')
            launcher.install_source_addons([addon],root/'installed',link=False)
            self.assertFalse(target.is_symlink())
            self.assertEqual(source.read_text(),'VALUE=2')


if __name__=='__main__':unittest.main()
