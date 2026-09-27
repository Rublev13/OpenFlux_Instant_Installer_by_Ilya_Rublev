"""Decode real installer PNGs, then run the Android v1.1.1 Go link decoder.

Only synthetic documents and fresh temporary keys. No VPN is installed.
Илья Рублев — https://t.me/Rublev_YouTube
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from test_profiles import Profiles, URL


REV = "e74f4b9ea03b905390931e61fd2c87fd06c69fe4"
SOURCE_URL = "https://raw.githubusercontent.com/damnurmum/OpenFlux-Android/" + REV + "/share/share.go"
SOURCE_SHA256 = "fd2a018c84cedc135d9cc26f1f6361cc64cc89accaf9d955e888a6fa0f02b5d9"

HARNESS = r'''
type Case struct {
    Label, Link, Secret, Context, Codec, Transport string
    Negotiate bool
}
func main() {
    raw, err := os.ReadFile(os.Args[1]); if err != nil { panic("test input missing") }
    var cases []Case
    if json.Unmarshal(raw, &cases) != nil { panic("test input invalid") }
    for _, item := range cases {
        c, err := Decode(item.Link)
        if err != nil { panic(item.Label + ": Android decoder rejected the link") }
        if c.Secret != item.Secret || c.Context != item.Context || c.Codec != item.Codec || c.Negotiate != item.Negotiate {
            panic(item.Label + ": encryption or mode changed during decoding")
        }
        if len(c.Transports) != 1 || c.Transports[0].Type != item.Transport || c.Transports[0].URL != item.Context || c.Transports[0].Priority != 100 {
            panic(item.Label + ": transport changed during decoding")
        }
        fmt.Println("PASS: real PNG -> Android share.Decode -> " + item.Label)
    }
}
'''


def main():
    for name in ("go", "qrencode", "zbarimg"):
        if not shutil.which(name):
            raise SystemExit("Required test tool is missing: " + name)
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        source = response.read().decode().rstrip("\n") + "\n"
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Pinned Android source checksum mismatch")
    # Keep the actual Config/Validate/Encode/Decode unchanged. The Android
    # QR-rendering helpers are unused here: the PNG comes from the installer.
    source = source.split("func qr(", 1)[0]
    source = source.replace('qrcode "github.com/skip2/go-qrcode"', '"os"')
    source = source.replace("package share", "package main", 1)
    fixture = Profiles()
    fixture.setUp()
    fixture.env = dict(os.environ)  # Real qrencode, not the unit-test double.
    try:
        cases = []
        for mode in ("session", "ios"):
            for transport in ("yandex", "vyandex"):
                stage = Path(tempfile.mkdtemp(dir=fixture.root))
                result = fixture.shell(
                    'WORK="$1"; DOC_URL="$2"; TRANSPORT="$3"; PROFILE_MODE="$4"; '
                    'set_profile_options; write_config; write_share', stage, URL, transport, mode)
                if result.returncode:
                    raise SystemExit("Installer profile generation failed")
                config = stage / "config"
                qr = subprocess.run(["zbarimg", "--quiet", "--raw", str(config / "connection.png")],
                                    capture_output=True, text=True, timeout=20)
                link = (config / "connection.txt").read_text().strip()
                if qr.returncode or qr.stdout.strip() != link:
                    raise SystemExit("PNG did not decode to the original link: " + mode + "/" + transport)
                cases.append({"Label": mode + "/" + transport, "Link": qr.stdout,
                              "Secret": (config / "secret.txt").read_text().strip(),
                              "Context": URL, "Codec": "legacy" if mode == "ios" else "batched",
                              "Negotiate": mode == "session", "Transport": transport})
        (fixture.root / "cases.json").write_text(json.dumps(cases))
        (fixture.root / "main.go").write_text(source + HARNESS)
        (fixture.root / "go.mod").write_text("module android-share-check\n\ngo 1.20\n")
        result = subprocess.run(["go", "run", ".", "cases.json"], cwd=fixture.root,
                                env=dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off"),
                                capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise SystemExit("Android decoder harness failed: " + result.stderr)
        print(result.stdout, end="")
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    main()
