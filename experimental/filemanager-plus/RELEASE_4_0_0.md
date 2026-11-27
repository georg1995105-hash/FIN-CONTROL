# File Manager+ 4.0.0 — release acceptance target

Requested by owner on 28.11.2026. **Target only, not a released APK.**

## Version
- Display version **4.0.0**.
- Recommended Android versionCode **2404000** (strictly greater than V8.2 test versionCode **2403089**).
- Preserve Android package `com.alphainventor.filemanager` and installed-data storage.
- A successful version change in documentation does not change installed app manifests.
- The final APK must be signed with the SAME certificate as the installed V8.2 build to upgrade in place; otherwise keep it separate and do not claim no data loss.

## Non-negotiable release gate
1. Retrieve and authenticate the exact original 3.8.5 APK and V8.2 reference; confirm package, target/min SDK, signature and DEX hashes.
2. Merge source-driven LAN transfer service **replacing QR-over-FTP**; reproduce browser QR, Android/TV TLS pinning, NSD, bounded authorization, file allowlist, progress, cancel, resume, filenames, conflict and download tests.
3. Per-folder display preferences, sort/thumbnail/icon settings, main screen, APK details, backup restore, all special screens; no cloud changes.
4. Debug/instrumented tests on Android phone, tablet and TV; D-pad, focus, file copy, move, cancel, restart, low storage, large files, display settings after process death.
5. Produce signed candidate, use Android PackageManager to verify install-over-V8.2 keeps data; test rollback/data backup. If signer mismatch, stop release.
6. Only after every gate passes: publish one **4.0.0 stable** APK and verified direct download link.

**Available source in this repo:** experimental feature modules only; original APK and V8.2 binaries, private signing key and Android device test evidence are absent. Do not mark the release complete.
