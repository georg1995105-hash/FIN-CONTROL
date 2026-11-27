package fmplus;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.net.URI;
import java.nio.charset.StandardCharsets;

/** Offline QR of the already running FTP server. No login policy changes. */
public final class QrExistingServer {
  private QrExistingServer() { }

  public static String buildUri(String serverUrl, String password) throws Exception {
    if (serverUrl == null || serverUrl.trim().length() == 0) throw new IllegalArgumentException("Start the network service first");
    URI address = new URI(serverUrl.trim());
    if (!"ftp".equalsIgnoreCase(address.getScheme()) || address.getHost() == null) throw new IllegalArgumentException("Invalid FTP address");
    String host = address.getHost();
    if (!isPrivateAddress(host)) throw new IllegalArgumentException("Local network address required");
    int port = address.getPort() > 0 ? address.getPort() : 21;
    String userInfo = password == null || password.isEmpty() ? null : "pc:" + password;
    String uri = new URI("ftp", userInfo, host, port, "/", null, null).toASCIIString();
    if (uri.getBytes(StandardCharsets.UTF_8).length > QrMatrix.MAX_BYTES) throw new IllegalArgumentException("QR connection string too long");
    return uri;
  }

  static boolean isPrivateAddress(String address) {
    if (address == null || !address.matches("[0-9.]+")) return false;
    String[] p = address.split("\\.");
    if (p.length != 4) return false;
    int[] n = new int[4];
    for (int i = 0; i < 4; i++) {
      try {
        if (p[i].isEmpty() || p[i].length() > 3) return false;
        n[i] = Integer.parseInt(p[i]);
        if (n[i] < 0 || n[i] > 255) return false;
      } catch (NumberFormatException e) { return false; }
    }
    return n[0] == 10 || (n[0] == 172 && n[1] >= 16 && n[1] <= 31)
        || (n[0] == 192 && n[1] == 168) || (n[0] == 169 && n[1] == 254);
  }

  public static void show(Activity activity, String serverUrl, String password) {
    if (activity == null || activity.isFinishing()) return;
    try {
      String payload = buildUri(serverUrl, password);
      QrMatrix qr = QrMatrix.encode(payload);
      final int scale = 7, border = 4;
      int edge = (QrMatrix.SIZE + border * 2) * scale;
      Bitmap bitmap = Bitmap.createBitmap(edge, edge, Bitmap.Config.ARGB_8888);
      bitmap.eraseColor(Color.WHITE);
      for (int y = 0; y < QrMatrix.SIZE; y++) {
        for (int x = 0; x < QrMatrix.SIZE; x++) {
          if (qr.get(x, y)) {
            int left = (x + border) * scale, top = (y + border) * scale;
            for (int yy = 0; yy < scale; yy++)
              for (int xx = 0; xx < scale; xx++) bitmap.setPixel(left + xx, top + yy, Color.BLACK);
          }
        }
      }
      LinearLayout content = new LinearLayout(activity);
      content.setOrientation(LinearLayout.VERTICAL);
      content.setPadding(20, 12, 20, 12);
      ImageView image = new ImageView(activity);
      image.setImageBitmap(bitmap);
      image.setContentDescription("QR for connecting to this device by FTP");
      image.setAdjustViewBounds(true);
      content.addView(image, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
      TextView label = new TextView(activity);
      label.setText("Scan from another device on the same Wi-Fi network. Use an FTP-capable file manager.");
      label.setTextSize(14f);
      label.setPadding(4, 12, 4, 0);
      content.addView(label);
      new AlertDialog.Builder(activity).setTitle("Connect using QR").setView(content)
          .setPositiveButton("Close", null).show();
    } catch (Exception e) {
      new AlertDialog.Builder(activity).setTitle("QR unavailable")
          .setMessage(e.getMessage() == null ? "Check network access" : e.getMessage())
          .setPositiveButton("OK", null).show();
    }
  }
}
