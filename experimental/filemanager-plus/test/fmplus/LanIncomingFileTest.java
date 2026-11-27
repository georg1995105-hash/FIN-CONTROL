package fmplus;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

public final class LanIncomingFileTest {
  private static int checked;
  private interface Action{void run()throws Exception;}
  private static void ok(boolean b){if(!b)throw new AssertionError();checked++;}
  private static void rejects(Action f)throws Exception{try{f.run();throw new AssertionError("Accepted invalid input");}catch(IOException expected){checked++;}}
  private static String hash(byte[] data)throws Exception{
    byte[] b=MessageDigest.getInstance("SHA-256").digest(data);
    StringBuilder s=new StringBuilder();for(byte v:b)s.append(String.format(Locale.ROOT,"%02x",v&255));return s.toString();
  }
  public static void main(String[] args)throws Exception{
    File folder=Files.createTempDirectory("lan-incoming-test").toFile();
    try{
      byte[] payload=new byte[65000];new Random(53).nextBytes(payload);
      for(String bad:new String[]{"../escape","a/../x","/a","a\\b","bad\nname","a/","CON","a|b"})
        rejects(()->LanIncomingFile.validatePath(bad));
      LanIncomingFile f=new LanIncomingFile(folder,"sub/video.bin",payload.length,hash(payload),payload.length);
      rejects(()->f.append(1,payload.length,hash(payload),new ByteArrayInputStream(payload)));
      rejects(()->f.append(0,payload.length,hash(payload),new ByteArrayInputStream(new byte[5])));
      ok(f.offset()==0);
      rejects(()->f.append(0,payload.length,hash(new byte[0]),new ByteArrayInputStream(payload)));
      ok(f.offset()==0);
      byte[] one=Arrays.copyOfRange(payload,0,20000),two=Arrays.copyOfRange(payload,20000,payload.length);
      f.append(0,one.length,hash(one),new ByteArrayInputStream(one));
      rejects(f::finish);
      f.append(one.length,two.length,hash(two),new ByteArrayInputStream(two));
      File result=f.finish();ok(Arrays.equals(Files.readAllBytes(result.toPath()),payload));
      rejects(f::finish);
      LanIncomingFile duplicate=new LanIncomingFile(folder,"sub/video.bin",0,hash(new byte[0]),0);
      File extra=duplicate.finish();ok(extra.getName().equals("video (1).bin"));ok(result.exists());
      LanIncomingFile tampered=new LanIncomingFile(folder,"tampered",payload.length,hash(new byte[0]),payload.length);
      tampered.append(0,payload.length,hash(payload),new ByteArrayInputStream(payload));rejects(tampered::finish);tampered.close();
      LanIncomingFile cancelled=new LanIncomingFile(folder,"cancelled",0,"",0);cancelled.close();rejects(cancelled::finish);
      System.out.println("PASS "+checked+" API21-compatible receiver checks");
    }finally{
      try(java.util.stream.Stream<Path> all=Files.walk(folder.toPath())){
        all.sorted(Comparator.reverseOrder()).forEach(p->p.toFile().delete());
      }
    }
  }
}
