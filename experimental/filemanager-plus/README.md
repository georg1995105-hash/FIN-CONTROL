# File Manager+ feature-core prototype

An isolated Java 17 prototype for the requested File Manager+ enhancements. **Not integrated with the proprietary APK**, **not installable** and **not a completed replacement**. This branch is separate from the FIN-CONTROL application.

## Existing runnable components

- Per-folder display preferences (view mode, sorting, thumbnail toggles)
- Versioned checksummed backup and safe restore of display settings (does not include secrets)
- Transfer-style local HTTP browser QR URL, bounded in-memory pairing and bearer-session checks (real file server and Android lifecycle integration NOT implemented)
- Basic D-pad grid focus targeting
- Local file copy with progress, cancellation, conflict handling and temp-file cleanup (SAF/SMB/FTP/cloud adapters NOT implemented)

## Verify

`javac -encoding UTF-8 -d build src/fmplus/*.java test/fmplus/*.java`

`java -cp build fmplus.FeatureCoreTest`

`java -cp build fmplus.SafeTransferTest\n\njava -cp build fmplus.LanPairingTest`

## Critical gaps

- Android UI glue, preference storage adapter, local HTTP/HTTPS transfer service, scoped file API and Android lifecycle
- Thumbnail cache engine, APK details UI, custom home screen, tablet/TV layout integration
- Android SDK build, APK integration and signing, instrumentation and physical device testing
- Original APK signature cannot be reproduced without the upstream owner's signing key

Do not insert this module into the original APK or claim that the requirements are complete without a separate integration and regression test cycle.
Source audit and exact endpoint mapping: [TRANSFER_SOURCE_AUDIT.md](TRANSFER_SOURCE_AUDIT.md). Experimental FTP QR creation was removed; the old Android helper is a rejecting compatibility shim. The real File Manager+ APK is **not modified or released** by these portable modules.

### Transferred from the owner's Android "Передача" repository
- `src/fmplus/LocalHttpsServer.java`: bounded HTTP request parser and restricted LAN socket server.
- `src/fmplus/IncomingTransfer.java`: validated path, upload chunk, staged atomic commit, SHA-256 checks and cancellation.
- `browser/`: same static transfer page/JS/CSS as the source application. These **must not** be exposed until the Android service implements all actual endpoints with authorization.
- Mirrored, separately executable JVM security tests `IncomingTransferTest` and `HttpTransportTest`.

These portable sources are not integrated in File Manager+ 3.8.5 APK. The old FTP server remains unchanged in users' installed V8.2 until an independently tested replacement APK exists.
