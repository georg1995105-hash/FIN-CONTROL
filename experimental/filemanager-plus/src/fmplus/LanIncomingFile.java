package fmplus;

import java.io.*;
import java.security.*;
import java.util.*;

/** API 21 compatible, bounded, resumable local receiver with no java.nio.file dependency. */
public final class LanIncomingFile implements AutoCloseable {
  public static final int MAX_CHUNK=4*1024*1024;
  private final File temporary,root;
  private final String relative,expectedSha;
  private final long total;
  private long offset;
  private boolean closed;
  public LanIncomingFile(File folder,String filename,long size,String sha,long limit)throws IOException{
    validatePath(filename);
    if(size<0||limit<0||size>limit)throw new IOException("Size exceeds available space");
    if(sha==null)sha="";
    if(!sha.isEmpty()&&!sha.matches("[a-fA-F0-9]{64}"))throw new IOException("Invalid file digest");
    total=size;relative=filename;expectedSha=sha.toLowerCase(Locale.ROOT);
    if(!folder.isDirectory()&&!folder.mkdirs())throw new IOException("Cannot create receive folder");
    root=folder.getCanonicalFile();
    File staging=new File(root,".staging");
    if(!staging.isDirectory()&&!staging.mkdirs())throw new IOException("Cannot create staging");
    temporary=File.createTempFile("incoming-",".part",staging.getCanonicalFile());
  }
  public synchronized long offset(){return offset;}
  public synchronized long append(long position,int bytes,String sha,InputStream input)throws IOException{
    ensureOpen();
    if(position!=offset||bytes<1||bytes>MAX_CHUNK||bytes>total-offset)throw new IOException("Invalid offset or length");
    if(sha!=null&&!sha.isEmpty()&&!sha.matches("[a-fA-F0-9]{64}"))throw new IOException("Bad chunk digest");
    MessageDigest checksum=digest();
    try(RandomAccessFile out=new RandomAccessFile(temporary,"rw")){
      out.setLength(offset);out.seek(offset);
      byte[] buffer=new byte[128*1024];int left=bytes;
      try{
        while(left>0){
          if(Thread.currentThread().isInterrupted())throw new InterruptedIOException();
          int count=input.read(buffer,0,Math.min(buffer.length,left));
          if(count<0)throw new EOFException("Incomplete chunk");
          if(count==0)continue;
          out.write(buffer,0,count);checksum.update(buffer,0,count);left-=count;
        }
        if(sha!=null&&!sha.isEmpty()&&!equal(sha.toLowerCase(Locale.ROOT),hex(checksum.digest())))
          throw new IOException("Chunk digest mismatch");
      }catch(IOException|RuntimeException e){out.setLength(offset);throw e;}
    }
    offset+=bytes;return offset;
  }
  public synchronized File finish()throws IOException{
    ensureOpen();
    if(offset!=total||temporary.length()!=total)throw new IOException("Incomplete file");
    try(RandomAccessFile f=new RandomAccessFile(temporary,"rw")){f.getFD().sync();}
    if(!expectedSha.isEmpty()){
      MessageDigest md=digest();
      try(InputStream in=new BufferedInputStream(new FileInputStream(temporary))){
        byte[] buffer=new byte[128*1024];int n;
        while((n=in.read(buffer))!=-1)md.update(buffer,0,n);
      }
      if(!equal(expectedSha,hex(md.digest())))throw new IOException("File digest mismatch");
    }
    File target=new File(root,relative).getCanonicalFile();
    if(!target.getPath().startsWith(root.getPath()+File.separator))throw new IOException("Unsafe destination");
    File parent=target.getParentFile();
    if(!parent.isDirectory()&&!parent.mkdirs())throw new IOException("Cannot create directory");
    synchronized(LanIncomingFile.class){
      if(target.exists())target=unique(target);
      if(target.exists())throw new IOException("Name conflict");
      if(!temporary.renameTo(target))throw new IOException("Cannot commit completed file");
    }
    closed=true;return target;
  }
  private static File unique(File file)throws IOException{
    String name=file.getName();int i=name.lastIndexOf('.');
    String base=i<=0?name:name.substring(0,i),ext=i<=0?"":name.substring(i);
    for(int n=1;n<10000;n++){File candidate=new File(file.getParentFile(),base+" ("+n+")"+ext);if(!candidate.exists())return candidate;}
    throw new IOException("Too many duplicate names");
  }
  private static MessageDigest digest(){try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException e){throw new AssertionError(e);}}
  private static String hex(byte[] data){
    char[] table="0123456789abcdef".toCharArray(),out=new char[data.length*2];
    for(int i=0;i<data.length;i++){int b=data[i]&255;out[i*2]=table[b>>>4];out[i*2+1]=table[b&15];}
    return new String(out);
  }
  private static boolean equal(String a,String b){return MessageDigest.isEqual(a.getBytes(java.nio.charset.StandardCharsets.US_ASCII),b.getBytes(java.nio.charset.StandardCharsets.US_ASCII));}
  private void ensureOpen()throws IOException{if(closed)throw new IOException("Closed");}
  @Override public synchronized void close()throws IOException{closed=true;if(temporary.exists()&&!temporary.delete())throw new IOException("Cannot delete partial");}
  public static void validatePath(String path)throws IOException{
    if(path==null||path.isEmpty()||path.length()>2000||path.startsWith("/")||path.indexOf('\\')>=0)throw new IOException("Invalid path");
    String[] parts=path.split("/",-1);
    if(parts.length>16)throw new IOException("Too deep");
    for(String p:parts){
      if(p.isEmpty()||p.equals(".")||p.equals("..")||p.endsWith(".")||p.endsWith(" ")||
          p.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>180)throw new IOException("Invalid name");
      String stem=p.split("[.]",2)[0].toUpperCase(Locale.ROOT);
      if(stem.matches("CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]"))throw new IOException("Reserved name");
      for(int i=0;i<p.length();i++){
        char c=p.charAt(i);
        if(Character.isISOControl(c)||"/\\:*?\"<>|".indexOf(c)>=0)throw new IOException("Invalid name");
      }
    }
  }
}
