package pro.veor.phantomcontrol

import java.net.HttpURLConnection
import java.nio.charset.StandardCharsets
import org.json.JSONObject
import org.json.JSONArray

data class ServiceStatus(val name: String, val state: String, val detail: String)
data class Capability(val kind: String, val models: List<String>)
data class Task(val id: String, val kind: String, val state: String, val title: String, val result: String)
data class Snapshot(val services: List<ServiceStatus>, val capabilities: List<Capability>, val tasks: List<Task>, val observedAt: String, val autopilot: String)
class ControlApi(origin: String, private val token: String) {
    private val endpoint = ControlEndpoint.normalize(origin)
    init { require(token.length in 24..4096 && token.all { it.code in 33..126 }) }
    private fun request(path: String, body: JSONObject? = null): JSONObject {
        val c = ControlEndpoint.url(endpoint, path).openConnection() as HttpURLConnection
        try {
            c.instanceFollowRedirects = false
            c.connectTimeout = 8000
            c.readTimeout = 15000
            c.useCaches = false
            c.setRequestProperty("Accept", "application/json")
            c.setRequestProperty("Authorization", "Bearer " + token)
            if (body != null) {
                val data = body.toString().toByteArray(StandardCharsets.UTF_8)
                c.requestMethod = "POST"
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                c.setFixedLengthStreamingMode(data.size)
                c.outputStream.use { it.write(data) }
            }
            val status = c.responseCode
            if (status !in 200..299) throw IllegalStateException("Сервер отклонил запрос (HTTP $status).")
            require(c.contentType?.substringBefore(';')?.trim()?.equals("application/json", true) == true) { "Неверный тип ответа." }
            val data = c.inputStream.use { input ->
                val out = java.io.ByteArrayOutputStream()
                val buf = ByteArray(8192)
                while (true) {
                    val n = input.read(buf)
                    if (n < 0) break
                    require(out.size() + n <= 1024 * 1024) { "Слишком большой ответ." }
                    out.write(buf, 0, n)
                }
                out.toString("UTF-8")
            }
            return JSONObject(data)
        } finally { c.disconnect() }
    }
    private fun objects(a: JSONArray): List<JSONObject> = (0 until a.length()).map { a.getJSONObject(it) }
    fun snapshot(): Snapshot {
        val s = request("/v1/status")
        require(s.getInt("version") == 1) { "Несовместимый API." }
        val services = objects(s.getJSONArray("services")).map { ServiceStatus(it.getString("name"), it.getString("state"), it.optString("detail")) }
        val caps = objects(s.getJSONArray("capabilities")).map {
            val a = it.getJSONArray("models")
            Capability(it.getString("kind"), (0 until a.length()).map { j -> a.getString(j) })
        }
        val tasks = objects(request("/v1/tasks").getJSONArray("tasks")).map {
            Task(it.getString("id"), it.getString("kind"), it.getString("state"), it.getString("title"), it.optString("result"))
        }
        return Snapshot(services, caps, tasks, s.optString("observed_at"), s.getString("autopilot"))
    }
    fun submit(id: String, kind: String, model: String, title: String): String =
        request("/v1/tasks", JSONObject().put("request_id", id).put("kind", kind).put("model", model).put("title", title)).getString("id")
}
