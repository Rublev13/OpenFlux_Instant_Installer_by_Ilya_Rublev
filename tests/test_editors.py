"""Separate offline installer checks for old Yandex Docs and VOLGA.

HTML fixtures follow the schemas read by the pinned upstream transports.
HTTP is mocked: these checks do not log into Yandex or validate a live tunnel.
Автор: Илья Рублев, https://t.me/Rublev_YouTube
"""

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import test_profiles as profiles


EDITORS = ('yandex', 'vyandex')


def config_for(editor, writable=True):
    if editor == 'yandex':
        return {'officeActionData': {
            'editor_config': {'document': {'key': 'test-doc', 'permissions': {'edit': writable}},
                              'token': 'test-only-token'},
            'balancer_url': 'https://example.invalid/balancer',
        }}
    return {'officeActionData': {'action_url': 'https://example.invalid/action',
                                 'access_token': 'test-only-token', 'access_token_ttl': 0},
            'editorParams': {'idDoc': 'test-volga-doc'}}


class EditorChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = profiles.Profiles()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.page = self.fixture.root / 'fixture.html'
        curl = self.fixture.root / 'mock-bin/curl'
        curl.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
if os.environ.get('MOCK_HTTP_FAIL') == '1':
    raise SystemExit(22)
pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_bytes(pathlib.Path(os.environ['MOCK_HTML']).read_bytes())
''')
        curl.chmod(0o755)
        self.fixture.env['MOCK_HTML'] = str(self.page)

    def detect(self, html, answer=''):
        self.page.write_text(html)
        work = Path(tempfile.mkdtemp(dir=self.fixture.root))
        return self.fixture.shell(
            'WORK="$1"; DOC_URL="$2"; TTY_FD=0; detect_transport; '
            'printf "DETECTED=%s\\n" "$TRANSPORT"',
            work, profiles.URL, input_text=answer,
        )

    def test_automatic_detection_and_generated_profiles(self):
        for editor in EDITORS:
            for mode in ('session', 'ios'):
                with self.subTest(editor=editor, mode=mode):
                    page = '<script id="client-config" type="application/json">\n' + json.dumps(config_for(editor)) + '\n</script>'
                    result = self.detect(page)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('DETECTED=' + editor, result.stdout)
                    stage = self.fixture.render(mode, editor)
                    self.fixture.verify(stage, mode, editor)

    def test_manual_choice_after_captcha_page(self):
        for editor in EDITORS:
            with self.subTest(editor=editor):
                result = self.detect('<html>Verification required</html>', '1\n' if editor == 'yandex' else '2\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('DETECTED=' + editor, result.stdout)

    def test_manual_choice_after_http_failure(self):
        self.fixture.env['MOCK_HTTP_FAIL'] = '1'
        for editor in EDITORS:
            with self.subTest(editor=editor):
                result = self.detect('', '1\n' if editor == 'yandex' else '2\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('DETECTED=' + editor, result.stdout)

    def test_unknown_page_can_be_cancelled(self):
        result = self.detect('<html>No editor schema</html>', '0\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('DETECTED=', result.stdout)
        self.assertFalse(self.fixture.config.exists())

    def test_old_editor_readonly_is_rejected(self):
        if 'yandex' not in EDITORS:
            self.skipTest('This read-only flag belongs to the old-editor schema.')
        page = '<script id="client-config">' + json.dumps(config_for('yandex', writable=False)) + '</script>'
        result = self.detect(page)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('редактирование запрещено', result.stderr)
        self.assertFalse(self.fixture.config.exists())

    def test_switch_editor_and_document_preserves_key(self):
        for initial in EDITORS:
            other = 'vyandex' if initial == 'yandex' else 'yandex'
            for mode in ('session', 'ios'):
                with self.subTest(initial=initial, mode=mode):
                    old = self.fixture.render(mode, initial)
                    key = self.fixture.verify(old, mode, initial)
                    shutil.copytree(old / 'config', self.fixture.config, dirs_exist_ok=True)
                    new_url = 'https://disk.yandex.ru/i/Changed_' + other
                    new = self.fixture.render(mode, other, url=new_url)
                    self.assertEqual(self.fixture.verify(new, mode, other, url=new_url), key)
                    shutil.copytree(new / 'config', self.fixture.config, dirs_exist_ok=True)
                    shutil.copyfile(new / 'openflux.service', self.fixture.root / 'openflux.service')
                    result = self.fixture.shell('need_root() { :; }; check_profile')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn(key, result.stdout + result.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport', choices=EDITORS)
    args, remaining = parser.parse_known_args()
    if args.transport:
        EDITORS = (args.transport,)
    print('Offline editor checks: ' + ', '.join(EDITORS), flush=True)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
