package cn.guanlan.monitor;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Pure Java so navigation and local-HTTP restrictions can be unit tested. */
final class ServerAddress {
    private ServerAddress() { }

    static String normalize(String input) {
        try {
            URI uri = new URI(input.trim());
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            String host = uri.getHost();
            if ((!scheme.equals("https") && !scheme.equals("http")) || host == null
                    || uri.getRawUserInfo() != null || uri.getRawQuery() != null || uri.getRawFragment() != null
                    || (uri.getRawPath() != null && !uri.getRawPath().isEmpty() && !uri.getRawPath().equals("/"))
                    || uri.getPort() == 0 || uri.getPort() > 65535)
                throw new IllegalArgumentException();
            if (scheme.equals("http") && !isLocal(host))
                throw new IllegalArgumentException("HTTP 仅支持局域网 IP；远程服务器请使用 HTTPS。");
            return new URI(scheme, null, host.toLowerCase(Locale.ROOT), uri.getPort(), "/", null, null).toString();
        } catch (URISyntaxException | NullPointerException e) {
            throw new IllegalArgumentException("请输入完整地址，例如 http://192.168.1.8:8788");
        } catch (IllegalArgumentException e) {
            if (e.getMessage() != null) throw e;
            throw new IllegalArgumentException("地址只能包含协议、主机和端口，不能包含路径、账号或配对码。");
        }
    }

    static boolean isLocal(String host) {
        if (host.equalsIgnoreCase("localhost") || host.equals("[::1]")) return true;
        String[] parts = host.split("\\.");
        if (parts.length != 4) return false;
        int[] bytes = new int[4];
        for (int i = 0; i < 4; i++) {
            if (!parts[i].matches("0|[1-9][0-9]{0,2}")) return false;
            bytes[i] = Integer.parseInt(parts[i]);
            if (bytes[i] > 255) return false;
        }
        return bytes[0] == 10 || bytes[0] == 127 || (bytes[0] == 192 && bytes[1] == 168)
                || (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31);
    }

    static boolean sameOrigin(String base, String candidate) {
        try {
            URI a = new URI(base), b = new URI(candidate);
            return b.getRawUserInfo() == null && a.getScheme().equalsIgnoreCase(b.getScheme())
                    && a.getHost().equalsIgnoreCase(b.getHost()) && port(a) == port(b);
        } catch (Exception e) { return false; }
    }

    private static int port(URI uri) {
        return uri.getPort() >= 0 ? uri.getPort() : "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }
}
