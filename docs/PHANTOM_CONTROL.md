# PHANTOM CONTROL — initial implementation

New owner-only product, distinct Android package pro.veor.phantomcontrol. FIN CONTROL and other branches are preserved. No production service, credentials, internal endpoint or infrastructure topology is included in this public client.

Protocol v1: explicit HTTPS origin, authenticated GET /v1/status and GET /v1/tasks, POST /v1/tasks with request_id, kind, model, title. Status includes version=1, observed_at, services (name/state/detail), capabilities (kind/models), autopilot. Tasks include id/kind/state/title/result. Capabilities come from the server; missing executors cannot be launched. A retry of an uncertain submission of identical content uses its existing request UUID within the session. Tokens are held in memory only. TLS verification remains platform default, redirects disabled.

First acceptance: unit tests, APK build and lint, actual client/server integration in isolation, safe authentication, durable task journal, recovery and no false green statuses. Server-side orchestration, official model adapters, permission policies, production rollout, verified model switching, auto-remediation and release signing are distinct next steps. No CLODEX. No new monitoring, production changes, paid services or release authorization from this branch alone. Do not treat debug build as complete product.

## Build and UI follow-up
First CI #46181026921 failed before Kotlin compilation: Maven Central HTTP 429 resolving AGP transitive dependencies. Use the already deployed Phantom project's Google-hosted Central mirror first, no versions or security checks changed. Refresh while the app is in foreground, back off on connection errors, clear unauthorized sessions; no background monitor added. Labels distinguish read-only diagnostics and missing observations.

## Alpha02 owner enrollment
Replace permanent bearer entry with one-use 256-bit enrollment code exchanged at /v1/session; session expiry 12h; revoke via POST /v1/session/revoke. Codes never persisted in client, bearer remains in ViewModel memory only. If initial response is lost request a new code. A 401 clears the session, a failed logout warns if remote revocation is unconfirmed. Server-side jobs remain independent of UI. No automatic repair. Private service PR 1455. Android runtime TLS testing still required.
