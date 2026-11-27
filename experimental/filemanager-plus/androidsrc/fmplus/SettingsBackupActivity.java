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
  private static final int LIMIT = 2000000;
  private static final String[] FOLDER_FIELDS = {"view_type", "icon_size", "sort_type", "show_hidden", "show_thumbnails", "hide_grid_filename"};
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
    note.setText("Сохраняются общие настройки, вид, значки и сортировка отдельных папок. Пароли, аккаунты и сетевые соединения не сохраняются.");
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
    // Keep controls readable on tablets and Android TV instead of spanning the entire screen.
    android.widget.FrameLayout host = new android.widget.FrameLayout(this);
    android.widget.FrameLayout.LayoutParams panel = new android.widget.FrameLayout.LayoutParams(
        Math.min(getResources().getDisplayMetrics().widthPixels, dp(560)),
        ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP | Gravity.CENTER_HORIZONTAL);
    host.addView(root, panel);
    android.widget.ScrollView scroll = new android.widget.ScrollView(this);
    scroll.setFillViewport(true);
    scroll.addView(host);
    setContentView(scroll);
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
  private static String category(String key, boolean folder) {
    if (key == null || key.length() > 2048) return null;
    if (!folder) {
      if (!ALLOW.contains(key)) return null;
      if (Arrays.asList("night_mode", "storage_full_threshold", "file_size_unit", "music_player_engine", "list_date_format", "app_backup_storage").contains(key)) return "string";
      return "boolean";
    }
    for (String field:FOLDER_FIELDS) {
      if (key.equals(field) || key.startsWith(field+":")) {
        if (key.indexOf('\n')>=0 || key.indexOf('\r')>=0 || key.indexOf((char)0)>=0) return null;
        return field.equals("view_type") || field.equals("icon_size") ? "int" :
          field.equals("sort_type") ? "string" : "boolean";
      }
    }
    return null;
  }
  private static JSONObject exportEntries(SharedPreferences prefs,boolean folder) throws Exception {
    JSONObject out=new JSONObject();
    for(java.util.Map.Entry<String,?> entry:prefs.getAll().entrySet()) {
      String kind=category(entry.getKey(),folder);Object value=entry.getValue();
      if (kind==null) continue;
      if (kind.equals("string") && value instanceof String ||
          kind.equals("boolean") && value instanceof Boolean ||
          kind.equals("int") && value instanceof Integer) out.put(entry.getKey(),value);
    }
    return out;
  }
  private static void validateValues(JSONObject values,boolean folder) throws Exception {
    if (values.length()>10000) throw new IllegalArgumentException("Слишком много параметров");
    java.util.Iterator<String> names=values.keys();
    while(names.hasNext()) {
      String key=names.next();String kind=category(key,folder);
      if(kind==null)throw new IllegalArgumentException("Недопустимый ключ настроек");
      Object value=values.get(key);
      if (!(kind.equals("string") && value instanceof String ||
            kind.equals("boolean") && value instanceof Boolean ||
            kind.equals("int") && value instanceof Integer))
        throw new IllegalArgumentException("Неверный тип параметра: "+key);
    }
  }
  private static void applyValues(SharedPreferences target,JSONObject values) throws Exception {
    SharedPreferences.Editor editor=target.edit();
    java.util.Iterator<String> names=values.keys();
    while(names.hasNext()) {
      String key=names.next();Object value=values.get(key);
      if (value instanceof String) editor.putString(key,(String)value);
      else if(value instanceof Boolean)editor.putBoolean(key,(Boolean)value);
      else if(value instanceof Integer)editor.putInt(key,(Integer)value);
    }
    if(!editor.commit())throw new IllegalStateException("Не удалось записать настройки");
  }
  private java.util.List<java.io.File> folderPreferenceFiles() {
    java.util.List<java.io.File> files=new java.util.ArrayList<>();
    java.io.File dir=new java.io.File(getApplicationInfo().dataDir,"shared_prefs");
    java.io.File[] found=dir.listFiles();if(found==null)return files;
    for(java.io.File file:found){
      String name=file.getName();
      if(name.matches("settings_[A-Za-z0-9_.-]{1,120}\\.xml") && file.isFile())files.add(file);
    }
    if(files.size()>2000) throw new IllegalArgumentException("Слишком много настроек папок");
    return files;
  }
  private void exportTo(Uri uri) throws Exception {
    JSONObject root=new JSONObject();
    root.put("format","filemanager-basic-settings");root.put("schema",2);
    root.put("values",exportEntries(prefs(),false));
    JSONArray folders=new JSONArray();
    for (java.io.File file:folderPreferenceFiles()){
      String filename=file.getName();String name=filename.substring(0,filename.length()-4);
      JSONObject values=exportEntries(getSharedPreferences(name,MODE_PRIVATE),true);
      if(values.length()>0){JSONObject obj=new JSONObject();obj.put("name",name);obj.put("values",values);folders.put(obj);}
    }
    root.put("folders",folders);
    byte[] content=root.toString(2).getBytes(StandardCharsets.UTF_8);
    if(content.length>LIMIT)throw new IllegalArgumentException("Копия слишком большая");
    try(OutputStream output=getContentResolver().openOutputStream(uri,"w")){
      if(output==null)throw new IllegalStateException("Не удалось открыть выбранный файл");
      output.write(content);output.flush();
    }
    Toast.makeText(this,"Настройки сохранены",Toast.LENGTH_LONG).show();
  }
  private void importFrom(Uri uri) throws Exception {
    ByteArrayOutputStream buffer=new ByteArrayOutputStream();
    try(InputStream input=getContentResolver().openInputStream(uri)){
      if(input==null)throw new IllegalStateException("Не удалось открыть копию");
      byte[] part=new byte[4096];int r;
      while((r=input.read(part))!=-1){
        if(buffer.size()+r>LIMIT)throw new IllegalArgumentException("Файл слишком большой");
        buffer.write(part,0,r);
      }
    }
    JSONObject root=new JSONObject(new String(buffer.toByteArray(),StandardCharsets.UTF_8));
    if(!"filemanager-basic-settings".equals(root.optString("format")))throw new IllegalArgumentException("Неизвестный формат копии");
    int schema=root.optInt("schema");
    if(schema!=1&&schema!=2)throw new IllegalArgumentException("Неподдерживаемая версия копии");
    JSONObject values=root.getJSONObject("values");validateValues(values,false);
    JSONArray folders=schema==2?root.getJSONArray("folders"):new JSONArray();
    if(folders.length()>2000)throw new IllegalArgumentException("Слишком много папок");
    java.util.Set<String> used=new java.util.HashSet<>();
    for(int i=0;i<folders.length();i++){
      JSONObject group=folders.getJSONObject(i);
      String name=group.getString("name");
      if(!name.matches("settings_[A-Za-z0-9_.-]{1,120}")||!used.add(name))
        throw new IllegalArgumentException("Неверное имя настроек папки");
      validateValues(group.getJSONObject("values"),true);
    }
    // All incoming JSON is validated BEFORE any preference file is changed.
    for(int i=0;i<folders.length();i++){
      JSONObject group=folders.getJSONObject(i);
      applyValues(getSharedPreferences(group.getString("name"),MODE_PRIVATE),group.getJSONObject("values"));
    }
    applyValues(prefs(),values);
    new AlertDialog.Builder(this).setTitle("Настройки восстановлены")
        .setMessage("Для применения всех изменений перезапустите приложение.")
        .setPositiveButton("Готово",(d,w)->finish()).show();
  }

}