# File Manager+ feature-core prototype

An isolated Java 17 prototype for the requested File Manager+ enhancements. **Not integrated with the proprietary APK**, **not installable** and **not a completed replacement**. This branch is separate from the FIN-CONTROL application.

## Existing runnable components

- Per-folder display preferences (view mode, sorting, thumbnail toggles)
- Versioned checksummed backup and safe restore of display settings (does not include secrets)
- FTPS pairing **URI** with a generated 192-bit password and 10-minute expiry metadata (QR bitmap creation and enforcement in the FTP service are NOT implemented)
- Basic D-pad grid focus targeting
- Local file copy with progress, cancellation, conflict handling and temp-file cleanup (SAF/SMB/FTP/cloud adapters NOT implemented)

## Verify

`javac -encoding UTF-8 -d build src/fmplus/*.java test/fmplus/*.java`

`java -cp build fmplus.FeatureCoreTest`

`java -cp build fmplus.SafeTransferTest`

## Critical gaps

- Android UI glue, preference storage adapter, QR display and server-side expiry enforcement
- Thumbnail cache engine, APK details UI, custom home screen, tablet/TV layout integration
- Android SDK build, APK integration and signing, instrumentation and physical device testing
- Original APK signature cannot be reproduced without the upstream owner's signing key

Do not insert this module into the original APK or claim that the requirements are complete without a separate integration and regression test cycle.