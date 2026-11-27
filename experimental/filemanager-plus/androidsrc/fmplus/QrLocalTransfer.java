package fmplus;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * QR of the ACTIVE in-app HTTP browser listener, never of an FTP server.
 * Caller must provide its real running address and manage service lifetime.
 */
public final class QrLocalTransfer {
  private QrLocalTransfer() {}
  public static String buildUri(String activeBrowserAddress) {
    String uri = LanPairing.canonicalBrowserUrl(activeBrowserAddress);
    if (uri.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > QrMatrix.MAX_BYTES)
      throw new IllegalArgumentException("QR URL too long");
    return uri;
  }
  private static Bitmap bitmap(String uri) {
    QrMatrix qr = QrMatrix.encode(uri);
    final int scale=7, border=4, side=(QrMatrix.SIZE+border*2)*scale;
    Bitmap image=Bitmap.createBitmap(side,side,Bitmap.Config.ARGB_8888);
    image.eraseColor(Color.WHITE);
    for(int y=0;y<QrMatrix.SIZE;y++)for(int x=0;x<QrMatrix.SIZE;x++)if(qr.get(x,y))
      for(int dy=0;dy<scale;dy++)for(int dx=0;dx<scale;dx++)
        image.setPixel((x+border)*scale+dx,(y+border)*scale+dy,Color.BLACK);
    return image;
  }
  public static void render(ImageView image,String activeBrowserAddress) {
    if(image==null)return;
    try {
      String uri=buildUri(activeBrowserAddress);
      image.setImageBitmap(bitmap(uri));
      image.setContentDescription("QR подключения: "+uri);
      image.setVisibility(View.VISIBLE);
    } catch (IllegalArgumentException error) {
      image.setImageDrawable(null);
      image.setVisibility(View.GONE);
    }
  }
  public static void show(Activity activity,String activeBrowserAddress) {
    if(activity==null||activity.isFinishing())return;
    try {
      String uri=buildUri(activeBrowserAddress);
      LinearLayout column=new LinearLayout(activity);
      column.setOrientation(LinearLayout.VERTICAL);
      int inset=(int)(16*activity.getResources().getDisplayMetrics().density);
      column.setPadding(inset,inset,inset,inset);
      ImageView qr=new ImageView(activity);
      qr.setImageBitmap(bitmap(uri));
      qr.setContentDescription("QR локальной передачи файлов");
      qr.setAdjustViewBounds(true);
      column.addView(qr,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
      TextView address=new TextView(activity);
      address.setText(uri);
      address.setTextIsSelectable(true);
      address.setPadding(0,inset,0,0);
      column.addView(address);
      TextView details=new TextView(activity);
      details.setText("Откройте QR в браузере другого устройства в этой Wi-Fi сети.");
      details.setPadding(0,inset,0,0);
      column.addView(details);
      new AlertDialog.Builder(activity).setTitle("Передача по QR").setView(column)
        .setPositiveButton("Закрыть",null).show();
    } catch (IllegalArgumentException error) {
      new AlertDialog.Builder(activity).setTitle("QR недоступен")
        .setMessage("Включите локальную передачу и проверьте адрес в Wi-Fi сети.")
        .setPositiveButton("ОК",null).show();
    }
  }
}
