package fmplus;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.widget.ImageView;

/** V8.2 method-signature compatibility; QR never embeds FTP URI/password. */
@Deprecated
public final class QrExistingServer {
  private QrExistingServer() {}
  private static void launch(Context c) {
    Intent intent = new Intent(c, LocalTransferService.class);
    if(Build.VERSION.SDK_INT>=26)c.startForegroundService(intent);
    else c.startService(intent);
  }
  public static String buildUri(String ftpUrl, String oldPassword) {
    throw new IllegalStateException("Active local HTTP service and Android Context required");
  }
  public static void render(ImageView image, String ftpUrl, String oldPassword) {
    if(image==null)return;
    try{launch(image.getContext());}catch(Exception error){image.setVisibility(android.view.View.GONE);return;}
    // Never open network sockets on Android's main/UI thread.
    new Thread(()->{
      try {
        final String uri=LocalTransferHub.start(image.getContext());
        image.post(()->{if(image.getWindowToken()!=null)QrLocalTransfer.render(image,uri);});
      }catch(Exception error){image.post(()->image.setVisibility(android.view.View.GONE));}
    },"fmplus-qr-prepare").start();
  }
  public static void show(Activity activity, String ftpUrl, String oldPassword) {
    if(activity==null||activity.isFinishing())return;
    try{launch(activity);}catch(Exception error){unavailable(activity);return;}
    new Thread(()->{
      try {
        final String uri=LocalTransferHub.start(activity);
        activity.runOnUiThread(()->{
          if(!activity.isFinishing() && !activity.isDestroyed())QrLocalTransfer.show(activity,uri);
        });
      } catch(Exception error) {activity.runOnUiThread(()->unavailable(activity));}
    },"fmplus-qr-dialog").start();
  }
  private static void unavailable(Activity activity) {
    if(activity.isFinishing()||activity.isDestroyed())return;
    new android.app.AlertDialog.Builder(activity).setTitle("Передача недоступна")
      .setMessage("Проверьте Wi-Fi и разрешения.")
      .setPositiveButton("ОК",null).show();
  }
}
