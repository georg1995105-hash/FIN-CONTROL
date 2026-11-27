package fmplus;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import java.util.ArrayList;

/**
 * Independent Transfer screen: open QR to send from browser and select local
 * files to allow downloading. Uses Android SAF read grants, never arbitrary
 * filesystem exposure. Focusable controls support Android TV D-pad.
 */
public final class TransferScreenActivity extends Activity {
  private static final int PICK_FILES=8125;
  private TextView status,address,selected;
  private ImageView qr;
  private boolean closed;
  public static void open(Activity parent) {
    parent.startActivity(new Intent(parent,TransferScreenActivity.class));
  }
  private int dp(int value){return (int)(getResources().getDisplayMetrics().density*value+0.5f);}
  private Button button(LinearLayout column,String title,View.OnClickListener action){
    Button b=new Button(this);b.setText(title);b.setFocusable(true);b.setOnClickListener(action);
    column.addView(b,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(54)));
    return b;
  }
  private TextView label(LinearLayout column,String value,int size){
    TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setPadding(0,dp(9),0,dp(9));
    column.addView(t,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
    return t;
  }
  @Override public void onCreate(Bundle state){
    super.onCreate(state);setTitle("Передача");
    ScrollView scroll=new ScrollView(this);
    LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
    body.setPadding(dp(20),dp(16),dp(20),dp(20));scroll.addView(body);setContentView(scroll);
    label(body,"Передача",24);
    status=label(body,"Запуск локальной передачи…",16);
    qr=new ImageView(this);qr.setContentDescription("QR для подключения с другого устройства");
    qr.setAdjustViewBounds(true);
    body.addView(qr,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(224)));
    address=label(body,"",16);address.setTextIsSelectable(true);
    label(body,"Откройте QR в браузере телефона или компьютера в той же Wi-Fi сети. На странице можно отправить файлы сюда и скачать выбранные файлы.",14);
    selected=label(body,"Не выбрано файлов для скачивания",15);
    button(body,"Выбрать файлы для скачивания",v->pick());
    button(body,"Очистить выбранные файлы",v->{LocalTransferHub.clearShared();selected.setText("Файлы скрыты");});
    button(body,"Открыть полученные файлы",v->{
      Intent intent=new Intent(Intent.ACTION_VIEW);
      intent.setType("*/*");intent.setAction(Intent.ACTION_GET_CONTENT);
      intent.addCategory(Intent.CATEGORY_OPENABLE);
      try{startActivityForResult(intent,PICK_FILES+1);}catch(Exception e){status.setText("Используйте раздел «Загрузки/Передача»");}
    });
    button(body,"Остановить передачу",v->{
      stopService(new Intent(this,LocalTransferService.class));
      status.setText("Передача остановлена");qr.setImageDrawable(null);address.setText("");
    });
    button(body,"Назад",v->finish());
    startAndShow();
  }
  private void startAndShow(){
    try{
      Intent launch=new Intent(this,LocalTransferService.class);
      if(Build.VERSION.SDK_INT>=26)startForegroundService(launch);else startService(launch);
    }catch(Exception e){status.setText("Не удалось запустить передачу: "+e.getMessage());return;}
    new Thread(()->{
      for(int i=0;i<60&&!closed;i++){
        String uri=LocalTransferHub.currentUrl();
        if(uri!=null){
          runOnUiThread(()->{
            if(closed)return;
            status.setText("Готово. Передача работает в локальной сети.");
            address.setText(uri);QrLocalTransfer.render(qr,uri);
          });return;
        }
        try{Thread.sleep(100);}catch(InterruptedException e){Thread.currentThread().interrupt();return;}
      }
      runOnUiThread(()->{if(!closed)status.setText("Не удалось получить адрес. Проверьте Wi-Fi.");});
    },"fmplus-transfer-address").start();
  }
  private void pick(){
    Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);
    intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("*/*");
    intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
    try{startActivityForResult(intent,PICK_FILES);}
    catch(Exception e){status.setText("Выбор файлов недоступен: "+e.getMessage());}
  }
  @Override protected void onActivityResult(int request,int result,Intent data){
    super.onActivityResult(request,result,data);
    if(request!=PICK_FILES||result!=RESULT_OK||data==null)return;
    ArrayList<Uri> list=new ArrayList<>();
    if(data.getData()!=null)list.add(data.getData());
    ClipData clip=data.getClipData();
    if(clip!=null)for(int i=0;i<clip.getItemCount()&&list.size()<100;i++){
      Uri uri=clip.getItemAt(i).getUri();if(uri!=null&&!list.contains(uri))list.add(uri);
    }
    try{
      int count=LocalTransferHub.share(this,list);
      selected.setText("Доступно для скачивания: "+count);
      status.setText("Выбранные файлы видны на странице QR");
    }catch(Exception e){status.setText("Не удалось выбрать файлы: "+e.getMessage());}
  }
  @Override protected void onDestroy(){closed=true;super.onDestroy();}
}
