package fmplus;

import java.net.URI;
import java.net.URISyntaxException;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

/**
 * LAN pairing contract based on the actual "Передача" implementation.
 * QR holds only an HTTP browser URL, never FTP credentials or bearer tokens.
 * This module is NOT a running file server; the Android service must enforce
 * authorization at every data endpoint, advertise via NSD and scope file access.
 */
public final class LanPairing {
  private LanPairing() {}
  public static String browserUrl(String ip, int port) {
    checkIp(ip);
    if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid port");
    return "http://" + ip + ":" + port + "/";
  }
  public static String nativeUrl(String ip, int port) {
    checkIp(ip);
    if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid port");
    return "https://" + ip + ":" + port;
  }
  public static String canonicalBrowserUrl(String text) {
    if (text == null) throw new IllegalArgumentException("Missing URL");
    try {
      URI u = new URI(text);
      if (!"http".equals(u.getScheme()) || u.getRawUserInfo() != null ||
          u.getRawQuery() != null || u.getRawFragment() != null ||
          !(u.getRawPath() == null || u.getRawPath().isEmpty() || "/".equals(u.getRawPath())))
        throw new IllegalArgumentException("Not a browser transfer URL");
      return browserUrl(u.getHost(), u.getPort());
    } catch (URISyntaxException e) {
      throw new IllegalArgumentException("Invalid URL", e);
    }
  }
  public static void checkIp(String ip) {
    if (ip == null || !ip.matches("[0-9.]+"))
      throw new IllegalArgumentException("Numeric IPv4 required");
    String[] p = ip.split("[.]", -1);
    if (p.length != 4) throw new IllegalArgumentException("Invalid IPv4");
    int[] n = new int[4];
    for (int i = 0; i < 4; i++) {
      if (p[i].isEmpty() || p[i].length() > 3 || (p[i].length() > 1 && p[i].startsWith("0")))
        throw new IllegalArgumentException("Non-canonical IPv4");
      try { n[i] = Integer.parseInt(p[i]); }
      catch (NumberFormatException e) { throw new IllegalArgumentException("Invalid IPv4", e); }
      if (n[i] > 255) throw new IllegalArgumentException("Invalid IPv4");
    }
    boolean local = n[0] == 10 || (n[0] == 172 && n[1] >= 16 && n[1] <= 31) ||
        (n[0] == 192 && n[1] == 168) || (n[0] == 169 && n[1] == 254);
    if (!local) throw new IllegalArgumentException("Local IP required");
  }

  /**
   * Source protocol: POST /pair returns request ID; GET /pair/{id} returns
   * an ephemeral bearer; Authorization: Bearer is required for subsequent APIs.
   * Automatic pairing, no code or prompt, exactly as in the current "Передача".
   * All timestamps are monotonic uptime milliseconds, not wall-clock time.
   */
  public static final class Sessions {
    private static final long PAIR_TTL = 120_000L, TOKEN_TTL = 3_600_000L, WINDOW = 60_000L;
    private final SecureRandom rng;
    private final Map<String,Pair> pending = new HashMap<>();
    private final Map<String,Long> active = new HashMap<>();
    private long windowStart = -1;
    private int attempts = 0;
    private static final class Pair {
      final String token; final long expiration;
      Pair(String t, long e) { token=t; expiration=e; }
    }
    public Sessions(SecureRandom rng) { this.rng = Objects.requireNonNull(rng); }
    private static void time(long t) {
      if (t < 0) throw new IllegalArgumentException("Monotonic time required");
    }
    private void expire(long t) {
      pending.entrySet().removeIf(x -> t >= x.getValue().expiration);
      active.entrySet().removeIf(x -> t >= x.getValue());
    }
    private String secret() {
      byte[] b = new byte[32]; rng.nextBytes(b);
      char[] digits = "0123456789abcdef".toCharArray(), result = new char[64];
      for (int i=0; i<32; i++) {
        int n = b[i] & 255;
        result[i*2] = digits[n >>> 4]; result[i*2+1] = digits[n & 15];
        b[i] = 0;
      }
      return new String(result);
    }
    public synchronized String begin(long now) {
      time(now); expire(now);
      if (windowStart < 0 || now < windowStart || now - windowStart >= WINDOW) {
        windowStart = now; attempts = 0;
      }
      if (attempts >= 5 || pending.size() >= 10 || active.size() >= 10)
        throw new SecurityException("Pairing limit reached");
      attempts++;
      String request = secret(), token = secret();
      while (pending.containsKey(request)) request = secret();
      while (active.containsKey(token)) token = secret();
      pending.put(request, new Pair(token, Math.addExact(now, PAIR_TTL)));
      active.put(token, Math.addExact(now, TOKEN_TTL));
      return request;
    }
    public synchronized String claim(String request, long now) {
      time(now); expire(now);
      Pair p = pending.get(request);
      if (p == null || !active.containsKey(p.token))
        throw new SecurityException("Pairing expired or revoked");
      return p.token;
    }
    public synchronized boolean authorized(String token, long now) {
      time(now); expire(now);
      return token != null && !token.isEmpty() && active.containsKey(token);
    }
    public synchronized void revoke(String token) {
      if (token == null) return;
      active.remove(token);
      pending.entrySet().removeIf(x -> x.getValue().token.equals(token));
    }
    public synchronized void stop() {
      active.clear(); pending.clear(); attempts = 0; windowStart = -1;
    }
    public synchronized int count(long now) {
      time(now); expire(now); return active.size();
    }
  }
}
