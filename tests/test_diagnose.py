"""Check diagnostics using synthetic files; no production key or system access.

Илья Рублев — https://t.me/Rublev_YouTube
"""

import base64
import importlib.util
import json
from pathlib import Path
import secrets
import tempfile
import unittest
import zlib


spec = importlib.util.spec_from_file_location("diagnose", Path(__file__).resolve().parents[1] / "openflux-diagnose.py")
diagnose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnose)


class Diagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "etc/openflux"
        self.config.mkdir(parents=True)
        self.key = secrets.token_hex(32)
        self.url = "https://disk.yandex.ru/i/Diagnostic_Test_Only"
        self.cookie = "Cookie_Test_" + secrets.token_hex(12)

    def profile(self, mode="ios", transport="yandex"):
        codec = "legacy" if mode == "ios" else "batched"
        (self.config / ".profile-mode").write_text(mode)
        (self.config / "server.conf").write_text(
            "[Interface]\nRole = exit\nMode = l4\nTransport = " + transport
            + "\nCodec = " + codec + "\nURL = " + self.url
            + "\nEncryptionKeyFile = /etc/openflux/secret.txt\n")
        (self.config / "secret.txt").write_text(self.key + "\n")
        profile = {"secret": self.key, "context": self.url, "codec": codec,
                   "negotiate": mode == "session",
                   "transports": [{"type": transport, "url": self.url, "priority": 100}]}
        encoder = zlib.compressobj(wbits=-15)
        packed = encoder.compress(json.dumps(profile).encode()) + encoder.flush()
        self.link = "openflux://v1/" + base64.urlsafe_b64encode(packed).decode().rstrip("=")
        (self.config / "connection.txt").write_text(self.link)

    def safe(self, lines):
        output = "\n".join(lines)
        for value in (self.key, self.url, self.cookie, getattr(self, "link", "unused_sensitive_link")):
            self.assertNotIn(value, output)
        return output

    def test_both_modes_and_editors(self):
        for mode in ("ios", "session"):
            for transport in ("yandex", "vyandex"):
                self.profile(mode, transport)
                output = self.safe(diagnose.config_report(self.root))
                self.assertIn("Режим установщика: " + mode, output)
                self.assertIn("Transport: " + transport, output)
                self.assertEqual(output.count("совпадают с"), 2)
                self.assertNotIn(": нет", output)

    def test_mismatch_and_broken_link_are_safe(self):
        self.profile()
        (self.config / "secret.txt").write_text(secrets.token_hex(32))
        self.assertIn("Ключ ссылки совпадает с VPS: нет", self.safe(diagnose.config_report(self.root)))
        for content in (self.key, "openflux://v1/%%%%", "openflux://v1/" + base64.urlsafe_b64encode(zlib.compress(b"bad")).decode()):
            (self.config / "connection.txt").write_text(content)
            self.assertIn("повреждена", self.safe(diagnose.config_report(self.root)))
        (self.config / "server.conf").write_text("[Interface]\nTransport = " + self.key + "\nCodec = " + self.url)
        self.safe(diagnose.config_report(self.root))

    def test_runtime_reads_flags_without_printing_urls(self):
        proc = self.root / "proc/321"
        proc.mkdir(parents=True)
        args = ["openflux", "--config=/etc/openflux/server.conf",
                "--encryption-key-file=/etc/openflux/secret.txt", "--negotiate",
                "--transports=yandex:100", "--yandex-url=" + self.url]
        (proc / "cmdline").write_bytes("\0".join(args).encode())
        output = self.safe(diagnose.runtime_report(self.root, {"MainPID": "321", "ActiveState": "active", "DropInPaths": self.cookie}))
        self.assertIn("Session в аргументах процесса: да", output)
        self.assertIn("Переопределения systemd: да", output)
        args = args[:3] + ["--negotiate=false"]
        (proc / "cmdline").write_bytes("\0".join(args).encode())
        self.assertIn("Session в аргументах процесса: нет", self.safe(diagnose.runtime_report(self.root, {"MainPID": "321"})))
        self.assertIn("не найден", self.safe(diagnose.runtime_report(self.root, {"MainPID": self.key})))

    def test_logs_never_print_raw_lines(self):
        path = self.root / "var/log/openflux/openflux.log"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join([
            "SmartCaptcha detected " + self.url,
            "captcha required Cookie: " + self.cookie,
            "key=" + self.key,
            "[BATCH] decode error: unknown batch version 0x00",
            "[YDOCS] WebSocket connected to " + self.url,
            "[STATS] packets=0 connected=0 established=0 retrans=0 secret=" + self.key,
        ]))
        output = self.safe(diagnose.log_report(self.root))
        self.assertIn("SmartCaptcha / требуется капча: 2", output)
        self.assertIn("Ошибка кодека: 1", output)
        self.assertIn("Последняя STATS", output)
        self.assertNotIn("key=", output)
        self.assertNotIn("Cookie:", output)

    def test_missing_files(self):
        self.safe(diagnose.config_report(self.root))
        self.safe(diagnose.log_report(self.root))
        self.safe(diagnose.runtime_report(self.root, {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
