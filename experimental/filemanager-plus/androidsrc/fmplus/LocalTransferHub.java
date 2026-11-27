package fmplus;

import android.content.Context;
import android.os.Build;
import android.os.Environment;
import android.media.MediaScannerConnection;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import javax.net.ServerSocketFactory;

/**
 * LAN browser transfer service: independent of the legacy FTP server.
 *
 * Source protocol: "Передача" TransferManager + LocalHttpsServer + IncomingTransfer.
 * Real browser uploads only; no remote filesystem listing, no unapproved file access.
 * Every upload is authenticated, path-limited, staged, and cancellable.
 *
 * This component is not a full replacement: native TLS/NSD and selected-file download
 * still need Android integration and separate end-to-end testing before stable release.
 */
public final class LocalTransferHub {
  private static LocalTransferHub active;
  private final Context app;
  private final SecureRandom rng = new SecureRandom();
  private final LanPairing.Sessions sessions = new LanPairing.Sessions(rng);
  private final Map<String,String> batches = new ConcurrentHashMap<>();
  private final Map<String,Upload> uploads = new ConcurrentHashMap<>();
  private LocalHttpsServer listener;
  private Thread listenerThread;
  private String url;

  private static final class Upload {
    final String token, name, batch;
    final IncomingTransfer receiver;
    Upload(String token, String name, String batch, IncomingTransfer receiver) {
      this.token=token; this.name=name; this.batch=batch; this.receiver=receiver;
    }
  }
  private LocalTransferHub(Context c){ app=c.getApplicationContext(); }
  private static long now(){ return android.os.SystemClock.elapsedRealtime(); }
  private String id(){
    byte[] b=new byte[32];rng.nextBytes(b);char[] chars=new char[64];
    final char[] alphabet="0123456789abcdef".toCharArray();
    for(int i=0;i<32;i++){int v=b[i]&255;chars[i*2]=alphabet[v>>>4];chars[i*2+1]=alphabet[v&15];b[i]=0;}
    return new String(chars);
  }
  private static String localIpv4() throws IOException {
    Enumeration<NetworkInterface> all=NetworkInterface.getNetworkInterfaces();
    if(all==null)throw new IOException("No network interfaces");
    String fallback=null;
    while(all.hasMoreElements()){
      NetworkInterface net=all.nextElement();
      if(!net.isUp()||net.isLoopback())continue;
      Enumeration<InetAddress> addresses=net.getInetAddresses();
      while(addresses.hasMoreElements()){
        InetAddress addr=addresses.nextElement();
        if(!(addr instanceof Inet4Address)||!addr.isSiteLocalAddress())continue;
        String ip=addr.getHostAddress();
        try {LanPairing.checkIp(ip);} catch(IllegalArgumentException error){continue;}
        if(net.getName().startsWith("wlan")||net.getName().startsWith("eth"))return ip;
        if(fallback==null)fallback=ip;
      }
    }
    if(fallback==null)throw new IOException("No private IPv4 Wi-Fi connection");
    return fallback;
  }
  public static synchronized String start(Context c) throws IOException {
    if(active!=null && active.listener!=null)return active.url;
    LocalTransferHub hub=new LocalTransferHub(c);
    // Bind before publishing QR, and close if no reachable LAN address exists.
    LocalHttpsServer server=new LocalHttpsServer(ServerSocketFactory.getDefault(),hub::handle);
    String address;
    try{ address=LanPairing.browserUrl(localIpv4(),server.port()); }
    catch(Exception e){server.close();throw new IOException("No usable LAN address",e);}
    hub.listener=server;hub.url=address;
    active=hub;
    hub.listenerThread=new Thread(server::run,"fmplus-lan-http");
    hub.listenerThread.setDaemon(true);
    hub.listenerThread.start();
    return address;
  }
  public static synchronized String currentUrl(){return active==null?null:active.url;}
  public static synchronized void stop(){
    if(active==null)return;
    LocalTransferHub hub=active;active=null;
    hub.listener.close();hub.sessions.stop();hub.batches.clear();
    for(Upload u:hub.uploads.values())try{u.receiver.close();}catch(IOException ignored){}
    hub.uploads.clear();
  }

  private static void reply(OutputStream out,int code,JSONObject j)throws IOException {
    LocalHttpsServer.reply(out,code,"application/json; charset=utf-8",
      j.toString().getBytes(StandardCharsets.UTF_8));
  }
  private static void fail(OutputStream out,int code,String reason)throws IOException{
    reply(out,code,new JSONObject().put("error",reason));
  }
  private static JSONObject body(LocalHttpsServer.Request r)throws IOException {
    if(r.length>16384)throw new IOException("Request too large");
    ByteArrayOutputStream data=new ByteArrayOutputStream();
    byte[] buf=new byte[8192];int n;
    while((n=r.body.read(buf))!=-1) {
      if(data.size()+n>16384)throw new IOException("Too much request data");
      data.write(buf,0,n);
    }
    try{return new JSONObject(new String(data.toByteArray(),StandardCharsets.UTF_8));}
    catch(Exception error){throw new IOException("Invalid JSON",error);}
  }
  private File receiverDir() throws IOException {
    File target;
    if(Build.VERSION.SDK_INT>=30 && !Environment.isExternalStorageManager()) {
      // Do not write to arbitrary shared storage without permission.
      target=new File(app.getFilesDir(),"received");
    } else {
      target=new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),"Передача");
    }
    if(!target.isDirectory()&&!target.mkdirs())throw new IOException("Cannot create receive directory");
    return target;
  }
  private void handle(LocalHttpsServer.Request r,OutputStream out) throws Exception {
    try {
      if(r.method.equals("GET") && (r.path.equals("/")||r.path.equals("/appjs")||r.path.equals("/style"))){
        String name=r.path.equals("/")?"index.html":r.path.equals("/appjs")?"app.js":"style.css";
        String type=name.endsWith(".html")?"text/html; charset=utf-8":name.endsWith(".js")?"text/javascript":"text/css";
        byte[] content;
        try(InputStream f=app.getAssets().open("fmplus-transfer/"+name)){content=readLimit(f,1024*1024);}
        LocalHttpsServer.reply(out,200,type,content);return;
      }
      if(r.path.equals("/pair")&&r.method.equals("POST")){
        JSONObject request=body(r);
        request.optString("name").substring(0,Math.min(60,request.optString("name").length()));
        String id=sessions.begin(now());
        reply(out,200,new JSONObject().put("id",id));return;
      }
      if(r.path.startsWith("/pair/")&&r.method.equals("GET")){
        String request=r.path.substring("/pair/".length());
        reply(out,200,new JSONObject().put("token",sessions.claim(request,now())));return;
      }
      String h=r.headers.get("authorization");
      String token=(h!=null && h.startsWith("Bearer "))?h.substring(7):"";
      if(!sessions.authorized(token,now())){fail(out,401,"Подключение истекло");return;}
      if(r.path.equals("/files")&&r.method.equals("GET")){
        // No arbitrary filesystem exposure; publication of selected files requires a separate integration.
        reply(out,200,new JSONObject().put("files",new JSONArray()));return;
      }
      if(r.path.equals("/batch")&&r.method.equals("POST")){
        if(batches.size()>=100){fail(out,429,"Лимит отправок");return;}
        String id=id();batches.put(id,token);
        reply(out,200,new JSONObject().put("id",id));return;
      }
      if(r.path.equals("/offer")&&r.method.equals("POST")){
        if(uploads.size()>=8){fail(out,429,"Лимит активных файлов");return;}
        JSONObject j=body(r);
        String name=j.getString("name"),batch=j.getString("batch");
        IncomingTransfer.validatePath(name);
        if(!token.equals(batches.get(batch))){fail(out,403,"Неверная передача");return;}
        long size=j.getLong("size");
        File target=receiverDir(),staging=new File(target,".staging");
        long space=target.getUsableSpace()-64L*1024*1024;
        if(size<0 || size>space){fail(out,413,"Недостаточно места");return;}
        IncomingTransfer incoming=new IncomingTransfer(staging.toPath(),target.toPath(),name,size,
          j.optString("sha256"),space,true).renameOnConflict();
        String id=id();uploads.put(id,new Upload(token,name,batch,incoming));
        reply(out,200,new JSONObject().put("id",id));return;
      }
      if(r.path.startsWith("/upload/")){
        String id=r.path.substring("/upload/".length());
        Upload job=uploads.get(id);
        if(job==null){fail(out,404,"Отправка не найдена");return;}
        if(!job.token.equals(token)){fail(out,403,"Запрос отклонён");return;}
        if(r.method.equals("GET")){
          reply(out,200,new JSONObject().put("accepted",true)
            .put("offset",job.receiver.offset()).put("done",false));return;
        }
        if(r.method.equals("DELETE")){
          if(uploads.remove(id,job))job.receiver.close();
          reply(out,200,new JSONObject());return;
        }
        if(r.method.equals("PUT")){
          long offset=Long.parseLong(r.headers.getOrDefault("x-offset","-1"));
          long done=job.receiver.append(offset,(int)r.length,r.headers.get("x-sha256"),r.body);
          reply(out,200,new JSONObject().put("offset",done));return;
        }
        if(r.method.equals("POST")){
          Path saved=job.receiver.finish();
          uploads.remove(id,job);
          MediaScannerConnection.scanFile(app,new String[]{saved.toString()},null,null);
          reply(out,200,new JSONObject().put("done",true));return;
        }
      }
      fail(out,404,"Не найдено");
    } catch (SecurityException e){fail(out,403,e.getMessage());}
      catch (IllegalArgumentException e){fail(out,400,e.getMessage());}
      catch (Exception e){fail(out,400,e.getMessage()==null?"Ошибка передачи":e.getMessage());}
  }
  private static byte[] readLimit(InputStream f,int max)throws IOException {
    ByteArrayOutputStream out=new ByteArrayOutputStream();
    byte[] b=new byte[8192];int n;
    while((n=f.read(b))!=-1) {if(out.size()+n>max)throw new IOException("Asset too large");out.write(b,0,n);}
    return out.toByteArray();
  }
}
