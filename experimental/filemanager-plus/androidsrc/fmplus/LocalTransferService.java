package fmplus;

import android.app.*;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/** Foreground lifecycle for LAN transfer. Stop immediately revokes bearer sessions. */
public final class LocalTransferService extends Service {
  private static final String CHANNEL="fmplus-local-transfer";
  @Override public void onCreate(){
    super.onCreate();
    NotificationManager manager=getSystemService(NotificationManager.class);
    if(Build.VERSION.SDK_INT>=26)manager.createNotificationChannel(
      new NotificationChannel(CHANNEL,"Передача файлов",NotificationManager.IMPORTANCE_LOW));
    Intent stop=new Intent(this,LocalTransferService.class).setAction("fmplus.stop");
    PendingIntent cancel=PendingIntent.getService(this,42,stop,
      PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
    Notification n=new Notification.Builder(this,CHANNEL)
      .setContentTitle("Локальная передача включена")
      .setContentText("Доступна только в Wi-Fi. Остановить после передачи.")
      .setSmallIcon(android.R.drawable.stat_sys_upload)
      .setOngoing(true)
      .addAction(new Notification.Action.Builder(null,"Остановить",cancel).build()).build();
    if(Build.VERSION.SDK_INT>=29)startForeground(42,n,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
    else startForeground(42,n);
  }
  @Override public int onStartCommand(Intent intent,int flags,int startId){
    if(intent!=null && "fmplus.stop".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}
    try {LocalTransferHub.start(this);} catch(Exception e){stopSelf();}
    return START_NOT_STICKY;
  }
  @Override public void onDestroy(){LocalTransferHub.stop();super.onDestroy();}
  @Override public IBinder onBind(Intent intent){return null;}
}
