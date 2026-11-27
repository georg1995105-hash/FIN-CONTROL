package fmplus;

import java.security.SecureRandom;

public final class LanPairingTest {
  private static int checked;
  private static void ok(boolean b, String why) { if (!b) throw new AssertionError(why); checked++; }
  private static void rejects(Runnable r) {
    try { r.run(); throw new AssertionError("Invalid input accepted"); }
    catch (IllegalArgumentException | SecurityException expected) { checked++; }
  }
  public static void main(String[] args) {
    String url = LanPairing.browserUrl("192.168.10.25", 48537);
    ok(url.equals("http://192.168.10.25:48537/"), "Browser QR is local HTTP");
    ok(LanPairing.canonicalBrowserUrl(url).equals(url), "Canonical URL");
    ok(LanPairing.canonicalBrowserUrl("http://10.1.2.3:1234").equals("http://10.1.2.3:1234/"), "LAN 10");
    ok(LanPairing.browserUrl("172.31.255.3", 1).startsWith("http://"), "LAN 172");
    ok(LanPairing.browserUrl("169.254.1.9", 123).startsWith("http://"), "LAN link-local");
    ok(LanPairing.nativeUrl("192.168.1.2", 4555).equals("https://192.168.1.2:4555"), "Native HTTPS");
    ok(!url.contains("@") && !url.contains("token") && !url.contains("ftp"), "No secret in QR");
    rejects(() -> LanPairing.canonicalBrowserUrl("ftp://192.168.1.2:21/"));
    rejects(() -> LanPairing.canonicalBrowserUrl("ftps://192.168.1.2:990/"));
    rejects(() -> LanPairing.canonicalBrowserUrl("https://192.168.1.2:443/"));
    rejects(() -> LanPairing.canonicalBrowserUrl("http://pc:secret@192.168.1.2:1234/"));
    rejects(() -> LanPairing.canonicalBrowserUrl("http://192.168.1.2:1234/?token=secret"));
    rejects(() -> LanPairing.canonicalBrowserUrl("http://192.168.1.2:1234/other"));
    rejects(() -> LanPairing.canonicalBrowserUrl("http://example.com:1234/"));
    rejects(() -> LanPairing.browserUrl("8.8.8.8", 80));
    rejects(() -> LanPairing.browserUrl("127.0.0.1", 80));
    rejects(() -> LanPairing.browserUrl("192.168.1.01", 80));
    rejects(() -> LanPairing.browserUrl("192.168.1.256", 80));
    rejects(() -> LanPairing.browserUrl("192.168.1.1", 0));
    rejects(() -> LanPairing.browserUrl("192.168.1.1", 65536));
    LanPairing.Sessions s = new LanPairing.Sessions(new SecureRandom());
    String id = s.begin(1_000L), token = s.claim(id, 1_000L);
    ok(id.matches("[0-9a-f]{64}"), "Opaque request ID");
    ok(token.matches("[0-9a-f]{64}") && !id.equals(token), "Separate 256-bit bearer");
    ok(s.authorized(token,119_000L), "Valid session");
    rejects(() -> s.claim(id, 121_000L));
    ok(s.authorized(token,121_000L), "Token lives longer than pairing");
    s.revoke(token);
    ok(!s.authorized(token,121_001L), "Bearer revoked");
    rejects(() -> s.claim(id,121_001L));
    for (int i=0;i<5;i++) s.begin(130_000L);
    rejects(() -> s.begin(130_000L));
    ok(s.count(130_000L)==5, "Limit enforced");
    s.stop();
    ok(s.count(130_000L)==0, "Stop clears sessions");
    ok(!s.authorized(token,130_000L), "Old token unavailable");
    s.begin(200_000L);
    ok(s.count(3_800_000L)==0, "Session expired");
    rejects(() -> s.begin(-1L));
    System.out.println("PASS "+checked+" LAN QR/pairing checks");
  }
}
