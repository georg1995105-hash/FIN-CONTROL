package pro.veor.phantomcontrol

import org.junit.Assert.*
import org.junit.Test

class ControlEndpointTest {
    @Test fun originAndFixedRoute(){
        assertEquals("https://example.test",ControlEndpoint.normalize(" https://example.test/ "))
        assertEquals("https://example.test:8443/v1/tasks",ControlEndpoint.url("https://example.test:8443","/v1/tasks").toString())
    }
    @Test fun rejectsUnsafeOrigins(){
        listOf("http://example.test","https://u:p@example.test","https://example.test/path","https://example.test/?q=1","https://example.test/#x","file:///tmp/x","https://example.test:99999").forEach {
            assertTrue(it,runCatching{ControlEndpoint.normalize(it)}.isFailure)
        }
    }
    @Test fun enrollmentRoutes(){
        assertEquals("https://example.test/v1/session",ControlEndpoint.url("https://example.test","/v1/session").toString())
        assertEquals("https://example.test/v1/session/revoke",ControlEndpoint.url("https://example.test","/v1/session/revoke").toString())
    }
    @Test fun refusesArbitraryRoute(){
        assertTrue(runCatching{ControlEndpoint.url("https://example.test","//evil.test/x")}.isFailure)
    }
}
