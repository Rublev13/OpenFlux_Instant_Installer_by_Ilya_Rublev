# Авторы и сторонние компоненты

Автор установщика и оформления: **Илья Рублев**.

- Telegram: https://t.me/Rublev_YouTube
- YouTube: https://www.youtube.com/@Ilya_Rublev
- Boosty: https://boosty.to/rublev13

## OpenFlux

Сетевое ядро разрабатывается в https://github.com/p1neappleXpress/OpenFlux.

Установщик скачивает готовый серверный бинарный файл версии node-v1.0.1 из релизов этого репозитория. В комплекте установщика нет бинарного файла OpenFlux. Его исходники доступны в исходном репозитории; соответствующая версия: https://github.com/p1neappleXpress/OpenFlux/tree/node-v1.0.1.

В файле COPYRIGHT проекта указаны OpenFlux Contributors и GNU General Public License версии 3 или более поздней версии:

- [COPYRIGHT](https://github.com/p1neappleXpress/OpenFlux/blob/node-v1.0.1/COPYRIGHT)
- [LICENSE](https://github.com/p1neappleXpress/OpenFlux/blob/node-v1.0.1/LICENSE)
- [NOTICE](https://github.com/p1neappleXpress/OpenFlux/blob/node-v1.0.1/NOTICE)

Формат ссылки `openflux://v1/` реализован по описанию и коду исходного проекта: [share/share.go](https://github.com/p1neappleXpress/OpenFlux/blob/09464988b85a1e813ca4de54a5d733c317b0e74a/share/share.go). Генерация ссылки в установщике не требует флага `--share` у закреплённого серверного бинарного файла.

## Официальные клиенты

- Android v2.0.1: https://github.com/p1neappleXpress/OpenFluxAndroid
- Desktop v2.0.2: https://github.com/p1neappleXpress/OpenFluxDesktop
- Общий модуль их импорта: [OpenFluxClientShared, 2c7c41c](https://github.com/p1neappleXpress/OpenFluxClientShared/tree/2c7c41c5937125e2d8da661ad8c09e3ee174f48f). В CI исходники скачиваются по коммиту и хэшу и исполняются без изменения логики.
- iOS/TestFlight: https://github.com/saharev1/OpenFlux/tree/ios-testflight
- Дополнительный CLI для архива: [OpenFlux v0.1.0](https://github.com/p1neappleXpress/OpenFlux/tree/v0.1.0).

Установщик не включает бинарники клиентских приложений; их авторство и лицензии принадлежат соответствующим проектам.

## Альтернативный Android-клиент

Репозиторий: https://github.com/damnurmum/OpenFlux-Android.

Формат импорта сверялся с [v1.1.1](https://github.com/damnurmum/OpenFlux-Android/tree/v1.1.1), в том числе с `mobile/share.go` и `android/app/src/main/java/io/openflux/app/Profile.java`. Авторство приложения принадлежит участникам соответствующего проекта. Установщик не содержит APK и не устанавливает приложение на телефон.

## Дополнительные зависимости

QR-коды строятся программой [qrencode](https://github.com/fukuchi/libqrencode), устанавливаемой из репозиториев ОС. Остальные системные пакеты также получают из репозиториев Ubuntu или Debian. Их лицензии и уведомления сохраняются в соответствующих пакетах.

Указание авторства Ильи Рублева не означает присвоение авторства OpenFlux, Android-клиента, qrencode или других сторонних компонентов. Установщик распространяется по GNU GPL версии 3, см. [LICENSE](LICENSE). Copyright © 2026 Илья Рублев. При изменении состава распространяемых файлов лицензионные обязательства следует проверить заново.
