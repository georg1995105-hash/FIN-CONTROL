package fmplus;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;

/** QR Code Version 5, ECC-L, byte mode. No Android dependency. */
public final class QrMatrix {
  public static final int SIZE=37;
  public static final int MAX_BYTES=106;
  private static final int DATA_CODEWORDS=108, ECC_CODEWORDS=26;
  private final boolean[][] modules=new boolean[SIZE][SIZE];
  private final boolean[][] function=new boolean[SIZE][SIZE];
  private QrMatrix() { }
  public boolean get(int x,int y){return modules[y][x];}

  public static QrMatrix encode(String value){
    if(value==null)throw new IllegalArgumentException("Null QR text");
    byte[] data=value.getBytes(StandardCharsets.UTF_8);
    if(data.length>MAX_BYTES)throw new IllegalArgumentException("Text too long for QR V5-L");
    // Mode 0100, length (8 bits), UTF-8 bytes, terminator and byte padding.
    ArrayList<Integer> bits=new ArrayList<>(DATA_CODEWORDS*8);
    append(bits,0x4,4);append(bits,data.length,8);
    for(byte b:data)append(bits,b&255,8);
    for(int i=0;i<4 && bits.size()<DATA_CODEWORDS*8;i++)bits.add(0);
    while((bits.size()&7)!=0)bits.add(0);
    boolean flip=true;
    while(bits.size()<DATA_CODEWORDS*8){append(bits,flip?0xEC:0x11,8);flip=!flip;}
    byte[] words=new byte[DATA_CODEWORDS+ECC_CODEWORDS];
    for(int i=0;i<DATA_CODEWORDS;i++)for(int j=0;j<8;j++)if(bits.get(i*8+j)!=0)words[i]|=1<<(7-j);
    byte[] ecc=rsEcc(Arrays.copyOf(words,DATA_CODEWORDS));
    System.arraycopy(ecc,0,words,DATA_CODEWORDS,ecc.length);
    QrMatrix qr=new QrMatrix();qr.drawFunctions();qr.drawData(words);qr.mask0();qr.drawFormat(0);
    return qr;
  }
  private static void append(ArrayList<Integer> list,int val,int len){for(int i=len-1;i>=0;i--)list.add((val>>>i)&1);}
  private void setFunction(int x,int y,boolean black){if(x<0||y<0||x>=SIZE||y>=SIZE)return;modules[y][x]=black;function[y][x]=true;}
  private void drawFinder(int cx,int cy){
    for(int dy=-4;dy<=4;dy++)for(int dx=-4;dx<=4;dx++){
      int d=Math.max(Math.abs(dx),Math.abs(dy));setFunction(cx+dx,cy+dy,d!=2&&d!=4);
    }
  }
  private void drawFunctions(){
    for(int i=0;i<SIZE;i++){
      setFunction(6,i,(i&1)==0);
      setFunction(i,6,(i&1)==0);
    }
    drawFinder(3,3);drawFinder(SIZE-4,3);drawFinder(3,SIZE-4);
    for(int dy=-2;dy<=2;dy++)for(int dx=-2;dx<=2;dx++)
      setFunction(30+dx,30+dy,Math.max(Math.abs(dx),Math.abs(dy))!=1);
    drawFormat(0);
  }
  private void drawData(byte[] data){
    int idx=0;
    for(int right=SIZE-1;right>=1;right-=2){
      if(right==6)right=5;
      for(int vert=0;vert<SIZE;vert++){
        int y=(((right+1)&2)==0)?SIZE-1-vert:vert;
        for(int j=0;j<2;j++){
          int x=right-j;
          if(!function[y][x]){
            boolean black=idx<data.length*8&&((data[idx>>>3]>>>(7-(idx&7)))&1)!=0;
            modules[y][x]=black;idx++;
          }
        }
      }
    }
    if(idx<data.length*8)throw new IllegalStateException("QR data placement failed");
  }
  private void mask0(){
    for(int y=0;y<SIZE;y++)for(int x=0;x<SIZE;x++)
      if(!function[y][x]&&((x+y)&1)==0)modules[y][x]=!modules[y][x];
  }
  private void drawFormat(int mask){
    // EC level L = 1, format polynomial 0x537, xor mask 0x5412.
    int bits=(1<<3)|mask,rem=bits;
    for(int i=0;i<10;i++)rem=(rem<<1)^(((rem>>>9)&1)*0x537);
    int fmt=((bits<<10)|rem)^0x5412;
    for(int i=0;i<=5;i++)setFunction(8,i,((fmt>>>i)&1)!=0);
    setFunction(8,7,((fmt>>>6)&1)!=0);setFunction(8,8,((fmt>>>7)&1)!=0);
    setFunction(7,8,((fmt>>>8)&1)!=0);
    for(int i=9;i<15;i++)setFunction(14-i,8,((fmt>>>i)&1)!=0);
    for(int i=0;i<8;i++)setFunction(SIZE-1-i,8,((fmt>>>i)&1)!=0);
    for(int i=8;i<15;i++)setFunction(8,SIZE-15+i,((fmt>>>i)&1)!=0);
    setFunction(8,SIZE-8,true);
  }
  private static byte[] rsEcc(byte[] data){
    int[] divisor=new int[]{1};int root=1;
    for(int i=0;i<ECC_CODEWORDS;i++){
      int[] next=new int[divisor.length+1];
      for(int j=0;j<divisor.length;j++){
        next[j]^=divisor[j];next[j+1]^=gfMul(divisor[j],root);
      }
      divisor=next;root=gfMul(root,2);
    }
    int[] remainder=new int[ECC_CODEWORDS];
    for(byte item:data){
      int factor=(item&255)^remainder[0];
      System.arraycopy(remainder,1,remainder,0,ECC_CODEWORDS-1);remainder[ECC_CODEWORDS-1]=0;
      for(int i=0;i<ECC_CODEWORDS;i++)remainder[i]^=gfMul(divisor[i+1],factor);
    }
    byte[] result=new byte[ECC_CODEWORDS];for(int i=0;i<ECC_CODEWORDS;i++)result[i]=(byte)remainder[i];
    return result;
  }
  private static int gfMul(int x,int y){
    int z=0;for(int i=7;i>=0;i--){z=(z<<1)^(((z>>>7)&1)*0x11d);z^=((y>>>i)&1)*x;}
    return z;
  }
  /** Portable PGM to validate scannability without Android bitmap dependencies. */
  public byte[] toPgm(int scale){
    if(scale<1||scale>40)throw new IllegalArgumentException("Invalid scale");
    int border=4,edge=(SIZE+border*2)*scale;
    String header="P5\n"+edge+" "+edge+"\n255\n";
    byte[] h=header.getBytes(StandardCharsets.US_ASCII);
    byte[] bytes=new byte[h.length+edge*edge];System.arraycopy(h,0,bytes,0,h.length);
    Arrays.fill(bytes,h.length,bytes.length,(byte)255);
    for(int y=0;y<SIZE;y++)for(int x=0;x<SIZE;x++)if(get(x,y))for(int yy=0;yy<scale;yy++)
      Arrays.fill(bytes,h.length+((y+border)*scale+yy)*edge+(x+border)*scale,
      h.length+((y+border)*scale+yy)*edge+(x+border+1)*scale,(byte)0);
    return bytes;
  }
}