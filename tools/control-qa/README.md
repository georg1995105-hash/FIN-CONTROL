# Device contract QA

The actual Android client is installed in Android 15 (API 35). The fixture uses synthetic data and HTTPS with a per-run certificate, trusted only in an ephemeral debug manifest overlay for the emulator host. No insecure trust code or lab CA is committed to the app. No lab APK is uploaded or distributed. Only screenshot/result evidence is collected. The private server is independently tested against the same v1 contract; this fixture does not establish a production connection or prove the private server's end-to-end operation with Android. No real payments, credentials, production endpoints, or model calls.

Test path: invalid code, successful enrollment, visible failed service, explicit diagnosis task, background return, logout, task history after re-enrollment, remote revocation, process restart. Failure must fail the workflow, not mark it optional.
