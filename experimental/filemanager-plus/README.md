# File Manager+ feature-core prototype

Experimental Android+Java source and offline APK integration tooling for File Manager+ enhancements. **Not an approved or released APK.** This branch is separate from FIN-CONTROL's own application.

## Existing runnable components

- Per-folder display preferences (view mode, sorting, thumbnail toggles)
- Versioned checksummed backup and safe restore of display settings (does not include secrets)
- Transfer-style local HTTP browser QR and bounded pairing; Android foreground service, upload API and API21-safe receiving engine (native TLS/NSD and selected-file download not yet integrated)
- Basic D-pad grid focus targeting
- Local file copy with progress, cancellation, conflict handling and temp-file cleanup (SAF/SMB/FTP/cloud adapters NOT implemented)

## Verify

`javac -encoding UTF-8 -d build src/fmplus/*.java test/fmplus/*.java`

`java -cp build fmplus.FeatureCoreTest`

`java -cp build fmplus.SafeTransferTest`\n\n`java -cp build fmplus.LanPairingTest`

## Critical gaps

- Full Android UI integration, per-folder preferences storage adapters, native HTTPS/NSD and selected-file download
- Thumbnail cache engine, APK details UI, custom home screen, tablet/TV layout integration
- Reproducible APK-level build exists; matching V8.2 signing key, instrumented Android/TV testing and final installation verification still missing
- Upgrade over installed V8.2 requires the earlier V8.2 private test key (not the upstream original key), which is unavailable

The offline integration patch was compiled into a private, unsigned 4.0.0 APK as a static test; never distribute or claim a stable result before signing/Android-device acceptance.
Source audit and exact endpoint mapping: [TRANSFER_SOURCE_AUDIT.md](TRANSFER_SOURCE_AUDIT.md). Experimental FTP QR creation was removed; the shim now starts an independent LAN HTTP service. Only an **unsigned offline integration** was assembled, not a released APK.

### Transferred from the owner's Android "Передача" repository
- `src/fmplus/LocalHttpsServer.java`: bounded HTTP request parser and restricted LAN socket server.
- `src/fmplus/IncomingTransfer.java`: validated path, upload chunk, staged atomic commit, SHA-256 checks and cancellation.
- `browser/`: same static transfer page/JS/CSS as the source application. These **must not** be exposed until the Android service implements all actual endpoints with authorization.
- Mirrored, separately executable JVM security tests `IncomingTransferTest` and `HttpTransportTest`.

The user's installed V8.2 is unchanged. For an offline 4.0.0 integration build, see `scripts/integrate_lan_qr_v40.py`; it requires private V8.2 bytes, Apktool 3.0.3 and CI feature DEX+browser artifact.

Per-folder display model now stores **detailed/list/grid, sort/direction, thumbnails, icon visibility and icon size (24–160dp)**; backup schema 2 migrates schema 1 with unchanged defaults. The verified original APK is accessible privately; real UI preference integration and Android runtime validation remain pending.

**Static validation (28.11.2026):** actual V8.2 decompiled and APKtool rebuilt. Offline unsigned 4.0.0 integration produced with package `com.alphainventor.filemanager`, versionCode `2404000`, 5 DEX, 3 browser assets; all ZIP CRCs valid. A separate disposable-signer check passed APK Signature Scheme v1/v2/v3 and that key was deleted. This does not prove installation, app behavior, or upgrade compatibility. See [WORK.md](WORK.md) and [RELEASE_4_0_0.md](RELEASE_4_0_0.md).
