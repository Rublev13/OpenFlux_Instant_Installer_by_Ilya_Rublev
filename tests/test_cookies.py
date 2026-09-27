"""Synthetic cookie import, service lifecycle and privacy regression tests.

Илья Рублев — https://t.me/Rublev_YouTube
"""

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("cookie_import", Path(__file__).resolve().parents[1] / "openflux-import-cookies.py")
cookie_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cookie_import)


class Cookies(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.doc = "https://disk.yandex.ru/i/Cookie_Test_Only"
        self.other = "https://disk.yandex.ru/i/Other_Test_Only"
        self.value = secrets.token_hex(32)
        self.key = secrets.token_hex(32)
        self.config = self.root / "etc/openflux"
        self.state = self.root / "var/lib/openflux"
        self.unit = self.root / "etc/systemd/system/openflux.service"
        for path in (self.config, self.state, self.unit.parent, self.root / "run/lock"):
            path.mkdir(parents=True, mode=0o700)
        (self.config / ".installer-owner").write_text(cookie_import.OWNER)
        (self.config / "server.conf").write_text(
            "[Interface]\nRole = exit\nTransport = vyandex\nURL = " + self.doc
            + "\nCookieStore = /var/lib/openflux/cookies.json\n")
        (self.config / "secret.txt").write_text(self.key)
        self.unit.write_text("# " + cookie_import.OWNER + "\nExecStart=/usr/local/bin/openflux --config=/etc/openflux/server.conf\n")
        self.store = self.state / "cookies.json"
        self.old = json.dumps({self.doc: {"expired": "old"}, self.other: {"kept": "unchanged"}}).encode()
        self.store.write_bytes(self.old)
        account = SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid())
        self.account_patch = patch.object(cookie_import.pwd, "getpwnam", return_value=account)
        self.account_patch.start()
        self.addCleanup(self.account_patch.stop)
        self.calls = []
        self.dropin = ""

    def ctl(self, *args):
        self.calls.append(args)
        if args[0] == "show":
            return ("User=openflux-rublev\nGroup=openflux-rublev\nLoadState=loaded\n"
                    "FragmentPath=/etc/systemd/system/openflux.service\nDropInPaths=" + self.dropin + "\n")
        if args[0] == "start":
            stored = json.loads(self.store.read_bytes())
            self.assertEqual(stored[self.doc], {"spravka": self.value})
        return ""

    def import_now(self, header=None):
        return cookie_import.import_cookies(self.root, header or "spravka=" + self.value, self.ctl)

    def assert_not_stopped(self):
        self.assertFalse(any(call[0] in ("stop", "start") for call in self.calls))

    def test_success_both_editors_preserves_other_document_and_key(self):
        for transport in ("yandex", "vyandex"):
            with self.subTest(transport=transport):
                conf = self.config / "server.conf"
                conf.write_text(conf.read_text().replace("Transport = vyandex", "Transport = " + transport)
                                .replace("Transport = yandex", "Transport = " + transport))
                conf_before = conf.read_bytes()
                self.store.write_bytes(self.old)
                self.calls.clear()
                self.assertEqual(self.import_now(), 1)
                result = json.loads(self.store.read_bytes())
                self.assertEqual(result[self.other], {"kept": "unchanged"})
                self.assertEqual(result[self.doc], {"spravka": self.value})
                self.assertEqual(conf.read_bytes(), conf_before)
                self.assertEqual((self.config / "secret.txt").read_text(), self.key)
                backup = self.config / "cookies-before-import.json"
                self.assertEqual(backup.read_bytes(), self.old)
                for path in (self.store, backup):
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual([c[0] for c in self.calls], ["show", "stop", "start"])
                self.assertEqual(list(self.state.glob(".cookies-import-*")), [])

    def test_missing_store_is_created(self):
        self.store.unlink()
        self.import_now()
        self.assertEqual(json.loads(self.store.read_bytes()), {self.doc: {"spravka": self.value}})
        self.assertEqual(json.loads((self.config / "cookies-before-import.json").read_bytes()), {})

    def test_document_trailing_slash_is_preserved_as_store_key(self):
        conf = self.config / "server.conf"
        conf.write_text(conf.read_text().replace(self.doc, self.doc + "/"))
        self.doc += "/"
        self.import_now()
        self.assertIn(self.doc, json.loads(self.store.read_bytes()))

    def test_header_parser_and_safe_errors(self):
        self.assertEqual(cookie_import.parse_header("Cookie: a=one==; b=; c=" + self.value),
                         {"a": "one==", "b": "", "c": self.value})
        for data in ("", "a=" + self.value + "\nOther: bad", "a=1; a=2", "Set-Cookie: a=1",
                     "curl 'https://example.com/'", "a=кириллица", "a=" + "x" * 65536, "a=1\r", "a=1\x1b"):
            with self.subTest(data_length=len(data)):
                with self.assertRaises(cookie_import.ImportErrorSafe) as raised:
                    cookie_import.parse_header(data)
                self.assertNotIn(self.value, str(raised.exception))

    def test_corrupt_store_or_wrong_service_is_untouched(self):
        for raw in (b"broken", b"[]", b'{"document":42}', b'{"document":{"bad":false}}'):
            self.store.write_bytes(raw)
            with self.assertRaises(cookie_import.ImportErrorSafe):
                self.import_now()
            self.assertEqual(self.store.read_bytes(), raw)
            self.assert_not_stopped()
        self.store.write_bytes(self.old)
        self.dropin = "/etc/systemd/system/openflux.service.d/custom.conf"
        with self.assertRaises(cookie_import.ImportErrorSafe):
            self.import_now()
        self.assert_not_stopped()

    def test_symlinks_and_foreign_installation_are_untouched(self):
        backup = self.config / "cookies-before-import.json"
        backup.symlink_to(self.config / "secret.txt")
        with self.assertRaises(cookie_import.ImportErrorSafe):
            self.import_now()
        backup.unlink()
        self.store.unlink()
        self.store.symlink_to(self.config / "secret.txt")
        with self.assertRaises(cookie_import.ImportErrorSafe):
            self.import_now()
        self.store.unlink()
        self.store.write_bytes(self.old)
        (self.config / ".installer-owner").write_text("unrelated installation")
        with self.assertRaises(cookie_import.ImportErrorSafe):
            self.import_now()
        self.assert_not_stopped()
        self.assertEqual((self.config / "secret.txt").read_text(), self.key)

    def test_atomic_write_failure_keeps_old_store(self):
        replace = cookie_import.os.replace

        def fail_on_store(src, dst):
            if dst == self.store:
                raise OSError("synthetic write failure")
            replace(src, dst)

        with patch.object(cookie_import.os, "replace", side_effect=fail_on_store):
            with self.assertRaises(OSError):
                self.import_now()
        self.assertEqual(self.store.read_bytes(), self.old)
        self.assertEqual((self.config / "cookies-before-import.json").read_bytes(), self.old)
        self.assertFalse(any(call[0] == "start" for call in self.calls))
        self.assertEqual(list(self.state.glob(".cookies-import-*")), [])

    def test_observation_detects_restarts_and_missing_fields(self):
        good = "ActiveState=active\nSubState=running\nNRestarts=0\nMainPID=123\n"
        for last, expected in ((good, True), (good.replace("NRestarts=0", "NRestarts=3"), False),
                               (good.replace("MainPID=123", "MainPID=124"), False), ("", False)):
            with self.subTest(expected=expected):
                replies = iter((good, last))
                self.assertEqual(cookie_import.observe(lambda *args: next(replies), lambda seconds: None), expected)

    def test_noninteractive_input_never_falls_back_or_imports(self):
        output = io.StringIO()
        with patch("sys.argv", ["openflux-import-cookies.py"]), \
                patch.object(cookie_import.os, "geteuid", return_value=0), \
                patch.object(cookie_import.getpass, "getpass", side_effect=cookie_import.getpass.GetPassWarning()), \
                patch.object(cookie_import, "import_cookies") as imported, redirect_stdout(output):
            self.assertEqual(cookie_import.main(), 1)
        imported.assert_not_called()
        for value in (self.value, self.key, self.doc):
            self.assertNotIn(value, output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
