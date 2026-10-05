# Python 2.7 behavior test for the in-game development adapter; no game required.
import imp
import os
import sys
import types

root = '/tmp/source-loader-smoke-' + str(os.getpid())
os.mkdir(root)
original_hooks = list(sys.path_hooks)
original_cache = dict(sys.path_importer_cache)
original_modules = set(sys.modules)
try:
    pack = os.path.join(root, 'pack')
    os.makedirs(os.path.join(pack, 'Probe'))
    open(os.path.join(pack, 'Probe', '__init__.py'), 'w').write('')
    open(os.path.join(pack, 'Probe', 'value.py'), 'w').write('VALUE = 42\n')
    outside = os.path.join(root, 'outside.py')
    open(outside, 'w').write('VALUE = 99\n')
    os.symlink(outside, os.path.join(pack, 'escape.py'))
    common = types.ModuleType('common'); common.__path__ = []
    module = types.ModuleType('common.minecraftMod')
    class MinecraftMod(object):
        loadingWindows = False
        calls = []
        def LoadWindowsAddonPy(self, paths, side):
            self.calls.append(('original', paths, side))
            return True
        def ImportModAndInit(self, name, side, mobile):
            self.calls.append((name, side, mobile))
    module.MinecraftMod = MinecraftMod
    common.minecraftMod = module
    sys.modules['common'] = common
    sys.modules['common.minecraftMod'] = module
    scope = {'SOURCE_ROOTS': [pack]}
    execfile(sys.argv[1], scope)
    importer = scope['_DeveloperSourceImporter'](pack)
    assert importer.find_module('Probe') is importer
    assert importer.find_module('escape') is None
    try:
        scope['_DeveloperSourceImporter'](root)
        raise AssertionError('accepted outside root')
    except ImportError:
        pass
    sys.path.insert(0, pack)
    import Probe.value
    assert Probe.value.VALUE == 42
    assert not os.path.exists(os.path.join(pack, 'Probe', 'value.pyc'))
    client = MinecraftMod()
    assert client.LoadWindowsAddonPy([os.path.join(pack, 'Probe', 'modMain.py'), outside], 'InitServer')
    assert client.calls == [('Probe.modMain', 'InitServer', False), ('original', [outside], 'InitServer')]
    assert client.loadingWindows is False
    count = len(sys.path_hooks)
    execfile(sys.argv[1], {'SOURCE_ROOTS': [pack]})
    assert len(sys.path_hooks) == count
    print('PASS: source import, package import, no pyc, path boundary, symlink escape, original fallback, idempotence')
finally:
    sys.path_hooks[:] = original_hooks
    sys.path_importer_cache.clear(); sys.path_importer_cache.update(original_cache)
    for name in set(sys.modules) - original_modules:
        del sys.modules[name]
    if hasattr(sys, '_netease_developer_source_roots'):
        del sys._netease_developer_source_roots
    for directory, folders, files in os.walk(root, topdown=False):
        for filename in files:
            os.unlink(os.path.join(directory, filename))
        for folder in folders:
            os.rmdir(os.path.join(directory, folder))
    os.rmdir(root)
