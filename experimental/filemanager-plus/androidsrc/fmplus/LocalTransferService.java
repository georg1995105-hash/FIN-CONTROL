package fmplus;

import android.app.*;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/** Foreground session lifecycle; close listener and revoke all sessions on Stop. */
public final class LocalTransferService extends Service {
  private static final String CHANNEL="fmplus-local-transfer";
  private final Object lifecycleLock=new Object();
  private boolean destroyed;

  @Override public void onCreate() {
    super.onCreate();
    NotificationManager manager=(NotificationManager)getSystemService(Context.NOTIFICATION_SERVICE);
    if(Build.VERSION.SDK_INT>=26)manager.createNotificationChannel(
      new NotificationChannel(CHANNEL,"Передача файлов",NotificationManager.IMPORTANCE_LOW));
    Intent stop=new Intent(this,LocalTransferService.class).setAction("fmplus.stop");
    int flags=PendingIntent.FLAG_UPDATE_CURRENT;
    if(Build.VERSION.SDK_INT>=23)flags|=PendingIntent.FLAG_IMMUTABLE;
    PendingIntent cancel=PendingIntent.getService(this,42,stop,flags);
    Notification.Builder builder=Build.VERSION.SDK_INT>=26
      ?new Notification.Builder(this,CHANNEL):new Notification.Builder(this);
    Notification notification=builder.setContentTitle("Локальная передача включена")
      .setContentText("Доступна в локальной сети. Остановить после передачи.")
      .setSmallIcon(android.R.drawable.stat_sys_upload)
      .setOngoing(true)
      .addAction(new Notification.Action.Builder(null,"Остановить",cancel).build()).build();
    if(Build.VERSION.SDK_INT>=29)startForeground(42,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
    else startForeground(42,notification);
  }
  @Override public int onStartCommand(Intent intent,int flags,int startId) {
    if(intent!=null && "fmplus.stop".equals(intent.getAction())){stopSelf();return START_NOT_STICKY;}
    new Thread(()->{
      synchronized(lifecycleLock) {
        if(destroyed)return;
        try {LocalTransferHub.start(this);}
        catch(Exception error){if(!destroyed)stopSelf();}
      }
    },"fmplus-server-start").start();
    return START_NOT_STICKY;
  }
  @Override public void onDestroy(){
    synchronized(lifecycleLock){
      destroyed=true;
      LocalTransferHub.stop();
    }
    super.onDestroy();
  }
  @Override public IBinder onBind(Intent intent){return null;}
}
