# Авторы и сторонние компоненты

Автор установщика и оформления: **Илья Рублев**.

- Telegram: https://t.me/Rublev_YouTube
- YouTube: https://www.youtube.com/@Ilya_Rublev
- Boosty: https://boosty.to/rublev13

## OpenFlux

Сетевое ядро разрабатывается в https://github.com/p1neappleXpress/OpenFlux.

Установщик скачивает готовый бинарный файл версии v0.1.0 из релизов этого репозитория. В комплекте установщика нет бинарного файла OpenFlux. Его исходники доступны в исходном репозитории; соответствующая версия: https://github.com/p1neappleXpress/OpenFlux/tree/v0.1.0.

В файле COPYRIGHT проекта указаны OpenFlux Contributors и GNU General Public License версии 3 или более поздней версии:

- [COPYRIGHT](https://github.com/p1neappleXpress/OpenFlux/blob/v0.1.0/COPYRIGHT)
- [LICENSE](https://github.com/p1neappleXpress/OpenFlux/blob/v0.1.0/LICENSE)
- [NOTICE](https://github.com/p1neappleXpress/OpenFlux/blob/v0.1.0/NOTICE)

Формат ссылки `openflux://v1/` реализован по описанию и коду исходного проекта: [share/share.go](https://github.com/p1neappleXpress/OpenFlux/blob/09464988b85a1e813ca4de54a5d733c317b0e74a/share/share.go). Генерация ссылки в установщике не требует флага `--share` у закреплённого серверного бинарного файла.

## Android-клиент

Репозиторий: https://github.com/damnurmum/OpenFlux-Android.

Формат импорта сверялся с [v1.1.1](https://github.com/damnurmum/OpenFlux-Android/tree/v1.1.1), в том числе с `mobile/share.go` и `android/app/src/main/java/io/openflux/app/Profile.java`. Авторство приложения принадлежит участникам соответствующего проекта. Установщик не содержит APK и не устанавливает приложение на телефон.

## Дополнительные зависимости

QR-коды строятся программой [qrencode](https://github.com/fukuchi/libqrencode), устанавливаемой из репозиториев ОС. Остальные системные пакеты также получают из репозиториев Ubuntu или Debian. Их лицензии и уведомления сохраняются в соответствующих пакетах.

Указание авторства Ильи Рублева не означает присвоение авторства OpenFlux, Android-клиента, qrencode или других сторонних компонентов. Установщик распространяется по GNU GPL версии 3, см. [LICENSE](LICENSE). Copyright © 2026 Илья Рублев. При изменении состава распространяемых файлов лицензионные обязательства следует проверить заново.
