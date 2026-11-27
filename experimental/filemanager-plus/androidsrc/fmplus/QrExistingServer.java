package fmplus;
import android.app.Activity;
import android.widget.ImageView;

/** Legacy experimental entrypoints; FTP/FTPS QR input is now explicitly rejected. */
@Deprecated
public final class QrExistingServer {
  private QrExistingServer() {}
  public static String buildUri(String url,String oldPassword) {
    return QrLocalTransfer.buildUri(url);
  }
  public static void render(ImageView image,String url,String oldPassword) {
    QrLocalTransfer.render(image,url);
  }
  public static void show(Activity activity,String url,String oldPassword) {
    QrLocalTransfer.show(activity,url);
  }
}
