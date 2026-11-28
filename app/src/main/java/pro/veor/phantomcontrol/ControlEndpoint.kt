package pro.veor.phantomcontrol

import java.net.URI
import java.net.URL

/** Only an explicitly configured HTTPS origin. No redirects or embedded credentials. */
object ControlEndpoint {
    fun normalize(input: String): String {
        val uri = URI(input.trim())
        require(uri.scheme.equals("https", true) && uri.host != null) { "Требуется HTTPS-адрес." }
        require(uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null)
        require(uri.rawPath.isNullOrEmpty() || uri.rawPath == "/")
        require(uri.port == -1 || uri.port in 1..65535)
        return URI("https", null, uri.host, uri.port, null, null, null).toASCIIString()
    }
    fun url(origin: String, path: String): URL {
        require(path in setOf("/v1/status", "/v1/tasks"))
        return URI(normalize(origin) + path).toURL()
    }
}
