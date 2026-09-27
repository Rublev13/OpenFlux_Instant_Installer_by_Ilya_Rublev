"""Compile the real upstream single-profile import method before/after our patch.

The test executes Swift logic, not SwiftUI, Keychain or a VPN extension.
Only generated test profiles are used. No production secret or document is read.
Автор: Илья Рублев, https://t.me/Rublev_YouTube
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zlib

from test_profiles import Profiles


REPO = Path(__file__).resolve().parents[1]
REV = '17557e472b7f11b66f1cfeba8283dc6f69b234c0'
FILES = {
    'ContentView.swift': '03f89c71fcd382c0dc97d331e424b838b59280c4b64f738d5633998a09ad5ee7',
    'ShareLink.swift': 'ab5bfba615b7c2f47bf58267c359d3d37cbf3fa9201b2f0256977f300020c57f',
    'TunnelController.swift': '6152cd845acb4ebf274358df03a59add9e8f25b9a694dec6a511e581ee59081f',
}


def extract(source, start, end):
    return start + source.split(start, 1)[1].split(end, 1)[0]


def harness(content, share, controller):
    kind = extract(controller, 'enum TransportKind:', '/// Swift wrapper')
    cfg = extract(share, 'struct ShareConfig:', '/// Раскладывает конфигурацию')
    method = extract(content, '    private func applyShareConfig(', '    /// Fill the editor fields')
    return 'import Foundation\n' + kind + cfg + '''
final class EditorHarness {
    var transportRaw = "yandex"
    var transport: TransportKind { TransportKind(rawValue: transportRaw) ?? .yandex }
    var url1 = "", single = "", name = "", encryptionKey = "", directKey = "", nodeAddr = ""
    var importMsg: String?
    func ingest(_ cfg: ShareConfig) { applyShareConfig(cfg) }
''' + method + '''
}
func require(_ ok: Bool, _ message: String) {
    if !ok { print("FAIL: " + message); exit(1) }
}
let original = CommandLine.arguments[1] == "original"
let list = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2]))) as! [[String: Any]]
for item in list {
    let label = item["label"] as! String
    if original && !(item["reproduce"] as! Bool) { continue }
    let data = try JSONSerialization.data(withJSONObject: item["config"]!)
    let cfg = try JSONDecoder().decode(ShareConfig.self, from: data)
    let editor = EditorHarness()
    if !original {
        editor.encryptionKey = "stale-main"
        editor.directKey = "stale-direct"
        editor.nodeAddr = "stale-address"
    }
    editor.ingest(cfg)
    if original {
        require(editor.encryptionKey.isEmpty && editor.directKey == cfg.secret,
                label + ": expected to reproduce the wrong key-slot bug")
        print("REPRODUCED: " + label)
    } else {
        require(editor.encryptionKey == (item["main"] as! String), label + ": wrong main key slot")
        require(editor.directKey == (item["direct"] as! String), label + ": wrong direct key slot")
        require(editor.nodeAddr == (item["address"] as! String), label + ": stale/wrong node address")
        print("PASS: " + label)
    }
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--prepare-only', action='store_true', help='Verify patch and prepare Swift sources; does not execute Swift.')
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ios-import-test-') as directory:
        root = Path(directory)
        sources = root / 'ios-app/OpenFlux'
        sources.mkdir(parents=True)
        loaded = {}
        for name, digest in FILES.items():
            if options.source_dir:
                data = (options.source_dir / 'ios-app/OpenFlux' / name).read_bytes()
            else:
                url = f'https://raw.githubusercontent.com/saharev1/OpenFlux/{REV}/ios-app/OpenFlux/{name}'
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read(1024 * 1024)
            data = data.rstrip(b'\r\n') + b'\n'
            if hashlib.sha256(data).hexdigest() != digest:
                raise SystemExit('Pinned source hash mismatch: ' + name)
            (sources / name).write_bytes(data)
            loaded[name] = data.decode()
        patch = REPO / 'patches/ios-single-profile-encryption.patch'
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=root, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=root, check=True)
        patched = (sources / 'ContentView.swift').read_text()
        cases = []
        fixture = Profiles()
        fixture.setUp()
        try:
            for mode in ('ios', 'session'):
                for transport in ('yandex', 'vyandex'):
                    # Only the platform-neutral profile generators are needed.
                    # write_client also emits Linux/Windows launchers with GNU sed.
                    stage = Path(tempfile.mkdtemp(prefix='share-', dir=fixture.root))
                    result = fixture.shell(
                        'WORK="$1"; DOC_URL="$2"; TRANSPORT="$3"; PROFILE_MODE="$4"; '
                        'set_profile_options; write_config; write_share',
                        stage, 'https://disk.yandex.ru/i/Installer_Test_Document', transport, mode,
                    )
                    if result.returncode:
                        raise SystemExit('Test-profile generation failed: ' + result.stderr)
                    link = (stage / 'config/connection.txt').read_text().strip()
                    packed = link.removeprefix('openflux://v1/')
                    cfg = json.loads(zlib.decompress(base64.urlsafe_b64decode(packed + '=' * (-len(packed) % 4)), -15))
                    key = (stage / 'config/secret.txt').read_text().strip()
                    cases.append(dict(label=mode + '/' + transport, reproduce=True,
                                      config=cfg, main=key, direct='', address=''))
        finally:
            fixture.doCleanups()
        dummy = 'test-only-shared-secret-not-for-use'
        cases += [
            dict(label='direct-only', reproduce=False, config=dict(secret=dummy, transports=[dict(type='direct', dial='192.0.2.10:9443')]), main=dummy, direct='', address=''),
            dict(label='docs-with-direct', reproduce=False, config=dict(secret=dummy, transports=[dict(type='yandex', url='https://example.invalid/doc'), dict(type='direct', dial='192.0.2.10:9443')]), main='', direct=dummy, address='192.0.2.10:9443'),
            dict(label='no-secret-clears-stale-slots', reproduce=False, config=dict(transports=[dict(type='yandex', url='https://example.invalid/doc')]), main='', direct='', address=''),
        ]
        case_path = root / 'test-cases.json'
        case_path.write_text(json.dumps(cases))
        for label, content in [('original', loaded['ContentView.swift']), ('patched', patched)]:
            path = root / (label + '.swift')
            path.write_text(harness(content, loaded['ShareLink.swift'], loaded['TunnelController.swift']))
            if not options.prepare_only:
                if not shutil.which('swiftc'):
                    raise SystemExit('swiftc required; run the macOS GitHub Actions job.')
                binary = root / label
                subprocess.run(['swiftc', '-swift-version', '5', str(path), '-o', str(binary)], check=True, timeout=120)
                subprocess.run([str(binary), label, str(case_path)], check=True, timeout=30)
        if options.prepare_only:
            print('Pinned sources and patch checked; Swift test harness prepared, not executed.')
        else:
            print('Verified: original import bug reproduced; patched Swift method passed 7 cases.')


if __name__ == '__main__':
    main()
