"""Check release SHA-256 and real encrypted L4 traffic on loopback in CI.

Direct is used ONLY by this local test; the installer still uses Yandex Docs.
This does not test Yandex, mobile routing, or access from a real VPS.
Илья Рублев — https://t.me/Rublev_YouTube
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = b"OpenFlux encrypted L4 fixture reached\n"
CLI_SHA = "fcc1db93e21a2d4f88e35ec642a54ce206fb9f611c4780b8d4857bbe2d58190a"


def download(version, arch, expected, target):
    url = f"https://github.com/p1neappleXpress/OpenFlux/releases/download/{version}/openflux-linux-{arch}"
    with urllib.request.urlopen(url, timeout=90) as response:
        data = response.read(20 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Release checksum mismatch: " + version + "/" + arch)
    target.write_bytes(data)
    target.chmod(0o700)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def exact(sock, n):
    result = b""
    while len(result) < n:
        part = sock.recv(n - len(result))
        if not part:
            raise RuntimeError("SOCKS connection closed")
        result += part
    return result


def request(socks_port, http_host, http_port):
    with socket.create_connection(("127.0.0.1", socks_port), timeout=5) as sock:
        sock.settimeout(8)
        sock.sendall(b"\x05\x01\x00")
        if exact(sock, 2) != b"\x05\x00":
            raise RuntimeError("SOCKS authentication failed")
        sock.sendall(b"\x05\x01\x00\x01" + socket.inet_aton(http_host) + struct.pack("!H", http_port))
        reply = exact(sock, 4)
        if reply[1] != 0:
            raise RuntimeError("SOCKS destination rejected")
        length = {1: 4, 4: 16}.get(reply[3])
        if length is None:
            length = exact(sock, 1)[0]
        exact(sock, length + 2)
        sock.sendall(b"GET / HTTP/1.0\r\nHost: fixture.test\r\n\r\n")
        data = b""
        while True:
            part = sock.recv(4096)
            if not part:
                break
            data += part
        if not data.endswith(EXPECTED) or not data.startswith(b"HTTP/1.0 200"):
            raise RuntimeError("Encrypted tunnel returned the wrong HTTP response")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(EXPECTED)))
        self.end_headers()
        self.wfile.write(EXPECTED)

    def log_message(self, *args):
        pass


def exercise(root, server_bin, client_bin, http_host, http_port, explicit_role):
    with tempfile.TemporaryDirectory(dir=root) as directory:
        work = Path(directory)
        key = work / "secret.txt"
        key.write_text(secrets.token_hex(32) + "\n")
        key.chmod(0o600)
        port, socks = free_port(), free_port()
        config = work / "server.conf"
        config.write_text("[Interface]\nRole = exit\nMode = l4\nCodec = batched\n")
        common = ["--negotiate", "--transports=direct:100", "--mode=l4", "--codec=batched",
                  "--encryption-key-file=" + str(key), "--debug=2"]
        server_cmd = [str(server_bin), "--config=" + str(config), "--direct-listen=127.0.0.1:" + str(port), *common]
        if explicit_role:
            server_cmd.append("--role=exit")
        client_cmd = [str(client_bin), "--role=client", "--inbound=socks5", "--socks5=127.0.0.1:" + str(socks),
                      "--direct-dial=127.0.0.1:" + str(port), *common]
        processes, logs = [], []
        try:
            for name, cmd in (("exit", server_cmd), ("client", client_cmd)):
                log = (work / (name + ".log")).open("wb")
                logs.append(log)
                processes.append(subprocess.Popen(cmd, cwd=work, stdout=log, stderr=log))
            deadline = time.monotonic() + 45
            while True:
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError("Core process terminated")
                try:
                    request(socks, http_host, http_port)
                    break
                except (OSError, RuntimeError):
                    if time.monotonic() > deadline:
                        raise RuntimeError("No HTTP traffic through the encrypted core pair") from None
                    time.sleep(0.5)
            print("PASS: release binaries -> encrypted Session -> SOCKS5 -> L4 HTTP; "
                  + ("explicit --role=exit" if explicit_role else "Role=exit from INI regression"))
        except Exception:
            for log in logs:
                log.flush()
            for path in sorted(work.glob("*.log")):
                # Only synthetic loopback logs; no real document or user key is used.
                print(path.name + ":\n" + "\n".join(path.read_text(errors="replace").splitlines()[-25:]))
            raise
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for log in logs:
                log.close()


def main():
    installer = (ROOT / "openflux-install.sh").read_text()
    def constant(name):
        return re.search(r"readonly " + name + r"='([^']+)'", installer).group(1)
    with tempfile.TemporaryDirectory(prefix="openflux-core-pair-") as directory:
        root = Path(directory)
        server, client = root / "node", root / "cli"
        download(constant("OPENFLUX_VERSION"), "amd64", constant("LINUX_AMD64_SHA"), server)
        download(constant("OPENFLUX_VERSION"), "arm64", constant("LINUX_ARM64_SHA"), root / "arm64-not-executed")
        download(constant("CLI_VERSION"), "amd64", CLI_SHA, client)
        print("PASS: pinned node amd64/arm64 and CLI amd64 release checksums")
        # gVisor rejects a 127/8 destination arriving from its virtual NIC.
        # Use this runner's OWN interface address as the HTTP target instead.
        # The Direct connection and SOCKS listener still bind only to loopback;
        # the HTTP fixture is on a local ephemeral port, not an external site.
        interfaces = json.loads(subprocess.check_output(["ip", "-j", "-4", "address", "show", "scope", "global"]))
        local_ips = [info["local"] for interface in interfaces for info in interface.get("addr_info", [])
                     if not ipaddress.ip_address(info["local"]).is_loopback]
        if not local_ips:
            raise RuntimeError("CI requires a non-loopback local IPv4 address for the HTTP fixture")
        http_host = local_ips[0]
        http = ThreadingHTTPServer((http_host, 0), Handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            exercise(root, server, client, http_host, http.server_port, True)
            exercise(root, server, server, http_host, http.server_port, False)
        finally:
            http.shutdown()
            http.server_close()


if __name__ == "__main__":
    main()
