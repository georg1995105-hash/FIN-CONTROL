package fmplus;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.widget.ImageView;

/**
 * Retires FTP pairing QR in the actual V8.2 call-site without changing the old
 * fragment's method signature. The old ftpUrl/password arguments are ignored.
 */
@Deprecated
public final class QrExistingServer {
  private QrExistingServer(){}
  private static String browser(Context c)throws Exception {
    String uri=LocalTransferHub.start(c);
    Intent i=new Intent(c,LocalTransferService.class);
    if(Build.VERSION.SDK_INT>=26)c.startForegroundService(i);
    else c.startService(i);
    return uri;
  }
  public static String buildUri(String ftpUrl,String oldPassword) {
    // Must not turn FTP URI into a fake HTTP URI. Service context is required.
    throw new IllegalStateException("Start LAN transfer using an Android Context");
  }
  public static void render(ImageView image,String ftpUrl,String oldPassword) {
    if(image==null)return;
    try{QrLocalTransfer.render(image,browser(image.getContext()));}
    catch(Exception e){image.setImageDrawable(null);image.setVisibility(android.view.View.GONE);}
  }
  public static void show(Activity activity,String ftpUrl,String oldPassword) {
    if(activity==null||activity.isFinishing())return;
    try{QrLocalTransfer.show(activity,browser(activity));}
    catch(Exception e){new android.app.AlertDialog.Builder(activity).setTitle("Передача недоступна")
      .setMessage(e.getMessage()==null?"Проверьте Wi-Fi":e.getMessage())
      .setPositiveButton("ОК",null).show();}
  }
}
