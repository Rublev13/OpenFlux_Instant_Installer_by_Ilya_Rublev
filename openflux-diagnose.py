#!/usr/bin/env python3
"""Read-only diagnostics for the Rublev OpenFlux installer; no raw logs/secrets.

Автор: Илья Рублев. GPL-3.0.
https://t.me/Rublev_YouTube | https://boosty.to/rublev13
https://www.youtube.com/@Ilya_Rublev
"""

import base64
import configparser
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zlib


PINNED_HASHES = {
    "8211dd5343dd4eac49fcd2838ffcb9e1912c14a0e878c735395967999b0573c5",
    "ffcc24b9c956517cb0b317a9fc7de5124c4bb29ebc9dafc837a84a55f6fcee7b",
}


def read(path, limit=65536):
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        return data if len(data) <= limit else b""
    except OSError:
        return b""


def enum(value, allowed):
    return value if value in allowed else "не определено"


def yes(value):
    return "да" if value else "нет"


def digest(path):
    try:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return ""


def decode_link(data):
    text = data.decode().strip()
    prefix = "openflux://v1/"
    if not text.startswith(prefix):
        raise ValueError("format")
    packed = text[len(prefix):]
    encoded = base64.b64decode(packed + "=" * (-len(packed) % 4), altchars=b"-_", validate=True)
    decoder = zlib.decompressobj(-15)
    raw = decoder.decompress(encoded, 16385)
    if len(raw) > 16384 or not decoder.eof or decoder.unused_data:
        raise ValueError("payload")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("object")
    return result


def config_report(root):
    out = []
    config = root / "etc/openflux"
    mode = read(config / ".profile-mode").decode(errors="replace").strip()
    out.append("Режим установщика: " + enum(mode, ("ios", "session")))
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(read(config / "server.conf").decode())
        section = parser["Interface"]
    except (UnicodeError, configparser.Error, KeyError):
        return out + ["Конфигурация: отсутствует или не читается"]
    for key, allowed in (("Role", ("exit", "client")), ("Mode", ("l4", "l3", "proxy")),
                         ("Transport", ("yandex", "vyandex")), ("Codec", ("legacy", "batched"))):
        out.append(key + ": " + enum(section.get(key), allowed))
    out.append("Файл ключа в конфигурации штатный: " + yes(section.get("EncryptionKeyFile") == "/etc/openflux/secret.txt"))
    key = read(config / "secret.txt", 4096).decode(errors="replace").strip()
    key_valid = bool(re.fullmatch(r"[a-fA-F0-9]{64}", key))
    out.append("Ключ: " + ("64 hex-символа" if key_valid else "отсутствует или неверный формат"))
    try:
        profile = decode_link(read(config / "connection.txt", 32768))
        transports = [{"type": section.get("Transport"), "url": section.get("URL"), "priority": 100}]
        out.append("Ключ ссылки совпадает с VPS: " + yes(key_valid and profile.get("secret") == key))
        out.append("Документ и контекст ссылки совпадают с VPS: " + yes(
            bool(section.get("URL")) and profile.get("context") == section.get("URL")
            and profile.get("transports") == transports))
        out.append("Кодек и Session ссылки совпадают с режимом VPS: " + yes(
            mode in ("ios", "session") and profile.get("codec") == section.get("Codec")
            and section.get("Codec") == ("legacy" if mode == "ios" else "batched")
            and profile.get("negotiate") is (mode == "session")))
    except (ValueError, TypeError, UnicodeError, zlib.error):
        out.append("Ссылка подключения: отсутствует или повреждена")
    return out


def option(args, name):
    value = None
    for i, arg in enumerate(args):
        if arg == name:
            value = args[i + 1] if i + 1 < len(args) else ""
        elif arg.startswith(name + "="):
            value = arg.split("=", 1)[1]
    return value


def runtime_report(root, properties):
    out = ["Служба: " + enum(properties.get("ActiveState"),
                          ("active", "inactive", "failed", "activating", "deactivating")),
           "Переопределения systemd: " + yes(bool(properties.get("DropInPaths")))]
    out.append("Подсостояние службы: " + enum(properties.get("SubState"),
                                              ("running", "start", "auto-restart", "dead", "failed", "stop-sigterm")))
    for prop, label in (("NRestarts", "Автоперезапусков systemd"), ("ExecMainStatus", "Код завершения процесса")):
        value = properties.get(prop, "")
        out.append(label + ": " + (value if re.fullmatch(r"[0-9]{1,12}", value) else "не определено"))
    pid = properties.get("MainPID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,9}", pid):
        return out + ["Работающий процесс: не найден"]
    proc = root / "proc" / pid
    data = read(proc / "cmdline")
    if not data:
        return out + ["Параметры работающего процесса: недоступны"]
    args = data.decode(errors="replace").split("\0")
    out.append("Процесс читает штатный server.conf: " + yes(option(args, "--config") == "/etc/openflux/server.conf"))
    out.append("Процессу передан штатный файл ключа: " + yes(option(args, "--encryption-key-file") == "/etc/openflux/secret.txt"))
    session = (option(args, "--negotiate") not in (None, "false")
               or "--negotiate" in args or bool(option(args, "--transports")))
    out.append("Session в аргументах процесса: " + yes(session))
    overrides = ("--role", "-r", "--mode", "-m", "--codec", "-c", "--transport", "-t", "--url", "-u")
    out.append("Параметры CLI могут перекрывать server.conf: " + yes(any(option(args, flag) is not None for flag in overrides)))
    actual = digest(proc / "exe")
    installed = digest(root / "usr/local/bin/openflux")
    out.append("Работающий бинарник соответствует закреплённому OpenFlux 0.0.5: " + yes(actual in PINNED_HASHES))
    out.append("Работающий бинарник совпадает с файлом на диске: " + yes(bool(actual) and actual == installed))
    out.append("Файлы конфигурации могли измениться после запуска; это не проверка настроек в памяти.")
    return out


def log_report(root):
    path = root / "var/log/openflux/openflux.log"
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 131072))
            text = stream.read(131072).decode(errors="replace")
        updated = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
    except OSError:
        return ["Журнал: отсутствует или не читается"]
    lines = text.splitlines()[-300:]
    out = ["Журнал обновлён (UTC): " + updated.strftime("%Y-%m-%d %H:%M:%S"),
           "Признаки в последних 300 строках (до 128 КиБ; могут включать прежние запуски):"]
    patterns = (
        ("SmartCaptcha / требуется капча", r"SmartCaptcha|captcha required|ErrCaptchaRequired"),
        ("Ошибка авторизации / токена", r"(?:status[ =:]|-> )40[13]|login required|ErrLoginRequired"),
        ("Не распознана страница документа", r"config not found|fetchDocInfo failed"),
        ("WebSocket закрыт сервером", r"websocket: close (?:1005|1006|4007)"),
        ("Ошибка кодека", r"\[BATCH\].*decode error|unknown batch version|lz4.*(?:invalid|error)"),
        ("Ошибка проверки шифрования", r"message authentication failed|decrypt.*(?:fail|error)"),
        ("Нет маршрута / DNS / таймаут", r"no route to host|no such host|i/o timeout|TLS handshake timeout"),
        ("Шифрование выключено", r"encryption: off|шифрование.*отключено"),
        ("Включено AES-256-GCM", r"AES-256-GCM enabled|AES-256-GCM включено"),
        ("Соединение WebSocket открыто", r"WebSocket connected|\[VOLGA\] WS connected"),
    )
    for label, pattern in patterns:
        count = sum(bool(re.search(pattern, line, re.I)) for line in lines)
        out.append(label + ": " + str(count))
    for line in reversed(lines):
        if "Failed to start transport:" not in line:
            continue
        reason = "другая ошибка (исходная строка скрыта)"
        for label, pattern in patterns[:7]:
            if re.search(pattern, line, re.I):
                reason = label
                break
        stamp = re.search(r"\b[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", line)
        out.append("Последний отказ запуска транспорта: " + reason)
        if stamp:
            out.append("Время отказа по журналу: " + stamp.group())
        break
    for line in reversed(lines):
        if "[STATS]" in line:
            values = re.findall(r"\b(packets|connected|established|retrans)=([0-9]{1,18})(?![0-9])", line)
            if values:
                out.append("Последняя STATS в этом фрагменте: " + " ".join(k + "=" + v for k, v in values))
            break
    out.append("Нулевые счётчики ошибок не доказывают исправность: подробные логи могут быть отключены.")
    return out


def main():
    if os.geteuid() != 0:
        print("Запустите через sudo или от root. Диагностика ничего не устанавливает и не перезапускает.")
        return 1
    print("OpenFlux: диагностика | Илья Рублев")
    print("https://t.me/Rublev_YouTube | https://boosty.to/rublev13 | https://www.youtube.com/@Ilya_Rublev")
    print("Только чтение. Ключ, документ, QR, cookies и исходные строки журнала не выводятся.")
    root = Path("/")
    properties = {}
    try:
        proc = subprocess.run(["systemctl", "show", "openflux.service", "--no-pager",
                               "--property=ActiveState,SubState,MainPID,DropInPaths,NRestarts,ExecMainStatus"],
                              capture_output=True, text=True, timeout=10)
        properties = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
    except (OSError, subprocess.SubprocessError):
        print("systemd: сведения недоступны")
    for group in (config_report(root), runtime_report(root, properties), log_report(root)):
        print()
        print("\n".join(group))
    print("\nЭто не сквозной тест. Версия клиента и его журнал нужны для проверки второго конца.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
