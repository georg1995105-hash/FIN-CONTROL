package fmplus;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.media.ThumbnailUtils;
import android.net.Uri;
import android.os.Build;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.util.Size;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Android-facing components. Integration with File Manager+ menus/FTP service is still required. */
public final class AndroidFeatures {
  private AndroidFeatures() { }
  public static final class ApkDetails {
    public final String packageId, version, title;
    public final long code,bytes;
    public final List<String> permissions;
    public final Drawable icon;
    ApkDetails(String packageId,String version,String title,long code,long bytes,List<String> permissions,Drawable icon){
      this.packageId=packageId;this.version=version;this.title=title;
      this.code=code;this.bytes=bytes;this.permissions=permissions;this.icon=icon;
    }
  }
  /** Reads metadata from an APK WITHOUT installing or executing it. */
  public static ApkDetails inspectApk(Context context,File file) throws IOException {
    if(!file.isFile()||file.length()==0)throw new IOException("APK missing");
    PackageManager pm=context.getPackageManager();
    PackageInfo info=pm.getPackageArchiveInfo(file.getAbsolutePath(),PackageManager.GET_PERMISSIONS);
    if(info==null||info.packageName==null)throw new IOException("APK metadata unreadable");
    ApplicationInfo app=info.applicationInfo;
    String title=info.packageName; Drawable icon=null;
    if(app!=null){
      app.sourceDir=file.getAbsolutePath();app.publicSourceDir=file.getAbsolutePath();
      try{CharSequence name=app.loadLabel(pm);if(name!=null&&!name.toString().trim().isEmpty())title=name.toString();}catch(RuntimeException ignored){}
      try{icon=app.loadIcon(pm);}catch(RuntimeException ignored){}
    }
    String version=info.versionName==null?"—":info.versionName;
    List<String> perms=info.requestedPermissions==null?Collections.emptyList():Arrays.asList(info.requestedPermissions.clone());
    return new ApkDetails(info.packageName,version,title,(Build.VERSION.SDK_INT>=28 ? info.getLongVersionCode() : (long)info.versionCode),file.length(),perms,icon);
  }
  public static void showApkDetails(Activity a,File apk) {
    try {
      ApkDetails info=inspectApk(a,apk);
      String message="Пакет: "+info.packageId+"\nВерсия: "+info.version+" ("+info.code+")\nРазмер: "+
          String.format(Locale.ROOT,"%.1f МБ",info.bytes/1048576d)+"\nРазрешений: "+info.permissions.size();
      new AlertDialog.Builder(a).setTitle(info.title).setMessage(message).setPositiveButton("Готово",null).show();
    } catch(IOException e){new AlertDialog.Builder(a).setTitle("APK").setMessage("Не удалось прочитать сведения: "+e.getMessage()).setPositiveButton("OK",null).show();}
  }

  /** Memory-bounded, cancelable thumbnail loading; request keys include file modification metadata. */
  public static final class ThumbnailLoader {
    public interface Callback { void onLoaded(Bitmap bitmap); }
    private final ExecutorService io=Executors.newFixedThreadPool(2);
    private final Handler main=new Handler(Looper.getMainLooper());
    private final LruCache<String,Bitmap> cache=new LruCache<String,Bitmap>(24*1024*1024) {
      @Override protected int sizeOf(String key,Bitmap value){return value.getByteCount();}
    };
    public Future<?> load(File file,boolean isVideo,int px,Callback callback) {
      if(file==null||!file.isFile()||px<32||px>512)return null;
      final String key=file.getAbsolutePath()+":"+file.length()+":"+file.lastModified()+":"+px+":"+isVideo;
      Bitmap cached=cache.get(key);
      if(cached!=null&&!cached.isRecycled()){main.post(()->callback.onLoaded(cached));return null;}
      return io.submit(()->{
        Bitmap result=null;
        try {
          if(Build.VERSION.SDK_INT>=29){
            if(isVideo)result=ThumbnailUtils.createVideoThumbnail(file,new Size(px,px),new CancellationSignal());
            else result=ThumbnailUtils.createImageThumbnail(file,new Size(px,px),new CancellationSignal());
          } else {
            if(isVideo)result=ThumbnailUtils.createVideoThumbnail(file.getAbsolutePath(),android.provider.MediaStore.Video.Thumbnails.MINI_KIND);
            else result=ThumbnailUtils.createImageThumbnail(file.getAbsolutePath(),android.provider.MediaStore.Images.Thumbnails.MINI_KIND);
          }
        } catch(Exception|OutOfMemoryError ignored){}
        if(result!=null){Bitmap bitmap=result;cache.put(key,bitmap);main.post(()->callback.onLoaded(bitmap));}
      });
    }
    public void clear(){cache.evictAll();}
    public void shutdown(){io.shutdownNow();cache.evictAll();}
  }

  /** Home-section visibility (no new home layout; caller applies state to original tiles). */
  public static final class HomeVisibility {
    private final SharedPreferences preferences;
    private final Set<String> allSections;
    public HomeVisibility(Context context,Set<String> validSectionIds) {
      if(validSectionIds==null||validSectionIds.isEmpty())throw new IllegalArgumentException("No sections");
      preferences=context.getSharedPreferences("fmplus_home_visibility",Context.MODE_PRIVATE);
      allSections=Collections.unmodifiableSet(new java.util.HashSet<>(validSectionIds));
    }
    public boolean visible(String id){validate(id);return preferences.getBoolean("show."+id,true);}
    public boolean setVisible(String id,boolean visible){
      validate(id);
      if(!visible){int count=0;for(String item:allSections)if(!item.equals(id)&&visible(item))count++;
        if(count==0)return false;
      }
      return preferences.edit().putBoolean("show."+id,visible).commit();
    }
    private void validate(String id){if(!allSections.contains(id))throw new IllegalArgumentException("Unknown section");}
  }

  /** Key-only restore/export via the Android Storage Access Framework. No secrets included. */
  public static final class SettingsIo {
    public static void exportTo(Context context,Uri selected,FeatureCore.FolderSettings settings) throws IOException {
      byte[] content=FeatureCore.exportSettings(settings.snapshot());
      try(OutputStream stream=context.getContentResolver().openOutputStream(selected,"w")){
        if(stream==null)throw new IOException("Cannot open destination");stream.write(content);stream.flush();
      }
    }
    public static void restoreFrom(Context context,Uri selected,FeatureCore.FolderSettings settings) throws IOException {
      byte[] bytes;
      try(InputStream input=context.getContentResolver().openInputStream(selected)){
        if(input==null)throw new IOException("Cannot open backup");
        java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();byte[] part=new byte[4096];int read;
        while((read=input.read(part))!=-1){if(out.size()+read>2_000_000)throw new IOException("Backup too large");out.write(part,0,read);}
        bytes=out.toByteArray();
      }
      settings.restore(FeatureCore.importSettings(bytes));
    }
    public static Intent documentCreateIntent(){
      Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/zip");
      i.putExtra(Intent.EXTRA_TITLE,"filemanager-settings.zip");return i;
    }
    public static Intent documentOpenIntent(){
      return new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/zip");
    }
  }

  /** QR is shown only when the server already knows the short-lived credential and enforces expiry. */
  public interface PairingProvider {
    FeatureCore.PairedSession createAndActivate() throws Exception;
    void revoke(FeatureCore.PairedSession session);
  }
  public static void showPairing(Activity activity,PairingProvider provider) throws Exception {
    FeatureCore.PairedSession session=provider.createAndActivate();
    if(session==null||session.expired(System.currentTimeMillis()))throw new IOException("FTPS session is invalid");
    QrMatrix qr=QrMatrix.encode(session.url);
    int module=7,border=4,edge=(QrMatrix.SIZE+border*2)*module;
    Bitmap bitmap=Bitmap.createBitmap(edge,edge,Bitmap.Config.ARGB_8888);
    bitmap.eraseColor(Color.WHITE);
    for(int y=0;y<QrMatrix.SIZE;y++)for(int x=0;x<QrMatrix.SIZE;x++)if(qr.get(x,y))for(int yy=0;yy<module;yy++)
      for(int xx=0;xx<module;xx++)bitmap.setPixel((x+border)*module+xx,(y+border)*module+yy,Color.BLACK);
    ImageView image=new ImageView(activity);image.setImageBitmap(bitmap);image.setContentDescription("QR для доступа к файлам через FTPS");
    new AlertDialog.Builder(activity).setTitle("Доступ по QR").setView(image)
      .setMessage("Только в одной локальной сети. Доступ временный и защищённый.")
      .setPositiveButton("Готово",(d,w)->provider.revoke(session))
      .setOnCancelListener(d->provider.revoke(session)).show();
  }
}