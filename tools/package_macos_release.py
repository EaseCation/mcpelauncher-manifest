#!/usr/bin/env python3
"""Create a game-free runtime archive, catalog and recursive Git source snapshot.

Nothing is uploaded. Relative catalog URLs work both in a local directory and
next to an immutable GitHub Release catalog.json.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=repo)


def add_bytes(archive, name, content, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.mtime = len(content), mode, 0
    archive.addfile(info, io.BytesIO(content))


def source_allowed(name):
    path = Path(name)
    return (not any(p in ('private', '.dart_tool', '__pycache__', 'node_modules', '.venv') for p in path.parts)
            and not name.startswith(('mcpelauncher-linux-bin/', 'mcpelauncher-mac-bin/lib/native/'))
            and path.name != 'libminecraftpe.so' and path.suffix.lower() not in ('.apk', '.mcp', '.mcs', '.dmg', '.pyc'))


def export_sources(target):
    modules = git(ROOT, 'submodule', 'status', '--recursive').decode().splitlines()
    repos = [(ROOT, '')] + [(ROOT / line[1:].split()[1], line[1:].split()[1] + '/') for line in modules]
    state = {'root_commit': git(ROOT, 'rev-parse', 'HEAD').decode().strip(), 'components': []}
    with gzip.GzipFile(filename='', mode='wb', fileobj=target.open('wb'), mtime=0) as compressed, \
         tarfile.open(fileobj=compressed, mode='w|') as output:
        for repo, prefix in repos:
            entries = git(repo, 'ls-tree', '-r', '-z', 'HEAD').split(b'\0')
            hashes, folded = {}, {}
            for row in entries:
                if not row: continue
                metadata, name = row.split(b'\t', 1); name = name.decode()
                mode, kind, blob = metadata.decode().split()
                if kind != 'blob': continue
                hashes[name] = blob; folded.setdefault(name.casefold(), []).append(name)
            dirty = {x.decode() for x in git(repo, 'diff', '--name-only', '-z', 'HEAD').split(b'\0') if x}
            overlays, collisions = {}, []
            for name in dirty:
                path = repo/name
                if path.is_file() and not path.is_symlink():
                    content = path.read_bytes()
                    blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
                    # Preserve both Git versions of case-colliding AOSP headers.
                    if any(other != name and hashes[other] == blob for other in folded.get(name.casefold(), [])):
                        collisions.append(name); continue
                    overlays[name] = (content, path.stat().st_mode & 0o777)
                elif not path.exists(): overlays[name] = None
            untracked = [x.decode() for x in git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if x]
            for name in untracked:
                path = repo/name
                if source_allowed(prefix + name) and path.is_file() and not path.is_symlink():
                    if path.suffix in ('.py', '.cpp', '.h', '.md', '.json', '.yml', '.yaml', '.patch', '.dart', '.lock'):
                        if path.stat().st_size > 2*1024*1024: raise ValueError('Review large untracked source: ' + str(path))
                        overlays[name] = (path.read_bytes(), path.stat().st_mode & 0o777)
            process = subprocess.Popen(['git', 'archive', '--format=tar', 'HEAD'], cwd=repo, stdout=subprocess.PIPE)
            with tarfile.open(fileobj=process.stdout, mode='r|') as exported:
                for member in exported:
                    name = prefix + member.name
                    if member.name in overlays or not source_allowed(name): continue
                    member.name = 'source/' + name
                    member.uid = member.gid = member.mtime = 0
                    member.uname = member.gname = ''
                    output.addfile(member, exported.extractfile(member) if member.isfile() else None)
            if process.wait(): raise RuntimeError('git archive failed: ' + str(repo))
            for name, value in overlays.items():
                if value is not None and source_allowed(prefix + name):
                    add_bytes(output, 'source/' + prefix + name, *value)
            state['components'].append({'path': prefix.rstrip('/') or '.', 'commit': git(repo, 'rev-parse', 'HEAD').decode().strip(),
                                        'overlaid_files': sorted(overlays), 'case_collision_headers_preserved_from_git': collisions})
        add_bytes(output, 'source/SOURCE_STATE.json', (json.dumps(state, indent=2)+'\n').encode())
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--version', required=True, help='Immutable release identifier, e.g. 0.1.0-preview.1')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,60}', args.version): p.error('Invalid version')
    app, out = args.runtime.resolve(), args.output.resolve()
    if out.exists(): p.error('--output must not exist')
    integrity = json.loads(app.with_suffix('.integrity.json').read_text())
    if {str(p.relative_to(app)) for p in app.rglob('*') if p.is_file()} != set(integrity['files']):
        raise ValueError('Runtime inventory changed; rebuild before packaging')
    for name, expected in integrity['files'].items():
        if sha(app/name) != expected: raise ValueError('Runtime checksum mismatch: ' + name)
    meta = json.loads((app/'Contents/Resources/runtime.json').read_text())
    if meta.get('launch_protocol') != 1: raise ValueError('Rebuild runtime with bundled launcher adapter')
    out.mkdir(parents=True)
    archive = out/('mcpy-runtime-' + args.version + '-macos-arm64.tar.gz')
    integrity['runtime'] = 'McpyRuntime.app'
    with archive.open('wb') as f, gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0) as gz, tarfile.open(fileobj=gz, mode='w') as tar:
        for path in [app, *sorted(app.rglob('*'))]:
            if path.is_symlink(): raise ValueError('Runtime links are not supported')
            relative = path.relative_to(app)
            name = 'McpyRuntime.app' + ('/' + relative.as_posix() if str(relative) != '.' else '')
            if path.is_dir():
                info = tarfile.TarInfo(name); info.type = tarfile.DIRTYPE; info.mode = 0o755; tar.addfile(info)
            else:
                if path.suffix in ('.apk', '.mcp', '.mcs') or path.name == 'libminecraftpe.so': raise ValueError('Game content in runtime')
                add_bytes(tar, name, path.read_bytes(), path.stat().st_mode & 0o755)
        add_bytes(tar, 'McpyRuntime.integrity.json', (json.dumps(integrity, indent=2)+'\n').encode())
    sources = out/('mcpy-runtime-' + args.version + '-sources.tar.gz')
    state = export_sources(sources)
    catalog = {'schema': 1, 'apk_source': 'netease-pe', 'runtime': {'id': 'macos-arm64-' + args.version, 'platform': 'darwin-arm64',
               'minimum_macos': meta['minimum_macos'], 'archive_root': 'McpyRuntime.app',
               'url': archive.name, 'size': archive.stat().st_size, 'sha256': sha(archive)},
               'profile': meta['game_profile'], 'source': {'url': sources.name, 'size': sources.stat().st_size,
               'sha256': sha(sources), 'root_commit': state['root_commit']}}
    (out/'catalog.json').write_text(json.dumps(catalog, indent=2)+'\n')
    (out/'SHA256SUMS').write_text(''.join(sha(x)+'  '+x.name+'\n' for x in [archive, sources, out/'catalog.json']))
    print(json.dumps({'catalog': str(out/'catalog.json'), 'runtime': str(archive), 'source': str(sources)}, indent=2))


if __name__ == '__main__': main()
