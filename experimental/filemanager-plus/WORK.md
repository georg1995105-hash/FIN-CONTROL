# File Manager+ 3.8.5 — изолированная работа

Это отдельная экспериментальная ветка для File Manager+; **не относится к FIN CONTROL**. Не сливать в main и не менять исходные файлы FIN CONTROL.

## Входные материалы
- Пользовательский APK: `com.alphainventor.filemanager` версии 3.8.5, код 2403085.
- Оригинальный APK и предыдущие V1–V4 находятся только в рабочей сессии ChatGPT, не в GitHub.
- Исходного Android-проекта и оригинального приватного ключа подписи нет.
- V2 вылетала; V3/V4 не проходили проверку на устройстве. Не использовать как базу без исправления дефекта.

## Запрошенные функции
1. Стабильные индивидуальные настройки вида и сортировки каждой папки, без автоматического изменения всех папок.
2. Ускоренные миниатюры; возможность включать значки/миниатюры во всех файловых разделах.
3. Удобная сортировка, настройки главного экрана, улучшенное копирование с прогрессом.
4. Расширенная информация об APK.
5. Адаптация для телефона, планшета и Android TV; полное управление D-pad.
6. Вместо ввода сетевого кода — QR-доступ с сохранением авторизации.
7. Экспорт и восстановление настроек.

## Условия завершения
- Разбирать и изменять оригинал, а не наращивать неподтверждённые патчи V2/V3/V4.
- Воспроизводимая сборка и статическая проверка DEX/APK.
- UI/инструментальные тесты на Android и TV (включая операции копирования, удаления, сеть и D-pad).
- Постоянный ключ подписи для собственных следующих версий; не обещать обновление поверх официально подписанного приложения.
- Полный набор функций и работающий APK необходимы для статуса «готово».

## Подтверждённые ограничения
- GitHub-ветка и запись в неё не являются доказательством завершения модификации приложения.
- Наличие GitHub Actions не восстанавливает недостающие исходники, подпись и доступ к APK автоматически.
- Не включать сторонний код или публиковать пользовательский APK без проверки прав и соответствия лицензиям.

## Проверенная V7 — точечный ремонт сохранения вида (28.11.2026)

- В исходном File Manager+ V6.2 сохраняемые режимы списка сбрасывались при пустом поле текущего пути: `a0.b8()` читал общий режим, не закрепляя путь, и `a0.n9()` мог открывать настройки без пути. Оба места исправлены в локально собранной V7; скрипт воспроизведения: `scripts/patch_filemanager_persistent_views.py`.
- Когда для обычной папки ещё нет сохранённого варианта, начальный режим — подробный список (идентификатор 2), но явный пользовательский выбор не перезаписывается. Настройка «для всех папок» остаётся скрытой.
- Исправлен потенциальный дефект переключателя значков: скрывается `ImageView`, а не родительский контейнер файла. Длинные подписи APK ограничены двумя строками; изменения прошли Android DEX CI.
- Проверено локально: декомпиляция V6.2, повторное применение скрипта (идемпотентность), сборка APK, целостность ZIP, подписи v1/v2/v3, версия code 2403087, сертификат совпадает с V6.2. **Это не тест на Android-устройстве и не подтверждение ежедневной стабильности.**
- Неустранённый блокер: Google Drive отображает ошибку подключения. В переподписанном приложении другой SHA-1 сертификат, чем у оригинального File Manager+; по документации Google OAuth для Android проверяет пакет и сертификат. Утверждать первопричину без logcat нельзя. Без зарегистрированного OAuth-клиента/альтернативной интеграции работоспособность Google Drive не доказана.
- Остаются непроверенными на устройствах: все формы списка и сортировки в специальных разделах (Новые файлы, анализ), Android TV D-pad, скорость миниатюр и копирования, FTP через QR с другого устройства, облако.
- Приватный APK/ключ не публиковались в GitHub; `main` не затронута. Готовым релизом V7 не считать.

## V8.1 targeted repair — 28.11.2026
- Confirmed in decoded V7: `Lax/g7/n0;->M3()Z` returned a hidden Apply-to-all checkbox state. Even though XML hid the checkbox, code could still copy preferences globally. V8.1 forces this return to false.
- `Lax/z7/f;->e(...)` discarded a folder suffix in Analysis mode. V8.1 preserves the suffix when a folder path exists. This does **not** make the analysis screen support new view layouts by itself.
- Two methods patched with three changed instruction bytes; DEX integrity hashes recomputed. Other 1,992 APK entries unchanged; versionCode 2403088, minSdk 21, same test signer as V7. Full rewrite of 54,208 methods avoided. The decoder round-trip confirmed the intended bytecode and no new branch-verifier warnings relative to V7.
- Script `scripts/surgical_prefs_v81.py` reproduces the **unsigned** patch from a validated V7 test APK. Test signing key/APK are not committed.
- Not claimed finished: current file-manager preferences still require Android runtime regression tests; analysis uses specialized layouts; Google Drive login remains unverified. Comparing source signer to custom signer confirms mismatch (upstream certificate SHA-1 `60:C2:CA:51:52:29:DA:14:CA:A5:52:7A:7B:8A:A8:6D:E3:BE:E7:3C`, custom SHA-1 `94:A4:55:E1:BC:8B:C0:39:84:CF:13:B0:F3:84:BD:A2:E2:A1:B2:14`), so Google authentication requires provider-compatible credentials or another supported authorization method. Signature mismatch is an evidence-backed risk, **not an established cause without logcat**.
- No verified Android hardware/emulator in this execution environment. Don't label experimental APK production-ready.

## Дополнительная проверка блокеров
- Исходные ресурсы содержат `msg_googledrive_not_allowed_on_tv`: штатный File Manager+ прямо запрещает вход в Google Drive на Android TV. Переупаковка и DEX-фиксы вида папок не меняют это ограничение. Для реальной TV-совместимости нужен отдельно реализованный и протестированный способ авторизации (например, поддерживаемый системный DocumentsProvider), а не снятие UI-запрета.
- На телефоне Google Drive показывает общую ошибку `msg_connection_failed`, но текст сам по себе не доказывает конкретную первопричину. Google документирует привязку OAuth Android к сертификату подписи; исходный и тестовый сертификаты различны. Без журналов авторизации и доступного зарегистрированного OAuth-клиента нельзя честно объявить исправление.
- Локальная V8.1: 37/37 тестов независимых Java-компонентов, тест QR-модуля, статическая проверка DEX 54 208 методов, подписи v1-v3, CRC ZIP. В итоговой подписанной APK отличаются только `classes.dex`, `AndroidManifest.xml` и три файла метаданных JAR-подписи; прочие 1 989 файлов побайтно совпадают с V7. Проверка реальных Android сценариев отсутствует. Следующий этап требует полноценных инструментальных тестов на устройстве и облачной авторизации через поддерживаемый канал.

## V8.2 — durability-only patch, 28.11.2026
- Applied *only* to validated V8.1 APK; no UI re-layout or file I/O replacement in this step.
- Six per-folder setters (`view_type`, `sort_type`, `icon_size`, `show_thumbnails`, `show_hidden`, `hide_grid_filename`) use `SharedPreferences.Editor.commit()` instead of `apply()`, preventing an immediate app termination from overtaking an asynchronous write at the moment of selection. The return value of `commit()` is not surfaced to the UI; persistence is not guaranteed if storage fails.
- DEX code-item method-ID references only: exactly 6 operands, `766 (apply) -> 768 (commit)`. Original code signatures and method sizes retained. AndroidManifest versionCode `2403088 -> 2403089`.
- Locally verified: ZIP CRC, signatures v1/v2/v3 with V8.1-compatible SHA-256 signer `371bac274c95fa9d590b10300ddbb17baa23c90b5862fde8639336504c0e497f`, identical DEX method/branch counts and static warning counts (54,208 methods, 104,869 branches, 550 preexisting warnings, no additional warnings). Of 1,994 ZIP entries, only classes.dex, AndroidManifest.xml and three JAR signature metadata files changed. 22+15 portable Java feature tests passed.
- Repro script: `scripts/patch_durable_preferences_v82.py`, expects exact DEX and manifest SHA-256 and refuses unknown APK. Emits unsigned archive; private signing key and APK remain local and are **not** pushed into public FIN-CONTROL.
- Still needs Android/TV runtime tests of folder selection persistence, copying, media thumbnails, QR pairing and analysis. This is a test build, **not** a complete daily-use release. Cloud intentionally out of scope at the owner's request.
- Special New Files list uses its own reduced menu (`res/menu/list_refresh.xml`); injecting arbitrary menu actions was deliberately avoided as a regression risk. Full per-section settings availability is not yet demonstrated.

## Source-driven QR revision (28.11.2026)
- Verified live «Передача» implementation at `georg1995105-hash/android-file-manager` (main): `TransferManager` dual HTTP/HTTPS listeners, NSD, bearer lifecycle, browser upload, scoped file sharing; details in `TRANSFER_SOURCE_AUDIT.md`.
- Retired FTPS QR payload from experimental `FeatureCore` and `AndroidFeatures`; new HTTP QR helper refuses ftp/ftps, bearer pairing contract and portable tests added. No automatic start of the service in File Manager+.
- **Not finished:** actual file-transfer server, app hooks and the APK patch require the original APK and compatible signing material. Keep V8.2 experimental. Clouds excluded.

## Целевая версия 4.0.0 — 28.11.2026
Версия 4.0.0 (versionCode 2404000) согласована как **целевой номер окончательного стабильного APK**; текущая V8.2 остаётся 3.8.5/2403089 и не переименована. Переносимый HTTP транспорт и проверка входящих файлов добавлены с исходника «Передачи» с отдельными тестами; код ещё не встроен в оригинальный File Manager+ APK. Правила выпуска: `RELEASE_4_0_0.md`.
