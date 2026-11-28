# PHANTOM CONTROL — состояние 28.11.2026

Владелец заменил назначение FIN CONTROL на персональное управление инфраструктурой и разработкой. Старые финансовые наработки остаются в main/истории; File Manager+ отдельная ветка, не трогаем. Новый package pro.veor.phantomcontrol. Не публиковать внутреннюю конфигурацию/секреты в публичный Git.

- Alpha02: Android APK build, unit, lint, manifest/digest success на e4113ce5ffad69fbf359b1307e5172eb81264dec: https://github.com/georg1995105-hash/FIN-CONTROL/actions/runs/46182140592 .
- Android 15 (API 35, x86_64) synthetic HTTPS UI contract success на 3ba2e12b464ba36f6f6afdcdb8fefa7d463bd8cd: https://github.com/georg1995105-hash/FIN-CONTROL/actions/runs/46182422893 . Evidence artifact 15277489300. Это проверка фактического Android-клиента с тестовым HTTPS backend, не полный production E2E.
- Отдельная серверная разработка в закрытом репозитории; постоянная очередь, одноразовое подключение, отзыв сеанса, строгая обработка устаревших наблюдений, unprivileged listener. Проверен официальный текстовый API adapter с synthetic transport, реальные модели/ключи и стоимость не проверены, выключено по умолчанию. CLODEX исключён из новой архитектуры.
- Следующие gates: полный Android + настоящий private backend E2E; mapping текущих проверок мониторинга, безопасный ingress/enrollment; доверенная официальная авторизация моделей и бюджет, многошаговый чат, Codex в изолированных рабочих средах, тесты отказов и независимый контроль перед внедрением. Production repair disabled.
- Не считать debug APK готовым приложением. Не выпускать без реальной интеграции и отдельной подписи/OTA.

Требования нового продукта: docs/PHANTOM_CONTROL.md. История первоначальной цели сохранена в main и прежних коммитах.
