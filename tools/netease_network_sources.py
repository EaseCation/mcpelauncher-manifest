# coding: utf-8
"""Python 2 network adapter for server-delivered plain-source behavior packs.

The developer APK's MCP importer resolves only packed .mcs modules, so a pack
that a development server delivers as plain .py files fails with ImportError.
PACK_CACHE is supplied by the host: the session's pack download directory.

Only pack directories below PACK_CACHE that contain Python sources and no
packed (.mcp/.mcs) or compiled files are handled here. Every other path,
including all reviewed MCP packs and mixed packs, stays with the game's own
importer. Release clients still require a reviewed .mcp package.
"""
import imp
import json
import os
import sys

_FOREIGN = ('.mcp', '.mcs', '.pyc', '.pyo')


def _inside(path, root):
    return path == root or path.startswith(root + os.sep)


def _pack_root(path):
    path = os.path.realpath(path)
    if path == _cache or not _inside(path, _cache):
        return None
    return os.path.join(_cache, os.path.relpath(path, _cache).split(os.sep)[0])


def _plain_pack(root):
    """A pack qualifies only as a whole, so one pack is never split between importers."""
    known = _plain.get(root)
    if known is not None:
        return known
    sources = False
    for directory, _, files in os.walk(root):
        for name in files:
            extension = os.path.splitext(name)[1].lower()
            if extension in _FOREIGN:
                _plain[root] = False
                return False
            sources = sources or extension == '.py'
    result = sources and os.path.isfile(os.path.join(root, 'manifest.json'))
    _plain[root] = result
    return result


def _record(root):
    if root in _loaded:
        return
    identity = {'name': None, 'uuid': None, 'version': None}
    try:
        with open(os.path.join(root, 'manifest.json'), 'rb') as handle:
            data = handle.read()
        if data.startswith('\xef\xbb\xbf'):
            data = data[3:]
        header = json.loads(data)['header']
        identity = {'name': header.get('name'), 'uuid': header.get('uuid'), 'version': header.get('version')}
    except (IOError, ValueError, KeyError, TypeError, AttributeError):
        pass
    _loaded[root] = identity
    print('[PlainSourcePack] Loaded plain sources for %s %s %s; release clients require a reviewed .mcp'
          % (identity['name'], identity['uuid'], identity['version']))


class _PlainPackImporter(object):
    def __init__(self, path):
        root = _pack_root(path) if os.path.isdir(path) else None
        if root is None or not _plain_pack(root):
            raise ImportError('Not a server-delivered plain-source pack')
        self.root = root
        self.directory = os.path.realpath(path)

    def _find(self, fullname):
        leaf = fullname.rsplit('.', 1)[-1]
        if not leaf or '/' in leaf or '\\' in leaf:
            raise ImportError('Invalid source module name')
        handle, filename, description = imp.find_module(leaf, [self.directory])
        valid = _inside(os.path.realpath(filename), self.root)
        if description[2] == imp.PKG_DIRECTORY:
            init = os.path.join(filename, '__init__.py')
            valid = valid and os.path.isfile(init) and _inside(os.path.realpath(init), self.root)
        else:
            valid = valid and description[2] == imp.PY_SOURCE
        if not valid:
            if handle:
                handle.close()
            raise ImportError('Plain-source packs accept only source modules inside the pack')
        return handle, filename, description

    def find_module(self, fullname, path=None):
        try:
            handle, _, _ = self._find(fullname)
        except ImportError:
            return None
        if handle:
            handle.close()
        return self

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        handle, filename, description = self._find(fullname)
        previous = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            module = imp.load_module(fullname, handle, filename, description)
        finally:
            sys.dont_write_bytecode = previous
            if handle:
                handle.close()
        _record(self.root)
        return module


_cache = os.path.realpath(PACK_CACHE)
if getattr(sys, '_mcpy_plain_source_cache', None) is not None:
    if sys._mcpy_plain_source_cache != _cache:
        raise RuntimeError('Restart the game to change the pack cache directory')
else:
    _plain = {}
    _loaded = {}
    sys.path_hooks.insert(0, _PlainPackImporter)
    for _path in list(sys.path_importer_cache):
        if _pack_root(_path) is not None:
            del sys.path_importer_cache[_path]
    sys._mcpy_plain_source_cache = _cache
    sys._mcpy_plain_source_packs = _loaded
    print('[PlainSourcePack] Enabled for server-delivered packs without .mcp/.mcs')
