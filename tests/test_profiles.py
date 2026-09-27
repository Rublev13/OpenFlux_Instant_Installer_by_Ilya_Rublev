"""Generate profiles in temporary directories, without installing or networking.

Автор установщика: Илья Рублев
https://t.me/Rublev_YouTube | https://boosty.to/rublev13
https://www.youtube.com/@Ilya_Rublev
"""

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import zlib


SOURCE = Path(__file__).resolve().parents[1] / "openflux-install.sh"
URL = "https://disk.yandex.ru/i/Installer_Test_Document"
OWNER = "rublev-openflux-installer-v1\n"


class Profiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="openflux-profiles-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "existing"
        self.script = self.root / "installer.sh"
        self.script.write_text(SOURCE.read_text().replace(
            "readonly CONFIG_DIR='/etc/openflux'",
            f"readonly CONFIG_DIR='{self.config}'",
        ).replace(
            "readonly UNIT='/etc/systemd/system/openflux.service'",
            f"readonly UNIT='{self.root / 'openflux.service'}'",
        ))
        mock_bin = self.root / "mock-bin"
        mock_bin.mkdir()
        qr = mock_bin / "qrencode"
        qr.write_text("""#!/usr/bin/env python3
import pathlib, sys
assert sys.stdin.read().startswith('openflux://v1/')
pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_bytes(b'mock QR image')
""")
        qr.chmod(0o755)
        self.env = dict(os.environ, PATH=str(mock_bin) + ":" + os.environ["PATH"])

    def shell(self, code, *args, input_text=None):
        return subprocess.run(
            ["bash", "-c", 'source "$1"; shift; ' + code,
             "profile-test", str(self.script), *map(str, args)],
            input=input_text, text=True, capture_output=True, env=self.env,
            timeout=20,
        )

    def render(self, mode, transport="yandex", fail=False):
        stage = Path(tempfile.mkdtemp(prefix="stage-", dir=self.root))
        result = self.shell(
            'WORK="$1"; DOC_URL="$2"; TRANSPORT="$3"; PROFILE_MODE="$4"; '
            'set_profile_options; write_config; write_client',
            stage, URL, transport, mode,
        )
        if fail:
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((stage / "openflux.service").exists())
        else:
            self.assertEqual(result.returncode, 0, result.stderr)
        return stage

    def verify(self, stage, mode, transport):
        cfg = stage / "config"
        key = (cfg / "secret.txt").read_text().strip()
        self.assertRegex(key, r"^[0-9a-f]{64}$")
        self.assertEqual((cfg / ".profile-mode").read_text().strip(), mode)
        link = (cfg / "connection.txt").read_text().strip()
        packed = link.removeprefix("openflux://v1/")
        data = zlib.decompress(base64.urlsafe_b64decode(packed + "=" * (-len(packed) % 4)), -15)
        profile = json.loads(data)
        self.assertEqual(profile["secret"], key)
        self.assertEqual(profile["context"], URL)
        self.assertIs(profile["negotiate"], mode == "session")
        self.assertEqual(profile["transports"], [{"type": transport, "url": URL, "priority": 100}])
        codec = "legacy" if mode == "ios" else "batched"
        self.assertEqual(profile['codec'], codec)
        server = (cfg / "server.conf").read_text()
        unit = (stage / "openflux.service").read_text()
        self.assertIn(f"EncryptionKeyFile = {self.config}/secret.txt", server)
        self.assertIn(f"Codec = {codec}\n", server)
        self.assertIn(f"URL = {URL}\n", server)
        self.assertIn(f"--encryption-key-file={self.config}/secret.txt", unit)
        self.assertNotIn(key, unit)
        with zipfile.ZipFile(cfg / "client.zip") as archive:
            self.assertEqual(archive.read("secret.txt"), (cfg / "secret.txt").read_bytes())
            self.assertEqual(archive.read("connection.txt"), (cfg / "connection.txt").read_bytes())
            client = archive.read("client.conf").decode()
            self.assertIn("EncryptionKeyFile = secret.txt", client)
            self.assertIn(f"Codec = {codec}\n", client)
            self.assertIn(f"URL = {URL}\n", client)
            windows = archive.read("start-openflux.cmd").decode()
            linux = archive.read("start-openflux.sh").decode()
            self.assertIn("\r\n", windows)
            for launcher in (unit, windows, linux):
                self.assertIn("--encryption-key-file=", launcher)
                if mode == "ios":
                    self.assertNotIn("--negotiate", launcher)
                    self.assertNotIn("--transports", launcher)
                else:
                    self.assertIn("--negotiate", launcher)
                    self.assertIn(f"--transports={transport}:100 --{transport}-url={URL}", launcher)
            check = subprocess.run(["bash", "-n"], input=linux, text=True, capture_output=True)
            self.assertEqual(check.returncode, 0, check.stderr)
        return key

    def test_both_modes_and_editors(self):
        keys = set()
        for mode in ("session", "ios"):
            for transport in ("yandex", "vyandex"):
                with self.subTest(mode=mode, transport=transport):
                    keys.add(self.verify(self.render(mode, transport), mode, transport))
        self.assertEqual(len(keys), 4, "Fresh installs must have independent keys")

    def test_mode_switch_preserves_key_and_default(self):
        old = self.render("session")
        key = self.verify(old, "session", "yandex")
        shutil.copytree(old / "config", self.config)
        new = self.render("ios", "vyandex")
        self.assertEqual(self.verify(new, "ios", "vyandex"), key)
        shutil.copytree(new / "config", self.config, dirs_exist_ok=True)
        result = self.shell('choose_mode; printf "mode=%s\\n" "$PROFILE_MODE"', input_text="\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mode=ios", result.stdout)
        back = self.render("session")
        self.assertEqual(self.verify(back, "session", "yandex"), key)

    def test_missing_empty_short_invalid_and_symlink_keys_fail(self):
        self.config.mkdir()
        (self.config / ".installer-owner").write_text(OWNER)
        key = self.config / "secret.txt"
        for value in (None, "", "abcd\n", "g" * 64, "a" * 63, "a" * 65):
            with self.subTest(value=value):
                if key.exists():
                    key.unlink()
                if value is not None:
                    key.write_text(value)
                self.render("ios", fail=True)
                self.assertEqual(key.read_text() if key.exists() else None, value)
        key.unlink()
        target = self.root / "other-key"
        target.write_text("a" * 64)
        key.symlink_to(target)
        self.render("session", fail=True)
        self.assertEqual(target.read_text(), "a" * 64)

    def test_diagnostic_checks_key_and_codec_without_exposing_them(self):
        for mode in ('session', 'ios'):
            with self.subTest(mode=mode):
                stage = self.render(mode)
                shutil.copytree(stage / 'config', self.config, dirs_exist_ok=True)
                shutil.copyfile(stage / 'openflux.service', self.root / 'openflux.service')
                result = self.shell('need_root() { :; }; check_profile')
                self.assertEqual(result.returncode, 0, result.stderr)
                key = (self.config / 'secret.txt').read_text().strip()
                self.assertNotIn(key, result.stdout + result.stderr)
                self.assertNotIn(URL, result.stdout + result.stderr)
                link_path = self.config / 'connection.txt'
                original_link = link_path.read_text()
                encoded = original_link.strip().removeprefix('openflux://v1/')
                profile = json.loads(zlib.decompress(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)), -15))
                for field, bad_value in [('secret', 'f' * 64), ('codec', 'wrong'), ('negotiate', mode != 'session')]:
                    bad = dict(profile, **{field: bad_value})
                    encoder = zlib.compressobj(wbits=-15)
                    packed = encoder.compress(json.dumps(bad).encode()) + encoder.flush()
                    link_path.write_text('openflux://v1/' + base64.urlsafe_b64encode(packed).decode().rstrip('=') + '\n')
                    result = self.shell('need_root() { :; }; check_profile')
                    self.assertNotEqual(result.returncode, 0, field)
                    self.assertNotIn(key, result.stdout + result.stderr)
                    self.assertNotIn(URL, result.stdout + result.stderr)
                link_path.write_text(original_link)


if __name__ == "__main__":
    unittest.main(verbosity=2)
