# coding: utf-8
"""Python 2 developer adapter, installed before world startup via the JNI bridge.

SOURCE_ROOTS is supplied by the host for explicitly selected behavior packs.
Only those directories use the interpreter's ordinary source importer. The
game's MCP importer and ModSDK lifecycle continue to handle all other modules.
"""
import imp
import os
import sys


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _root_for(path):
    for root in _source_roots:
        if _inside(path, root):
            return root
    return None


class _DeveloperSourceImporter(object):
    def __init__(self, directory):
        if not os.path.isdir(directory) or _root_for(directory) is None:
            raise ImportError('Outside developer source roots')
        self.directory = os.path.realpath(directory)

    def _find(self, fullname):
        leaf = fullname.rsplit('.', 1)[-1]
        if not leaf or '/' in leaf or '\\' in leaf:
            raise ImportError('Invalid source module name')
        handle, filename, description = imp.find_module(leaf, [self.directory])
        valid = _root_for(filename) is not None
        if description[2] == imp.PKG_DIRECTORY:
            init = os.path.join(filename, '__init__.py')
            valid = valid and os.path.isfile(init) and _root_for(init) is not None
        else:
            valid = valid and description[2] == imp.PY_SOURCE
        if not valid:
            if handle:
                handle.close()
            raise ImportError('Developer loader accepts only source packages/modules')
        return handle, filename, description

    def find_module(self, fullname, path=None):
        try:
            handle, _, _ = self._find(fullname)
            if handle:
                handle.close()
            return self
        except ImportError:
            return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        handle, filename, description = self._find(fullname)
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            return imp.load_module(fullname, handle, filename, description)
        finally:
            sys.dont_write_bytecode = previous
            if handle:
                handle.close()


def _load_developer_paths(self, paths, side):
    selected, remaining = [], []
    for path in paths:
        root = _root_for(path)
        if root is None:
            remaining.append(path)
            continue
        relative = os.path.relpath(os.path.realpath(path), root)
        parts = relative.split(os.sep)
        if not parts or parts[-1] != 'modMain.py' or '..' in parts:
            raise ValueError('Expected a modMain.py inside the selected behavior pack')
        selected.append('.'.join(parts)[:-3])
    for module in selected:
        # Preserve the original Windows entry's optional modGoodsMain behavior.
        previous = self.loadingWindows
        try:
            self.loadingWindows = True
            self.ImportModAndInit(module, side, False)
        finally:
            self.loadingWindows = previous
    other_loaded = _original_windows(self, remaining, side) if remaining else False
    return bool(selected) or bool(other_loaded)


_source_roots = tuple(os.path.realpath(root) for root in SOURCE_ROOTS)
if not _source_roots or any(not os.path.isdir(root) for root in _source_roots):
    raise ValueError('Developer behavior pack source roots must exist')
if getattr(sys, '_netease_developer_source_roots', None) is not None:
    if tuple(sys._netease_developer_source_roots) != _source_roots:
        raise RuntimeError('Restart the game to change developer source roots')
else:
    import common.minecraftMod as _minecraft_mod
    _original_windows = _minecraft_mod.MinecraftMod.LoadWindowsAddonPy
    sys.path_hooks.insert(0, _DeveloperSourceImporter)
    for _path in list(sys.path_importer_cache):
        if _root_for(_path) is not None:
            del sys.path_importer_cache[_path]
    _minecraft_mod.MinecraftMod.LoadWindowsAddonPy = _load_developer_paths
    sys._netease_developer_source_roots = _source_roots
    print('[DeveloperSource] Enabled %d explicitly selected behavior pack(s)' % len(_source_roots))
