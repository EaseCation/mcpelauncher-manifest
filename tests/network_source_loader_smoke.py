# Python 2.7 behavior test for the network plain-source pack adapter; no game required.
# Usage: python2 tests/network_source_loader_smoke.py tools/netease_network_sources.py
import imp
import json  # noqa: F401  the game has json loaded before the adapter runs
import os
import shutil
import sys
import tempfile

root = tempfile.mkdtemp(prefix='network-source-smoke-')
original_hooks = list(sys.path_hooks)
original_cache = dict(sys.path_importer_cache)
original_modules = set(sys.modules)


class FakeMcpImporter(object):
    """Stands in for the game's importer: claims directories and .mcp paths, resolves only .mcs."""
    def __init__(self, path):
        if not (os.path.isdir(path) or path.endswith('.mcp')):
            raise ImportError('not mcp')
        self.base = path[:-4] + '.content' if path.endswith('.mcp') else path

    def _locate(self, fullname):
        leaf = fullname.rsplit('.', 1)[-1]
        for candidate, package in ((os.path.join(self.base, leaf, '__init__.mcs'), True),
                                   (os.path.join(self.base, leaf + '.mcs'), False)):
            if os.path.isfile(candidate):
                return candidate, package
        return None, False

    def find_module(self, fullname, path=None):
        return self if self._locate(fullname)[0] else None

    def load_module(self, fullname):
        filename, package = self._locate(fullname)
        module = sys.modules.setdefault(fullname, imp.new_module(fullname))
        module.__file__ = filename
        if package:
            module.__path__ = [os.path.dirname(filename)]
        exec(open(filename).read(), module.__dict__)
        return module


def write(path, text):
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, 'w') as handle:
        handle.write(text)


def manifest(pack, bom=False):
    write(os.path.join(pack, 'manifest.json'), ('\xef\xbb\xbf' if bom else '') +
          '{"header": {"name": "Probe", "uuid": "6d1c1f9e-5a8b-4c2e-9f00-0a1b2c3d4e5f", "version": [1, 0, 0]}}')


def load(path_entry, fullname):
    top = fullname.split('.')[0]
    for name in list(sys.modules):
        if name == top or name.startswith(top + '.'):
            del sys.modules[name]
    sys.path.insert(0, path_entry)
    try:
        module = __import__(fullname, fromlist=[''])
        return getattr(module, 'ORIGIN', None), module
    except ImportError:
        return 'ImportError', None
    finally:
        sys.path.remove(path_entry)


try:
    cache = os.path.join(root, 'games', 'com.netease', 'packcache')
    plain = os.path.join(cache, 'plainhash=')
    manifest(plain, bom=True)
    write(os.path.join(plain, 'Probe', '__init__.py'), '')
    write(os.path.join(plain, 'Probe', 'modMain.py'), "ORIGIN = 'plain'\n")
    write(os.path.join(root, 'outside.py'), "ORIGIN = 'outside'\n")
    os.symlink(os.path.join(root, 'outside.py'), os.path.join(plain, 'escape.py'))
    packed = os.path.join(cache, 'mcphash=')
    manifest(packed)
    write(os.path.join(packed, 'Packed.mcp'), 'MCPK')
    write(os.path.join(packed, 'Packed.content', 'Packed', '__init__.mcs'), "ORIGIN = 'mcp'\n")
    mixed = os.path.join(cache, 'mixedhash=')
    manifest(mixed)
    write(os.path.join(mixed, 'Mixed', '__init__.mcs'), "ORIGIN = 'mcp'\n")
    write(os.path.join(mixed, 'Mixed', 'extra.py'), "ORIGIN = 'plain'\n")
    local = os.path.join(root, 'games', 'com.netease', 'behavior_packs', 'local')
    manifest(local)
    write(os.path.join(local, 'Local', '__init__.mcs'), "ORIGIN = 'mcp'\n")
    write(os.path.join(local, 'Plain', '__init__.py'), "ORIGIN = 'plain'\n")

    sys.path_hooks.append(FakeMcpImporter)
    execfile(sys.argv[1], {'PACK_CACHE': cache})
    count = len(sys.path_hooks)

    origin, module = load(plain, 'Probe.modMain')
    assert origin == 'plain', origin
    assert not os.path.exists(os.path.join(plain, 'Probe', 'modMain.pyc'))
    assert load(plain, 'escape')[0] == 'ImportError'
    packs = sys._mcpy_plain_source_packs
    assert list(packs.values())[0]['uuid'] == '6d1c1f9e-5a8b-4c2e-9f00-0a1b2c3d4e5f', packs
    assert load(os.path.join(packed, 'Packed.mcp'), 'Packed')[0] == 'mcp'
    assert load(packed, 'Packed')[0] == 'ImportError'  # .mcs lives only inside the archive
    assert load(mixed, 'Mixed')[0] == 'mcp'
    assert load(local, 'Local')[0] == 'mcp'
    assert load(local, 'Plain')[0] == 'ImportError'  # outside the session pack cache
    assert len(packs) == 1, packs

    execfile(sys.argv[1], {'PACK_CACHE': cache})
    assert len(sys.path_hooks) == count
    try:
        execfile(sys.argv[1], {'PACK_CACHE': os.path.join(root, 'other')})
        raise AssertionError('accepted a different cache')
    except RuntimeError:
        pass
    print('PASS: plain pack import, BOM manifest record, no pyc, symlink escape, MCP archive/mixed/local '
          'packs left to the game importer, idempotence')
finally:
    sys.path_hooks[:] = original_hooks
    sys.path_importer_cache.clear()
    sys.path_importer_cache.update(original_cache)
    for name in set(sys.modules) - original_modules:
        del sys.modules[name]
    for name in ('_mcpy_plain_source_cache', '_mcpy_plain_source_packs'):
        if hasattr(sys, name):
            delattr(sys, name)
    shutil.rmtree(root)
