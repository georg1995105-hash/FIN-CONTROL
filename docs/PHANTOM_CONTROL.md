# PHANTOM CONTROL — initial implementation

New owner-only product, distinct Android package pro.veor.phantomcontrol. FIN CONTROL and other branches are preserved. No production service, credentials, internal endpoint or infrastructure topology is included in this public client.

Protocol v1: explicit HTTPS origin, authenticated GET /v1/status and GET /v1/tasks, POST /v1/tasks with request_id, kind, model, title. Status includes version=1, observed_at, services (name/state/detail), capabilities (kind/models), autopilot. Tasks include id/kind/state/title/result. Capabilities come from the server; missing executors cannot be launched. A retry of an uncertain submission of identical content uses its existing request UUID within the session. Tokens are held in memory only. TLS verification remains platform default, redirects disabled.

First acceptance: unit tests, APK build and lint, actual client/server integration in isolation, safe authentication, durable task journal, recovery and no false green statuses. Server-side orchestration, official model adapters, permission policies, production rollout, verified model switching, auto-remediation and release signing are distinct next steps. No CLODEX. No new monitoring, production changes, paid services or release authorization from this branch alone. Do not treat debug build as complete product.
