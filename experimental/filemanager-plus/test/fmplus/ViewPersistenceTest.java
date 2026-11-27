package fmplus;

import java.io.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;

/** Schema migration + per-folder display independence, including icons and size. */
public final class ViewPersistenceTest {
  private static int checked;
  private static void ok(boolean b,String why){if(!b)throw new AssertionError(why);checked++;}
  private static void reject(Runnable x){
    try{x.run();throw new AssertionError("Invalid setting accepted");}
    catch(IllegalArgumentException expected){checked++;}
  }
  private static byte[] v1Archive() throws Exception {
    Properties props=new Properties();
    props.setProperty("schema","1");props.setProperty("count","1");
    props.setProperty("folder.0.path","/storage/emulated/0/Download");
    props.setProperty("folder.0.view","DETAILED");
    props.setProperty("folder.0.sort","DATE");
    props.setProperty("folder.0.desc","true");
    props.setProperty("folder.0.thumbs","ON");
    ByteArrayOutputStream text=new ByteArrayOutputStream();props.store(text,"v1 fixture");
    byte[] bytes=text.toByteArray();
    byte[] sum=MessageDigest.getInstance("SHA-256").digest(bytes);
    StringBuilder hex=new StringBuilder();for(byte b:sum)hex.append(String.format(Locale.ROOT,"%02x",b&255));
    ByteArrayOutputStream output=new ByteArrayOutputStream();
    try(ZipOutputStream zip=new ZipOutputStream(output)){
      zip.putNextEntry(new ZipEntry("folder-display.properties"));zip.write(bytes);zip.closeEntry();
      zip.putNextEntry(new ZipEntry("sha256.txt"));zip.write(hex.toString().getBytes("US-ASCII"));zip.closeEntry();
    }
    return output.toByteArray();
  }
  public static void main(String[] args) throws Exception {
    FeatureCore.FolderView first=FeatureCore.FolderView.initialDefault();
    ok(first.view==FeatureCore.View.DETAILED,"Detailed list first use");
    ok(first.sort==FeatureCore.Sort.NAME,"Default sort");
    ok(first.showIcons && first.iconSizeDp==48,"Default icons");
    FeatureCore.FolderSettings settings=new FeatureCore.FolderSettings();
    FeatureCore.FolderView a=new FeatureCore.FolderView(
      FeatureCore.View.GRID,FeatureCore.Sort.SIZE,true,FeatureCore.Thumbnails.OFF,96,false);
    settings.put("/storage/emulated/0/DCIM",a);
    settings.put("/storage/emulated/0/Download",first);
    ok(settings.get("/storage/emulated/0/DCIM",first)==a,"Folder independent");
    ok(settings.get("/storage/emulated/0/Music",first)==first,"Unconfigured default unchanged");
    byte[] exported=FeatureCore.exportSettings(settings.snapshot());
    Map<String,FeatureCore.FolderView> recovered=FeatureCore.importSettings(exported);
    FeatureCore.FolderView restored=recovered.get("/storage/emulated/0/DCIM");
    ok(restored.view==FeatureCore.View.GRID && restored.sort==FeatureCore.Sort.SIZE,"View/sort restored");
    ok(restored.iconSizeDp==96 && !restored.showIcons,"Icon visibility/size restored");
    ok(restored.thumbnails==FeatureCore.Thumbnails.OFF && restored.descending,"Thumbnail/sort order restored");
    ok(recovered.get("/storage/emulated/0/Download").iconSizeDp==48,"No global overwrite");
    Map<String,FeatureCore.FolderView> legacy=FeatureCore.importSettings(v1Archive());
    FeatureCore.FolderView migrated=legacy.get("/storage/emulated/0/Download");
    ok(migrated.iconSizeDp==48 && migrated.showIcons,"Schema1 defaults restored");
    ok(migrated.sort==FeatureCore.Sort.DATE && migrated.descending,"Legacy sort preserved");
    reject(()->new FeatureCore.FolderView(FeatureCore.View.LIST,FeatureCore.Sort.NAME,false,FeatureCore.Thumbnails.ON,10,true));
    reject(()->new FeatureCore.FolderView(FeatureCore.View.LIST,FeatureCore.Sort.NAME,false,FeatureCore.Thumbnails.ON,161,true));
    System.out.println("PASS "+checked+" per-folder view / schema migration checks");
  }
}
