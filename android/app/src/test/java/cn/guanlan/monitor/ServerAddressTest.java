package cn.guanlan.monitor;

import org.junit.Test;
import static org.junit.Assert.*;

public class ServerAddressTest {
    @Test public void supportsLanAndHttps() {
        assertEquals("http://192.168.1.8:8788/", ServerAddress.normalize(" http://192.168.1.8:8788 "));
        assertEquals("https://example.com/", ServerAddress.normalize("https://EXAMPLE.com"));
        assertTrue(ServerAddress.isLocal("172.31.1.2"));
        assertFalse(ServerAddress.isLocal("172.32.1.2"));
    }
    @Test public void rejectsUnsafeAndAmbiguousAddresses() {
        for (String input : new String[]{"file:///etc/passwd", "javascript:alert(1)", "http://example.com",
                "http://192.168.1.8.evil.com", "https://user:pass@example.com", "https://example.com/path",
                "https://example.com/?token=secret", "https://example.com/#foo", "http://192.168.1.8:99999",
                "http://192.168.001.8", "http://2130706433", "https://example.com:0"}) {
            assertThrows(input, IllegalArgumentException.class, () -> ServerAddress.normalize(input));
        }
    }
    @Test public void originIncludesSchemeHostAndPort() {
        assertTrue(ServerAddress.sameOrigin("https://example.com/", "https://example.com:443/api/status"));
        for (String url : new String[]{"https://example.com.evil.com/", "http://example.com/", "https://example.com:444/",
                "https://example.com@evil.com/", "https://evil@example.com/", "file:///etc/passwd", "//example.com/"})
            assertFalse(url, ServerAddress.sameOrigin("https://example.com/", url));
    }
}
