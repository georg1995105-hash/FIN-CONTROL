# FIN CONTROL — Android offline shell (first build milestone)

Branch: `feature/android-shell-20261126`. Android Kotlin + Jetpack Compose module in `app/`, Gradle 8.9 / AGP 8.7.3 / Kotlin and Compose compiler 2.0.21, compile SDK 35, min SDK 28. Build debug APK via `gradle :app:assembleDebug :app:lintDebug`; the workflow uses exactly these versions. No application signing or OTA is configured.

## Implemented code paths

- Four bottom tabs (Home, History, PRO, Settings) and sections for financial checks, vision and smart camera; responsive navigation rail on screens >=700dp. Four manually chosen themes and approved base palette. Approved HTML nine-screen reference remains unchanged.
- Actual Android Storage Access Framework file picker for image/PDF, external system camera via FileProvider without camera/storage permissions, offline preview. PDF page-by-page via PdfRenderer. Large image decode bounded to ~1600 pixels per longest side. No cloud API and no INTERNET permission.
- Tested pre-existing Kotlin financial core compiled into APK. It **is not yet used to automatically analyze document photos**: no Russian OCR model, text extraction, line-item provenance, history database, report export, payments or license.
- Clear in-app explanations distinguish file preview from actual document recognition. Empty History/PRO screens do not fabricate results or offer a live purchase.
- Files opened through SAF are not copied to the repository; captured photos live temporarily under app cache. Backup disabled, no analytics/telemetry.

## Not verified yet

Android physical device behavior, actual standalone installation, input providers for non-seekable PDFs, CameraX inline capture, receipt recognition quality, performance and memory on older devices, accessibility/contrast on all four themes, landscape and tablets, licensing and release signing. GitHub Actions only compiles and inspects a **debug** APK; it does not qualify as a production release.

## Next acceptance

After CI APK succeeds, inspect lint warnings and artifact metadata. The next implementation should integrate a commercially licensed **offline Cyrillic OCR** into the source-verification contract, with explicit manual choice, robust document capture and full financial statement parsing; validate with independently labelled real documents and device installation before public release. Do not select Latin-only ML Kit as a Russian OCR solution. No production Phantom servers are needed.
