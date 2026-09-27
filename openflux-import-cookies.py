#!/usr/bin/env python3
"""Import manually obtained document cookies into the installer's cookie store.

Автор: Илья Рублев. GPL-3.0.
https://t.me/Rublev_YouTube | https://boosty.to/rublev13
https://www.youtube.com/@Ilya_Rublev
"""

import argparse
import configparser
from contextlib import contextmanager
import fcntl
import getpass
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import tempfile
import time
import warnings


OWNER = "rublev-openflux-installer-v1"
ACCOUNT = "openflux-rublev"
SERVICE = "openflux.service"
LIMIT = 1048576
COOKIE_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
COOKIE_VALUE = re.compile(r'[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]*')


class ImportErrorSafe(Exception):
    """Only fixed, non-sensitive messages may be passed to this exception."""


def parse_header(text):
    if not text or len(text) > 65536 or any(ord(c) < 32 or ord(c) > 126 for c in text):
        raise ImportErrorSafe("Нужна одна строка Cookie, без переносов и других HTTP-заголовков.")
    text = text.strip()
    if text.lower().startswith("cookie:"):
        text = text[7:].strip()
    result = {}
    for pair in text.split(";"):
        name, sep, value = pair.strip().partition("=")
        if (not sep or not COOKIE_NAME.fullmatch(name) or name in result
                or not COOKIE_VALUE.fullmatch(value)):
            raise ImportErrorSafe("Не удалось разобрать Cookie. Копируйте только значение заголовка запроса.")
        result[name] = value
    if not result or len(result) > 256:
        raise ImportErrorSafe("Неверное количество cookies.")
    return result


def checked_path(path):
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ImportErrorSafe("В пути обнаружена символьная ссылка; требуется ручная проверка.")


def read_file(path, missing=False):
    checked_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if missing:
            return None
        raise ImportErrorSafe("Не найден необходимый файл установки.") from None
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ImportErrorSafe("Ожидался обычный файл.")
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ImportErrorSafe("Файл превышает допустимый размер.")
    return data


def parse_store(data):
    if data is None or not data:
        return {}
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError):
        raise ImportErrorSafe("Хранилище cookies повреждено. Автоматическая перезапись отменена.") from None
    if not isinstance(result, dict) or any(
        not isinstance(key, str) or not isinstance(jar, dict)
        or any(not isinstance(k, str) or not isinstance(v, str) for k, v in jar.items())
        for key, jar in result.items()
    ):
        raise ImportErrorSafe("Неизвестный формат хранилища cookies. Перезапись отменена.")
    return result


def atomic_write(path, data, uid, gid):
    checked_path(path)
    fd, tmp = tempfile.mkstemp(prefix=".cookies-import-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            os.fchown(stream.fileno(), uid, gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def systemctl(*args):
    try:
        result = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=35)
    except (OSError, subprocess.SubprocessError):
        raise ImportErrorSafe("Не удалось выполнить systemctl; проверьте состояние службы.") from None
    if result.returncode:
        raise ImportErrorSafe("systemctl вернул ошибку; проверьте состояние службы.")
    return result.stdout


def properties(ctl, names):
    output = ctl("show", SERVICE, "--no-pager", "--property=" + ",".join(names))
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def installation(root):
    config = root / "etc/openflux"
    if read_file(config / ".installer-owner").strip() != OWNER.encode():
        raise ImportErrorSafe("Установка этого скрипта не найдена.")
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(read_file(config / "server.conf").decode())
        section = parser["Interface"]
        document = section["URL"]
    except (UnicodeError, KeyError, configparser.Error):
        raise ImportErrorSafe("Не удалось прочитать конфигурацию установки.") from None
    if (section.get("Role") != "exit" or section.get("Transport") not in ("yandex", "vyandex")
            or section.get("CookieStore") != "/var/lib/openflux/cookies.json"
            or not re.fullmatch(r"https://disk\.yandex\.ru/i/[A-Za-z0-9_-]+/?", document)):
        raise ImportErrorSafe("Нужна штатная конфигурация выхода Yandex Docs/VOLGA этого установщика.")
    unit = read_file(root / "etc/systemd/system/openflux.service").decode()
    if ("# " + OWNER not in unit or "--cookie-store" in unit
            or "--config=/etc/openflux/server.conf" not in unit):
        raise ImportErrorSafe("Файл службы изменён; требуется ручная проверка параметров.")
    state = root / "var/lib/openflux"
    checked_path(state)
    try:
        account = pwd.getpwnam(ACCOUNT)
    except KeyError:
        raise ImportErrorSafe("Не найдена учётная запись службы.") from None
    info = state.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != account.pw_uid
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ImportErrorSafe("Права каталога cookies отличаются от штатных; нужна ручная проверка.")
    return document, state / "cookies.json", config / "cookies-before-import.json", account


@contextmanager
def operation_lock(root):
    path = root / "run/lock/openflux-rublev.lock"
    checked_path(path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ImportErrorSafe("Некорректный файл блокировки установщика.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ImportErrorSafe("Другая операция установщика уже выполняется.") from None
        yield
    finally:
        os.close(fd)


def import_cookies(root, header, ctl=systemctl):
    cookies = parse_header(header)
    with operation_lock(root):
        document, path, backup, account = installation(root)
        unit = properties(ctl, ("User", "Group", "DropInPaths", "FragmentPath", "LoadState"))
        if (unit.get("User") != ACCOUNT or unit.get("Group") != ACCOUNT
                or unit.get("DropInPaths") or unit.get("LoadState") != "loaded"
                or unit.get("FragmentPath") != "/etc/systemd/system/openflux.service"):
            raise ImportErrorSafe("У службы нестандартные настройки; автоматический импорт отменён.")
        # Validate before stopping, then read again after stopping to avoid a lost update.
        parse_store(read_file(path, missing=True))
        checked_path(backup)
        ctl("stop", SERVICE)
        old = read_file(path, missing=True)
        store = parse_store(old)
        store[document] = cookies
        data = (json.dumps(store, ensure_ascii=True, indent=2) + "\n").encode()
        if len(data) > LIMIT:
            raise ImportErrorSafe("Хранилище слишком большое. Служба оставлена остановленной.")
        # A root-only backup is kept outside the service-writable state directory.
        # An absent old file is backed up as an empty valid store for deterministic recovery.
        atomic_write(backup, old if old else b"{}\n", os.geteuid(), os.getegid())
        atomic_write(path, data, account.pw_uid, account.pw_gid)
        ctl("start", SERVICE)
    return len(cookies)


def observe(ctl=systemctl, pause=time.sleep):
    fields = ("ActiveState", "SubState", "NRestarts", "MainPID")
    first = properties(ctl, fields)
    pause(20)
    last = properties(ctl, fields)
    return (first.get("ActiveState") == last.get("ActiveState") == "active"
            and first.get("SubState") == last.get("SubState") == "running"
            and bool(re.fullmatch(r"[0-9]+", first.get("NRestarts", "")))
            and first.get("NRestarts") == last.get("NRestarts")
            and first.get("MainPID", "0") not in ("", "0")
            and first.get("MainPID") == last.get("MainPID"))


def main():
    argparse.ArgumentParser(description="Импорт Cookie после ручной капчи через IP VPS; перезапускает OpenFlux.").parse_args()
    print("OpenFlux: импорт cookies | Илья Рублев")
    print("https://t.me/Rublev_YouTube | https://boosty.to/rublev13 | https://www.youtube.com/@Ilya_Rublev")
    if os.geteuid() != 0:
        print("Запустите скрипт через sudo или от root.")
        return 1
    print("Сначала вручную пройдите капчу в браузере через IP этого VPS.")
    print("Вставляйте только Cookie успешного запроса документа. Не присылайте cookies в чат.")
    print("После ввода скрипт сохранит резервную копию cookies и запустит службу заново.")
    print("Ключ шифрования, документ и настройки профиля не меняются. Ввод скрыт.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            header = getpass.getpass("Cookie: ")
        count = import_cookies(Path("/"), header)
        print("Импортировано cookies:", count)
        print("Резервная копия: /etc/openflux/cookies-before-import.json (только root).")
        print("Наблюдаем службу 20 секунд…")
        if observe():
            print("Процесс проработал 20 секунд без перезапуска. Проверьте интернет и IP на одном клиенте.")
            print("Это ещё не подтверждение обмена данными с клиентом.")
        else:
            print("Стабильная работа не подтверждена. Повторите безопасную диагностику VPS.")
            return 2
    except ImportErrorSafe as error:
        print("Ошибка:", error)
        return 1
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("\nВвод отменён или скрытый ввод недоступен. Используйте интерактивный SSH-терминал.")
        return 1
    except (OSError, UnicodeError, ValueError):
        print("Ошибка чтения или записи. Проверьте состояние службы; исходные данные скрыты.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
