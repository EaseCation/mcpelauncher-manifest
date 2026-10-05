#!/usr/bin/env python3
"""Collect private login input or authenticate using the existing Dart MPay client."""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'build-macos-arm64/netease-online/private'


def private_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_config(directory):
    source = ROOT / 'build-macos-arm64/netease-dev/game/assets/netease_data'
    sdk = json.loads(base64.b64decode(source.read_bytes()))
    # SdkBase.doConfigVal calls StrUtil.validate for APPID/JF_GAMEID.
    # UNISDK_SERVER_KEY is a 124-byte substitution table, not a login secret.
    table = base64.b64decode(sdk['UNISDK_SERVER_KEY'])
    if len(table) != 124:
        raise ValueError('Unexpected SDK configuration encoding')
    mapping = {(table[i] - 76 + table[62+i]) & 255: table[62+i] for i in range(62)}
    decode = lambda value: bytes(mapping.get(c, c) for c in value.encode()).decode()
    app_id, game_id = decode(sdk['APPID']), decode(sdk['JF_GAMEID'])
    if game_id != 'x19':
        raise ValueError('Unexpected developer APK product')
    # MpayApi.getVersion() in this APK returns 3.4.0.
    config = {
        'package_name': 'com.netease.mctest',
        'user_agent': 'com.netease.mctest/840297020 NeteaseMobileGame/a3.4.0 (macOS arm64;32)',
        'mpay_app': {
            'game_id': app_id, 'jf_game_id': game_id,
            'app_channel': sdk['APP_CHANNEL'], 'pkg_channel': sdk['APP_CHANNEL'],
            'gv': '840297020', 'gvn': '3.9.100.297020', 'cv': 'a3.4.0', 'sv': '32',
            # Do not send identifiers copied from the Dart library's x19 defaults.
            'ext_ci': '', 'mcount_app_key': '',
        },
    }
    private_json(directory / 'sdk-config.json', config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-only', action='store_true', help='Prompt locally and save private input; no network')
    parser.add_argument('--prepare-only', action='store_true', help='Write non-secret APK configuration; no network')
    parser.add_argument('--private-dir', type=Path, default=PRIVATE)
    args = parser.parse_args()
    os.umask(0o077)
    directory = args.private_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.stat().st_uid != os.getuid() or stat.S_IMODE(directory.stat().st_mode) & 0o077:
        parser.error('Private directory must be owned by you with mode 0700')
    prepare_config(directory)
    if args.prepare_only:
        print('Developer APK login configuration prepared; no network request sent.')
        return 0
    credentials = directory / 'login.json'
    if args.collect_only or not credentials.exists():
        if not sys.stdin.isatty():
            parser.error('Run --collect-only in your local terminal first')
        username = getpass.getpass('网易账号（输入隐藏）: ')
        password = getpass.getpass('密码（输入隐藏）: ')
        if not username or not password:
            parser.error('Account and password must not be empty')
        private_json(credentials, {'username': username, 'password': password})
        del username, password
    st = credentials.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        parser.error('Input must be a private regular file owned by you (0600)')
    if args.collect_only:
        print('已保存私有输入；尚未联网。可以回到对话告诉我已准备好。')
        return 0
    project = ROOT / 'tools/netease_auth'
    subprocess.run(['dart', 'pub', 'get'], cwd=project, check=True, stdout=subprocess.DEVNULL)
    session = directory / 'session.json'
    session.unlink(missing_ok=True)  # A failed new login must not reuse an older session.
    return subprocess.run(['dart', 'run', 'bin/login.dart', str(directory/'sdk-config.json'),
                           str(credentials), str(directory/'device.json'), str(session)], cwd=project).returncode


if __name__ == '__main__':
    sys.exit(main())
