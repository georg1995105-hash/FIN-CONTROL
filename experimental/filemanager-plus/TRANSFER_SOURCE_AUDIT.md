# Реальный QR-протокол «Передачи» — аудит 28.11.2026

**Исходник:** [android-file-manager](https://github.com/georg1995105-hash/android-file-manager), ветка `main`.

Проверено по коду: `TransferManager.kt`, `TransferService.kt`, `TransferTls.kt`, `TransferDiscovery.kt`, `TransferClient.kt`, `LocalHttpsServer.java`, `IncomingTransfer.java`, `TransferScreen.kt`, `TransferPeerPanel.kt`, `assets/transfer/app.js` и `docs/TRANSFER.md`.

## Текущая схема (не путать с историей версии 0.10)
1. При открытии экрана стартует foreground service. NSD `_pfmtransfer._tcp.` обнаруживает соседние Android/TV устройства.
2. Устройство слушает два разных порта: HTTPS для приложения с пиннингом SHA-256 сертификата Android Keystore и HTTP для обычного браузера.
3. **QR содержит только `http://<LAN_IP>:<BROWSER_PORT>/`**, открывая встроенную локальную страницу. QR не содержит токенов, секретов, FTP/FTPS-URL.
4. Браузер без дополнительных кнопок выполняет `POST /pair` → `GET /pair/{id}` и получает непредсказуемый bearer в памяти. В актуальном коде кода сопряжения и окна подтверждения нет; лимит 5 попыток/мин., 10 сессий; запрос pairing — 2 мин., bearer — 1 час.
5. API: `/files` только для выбранных файлов, `/batch`, `/offer`, `/upload/{id}`, `/ticket/{id}`, `/download/{ticket}`. Блоки до 4 МиБ, возобновление со смещения, SHA-256, staging с атомарным сохранением, отмена и разрешение конфликтов имён.
6. Выключение службы сбрасывает временные сессии. **Браузерный HTTP не шифруется.** Передача допускает подключение с LAN без диалогов — не включать автоматически по запуску File Manager+ и не предоставлять весь файловый каталог.

## Перенос в File Manager+ 3.8.5
- `src/fmplus/LanPairing.java`: переносимый, без Android-зависимостей контракт адреса QR, ограничений и временной авторизации. Вместо прежнего экспериментального `ftps://user:password@`.
- Для завершения нужны реально работающий Android HTTP/HTTPS сервис, страницы, сохранение файлов, явная область доступа, NSD, Android Keystore, UI для D-pad, тесты сценариев и интеграция в оригинальный DEX/APK.
- Оригинальный File Manager+ APK и прежняя экспериментальная V8.2/приватный ключ не хранятся в этой GitHub-ветке. Модуль сам по себе **не является устанавливаемым APK**. Никаких утверждений о реальном QR-подключении через File Manager+ до испытаний.
- Google Drive и облака вне области работ.
