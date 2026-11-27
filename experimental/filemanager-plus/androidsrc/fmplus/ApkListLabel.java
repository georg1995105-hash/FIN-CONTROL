package fmplus;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.TextView;
import android.widget.ImageView;
import android.view.View;
import android.view.ViewParent;
import android.widget.GridView;
import android.text.TextUtils;
import java.io.File;
import java.util.Locale;
import java.util.WeakHashMap;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * Non-blocking APK title/version labels for the existing file list.
 * Leaves the original filename untouched for unreadable/remote APKs.
 * All view/cache access is on the main thread; work queue is bounded.
 */
public final class ApkListLabel {
  private ApkListLabel() {}
  private static final Handler MAIN = new Handler(Looper.getMainLooper());
  private static final ThreadPoolExecutor IO = new ThreadPoolExecutor(
      1, 1, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<Runnable>(64),
      new ThreadPoolExecutor.DiscardPolicy());
  private static final WeakHashMap<TextView, String> BOUND = new WeakHashMap<>();
  private static final LruCache<String, String> CACHE = new LruCache<>(128);

  private static boolean isGridItem(View view) {
    ViewParent p = view.getParent();
    while (p instanceof View) {
      if (p instanceof GridView) return true;
      p = p.getParent();
    }
    return false;
  }

  public static void bind(Context context, String filename, String path, TextView view, ImageView icon) {
    if (view == null) return;
    BOUND.remove(view);
    // Keep very long APK filenames from expanding rows and causing scroll jumps.
    view.setMaxLines(2);
    view.setEllipsize(TextUtils.TruncateAt.END);
    // Hide only the icon, never its parent: the parent may be the entire file row.
    // Recycled grid rows must always restore icon visibility.
    if (icon != null) {
      boolean visible = context.getSharedPreferences(
          context.getPackageName() + "_preferences", Context.MODE_PRIVATE)
          .getBoolean("fmplus_show_icons", true);
      icon.setVisibility(isGridItem(view) || visible ? View.VISIBLE : View.GONE);
    }
    if (filename == null || !filename.toLowerCase(Locale.ROOT).endsWith(".apk")
        || path == null || !path.startsWith("/")) return;
    File file = new File(path);
    if (!file.isFile() || file.length() == 0) return;
    final String key = file.getAbsolutePath() + ":" + file.length() + ":" + file.lastModified();
    BOUND.put(view, key);
    String cached = CACHE.get(key);
    if (cached != null) {
      if (!cached.isEmpty()) view.setText(cached + "\n" + filename);
      return;
    }
    final Context app = context.getApplicationContext();
    IO.execute(() -> {
      String label = "";
      try {
        PackageManager pm = app.getPackageManager();
        PackageInfo info = pm.getPackageArchiveInfo(file.getAbsolutePath(), 0);
        if (info != null && info.applicationInfo != null) {
          ApplicationInfo ai = info.applicationInfo;
          ai.sourceDir = file.getAbsolutePath();
          ai.publicSourceDir = file.getAbsolutePath();
          String name = String.valueOf(ai.loadLabel(pm)).trim();
          String version = info.versionName == null ? "" : info.versionName.trim();
          if (!name.isEmpty() && !name.equalsIgnoreCase("null")) {
            label = name + (version.isEmpty() ? "" : " · " + version);
          }
        }
      } catch (RuntimeException | LinkageError ignored) {
        // Preserve the original filename, never crash the file list.
      }
      final String result = label;
      MAIN.post(() -> {
        CACHE.put(key, result);
        if (key.equals(BOUND.get(view)) && !result.isEmpty()) {
          view.setText(result + "\n" + filename);
        }
      });
    });
  }
}
