package fmplus;
import java.io.*;
import java.security.*;
import java.util.*;
public class FeatureCoreTest {
  static int passes=0;
  static void check(boolean b,String message){if(!b)throw new AssertionError(message);passes++;}
  static void fails(Class<? extends Exception> cl, Runnable a) {
    try {a.run();}catch(Exception e){check(cl.isInstance(e),"expected "+cl+" got "+e);return;}
    throw new AssertionError("Expected failure");
  }
  public static void main(String[] args) throws Exception {
    FeatureCore.FolderView fallback=new FeatureCore.FolderView(FeatureCore.View.LIST,FeatureCore.Sort.NAME,false,FeatureCore.Thumbnails.OFF);
    FeatureCore.FolderSettings settings=new FeatureCore.FolderSettings();
    settings.put("/sdcard/Download/",FeatureCore.FolderView.downloadsDefault());
    settings.put("/sdcard/Pictures",fallback);
    check(settings.get("/sdcard/Download",fallback).sort==FeatureCore.Sort.DATE,"Download sort");
    check(settings.get("/sdcard/Pictures",null).view==FeatureCore.View.LIST,"Independent folder settings");
    check(settings.get("/sdcard/Music",fallback)==fallback,"Fallback unchanged");
    check(settings.size()==2,"Two independent folder settings");
    check(FeatureCore.normalizePath("smb://nas/share/").equals("smb://nas/share"),"SMB path retained");
    check(FeatureCore.normalizePath("content://auth/a/").equals("content://auth/a"),"SAF path retained");
    byte[] backup=FeatureCore.exportSettings(settings.snapshot());
    Map<String,FeatureCore.FolderView> imported=FeatureCore.importSettings(backup);
    check(imported.size()==2,"Roundtrip folder count");
    check(imported.get("/sdcard/Download").descending,"Roundtrip descending");
    check(imported.get("/sdcard/Download").thumbnails==FeatureCore.Thumbnails.ON,"Roundtrip thumb preference");
    check(backup.length<2048,"Compact backup");
    byte[] broken=backup.clone();broken[broken.length/2]^=127;
    try{FeatureCore.importSettings(broken);throw new AssertionError("Accepted damaged backup");}
    catch(IOException expected){passes++;}
    try{FeatureCore.importSettings(new byte[2_000_001]);throw new AssertionError("Accepted oversize backup");}
    catch(IOException expected){passes++;}
    check(FeatureCore.nextFocus(0,3,new boolean[]{true,false,true,true,true,true},1,0)==2,"Skip disabled focus");
    check(FeatureCore.nextFocus(4,3,new boolean[]{true,false,true,true,true,true},0,-1)==-1,"Out of row focus");
    check(FeatureCore.nextFocus(3,3,new boolean[]{true,false,true,true,true,true},0,-1)==0,"Focus up");
    System.out.println("PASS "+passes+" checks");
  }
}