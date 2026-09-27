#!/usr/bin/env bash
# OpenFlux_Instant_Installer by_Ilya_Rublev 1.1.0 — автор установщика: Илья Рублев.
# Copyright (C) 2026 Илья Рублев
# License: GNU General Public License version 3; see LICENSE.
# Telegram: https://t.me/Rublev_YouTube
# Boosty: https://boosty.to/rublev13
# YouTube: https://www.youtube.com/@Ilya_Rublev
# OpenFlux (отдельный проект): https://github.com/p1neappleXpress/OpenFlux
# Запуск: sudo bash openflux-install.sh
# Проверка синтаксиса, без установки: bash -n openflux-install.sh
# Требования: Ubuntu 22.04/24.04 или Debian 12/13, systemd, amd64/arm64.
# Скрипт устанавливает выходную ноду. Для зарубежного выхода нужен зарубежный VPS.
# Одна установка обслуживает одну активную клиентскую сессию.

set -Eeuo pipefail
umask 077

readonly INSTALLER_VERSION='1.1.0'
readonly OPENFLUX_VERSION='0.0.5'
readonly UPSTREAM='https://github.com/p1neappleXpress/OpenFlux'
readonly OWNER_TAG='rublev-openflux-installer-v1'
readonly CONFIG_DIR='/etc/openflux'
readonly STATE_DIR='/var/lib/openflux'
readonly LOG_DIR='/var/log/openflux'
readonly BIN='/usr/local/bin/openflux'
readonly MANAGER='/usr/local/sbin/openflux-setup'
readonly UNIT='/etc/systemd/system/openflux.service'
readonly ROTATE='/etc/logrotate.d/openflux'
readonly SERVICE='openflux.service'
readonly ACCOUNT='openflux-rublev'
readonly MARKER="$CONFIG_DIR/.installer-owner"
readonly LINUX_AMD64_SHA='8211dd5343dd4eac49fcd2838ffcb9e1912c14a0e878c735395967999b0573c5'
readonly LINUX_ARM64_SHA='ffcc24b9c956517cb0b317a9fc7de5124c4bb29ebc9dafc837a84a55f6fcee7b'

WORK=''
TRANSACTION=0
HAD_INSTALL=0
WAS_ACTIVE=0
WAS_ENABLED=0
DOC_URL=''
TRANSPORT=''
PROFILE_MODE='session'
CODEC='batched'
SESSION_FLAGS=''
SESSION_LABEL='включено'
ARCH=''
ASSET_SHA=''
TTY_FD=0
C_RESET='' C_TITLE='' C_OK='' C_WARN='' C_ERR='' C_DIM=''

colors() {
    if [[ -t 1 && -z ${NO_COLOR:-} && ${TERM:-dumb} != dumb ]]; then
        C_RESET=$'\033[0m'; C_TITLE=$'\033[1;36m'; C_OK=$'\033[1;32m'
        C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_DIM=$'\033[2m'
    fi
}
say() { printf '%s\n' "$*"; }
ok() { printf '%s✓ %s%s\n' "$C_OK" "$*" "$C_RESET"; }
warn() { printf '%s! %s%s\n' "$C_WARN" "$*" "$C_RESET"; }
fail() { printf '%sОшибка: %s%s\n' "$C_ERR" "$*" "$C_RESET" >&2; exit 1; }
step() { printf '\n%s%s%s\n' "$C_TITLE" "$*" "$C_RESET"; }
brand() {
    printf '\n%sOpenFlux_Instant_Installer by_Ilya_Rublev  /  УСТАНОВКА НА VPS%s\n' "$C_TITLE" "$C_RESET"
    say "Автор установщика: Илья Рублев  •  версия $INSTALLER_VERSION"
    say 'Telegram  https://t.me/Rublev_YouTube'
    say 'Boosty    https://boosty.to/rublev13'
    say 'YouTube   https://www.youtube.com/@Ilya_Rublev'
    printf '%sПроект OpenFlux: %s%s\n\n' "$C_DIM" "$UPSTREAM" "$C_RESET"
}
help_text() {
    brand
    cat <<'HELP'
Запуск на VPS: sudo bash openflux-install.sh
После установки меню доступно командой: sudo openflux-setup

  --install    Установить / перенастроить (старый ключ сохраняется).
  --install-ios Установить / перенастроить в режиме iPhone без negotiate.
  --uninstall  Удалить установку этого скрипта, включая ключ и профили.
  --status     Показать состояние службы.
  --logs       Последние 60 строк журнала OpenFlux.
  --client     Показать параметры клиента, включая секретный ключ.
  --key        Показать только текущий ключ шифрования.
  --qr         Показать ссылку openflux://v1/ и QR-код выбранного режима.
  --help       Эта справка. Ничего не устанавливает.

Поддерживаемые ОС: Ubuntu 22.04/24.04, Debian 12/13; amd64/arm64; systemd.
Нужны root/sudo, доступ к пакетным репозиториям, GitHub и Яндексу.
Шифрование AES-256-GCM обязательно в обоих режимах; без изменения firewall.
Android/ПК: L4, batched, negotiate. iPhone: L4, legacy, без negotiate.
Создайте отдельный пустой документ, откройте редактирование по ссылке.
Ссылка из «Поделиться» часто начинается с https://disk.yandex.ru/i/.
Домен disk.yandex.ru в такой ссылке — это нормально.
Скрипт определяет редактор по странице; если не удалось — спрашивает его.
Служба active ещё не означает, что клиент уже соединился с VPS.
Android: damnurmum/OpenFlux-Android v1.1.1, «Профили» → кнопка QR.
iPhone: https://testflight.apple.com/join/BwnAcdus
Выберите режим iPhone. Нужна сборка с шифрованием AES-256-GCM.
В проверенной ветке ios-testflight есть импорт ссылки/QR, но нет Session.
Сквозной тест iOS не выполнен; ошибка SmartCaptcha требует решения в клиенте.

Удаление затрагивает только установку, принадлежащую этому скрипту.
Чужая установка (в том числе сделанная вручную) не перезаписывается.
Общие пакеты ОС и системный journal не удаляются. Скачанная вами исходная
копия установщика и уже скопированные на другие устройства ключи остаются.
HELP
}
need_root() { [[ $EUID -eq 0 ]] || fail 'Запустите через sudo или от пользователя root.'; }
need_tty() {
    if [[ -t 0 ]]; then TTY_FD=0
    elif { exec 3<>/dev/tty; } 2>/dev/null; then TTY_FD=3
    else fail 'Нужен интерактивный SSH-терминал: запустите сохранённый файл через sudo bash.'
    fi
}
ask() {
    local prompt_text=$1 target_name=$2 read_value
    printf '%s' "$prompt_text"
    IFS= read -r -u "$TTY_FD" read_value || fail 'Ввод прерван.'
    printf -v "$target_name" '%s' "$read_value"
}
owned() { [[ -f $MARKER && ! -L $MARKER ]] && [[ $(cat "$MARKER") == "$OWNER_TAG" ]]; }
assert_paths() {
    local p
    for p in "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR" "$BIN" "$MANAGER" "$UNIT" "$ROTATE"; do
        [[ ! -L $p ]] || fail "Обнаружена символьная ссылка: $p. Требуется ручная проверка."
    done
    if owned; then
        if [[ -e $UNIT ]] && ! grep -Fqx "# $OWNER_TAG" "$UNIT"; then
            fail 'Служба openflux.service заменена сторонней настройкой. Автоматическая операция отменена.'
        fi
    else
        for p in "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR" "$BIN" "$MANAGER" "$UNIT" "$ROTATE"; do
            [[ ! -e $p ]] || fail "Уже существует $p без метки этого установщика. Чужие файлы не изменены."
        done
        if [[ $(systemctl show -p LoadState --value "$SERVICE" 2>/dev/null) != not-found ]]; then
            fail 'В системе уже зарегистрирована другая служба openflux.service.'
        fi
    fi
}
preflight() {
    need_root
    [[ $(uname -s) == Linux ]] || fail 'Нужен Linux VPS.'
    [[ -r /etc/os-release ]] || fail 'Не найден /etc/os-release.'
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}:${VERSION_ID:-}" in
        ubuntu:22.04|ubuntu:24.04|debian:12|debian:13) ;;
        *) fail 'Поддерживаются Ubuntu 22.04/24.04 и Debian 12/13.' ;;
    esac
    [[ -d /run/systemd/system ]] || fail 'Нужна система с работающим systemd.'
    for utility in apt-get systemctl flock getent useradd userdel groupdel; do
        command -v "$utility" >/dev/null || fail "Не найдена системная команда: $utility"
    done
    case "$(uname -m)" in
        x86_64) ARCH=amd64; ASSET_SHA=$LINUX_AMD64_SHA ;;
        aarch64|arm64) ARCH=arm64; ASSET_SHA=$LINUX_ARM64_SHA ;;
        *) fail 'Поддерживаются только amd64 и arm64.' ;;
    esac
}
lock_operation() {
    # Один inode на всё время работы; не удалять файл блокировки вручную.
    exec 9>/run/lock/openflux-rublev.lock
    flock -n 9 || fail 'Другая копия установщика уже работает.'
}
make_work() {
    WORK=$(mktemp -d /var/tmp/openflux-installer.XXXXXXXX)
    # Сохраняем исходник до любых замен установленного меню.
    [[ -f ${BASH_SOURCE[0]} ]] || fail 'Сначала скачайте скрипт в файл, затем запустите sudo bash ИМЯ_ФАЙЛА.'
    cp -- "${BASH_SOURCE[0]}" "$WORK/installer.sh"
}
valid_url() {
    # Только публичная каноническая ссылка: без query, фрагментов и INI-комментариев.
    [[ $1 =~ ^https://disk\.yandex\.ru/i/[A-Za-z0-9_-]+/?$ ]]
}
choose_url() {
    local input previous=''
    if owned && [[ -f $CONFIG_DIR/server.conf ]]; then
        previous=$(sed -n 's/^URL = //p' "$CONFIG_DIR/server.conf")
    fi
    say 'В Яндекс.Документах: «Поделиться» → доступ по ссылке → «Редактирование».'
    say 'Проверьте в режиме инкогнито: документ должен редактироваться без входа.'
    say 'Скопируйте публичную ссылку вида https://disk.yandex.ru/i/…'
    [[ -z $previous ]] || say "Текущая ссылка: $previous (Enter — оставить)"
    while :; do
        ask 'Ссылка на документ: ' input
        [[ -n $input ]] || input=$previous
        if valid_url "$input"; then DOC_URL=$input; break; fi
        warn 'Нужна полная ссылка https://disk.yandex.ru/i/ID из «Поделиться», без пробелов.'
    done
}
choose_mode() {
    local choice default_choice=1
    if [[ ${1:-} == ios ]]; then
        PROFILE_MODE=ios
        return
    fi
    if owned && [[ -f $CONFIG_DIR/.profile-mode && ! -L $CONFIG_DIR/.profile-mode ]] &&
        [[ $(cat "$CONFIG_DIR/.profile-mode") == ios ]]; then
        default_choice=2
    fi
    say 'Выберите режим подключения (AES-256-GCM включён в обоих):'
    say '  1 — Android / ПК: согласование сессии (negotiate), batched'
    say '  2 — iPhone / TestFlight: без negotiate, legacy (совместимость по исходникам)'
    say 'Смена режима требует заново импортировать профиль на клиенте.'
    while :; do
        ask "Режим [$default_choice]: " choice
        case "${choice:-$default_choice}" in
            1) PROFILE_MODE=session; break ;;
            2) PROFILE_MODE=ios; break ;;
            *) warn 'Введите 1 или 2.' ;;
        esac
    done
}
set_profile_options() {
    case "$PROFILE_MODE" in
        session)
            CODEC=batched
            SESSION_FLAGS="--negotiate --transports=$TRANSPORT:100 --$TRANSPORT-url=$DOC_URL"
            SESSION_LABEL='включено' ;;
        ios)
            CODEC=legacy
            SESSION_FLAGS=''
            SESSION_LABEL='выключено (режим iPhone)' ;;
        *) fail 'Неизвестный режим профиля.' ;;
    esac
}
validate_key() {
    local key_file=$1 key_value
    [[ -f $key_file && ! -L $key_file ]] || fail 'Файл ключа отсутствует или заменён ссылкой. Ключ автоматически не меняется.'
    key_value=$(cat "$key_file")
    [[ $key_value =~ ^[0-9a-fA-F]{64}$ ]] || fail 'Ключ повреждён: ожидаются 64 шестнадцатеричных символа. Восстановите secret.txt из своей резервной копии.'
}
dependencies() {
    step '1/5  Проверяем необходимые пакеты'
    local missing=() package
    for package in ca-certificates curl openssl python3 logrotate qrencode; do
        if [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]]; then
            missing+=("$package")
        fi
    done
    if ((${#missing[@]})); then
        apt-get -o DPkg::Lock::Timeout=120 update
        DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends "${missing[@]}"
    fi
    ok 'Зависимости готовы'
}
detect_transport() {
    step '2/5  Проверяем страницу Яндекс.Документов'
    local detected='' choice
    # Публичный GET — проверка страницы, не проверка полного туннеля.
    if curl --proto '=https' --proto-redir '=https' -fsSL --max-redirs 10 \
        --connect-timeout 10 --max-time 35 --max-filesize 8388608 \
        -A 'Mozilla/5.0' -o "$WORK/document.html" "$DOC_URL" 2>"$WORK/url-error.txt"; then
        detected=$(python3 - "$WORK/document.html" <<'PY'
import json, sys
from html.parser import HTMLParser
class ConfigParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.inside = False; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == 'client-config':
            self.inside = True
    def handle_endtag(self, tag):
        if tag == 'script': self.inside = False
    def handle_data(self, data):
        if self.inside: self.parts.append(data)
try:
    parser = ConfigParser()
    with open(sys.argv[1], encoding='utf-8', errors='replace') as f: parser.feed(f.read())
    cfg = json.loads(''.join(parser.parts))
    office = cfg.get('officeActionData') or {}
    editor = office.get('editor_config') or {}
    if editor.get('document') and editor.get('token') and office.get('balancer_url'):
        permissions = editor['document'].get('permissions') or {}
        print('readonly' if permissions.get('edit') is False else 'yandex')
    elif office.get('action_url') and office.get('access_token') and (cfg.get('editorParams') or {}).get('idDoc'):
        print('vyandex')
except (ValueError, TypeError, AttributeError, OSError):
    pass
PY
        )
    fi
    case "$detected" in
        readonly) fail 'Страница сообщает, что редактирование запрещено. Измените доступ и запустите установку снова.' ;;
        yandex|vyandex) TRANSPORT=$detected; ok "Редактор определён: $TRANSPORT" ;;
        *)
            warn 'Автоматически определить редактор не удалось: возможны капча, закрытый доступ или ошибка сети.'
            say 'Продолжить можно, если вы проверили доступ к документу в браузере.'
            say '  1 — Старый редактор (yandex)'
            say '  2 — Новый редактор / Волга (vyandex)'
            say '  0 — Отмена'
            while :; do
                ask 'Выберите редактор [0]: ' choice
                case "$choice" in
                    1) TRANSPORT=yandex; break ;;
                    2) TRANSPORT=vyandex; break ;;
                    0|'') say 'Установка отменена.'; exit 0 ;;
                    *) warn 'Введите 1, 2 или 0.' ;;
                esac
            done ;;
    esac
}
download_binary() {
    step "3/5  Загружаем OpenFlux $OPENFLUX_VERSION ($ARCH)"
    curl --proto '=https' --proto-redir '=https' -fL --retry 3 \
        --connect-timeout 15 --max-time 300 \
        "$UPSTREAM/releases/download/$OPENFLUX_VERSION/openflux-linux-$ARCH" -o "$WORK/openflux"
    printf '%s  %s\n' "$ASSET_SHA" "$WORK/openflux" | sha256sum -c - >/dev/null
    chmod 755 "$WORK/openflux"
    ok 'Файл получен; SHA-256 совпадает с закреплённым релизом'
}
write_config() {
    mkdir -p "$WORK/config" "$WORK/client"
    if owned; then
        validate_key "$CONFIG_DIR/secret.txt"
        cp "$CONFIG_DIR/secret.txt" "$WORK/config/secret.txt"
    else
        openssl rand -hex 32 > "$WORK/config/secret.txt"
    fi
    validate_key "$WORK/config/secret.txt"
    printf '%s\n' "$PROFILE_MODE" > "$WORK/config/.profile-mode"
    printf '%s\n' "$OWNER_TAG" > "$WORK/config/.installer-owner"
    cat > "$WORK/config/server.conf" <<EOF
# Установщик: Илья Рублев — https://t.me/Rublev_YouTube
# https://boosty.to/rublev13 | https://www.youtube.com/@Ilya_Rublev
# OpenFlux: $UPSTREAM
[Interface]
Role = exit
Mode = l4
Transport = $TRANSPORT
Codec = $CODEC
URL = $DOC_URL
EncryptionKeyFile = $CONFIG_DIR/secret.txt
CookieStore = $STATE_DIR/cookies.json
EOF
    cat > "$WORK/openflux.service" <<EOF
# $OWNER_TAG
# Автор установщика: Илья Рублев
# https://t.me/Rublev_YouTube
# https://boosty.to/rublev13
# https://www.youtube.com/@Ilya_Rublev
# OpenFlux: $UPSTREAM
[Unit]
Description=OpenFlux exit node - installer by Ilya Rublev
Documentation=$UPSTREAM
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$ACCOUNT
Group=$ACCOUNT
WorkingDirectory=$STATE_DIR
ExecStart=$BIN --config=$CONFIG_DIR/server.conf --encryption-key-file=$CONFIG_DIR/secret.txt $SESSION_FLAGS
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
UMask=0077
StateDirectory=openflux
StateDirectoryMode=0700
LogsDirectory=openflux
LogsDirectoryMode=0700
StandardOutput=append:$LOG_DIR/openflux.log
StandardError=append:$LOG_DIR/openflux.log
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=$STATE_DIR $LOG_DIR
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
EOF
    cat > "$WORK/logrotate" <<EOF
# $OWNER_TAG — Илья Рублев — https://t.me/Rublev_YouTube
# https://boosty.to/rublev13 | https://www.youtube.com/@Ilya_Rublev
$LOG_DIR/openflux.log {
    daily
    maxsize 5M
    rotate 3
    missingok
    notifempty
    copytruncate
    compress
    delaycompress
}
EOF
}
write_client() {
    cp "$WORK/config/secret.txt" "$WORK/client/secret.txt"
    cat > "$WORK/client/client.conf" <<EOF
# Установщик: Илья Рублев — https://t.me/Rublev_YouTube
# https://boosty.to/rublev13 | https://www.youtube.com/@Ilya_Rublev
# OpenFlux: $UPSTREAM
# Запускайте через прилагаемый start-openflux: он передаёт флаги выбранного режима.
[Interface]
Role = client
Inbound = socks5
Transport = $TRANSPORT
Codec = $CODEC
Socks5 = 127.0.0.1:1080
URL = $DOC_URL
EncryptionKeyFile = secret.txt
CookieStore = cookies.json
EOF
    cat > "$WORK/client/start-openflux.cmd" <<'CMD'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo OpenFlux_Instant_Installer by_Ilya_Rublev
echo Автор установщика: Илья Рублев
echo Telegram https://t.me/Rublev_YouTube
echo Boosty https://boosty.to/rublev13
echo YouTube https://www.youtube.com/@Ilya_Rublev
echo Проект: https://github.com/p1neappleXpress/OpenFlux
if not exist "openflux.exe" (
  echo Сначала скачайте официальный Windows-бинарник по ссылке в README.txt.
  echo Сохраните его в эту папку с именем openflux.exe.
  pause
  exit /b 1
)
"%~dp0openflux.exe" --config=client.conf --encryption-key-file=secret.txt __SESSION_FLAGS__
pause
CMD
    sed -i "s|__SESSION_FLAGS__|$SESSION_FLAGS|" "$WORK/client/start-openflux.cmd"
    # Windows cmd expects CRLF.
    sed -i 's/$/\r/' "$WORK/client/start-openflux.cmd"
    cat > "$WORK/client/start-openflux.sh" <<'SH'
#!/usr/bin/env bash
# Автор установщика: Илья Рублев
# https://t.me/Rublev_YouTube | https://boosty.to/rublev13
# https://www.youtube.com/@Ilya_Rublev
# OpenFlux: https://github.com/p1neappleXpress/OpenFlux
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ -x ./openflux ]] || { echo 'Добавьте сюда официальный бинарник openflux и выполните chmod +x openflux.'; exit 1; }
exec ./openflux --config=client.conf --encryption-key-file=secret.txt __SESSION_FLAGS__
SH
    sed -i "s|__SESSION_FLAGS__|$SESSION_FLAGS|" "$WORK/client/start-openflux.sh"
    cat > "$WORK/config/client.txt" <<EOF
OpenFlux_Instant_Installer by_Ilya_Rublev
ПАРАМЕТРЫ КЛИЕНТА
Автор установщика: Илья Рублев
Telegram: https://t.me/Rublev_YouTube
Boosty: https://boosty.to/rublev13
YouTube: https://www.youtube.com/@Ilya_Rublev
OpenFlux: $UPSTREAM

Версия ядра: $OPENFLUX_VERSION
Ссылка (переносите без изменений): $DOC_URL
Транспорт: $TRANSPORT
Режим профиля: $PROFILE_MODE
Codec: $CODEC
Шифрование: AES-256-GCM (обязательно)
negotiate / Session: $SESSION_LABEL
Секретный ключ (не публикуйте): $(cat "$WORK/config/secret.txt")
Локальный SOCKS5 на ПК: 127.0.0.1:1080

Профиль с ключом: $CONFIG_DIR/client.zip — скачайте через SFTP на свой ПК.
Одна активная клиентская сессия. Выход — через этот VPS.
Android: https://github.com/damnurmum/OpenFlux-Android/releases/tag/v1.1.1
В приложении: «Профили» → кнопка QR → отсканируйте код с экрана VPS.
Можно открыть ссылку openflux://v1/… на телефоне с установленным приложением.
Ссылка и QR содержат ключ. Не публикуйте их и не показывайте в видео.
Повторный вывод ссылки и QR: sudo openflux-setup --qr

iPhone: https://testflight.apple.com/join/BwnAcdus
На VPS выберите режим iPhone (ios): legacy без negotiate.
В проверенной ветке ios-testflight есть импорт openflux:// и QR.
После импорта проверьте AES-256-GCM и общий секрет в настройках профиля.
Если импорта нет, введите ссылку, транспорт и секрет выше вручную.
Для vyandex в iOS может использоваться название VOLGA / Волга.
Ключ и ссылка должны совпадать с сервером без изменений.
Шифрование не отключается при выборе iPhone. Сквозной тест iOS не выполнен.
SmartCaptcha может остановить авторизацию ещё до подключения к VPS;
серверный установщик не исправляет обработку капчи в приложении.
client.conf — формат CLI; его импорт в мобильные приложения не предусмотрен.
EOF
    cp "$WORK/config/client.txt" "$WORK/client/README.txt"
    cat >> "$WORK/client/README.txt" <<EOF

WINDOWS 10/11 x64
1. Распакуйте весь архив в отдельную папку.
2. Скачайте:
$UPSTREAM/releases/download/$OPENFLUX_VERSION/openflux-windows-amd64.exe
3. Переименуйте скачанный файл в openflux.exe и поместите в ту же папку.
SHA-256: 665333ce7ba168c03121a70e7ef5c72ee61eefdaf5e753e728b2dd1009608e79
4. Дважды нажмите start-openflux.cmd. Оставьте окно открытым.
5. В Firefox: Настройки → Настройки сети → Настроить → Ручная настройка.
   SOCKS: 127.0.0.1, порт 1080, SOCKS v5; поля HTTP и HTTPS пустые.
   Это прокси для настроенных приложений, а не VPN всего компьютера.
   Разрешение DNS-имён в этой версии ядра может оставаться локальным.
6. Откройте https://api.ipify.org в этом браузере: ожидается внешний IP VPS.
   Либо в cmd: curl.exe -4 --proxy socks5://127.0.0.1:1080 --max-time 40 https://api.ipify.org
7. Остановка: Ctrl+C в окне клиента. Затем отключите прокси в браузере.

LINUX
Возьмите openflux-linux-amd64 или openflux-linux-arm64 из того же релиза,
переименуйте в openflux, дайте право исполнения и запустите bash start-openflux.sh.

НА VPS
Меню: sudo openflux-setup
Настройки: sudo openflux-setup --client
Журнал: sudo openflux-setup --logs
Перезапуск: sudo systemctl restart openflux

Статус службы active подтверждает только запуск процесса. Если связи нет,
проверьте редактор, доступ на редактирование, одинаковую ссылку/ключ/режим
на двух сторонах и доступность Яндекса. Капча или изменение протокола
Яндекса могут помешать соединению; установщик их работу не гарантирует.
EOF
    write_share
    cp "$WORK/config/connection.txt" "$WORK/client/connection.txt"
    cp "$WORK/config/connection.png" "$WORK/client/connection.png"
    python3 - "$WORK/client" "$WORK/config/client.zip" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2], 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(root.iterdir()): z.write(path, path.name)
PY
}
write_share() {
    # Формат upstream share/share.go: JSON → raw DEFLATE → base64url без padding.
    # Не зависит от наличия --share в серверном бинарнике 0.0.5.
    python3 - "$WORK/config/secret.txt" "$DOC_URL" "$TRANSPORT" "$WORK/config/connection.txt" "$PROFILE_MODE" <<'PY'
import base64, json, pathlib, re, sys, zlib
key_path, url, transport, out_path, mode = sys.argv[1:]
key = pathlib.Path(key_path).read_text(encoding='utf-8').strip()
if not re.fullmatch(r'[0-9a-fA-F]{64}', key):
    raise SystemExit('Ключ шифрования должен содержать 64 шестнадцатеричных символа.')
if mode not in ('session', 'ios'):
    raise SystemExit('Неизвестный режим профиля.')
profile = {
    'name': 'OpenFlux_Instant_Installer by_Ilya_Rublev',
    'negotiate': mode == 'session',
    'secret': key,
    'context': url,
    'transports': [{'type': transport, 'url': url, 'priority': 100}],
}
raw = json.dumps(profile, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
encoder = zlib.compressobj(level=9, wbits=-15)
packed = encoder.compress(raw) + encoder.flush()
link = 'openflux://v1/' + base64.urlsafe_b64encode(packed).decode('ascii').rstrip('=')
pathlib.Path(out_path).write_text(link + '\n', encoding='utf-8')
PY
    qrencode -l M -s 8 -m 4 -t PNG -o "$WORK/config/connection.png" < "$WORK/config/connection.txt"
}
show_qr() {
    need_root
    owned || fail 'Установка этого скрипта не найдена.'
    [[ -s $CONFIG_DIR/connection.txt ]] || fail 'Ссылка ещё не создана. Запустите пункт 1 для перенастройки.'
    step 'Подключение OpenFlux / AES-256-GCM'
    say 'Клиент: https://github.com/damnurmum/OpenFlux-Android/releases/tag/v1.1.1'
    say 'iPhone: https://testflight.apple.com/join/BwnAcdus (на VPS нужен режим iPhone)'
    say 'Откройте «Профили» → кнопку QR, отсканируйте код, сохраните профиль.'
    warn 'Ссылка и QR содержат ключ доступа. Не публикуйте их.'
    say ''
    cat "$CONFIG_DIR/connection.txt"
    say ''
    if command -v qrencode >/dev/null; then
        qrencode -l M -m 4 -t ANSIUTF8 -o - < "$CONFIG_DIR/connection.txt" || warn 'Не удалось вывести QR в терминал; используйте сохранённый PNG.'
    fi
    say "PNG с QR: $CONFIG_DIR/connection.png (также внутри client.zip)."
    say 'Если QR переносится на новую строку, расширьте окно терминала или откройте PNG.'
    say 'Параметры выбранного режима: sudo openflux-setup --client'
    say 'Показать только ключ шифрования: sudo openflux-setup --key'
    warn 'Совместимость с конкретной сборкой TestFlight требует проверки на телефоне.'
}
account_matches() {
    local row
    row=$(getent passwd "$ACCOUNT") || return 1
    [[ $(cut -d: -f6 <<< "$row") == "$STATE_DIR" ]] &&
        [[ $(cut -d: -f7 <<< "$row") == /usr/sbin/nologin ]]
}
snapshot() {
    if owned; then
        HAD_INSTALL=1
        account_matches || fail 'Системный пользователь установки отсутствует или изменён.'
        systemctl is-active --quiet "$SERVICE" && WAS_ACTIVE=1
        systemctl is-enabled --quiet "$SERVICE" && WAS_ENABLED=1
        mkdir "$WORK/backup"
        cp -a "$CONFIG_DIR" "$WORK/backup/config"
        local p
        for p in "$BIN" "$UNIT" "$MANAGER" "$ROTATE"; do
            [[ ! -e $p ]] || cp -a "$p" "$WORK/backup/${p//\//_}"
        done
    else
        if getent passwd "$ACCOUNT" >/dev/null || getent group "$ACCOUNT" >/dev/null; then
            fail "Имя $ACCOUNT уже занято. Существующая учётная запись не изменена."
        fi
    fi
    return 0
}
atomic_install() {
    local source=$1 target=$2 mode=$3 temp
    temp=$(mktemp "${target}.XXXXXXXX")
    if install -o root -g root -m "$mode" "$source" "$temp"; then
        mv -fT -- "$temp" "$target"
    else
        rm -f -- "$temp"
        return 1
    fi
}
remove_account() {
    if getent passwd "$ACCOUNT" >/dev/null; then
        account_matches || { warn "Пользователь $ACCOUNT изменён: удалите его вручную после проверки."; return 1; }
        userdel "$ACCOUNT"
    fi
    if getent group "$ACCOUNT" >/dev/null; then groupdel "$ACCOUNT"; fi
}
rollback() {
    warn 'Установка не завершена. Откатываем изменения OpenFlux.'
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    if ((HAD_INSTALL)); then
        rm -rf -- "$CONFIG_DIR"
        cp -a "$WORK/backup/config" "$CONFIG_DIR"
        local p
        for p in "$BIN" "$UNIT" "$MANAGER" "$ROTATE"; do
            if [[ -e $WORK/backup/${p//\//_} ]]; then
                cp -a "$WORK/backup/${p//\//_}" "$p"
            else rm -f -- "$p"; fi
        done
        systemctl daemon-reload
        if ((WAS_ENABLED)); then systemctl enable "$SERVICE" >/dev/null 2>&1
        else systemctl disable "$SERVICE" >/dev/null 2>&1 || true; fi
        (( ! WAS_ACTIVE )) || systemctl start "$SERVICE"
    else
        systemctl disable "$SERVICE" >/dev/null 2>&1 || true
        rm -f -- "$BIN" "$UNIT" "$MANAGER" "$ROTATE"
        rm -rf -- "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
        remove_account || true
        systemctl daemon-reload
        systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true
    fi
    warn 'Общие пакеты ОС, установленные как зависимости, сохранены.'
}
on_exit() {
    local rc=$?
    trap - EXIT ERR INT TERM
    set +e
    if ((TRANSACTION)); then rollback; (( rc != 0 )) || rc=1; fi
    [[ -z $WORK ]] || rm -rf -- "$WORK"
    exit "$rc"
}
install_openflux() {
    preflight
    lock_operation
    assert_paths
    need_tty
    choose_url
    choose_mode "${1:-}"
    make_work
    dependencies
    detect_transport
    set_profile_options
    download_binary
    write_config
    write_client
    snapshot
    step '4/5  Устанавливаем файлы и службу автозапуска'
    TRANSACTION=1
    if ((HAD_INSTALL)); then
        systemctl stop "$SERVICE"
    else
        useradd --system --user-group --no-create-home --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$ACCOUNT"
    fi
    install -d -m 750 -o root -g "$ACCOUNT" "$CONFIG_DIR"
    install -d -m 700 -o "$ACCOUNT" -g "$ACCOUNT" "$STATE_DIR" "$LOG_DIR"
    install -m 640 -o root -g "$ACCOUNT" "$WORK/config/server.conf" "$CONFIG_DIR/server.conf"
    install -m 640 -o root -g "$ACCOUNT" "$WORK/config/secret.txt" "$CONFIG_DIR/secret.txt"
    install -m 600 -o root -g root "$WORK/config/.installer-owner" "$MARKER"
    install -m 600 -o root -g root "$WORK/config/.profile-mode" "$CONFIG_DIR/.profile-mode"
    install -m 600 -o root -g root "$WORK/config/client.txt" "$CONFIG_DIR/client.txt"
    install -m 600 -o root -g root "$WORK/config/client.zip" "$CONFIG_DIR/client.zip"
    install -m 600 -o root -g root "$WORK/config/connection.txt" "$CONFIG_DIR/connection.txt"
    install -m 600 -o root -g root "$WORK/config/connection.png" "$CONFIG_DIR/connection.png"
    atomic_install "$WORK/openflux" "$BIN" 755
    atomic_install "$WORK/openflux.service" "$UNIT" 644
    atomic_install "$WORK/logrotate" "$ROTATE" 644
    atomic_install "$WORK/installer.sh" "$MANAGER" 755
    systemctl daemon-reload
    systemctl enable "$SERVICE"
    systemctl start "$SERVICE"
    step '5/5  Проверяем запуск службы'
    sleep 3
    if ! systemctl is-active --quiet "$SERVICE"; then
        [[ ! -f $LOG_DIR/openflux.log ]] || tail -n 30 "$LOG_DIR/openflux.log"
        fail 'Служба не запустилась. Изменения будут отменены.'
    fi
    TRANSACTION=0
    ok 'OpenFlux установлен; процесс запущен; автозапуск включён'
    ok "AES-256-GCM настроено; ключ включён в ссылку и QR; режим: $PROFILE_MODE"
    say 'Соединение через документ проверяется после подключения клиента.'
    say "Клиентский архив: $CONFIG_DIR/client.zip (содержит ключ; скачайте через SFTP)."
    say "Параметры клиента: sudo openflux-setup --client"
    say 'Меню: sudo openflux-setup'
    say 'Журнал: sudo openflux-setup --logs'
    say 'Windows: в архиве есть запуск двойным щелчком и инструкция README.txt.'
    say 'Для зарубежного выхода эта установка должна работать на зарубежном VPS.'
    show_qr
    brand
}
uninstall_openflux() {
    need_root
    command -v systemctl >/dev/null || fail 'Не найден systemctl.'
    lock_operation
    assert_paths
    if ! owned; then say 'Установка этого скрипта не найдена.'; return; fi
    need_tty
    warn 'Будут удалены OpenFlux, служба, ключ, конфигурация, cookies, профили и журналы OpenFlux.'
    say "Каталоги: $CONFIG_DIR, $STATE_DIR, $LOG_DIR"
    say "Файлы: $BIN, $UNIT, $ROTATE, $MANAGER"
    say "Системный пользователь: $ACCOUNT"
    local answer
    ask 'Для полного удаления введите УДАЛИТЬ: ' answer
    if [[ $answer != УДАЛИТЬ ]]; then say 'Удаление отменено.'; return; fi
    if systemctl is-active --quiet "$SERVICE" || [[ -e $UNIT ]]; then
        systemctl stop "$SERVICE"
    fi
    systemctl disable "$SERVICE" >/dev/null 2>&1 || true
    # Не очищаем общий journal и не удаляем системные зависимости.
    remove_account
    rm -f -- "$BIN" "$UNIT" "$ROTATE" "$MANAGER"
    rm -rf -- "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"
    systemctl daemon-reload
    systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true
    ok 'Установка OpenFlux и её данные удалены'
    say 'Общие пакеты ОС, системный journal и ваша исходная копия скрипта сохранены.'
    say 'Если ключи были скопированы на клиентские устройства, удалите их там отдельно.'
    brand
}
show_client() {
    need_root
    owned || fail 'Установка этого скрипта не найдена.'
    cat "$CONFIG_DIR/client.txt"
}
show_key() {
    need_root
    owned || fail 'Установка этого скрипта не найдена.'
    validate_key "$CONFIG_DIR/secret.txt"
    cat "$CONFIG_DIR/secret.txt"
}
show_logs() {
    need_root
    owned || fail 'Установка этого скрипта не найдена.'
    [[ -f $LOG_DIR/openflux.log ]] || fail 'Файл журнала ещё не создан.'
    tail -n 60 "$LOG_DIR/openflux.log"
}
main() {
    colors
    trap on_exit EXIT
    trap 'printf "\n%sОшибка на строке %s. Операция остановлена.%s\n" "$C_ERR" "$LINENO" "$C_RESET" >&2' ERR
    trap 'exit 130' INT
    trap 'exit 143' TERM
    local action=${1:-} choice
    (($# <= 1)) || fail 'Допускается один параметр. Справка: --help'
    if [[ $action == --help || $action == -h ]]; then help_text; return; fi
    if [[ $action == --key ]]; then show_key; return; fi
    brand
    case "$action" in
        --install) install_openflux ;;
        --install-ios) install_openflux ios ;;
        --uninstall) uninstall_openflux ;;
        --status) systemctl --no-pager --full status "$SERVICE" ;;
        --logs) show_logs ;;
        --client) show_client ;;
        --key) show_key ;;
        --qr) show_qr ;;
        '')
            need_root
            need_tty
            say '  1. Установить / перенастроить OpenFlux'
            say '  2. Полностью удалить OpenFlux'
            say '  3. Показать QR-код и ссылку подключения'
            say '  4. Показать ключ шифрования'
            say '  0. Выход'
            say ''
            while :; do
                ask 'Выберите пункт [1]: ' choice
                case "$choice" in
                    1|'') install_openflux; break ;;
                    2) uninstall_openflux; break ;;
                    3) show_qr; break ;;
                    4) show_key; break ;;
                    0) break ;;
                    *) warn 'Введите 1, 2, 3, 4 или 0.' ;;
                esac
            done ;;
        *) fail "Неизвестный параметр: $action. Справка: --help" ;;
    esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
