package cn.guanlan.monitor;
import org.junit.Test;
import static org.junit.Assert.*;
public class LocalOriginTest {
    @Test public void onlyKnownPackagedFiles() {
        assertEquals("index.html", LocalOrigin.asset(LocalOrigin.URL));
        assertEquals("app.js", LocalOrigin.asset(LocalOrigin.URL + "app.js?v=3"));
        for (String value : new String[]{"http://appassets.androidplatform.net/app.js", "https://evil.test/", "file:///app.js",
                LocalOrigin.URL + "../secrets", LocalOrigin.URL + "%61pp.js", LocalOrigin.URL + "api/status",
                "https://appassets.androidplatform.net:443/app.js", "https://evil@appassets.androidplatform.net/app.js"})
            assertNull(value, LocalOrigin.asset(value));
    }
}
