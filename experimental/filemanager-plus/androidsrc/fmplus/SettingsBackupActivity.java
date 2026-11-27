package fmplus;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import org.json.JSONArray;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/** User-selected, secret-free backup of the app's MAIN preferences (not folders/accounts). */
public final class SettingsBackupActivity extends Activity {
  private static final int EXPORT = 2101, IMPORT = 2102;
  private static final int LIMIT = 131072;
  private static final Set<String> ALLOW = new HashSet<>(Arrays.asList(
      "night_mode", "use_internal_image_viewer", "use_internal_video_player",
      "use_internal_music_player", "use_internal_text_editor", "use_recycle_bin",
      "recycle_bin_confirmation_2", "storage_full_threshold", "show_drawer_always",
      "detect_usb_attached", "show_system", "show_dual_apps", "file_size_unit",
      "music_player_engine", "list_date_format", "show_history", "app_backup_storage",
      "show_add_to_favorite", "show_add_to_home_screen", "show_hide_unhide", "show_open_as"));

  private SharedPreferences prefs() {
    return getSharedPreferences(getPackageName()+"_preferences",MODE_PRIVATE);
  }
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    LinearLayout root = new LinearLayout(this);
    root.setOrientation(LinearLayout.VERTICAL);
    root.setGravity(Gravity.CENTER_HORIZONTAL);
    int margin = dp(20);
    root.setPadding(margin,margin,margin,margin);
    TextView title = new TextView(this);
    title.setText("Резервная копия настроек");
    title.setTextSize(23f);
    root.addView(title,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
    TextView note = new TextView(this);
    note.setText("Сохраняются только общие параметры отображения и поведения. Пароли, аккаунты, сетевые соединения и настройки отдельных папок в копию не входят.");
    note.setTextSize(15f);
    LinearLayout.LayoutParams np = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);
    np.topMargin=dp(12);np.bottomMargin=dp(16);
    root.addView(note,np);
    Button export = new Button(this); export.setText("Сохранить настройки"); export.setMinHeight(dp(52));
    export.setOnClickListener(v -> chooseExport());
    root.addView(export,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
    Button restore = new Button(this); restore.setText("Восстановить настройки"); restore.setMinHeight(dp(52));
    restore.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("Восстановить настройки?")
       .setMessage("Сохранённые общие параметры заменят текущие. Файлы не затрагиваются.")
       .setNegativeButton("Отмена",null).setPositiveButton("Продолжить",(d,w)->chooseImport()).show());
    root.addView(restore,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
    setContentView(root);
  }
  private int dp(int d) {return (int)(d*getResources().getDisplayMetrics().density+0.5f);}
  private void chooseExport() {
    Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
        .setType("application/json");
    i.putExtra(Intent.EXTRA_TITLE,"filemanager-settings.json");
    startActivityForResult(i,EXPORT);
  }
  private void chooseImport() {
    Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
        .setType("application/json");
    startActivityForResult(i,IMPORT);
  }
  @Override protected void onActivityResult(int requestCode,int resultCode,Intent data) {
    super.onActivityResult(requestCode,resultCode,data);
    if(resultCode!=RESULT_OK || data==null || data.getData()==null)return;
    try {
      if(requestCode==EXPORT) exportTo(data.getData());
      if(requestCode==IMPORT) importFrom(data.getData());
    } catch (Exception e) {
      new AlertDialog.Builder(this).setTitle("Не удалось обработать копию")
        .setMessage(e.getMessage()==null?"Ошибка чтения файла":e.getMessage())
        .setPositiveButton("Понятно",null).show();
    }
  }
  private void exportTo(Uri uri) throws Exception {
    JSONObject root=new JSONObject();JSONObject values=new JSONObject();
    root.put("format","filemanager-basic-settings");root.put("schema",1);
    for(java.util.Map.Entry<String,?> entry:prefs().getAll().entrySet()) {
      if(!ALLOW.contains(entry.getKey()))continue;
      Object value=entry.getValue();
      if(value instanceof String || value instanceof Boolean || value instanceof Number) values.put(entry.getKey(),value);
      else if(value instanceof Set) values.put(entry.getKey(),new JSONArray((Set<?>)value));
    }
    root.put("values",values);
    byte[] content=root.toString(2).getBytes(StandardCharsets.UTF_8);
    if(content.length>LIMIT)throw new IllegalArgumentException("Слишком много настроек");
    try(OutputStream output=getContentResolver().openOutputStream(uri,"w")) {
      if(output==null)throw new IllegalStateException("Не удалось открыть выбранный файл");
      output.write(content);output.flush();
    }
    Toast.makeText(this,"Настройки сохранены",Toast.LENGTH_LONG).show();
  }
  private void importFrom(Uri uri) throws Exception {
    ByteArrayOutputStream buffer=new ByteArrayOutputStream();
    try(InputStream input=getContentResolver().openInputStream(uri)) {
      if(input==null)throw new IllegalStateException("Не удалось открыть копию");
      byte[] part=new byte[4096];int r;
      while((r=input.read(part))!=-1) {
        if(buffer.size()+r>LIMIT)throw new IllegalArgumentException("Файл слишком большой");
        buffer.write(part,0,r);
      }
    }
    JSONObject root=new JSONObject(new String(buffer.toByteArray(),StandardCharsets.UTF_8));
    if(!"filemanager-basic-settings".equals(root.optString("format"))||root.optInt("schema")!=1)
      throw new IllegalArgumentException("Неизвестный формат копии");
    JSONObject values=root.getJSONObject("values");
    SharedPreferences.Editor editor=prefs().edit();
    java.util.Iterator<String> names=values.keys();
    while(names.hasNext()) {
      String key=names.next();
      if(!ALLOW.contains(key))throw new IllegalArgumentException("Недопустимый параметр: "+key);
      Object value=values.get(key);
      if(value instanceof String) editor.putString(key,(String)value);
      else if(value instanceof Boolean) editor.putBoolean(key,(Boolean)value);
      else if(value instanceof Integer) editor.putInt(key,(Integer)value);
      else if(value instanceof Long) editor.putLong(key,(Long)value);
      else if(value instanceof Double) editor.putFloat(key,((Double)value).floatValue());
      else if(value instanceof JSONArray) {
        JSONArray ar=(JSONArray)value;Set<String> set=new HashSet<>();
        if(ar.length()>1000)throw new IllegalArgumentException("Неверный список настроек");
        for(int i=0;i<ar.length();i++)set.add(ar.getString(i));
        editor.putStringSet(key,set);
      } else throw new IllegalArgumentException("Неподдерживаемый тип настройки");
    }
    if(!editor.commit())throw new IllegalStateException("Не удалось сохранить настройки");
    new AlertDialog.Builder(this).setTitle("Настройки восстановлены")
       .setMessage("Изменения вступят в силу после повторного запуска приложения.")
       .setPositiveButton("Готово",(d,w)->finish()).show();
  }
}