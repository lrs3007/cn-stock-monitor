package cn.guanlan.monitor;

import java.net.URI;
import java.util.Set;

/** The bridge is only reachable from immutable, packaged application files. */
final class LocalOrigin {
    static final String URL = "https://appassets.androidplatform.net/";
    private static final Set<String> FILES = Set.of("index.html", "app.js", "style.css", "icon.svg", "manifest.webmanifest");
    static String asset(String url) {
        try {
            URI uri = new URI(url);
            if (!"https".equals(uri.getScheme()) || !"appassets.androidplatform.net".equals(uri.getHost())
                    || uri.getRawUserInfo() != null || uri.getPort() != -1) return null;
            String path = uri.getRawPath();
            if (path == null || path.equals("/")) return "index.html";
            return path.startsWith("/") && FILES.contains(path.substring(1)) ? path.substring(1) : null;
        } catch (Exception e) { return null; }
    }
}
