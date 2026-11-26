import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


OLD = 'Kotokowa/webtools'
NEW = 'Kotokowa/FresnelWaterwave'
LATEST = 'waterwave-v2.2.0'
TAGS = ('waterwave-v2.0.1', 'waterwave-v2.0.2', 'waterwave-v2.1.0', LATEST)
STORE = Path(__file__).with_name('waterwave-release-migration')
API = 'https://api.github.com'
HEADERS = {'User-Agent': 'WaterWave-release-migration', 'Accept': 'application/vnd.github+json'}
AUTH = {}


def login():
    if token := os.environ.get('GH_TOKEN'):
        AUTH['Authorization'] = 'Bearer ' + token
        return
    credentials = subprocess.run(
        ['git', 'credential', 'fill'], text=True, input='protocol=https\nhost=github.com\npath=Kotokowa/webtools.git\n\n',
        capture_output=True, check=True, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'},
    )
    password = next(line.partition('=')[2] for line in credentials.stdout.splitlines() if line.startswith('password='))
    AUTH['Authorization'] = 'Bearer ' + password


def api(path, method='GET', data=None, auth=True):
    headers = HEADERS | (AUTH if auth else {})
    body = None if data is None else json.dumps(data).encode()
    if body is not None:
        headers['Content-Type'] = 'application/json'
    with urlopen(Request(API + path, data=body, headers=headers, method=method), timeout=60) as response:
        return None if response.status == 204 else json.load(response)


def releases(repository, auth=True):
    return {entry['tag_name']: entry for entry in api(f'/repos/{repository}/releases?per_page=100', auth=auth) if entry['tag_name'] in TAGS}


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def matches(asset, path):
    return path.is_file() and path.stat().st_size == asset['size'] and (
        not asset.get('digest') or asset['digest'] == 'sha256:' + file_hash(path))


def retry(fn):
    for attempt in range(4):
        try:
            return fn()
        except (OSError, ValueError) as error:
            if attempt == 3 or isinstance(error, HTTPError) and error.code in (401, 403, 404, 422):
                raise
            print(f'Retrying after {type(error).__name__}: {error}', flush=True)
            time.sleep(2 ** (attempt + 1))


def download(tag, asset):
    path = STORE / tag / asset['name']
    path.parent.mkdir(parents=True, exist_ok=True)
    if matches(asset, path):
        return
    partial = path.with_suffix(path.suffix + '.partial')

    def fetch():
        with urlopen(Request(asset['browser_download_url'], headers={'User-Agent': HEADERS['User-Agent']}), timeout=90) as response, partial.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if not matches(asset, partial):
            raise ValueError(f'Size or digest mismatch for {tag}/{asset["name"]}')
        partial.replace(path)

    retry(fetch)
    print(f'Downloaded {tag}/{asset["name"]}', flush=True)


def validate(tag, assets):
    base = STORE / tag
    original = {asset['name']: asset for asset in assets}
    listed = {}
    for line in (base / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, raw_name = line.split(maxsplit=1)
        name = raw_name.removeprefix('*').removeprefix('./')
        if name not in original or not re.fullmatch(r'[0-9a-f]{64}', digest) or name in listed:
            raise ValueError(f'Unexpected manifest entry in {tag}: {line}')
        listed[name] = digest
    if set(listed) != set(original) - {'SHA256SUMS.txt'}:
        raise ValueError(f'Incomplete SHA256SUMS.txt for {tag}')
    for name, digest in listed.items():
        if file_hash(base / name) != digest:
            raise ValueError(f'SHA256 mismatch for {tag}/{name}')
    return {**listed, 'SHA256SUMS.txt': file_hash(base / 'SHA256SUMS.txt')}


def release_assets(repository, release_id, auth=True):
    return {asset['name']: asset for asset in api(f'/repos/{repository}/releases/{release_id}/assets?per_page=100', auth=auth)}


def check_remote(asset, original, digest):
    return asset['state'] == 'uploaded' and asset['size'] == original['size'] and asset.get('digest') == 'sha256:' + digest


def upload(tag, release, original, digest):
    name = original['name']
    path = STORE / tag / name
    asset_query = quote(name, safe='')
    if original.get('label'):
        asset_query += '&label=' + quote(original['label'], safe='')
    url = f'https://uploads.github.com/repos/{NEW}/releases/{release["id"]}/assets?name={asset_query}'
    headers = HEADERS | AUTH | {'Content-Type': original['content_type'], 'Content-Length': str(original['size'])}

    def push():
        asset = release_assets(NEW, release['id']).get(name)
        if asset:
            if check_remote(asset, original, digest):
                return
            if asset['state'] != 'starter':
                raise RuntimeError(f'Existing asset differs: {tag}/{name}')
            api(f'/repos/{NEW}/releases/assets/{asset["id"]}', 'DELETE')
        with path.open('rb') as stream:
            with urlopen(Request(url, data=stream, headers=headers, method='POST'), timeout=150) as response:
                asset = json.load(response)
        if not check_remote(asset, original, digest):
            raise RuntimeError(f'Uploaded digest or size mismatch: {tag}/{name}')
        print(f'Uploaded and verified {tag}/{name}', flush=True)

    retry(push)


def verify(source):
    target = releases(NEW, auth=False)
    assert set(target) == set(source) == set(TAGS), 'Missing public release'
    latest = api(f'/repos/{NEW}/releases/latest', auth=False)
    assert latest['tag_name'] == LATEST, 'Wrong latest release'
    for tag, release in source.items():
        originals = {asset['name']: asset for asset in release['assets']}
        digests = validate(tag, release['assets'])
        assets = release_assets(NEW, target[tag]['id'], auth=False)
        assert set(assets) == set(originals), f'Asset set mismatch in {tag}'
        for name, asset in assets.items():
            assert check_remote(asset, originals[name], digests[name]), f'Public asset {tag}/{name} differs'
        print(f'Verified public {tag}: {len(assets)} assets', flush=True)


def main(mode):
    if mode in ('copy', 'delete') or os.environ.get('GH_TOKEN'):
        login()
    source = releases(OLD)
    if set(source) != set(TAGS):
        raise RuntimeError(f'Unexpected source releases: {list(source)}')
    if mode == 'download':
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            tasks = [pool.submit(download, tag, asset) for tag in TAGS for asset in source[tag]['assets']]
            for task in concurrent.futures.as_completed(tasks):
                task.result()
        for tag, release in source.items():
            validate(tag, release['assets'])
        return
    if mode == 'copy':
        target = releases(NEW)
        for tag in TAGS:
            original = source[tag]
            digests = validate(tag, original['assets'])
            migrated = target.get(tag) or api(f'/repos/{NEW}/releases', 'POST', {
                'tag_name': tag, 'name': original['name'], 'body': (original['body'] or '').replace(OLD, NEW),
                'draft': True, 'prerelease': original['prerelease'], 'make_latest': 'false',
            })
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                tasks = [pool.submit(upload, tag, migrated, asset, digests[asset['name']]) for asset in original['assets']]
                for task in concurrent.futures.as_completed(tasks):
                    task.result()
            if migrated['draft']:
                api(f'/repos/{NEW}/releases/{migrated["id"]}', 'PATCH', {'draft': False, 'make_latest': 'true' if tag == LATEST else 'false'})
            print(f'Published {tag}', flush=True)
    if mode != 'copy':
        verify(source)
    if mode == 'delete':
        for tag in TAGS:
            api(f'/repos/{OLD}/releases/{source[tag]["id"]}', 'DELETE')
            print(f'Removed old release {tag}', flush=True)
        assert not releases(OLD), 'Old releases still present'


if __name__ == '__main__':
    try:
        main(sys.argv[1])
    except HTTPError as error:
        print(error.read().decode(errors='replace'), file=sys.stderr)
        raise
